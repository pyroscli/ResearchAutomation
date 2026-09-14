from __future__ import annotations

import asyncio
import logging
import uuid

from researchbot.config import Settings
from researchbot.db import repo
from researchbot.db.models import TaskStatus
from researchbot.db.session import session_scope
from researchbot.research.cursor_agent import CursorAgentError, CursorResearchRuntime
from researchbot.research.schema import ResearchReport

logger = logging.getLogger(__name__)


class ResearchBusyError(RuntimeError):
    pass


class QueryRejectedError(ValueError):
    pass


class ResearchService:
    def __init__(self, settings: Settings, runtime: CursorResearchRuntime) -> None:
        self._settings = settings
        self._runtime = runtime
        self._global_slots = asyncio.Semaphore(settings.max_concurrent_global)

    async def start_research(
        self, telegram_user_id: int, query: str
    ) -> tuple[uuid.UUID, asyncio.Task[ResearchReport]]:
        cleaned = query.strip()
        if not cleaned:
            raise QueryRejectedError("Send a research topic or question.")
        if len(cleaned) > self._settings.max_query_length:
            raise QueryRejectedError(
                f"Keep the query under {self._settings.max_query_length} characters."
            )

        async with session_scope() as session:
            user = await repo.get_or_create_user(session, telegram_user_id)
            if await repo.user_has_in_flight_task(session, user.id):
                raise ResearchBusyError(
                    "A research task is already running. Wait for it to finish."
                )
            if await repo.count_global_in_flight(session) >= self._settings.max_concurrent_global:
                raise ResearchBusyError(
                    "The research queue is full. Try again in a few minutes."
                )
            research_session = await repo.get_or_create_session(session, user.id)
            task = await repo.create_task(session, research_session.id, cleaned)
            task_id = task.id
            session_id = research_session.id

        job = asyncio.create_task(
            self._execute(session_id, task_id, cleaned),
            name=f"research-{task_id}",
        )
        return task_id, job

    async def _execute(
        self, session_id: uuid.UUID, task_id: uuid.UUID, query: str
    ) -> ResearchReport:
        async with self._global_slots:
            await self._set_status(task_id, TaskStatus.SEARCHING)
            ticker = asyncio.create_task(self._progress_ticker(task_id))
            try:
                agent_id, run_id, report = await asyncio.wait_for(
                    self._runtime.run_research(query),
                    timeout=self._settings.research_timeout_seconds,
                )
            except TimeoutError as exc:
                logger.exception("Research timed out for task %s", task_id)
                await self._fail(task_id, "Research timed out")
                raise CursorAgentError("Research timed out") from exc
            except CursorAgentError as exc:
                logger.exception("Research agent error for task %s: %s", task_id, exc)
                if exc.agent_id:
                    async with session_scope() as session:
                        await repo.attach_agent(session, session_id, exc.agent_id)
                await self._fail(task_id, str(exc), cursor_run_id=exc.run_id)
                raise
            except Exception:
                logger.exception("Unexpected research failure for task %s", task_id)
                await self._fail(task_id, "Research agent failed")
                raise CursorAgentError("Research agent failed")
            finally:
                ticker.cancel()

        await self._set_status(task_id, TaskStatus.SUMMARIZING, cursor_run_id=run_id)
        async with session_scope() as session:
            if agent_id:
                await repo.attach_agent(session, session_id, agent_id)
            await repo.save_report(session, task_id, report)
            await repo.mark_session_last_task(session, session_id, task_id)
        return report

    async def _progress_ticker(self, task_id: uuid.UUID) -> None:
        try:
            await asyncio.sleep(45)
            await self._set_status(task_id, TaskStatus.ANALYZING)
        except asyncio.CancelledError:
            return

    async def _set_status(
        self,
        task_id: uuid.UUID,
        status: TaskStatus,
        *,
        cursor_run_id: str | None = None,
    ) -> None:
        async with session_scope() as session:
            await repo.set_task_status(
                session, task_id, status, cursor_run_id=cursor_run_id
            )

    async def _fail(
        self,
        task_id: uuid.UUID,
        error: str,
        *,
        cursor_run_id: str | None = None,
    ) -> None:
        async with session_scope() as session:
            await repo.set_task_status(
                session,
                task_id,
                TaskStatus.FAILED,
                error=error,
                cursor_run_id=cursor_run_id,
            )
