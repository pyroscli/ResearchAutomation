from pathlib import Path

from researchbot.research.validator import parse_report
from researchbot.telegram.formatter import format_report

SAMPLE = Path(__file__).parent / "fixtures" / "sample_report.json"


def test_format_report_contains_links_and_sections() -> None:
    report = parse_report(SAMPLE.read_text(encoding="utf-8"))
    messages = format_report(report)
    joined = "\n".join(messages)
    assert "RESEARCH PAPERS" in joined
    assert "TECHNICAL ARTICLES" in joined
    assert "YOUTUBE" in joined
    assert "Original paper" in joined
    assert "Watch video" in joined
    assert "https://www.usenix.org" in joined
    assert all(len(message) < 4096 for message in messages)
