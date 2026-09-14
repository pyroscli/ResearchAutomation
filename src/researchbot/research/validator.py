from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from researchbot.research.schema import ResearchReport


_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ReportValidationError(ValueError):
    pass


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = _FENCE.search(text)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        match = _OBJECT.search(text)
        if match is None:
            raise ReportValidationError("No JSON object found in agent output")
        raw = match.group(0)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReportValidationError(f"Agent output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReportValidationError("Agent JSON must be an object")
    return payload


def parse_report(payload: dict[str, Any] | str) -> ResearchReport:
    if isinstance(payload, str):
        payload = extract_json_object(payload)
    try:
        return ResearchReport.model_validate(payload)
    except ValidationError as exc:
        raise ReportValidationError(str(exc)) from exc
