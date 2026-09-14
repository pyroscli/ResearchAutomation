from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from researchbot.db.models import (
    Reliability,
    ResearchResult,
    ResearchSession,
    ResearchTask,
    SessionStatus,
    Source,
    SourceType,
    TaskStatus,
    User,
)
from researchbot.research.schema import ResearchReport, SourceItem


IN_FLIGHT = (
    TaskStatus.QUEUED,
    TaskStatus.SEARCHING,
    TaskStatus.ANALYZING,
    TaskStatus.SUMMARIZING,
)


async def get_or_create_user(session: AsyncSession, telegram_user_id: int) -> User:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_user_id=telegram_user_id)
        session.add(user)
        await session.flush()
    return user


async def get_active_session(
    session: AsyncSession, user_id: uuid.UUID
) -> ResearchSession | None:
    result = await session.execute(
        select(ResearchSession)
        .where(
            ResearchSession.user_id == user_id,
            ResearchSession.status == SessionStatus.ACTIVE,
        )
        .order_by(ResearchSession.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_session(
    session: AsyncSession, user_id: uuid.UUID
) -> ResearchSession:
    existing = await get_active_session(session, user_id)
    if existing is not None:
        return existing
    research_session = ResearchSession(user_id=user_id)
    session.add(research_session)
    await session.flush()
    return research_session


async def user_has_in_flight_task(session: AsyncSession, user_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(ResearchTask.id)
        .join(ResearchSession, ResearchTask.session_id == ResearchSession.id)
        .where(
            ResearchSession.user_id == user_id,
            ResearchTask.status.in_(IN_FLIGHT),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def count_global_in_flight(session: AsyncSession) -> int:
    result = await session.execute(
        select(ResearchTask.id).where(ResearchTask.status.in_(IN_FLIGHT))
    )
    return len(result.scalars().all())


async def create_task(
    session: AsyncSession, session_id: uuid.UUID, query: str
) -> ResearchTask:
    task = ResearchTask(
        session_id=session_id,
        query=query,
        status=TaskStatus.QUEUED,
        started_at=datetime.now(UTC),
    )
    session.add(task)
    await session.flush()
    return task


async def set_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: TaskStatus,
    *,
    error: str | None = None,
    cursor_run_id: str | None = None,
    report_summary: str | None = None,
    raw_report: dict | None = None,
) -> None:
    task = await session.get(ResearchTask, task_id)
    if task is None:
        return
    task.status = status
    if error is not None:
        task.error = error
    if cursor_run_id is not None:
        task.cursor_run_id = cursor_run_id
    if report_summary is not None:
        task.report_summary = report_summary
    if raw_report is not None:
        task.raw_report = raw_report
    if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        task.completed_at = datetime.now(UTC)
    await session.flush()


async def attach_agent(
    session: AsyncSession, session_id: uuid.UUID, agent_id: str
) -> None:
    research_session = await session.get(ResearchSession, session_id)
    if research_session is None:
        return
    research_session.cursor_agent_id = agent_id
    await session.flush()


async def mark_session_last_task(
    session: AsyncSession, session_id: uuid.UUID, task_id: uuid.UUID
) -> None:
    research_session = await session.get(ResearchSession, session_id)
    if research_session is None:
        return
    research_session.last_task_id = task_id
    await session.flush()


def canonical_key_for(item: SourceItem) -> str:
    if item.canonical_id:
        return f"{item.type.value}:{item.canonical_id.strip().lower()}"
    if item.doi:
        return f"doi:{item.doi.strip().lower()}"
    if item.arxiv_id:
        return f"arxiv:{item.arxiv_id.strip().lower()}"
    return f"url:{item.url.strip().lower().rstrip('/')}"


async def upsert_source(session: AsyncSession, item: SourceItem) -> Source:
    key = canonical_key_for(item)
    result = await session.execute(select(Source).where(Source.canonical_key == key))
    source = result.scalar_one_or_none()
    metadata = {
        "authors": item.authors,
        "published_date": item.published_date,
        "doi": item.doi,
        "arxiv_id": item.arxiv_id,
        "channel": item.channel,
        "duration": item.duration,
        "author": item.author,
        "website": item.website,
    }
    if source is None:
        source = Source(
            type=SourceType(item.type.value),
            canonical_key=key,
            url=item.url,
            title=item.title,
            source_name=item.source_name,
            reliability=Reliability(item.reliability.value),
            raw_metadata=metadata,
        )
        session.add(source)
        await session.flush()
        return source
    source.url = item.url
    source.title = item.title
    source.source_name = item.source_name
    source.reliability = Reliability(item.reliability.value)
    source.raw_metadata = metadata
    await session.flush()
    return source


async def save_report(
    session: AsyncSession, task_id: uuid.UUID, report: ResearchReport
) -> None:
    for rank, item in enumerate(report.sources, start=1):
        source = await upsert_source(session, item)
        session.add(
            ResearchResult(
                task_id=task_id,
                source_id=source.id,
                relevance_score=item.relevance_score,
                verified=item.verified,
                unavailable_reason=item.unavailable_reason,
                summary_json=item.summary.model_dump(),
                rank=rank,
            )
        )
    await set_task_status(
        session,
        task_id,
        TaskStatus.COMPLETED,
        report_summary=report.summary,
        raw_report=report.model_dump(),
    )


async def list_recent_tasks(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 15
) -> list[ResearchTask]:
    result = await session.execute(
        select(ResearchTask)
        .join(ResearchSession, ResearchTask.session_id == ResearchSession.id)
        .where(ResearchSession.user_id == user_id)
        .order_by(ResearchTask.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
