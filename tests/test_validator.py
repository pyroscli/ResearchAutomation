from pathlib import Path

import pytest

from researchbot.research.validator import (
    ReportValidationError,
    extract_json_object,
    parse_report,
)

SAMPLE = Path(__file__).parent / "fixtures" / "sample_report.json"


def test_parse_sample_report() -> None:
    report = parse_report(SAMPLE.read_text(encoding="utf-8"))
    assert report.query.startswith("continuous batching")
    assert len(report.sources) == 3
    assert report.sources[0].relevance_score >= report.sources[1].relevance_score


def test_extract_from_fenced_text() -> None:
    payload = extract_json_object("Here you go:\n```json\n" + SAMPLE.read_text() + "\n```\n")
    assert payload["query"]


def test_rejects_missing_url() -> None:
    raw = {
        "query": "x",
        "summary": "y",
        "sources": [
            {
                "type": "paper",
                "title": "Untitled",
                "url": "not-a-url",
                "source_name": "arXiv",
                "reliability": "high",
                "relevance_score": 8,
                "verified": True,
                "summary": {"tldr": "Hello"},
            }
        ],
    }
    with pytest.raises(ReportValidationError):
        parse_report(raw)


def test_unverified_gets_safe_tldr() -> None:
    report = parse_report(
        {
            "query": "x",
            "summary": "overview",
            "sources": [
                {
                    "type": "blog",
                    "title": "Hidden",
                    "url": "https://example.com/paywall",
                    "source_name": "example.com",
                    "reliability": "unknown",
                    "relevance_score": 7,
                    "verified": False,
                    "summary": {"tldr": "Unable to verify this source."},
                }
            ],
        }
    )
    assert report.sources[0].unavailable_reason == "Unable to verify this source."


def test_null_lists_are_treated_as_empty() -> None:
    report = parse_report(
        {
            "query": "robotics workbench",
            "summary": "overview",
            "sources": [
                {
                    "type": "paper",
                    "title": "RoboWork",
                    "url": "https://arxiv.org/abs/0000.00000",
                    "source_name": "arXiv",
                    "reliability": "high",
                    "relevance_score": 9.1,
                    "verified": True,
                    "summary": {
                        "tldr": "A robotics coding workbench.",
                        "key_findings": None,
                        "important_concepts": None,
                        "technical_takeaways": None,
                        "key_concepts": None,
                        "timestamps": None,
                    },
                }
            ],
        }
    )
    summary = report.sources[0].summary
    assert summary.key_findings == []
    assert summary.important_concepts == []
    assert summary.technical_takeaways == []
    assert summary.key_concepts == []
    assert summary.timestamps == []
