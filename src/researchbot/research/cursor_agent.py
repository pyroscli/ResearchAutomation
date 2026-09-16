from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from researchbot.config import Settings, repo_root
from researchbot.research.playbook import build_research_prompt
from researchbot.research.schema import ResearchReport
from researchbot.research.validator import (
    ReportValidationError,
    extract_json_object,
    parse_report,
)

logger = logging.getLogger(__name__)

RESULT_ARTIFACT_NAMES = (
    "artifacts/research-result.json",
    "research-result.json",
)


class CursorAgentError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        agent_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.agent_id = agent_id
        self.run_id = run_id


class CursorResearchRuntime:
    """Launches Cursor Cloud Agents. No LLM provider is called by this process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Any = None

    async def start(self) -> None:
        from cursor_sdk import AsyncClient

        os.environ.setdefault("CURSOR_API_KEY", self._settings.cursor_api_key)
        self._client = await AsyncClient.launch_bridge(workspace=repo_root())

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        aclose = getattr(client, "aclose", None)
        if aclose is not None:
            await aclose()
            return
        close = getattr(client, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    async def run_research(self, query: str) -> tuple[str, str | None, ResearchReport]:
        """Return (agent_id, run_id, report)."""
        if self._client is None:
            raise CursorAgentError("Cursor client is not started")

        from cursor_sdk import (
            AgentOptions,
            CloudAgentOptions,
            CloudRepository,
            CursorAgentError as SdkAgentError,
        )

        cloud_kwargs: dict[str, Any] = {"auto_create_pr": False}
        if self._settings.playbook_repo_url:
            cloud_kwargs["repos"] = [
                CloudRepository(
                    url=self._settings.playbook_repo_url,
                    starting_ref=self._settings.playbook_repo_ref,
                )
            ]
        else:
            cloud_kwargs["repos"] = []

        prompt = build_research_prompt(self._settings, query)
        logger.info("Launching Cloud Agent for query (%s chars, prompt %s chars)", len(query), len(prompt))

        try:
            agent = await self._client.agents.create(
                AgentOptions(
                    model=self._settings.cursor_model,
                    api_key=self._settings.cursor_api_key,
                    name=f"Research: {query[:80]}",
                    cloud=CloudAgentOptions(**cloud_kwargs),
                )
            )
        except SdkAgentError as exc:
            logger.exception("Cloud Agent create failed: %s", exc)
            raise CursorAgentError(
                "Could not start the research agent",
                retryable=bool(getattr(exc, "is_retryable", False)),
            ) from exc
        except Exception as exc:
            logger.exception("Cloud Agent create failed")
            raise CursorAgentError("Could not start the research agent") from exc

        agent_id = getattr(agent, "agent_id", None) or ""
        run_id: str | None = None
        logger.info("Cloud Agent created id=%s", agent_id)
        try:
            run = await agent.send(prompt)
            run_id = getattr(run, "id", None)
            logger.info("Cloud Agent run started id=%s status=%s", run_id, getattr(run, "status", None))
            result = await run.wait()
            run_id = getattr(result, "id", None) or run_id
            status = getattr(result, "status", None)
            detail = (getattr(result, "result", None) or "").strip()
            # The SDK stream sometimes emits an empty error the instant a
            # cloud VM starts. The run is still alive — poll until it settles.
            if status != "finished" and not detail:
                logger.warning(
                    "Ignoring empty %s from stream; polling cloud run %s",
                    status,
                    run_id,
                )
                result = await self._poll_cloud_run(agent_id, run_id)
                run_id = getattr(result, "id", None) or run_id
                status = getattr(result, "status", None)
                detail = (getattr(result, "result", None) or "").strip()
            if status != "finished":
                logger.error(
                    "Cloud Agent run failed agent=%s run=%s status=%s detail=%s",
                    agent_id,
                    run_id,
                    status,
                    detail[:500],
                )
                raise CursorAgentError(
                    f"Research agent run ended with status {status or 'unknown'}",
                    agent_id=agent_id,
                    run_id=run_id,
                )
            report = await self._load_report(agent, run, result)
            logger.info("Cloud Agent report ready with %s sources", len(report.sources))
            return agent_id, run_id, report
        except CursorAgentError:
            raise
        except SdkAgentError as exc:
            logger.exception("Cloud Agent run failed: %s", exc)
            raise CursorAgentError(
                "Research agent failed",
                retryable=bool(getattr(exc, "is_retryable", False)),
                agent_id=agent_id,
                run_id=run_id,
            ) from exc
        except ReportValidationError as exc:
            logger.exception("Invalid Cloud Agent report")
            raise CursorAgentError(
                "Research agent returned an invalid report",
                agent_id=agent_id,
                run_id=run_id,
            ) from exc
        finally:
            close = getattr(agent, "close", None)
            if close is not None:
                maybe = close()
                if hasattr(maybe, "__await__"):
                    await maybe

    async def _poll_cloud_run(self, agent_id: str, run_id: str | None) -> Any:
        if not run_id or self._client is None:
            raise CursorAgentError(
                "Research agent run ended with status error",
                agent_id=agent_id,
                run_id=run_id,
            )
        deadline = asyncio.get_running_loop().time() + self._settings.research_timeout_seconds
        last: Any = None
        while asyncio.get_running_loop().time() < deadline:
            handle = await self._client.get_run(
                run_id,
                {
                    "apiKey": self._settings.cursor_api_key,
                    "runtime": "cloud",
                    "agentId": agent_id,
                },
            )
            last = handle
            status = getattr(handle, "status", None)
            if status == "finished" or (
                status in {"error", "cancelled", "expired"}
                and (getattr(handle, "result", None) or getattr(handle, "duration_ms", 0))
            ):
                waited = getattr(handle, "wait", None)
                if waited is not None:
                    return await _maybe_await(waited())
                return handle
            logger.info("Cloud run %s still %s; waiting", run_id, status)
            await asyncio.sleep(4)
        return last

    async def _load_report(self, agent: Any, run: Any, result: Any) -> ResearchReport:
        payload = await self._download_artifact_json(agent)
        if payload is None:
            text = await self._final_text(run, result)
            if not text:
                raise ReportValidationError("Agent finished without a JSON report")
            payload = extract_json_object(text)
        return parse_report(payload)

    async def _download_artifact_json(self, agent: Any) -> dict | None:
        list_artifacts = getattr(agent, "list_artifacts", None)
        download = getattr(agent, "download_artifact", None)
        if list_artifacts is None or download is None:
            return None
        try:
            artifacts = await _maybe_await(list_artifacts())
        except Exception:
            logger.exception("Failed to list Cloud Agent artifacts")
            return None
        paths = [getattr(item, "path", "") for item in artifacts or []]
        chosen = next((path for path in paths if path in RESULT_ARTIFACT_NAMES), None)
        if chosen is None:
            chosen = next((path for path in paths if path.endswith("research-result.json")), None)
        if chosen is None:
            logger.info("No research-result artifact; paths=%s", paths)
            return None
        try:
            raw = await _maybe_await(download(chosen))
        except Exception:
            logger.exception("Failed to download artifact %s", chosen)
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return extract_json_object(raw)
        except ReportValidationError:
            logger.exception("Artifact %s was not valid JSON", chosen)
            return None

    async def _final_text(self, run: Any, result: Any) -> str:
        for candidate in (
            getattr(result, "result", None),
            getattr(result, "text", None),
            getattr(run, "result", None),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        text_fn = getattr(run, "text", None)
        if text_fn is not None:
            try:
                value = await _maybe_await(text_fn())
                if isinstance(value, str):
                    return value
            except Exception:
                logger.exception("Failed to read run text")
        return ""


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value
