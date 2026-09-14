from __future__ import annotations

from html import escape

from researchbot.research.schema import ResearchReport, SourceItem, SourceType

TELEGRAM_LIMIT = 3900

TYPE_LABEL = {
    SourceType.PAPER: "RESEARCH PAPERS",
    SourceType.BLOG: "TECHNICAL ARTICLES",
    SourceType.VIDEO: "YOUTUBE",
    SourceType.PATENT: "PATENTS",
    SourceType.REPOSITORY: "GITHUB",
}

TYPE_LINK = {
    SourceType.PAPER: "Original paper",
    SourceType.BLOG: "Read article",
    SourceType.VIDEO: "Watch video",
    SourceType.PATENT: "Open patent",
    SourceType.REPOSITORY: "GitHub",
}


def format_report(report: ResearchReport) -> list[str]:
    chunks: list[str] = []
    header = (
        f"<b>RESEARCH:</b> {escape(report.query)}\n\n"
        f"{escape(report.summary)}\n\n"
        "I analyzed relevant papers, technical articles, and videos."
    )
    chunks.append(header)

    for source_type in (
        SourceType.PAPER,
        SourceType.BLOG,
        SourceType.VIDEO,
        SourceType.PATENT,
        SourceType.REPOSITORY,
    ):
        items = [item for item in report.sources if item.type == source_type]
        if not items:
            continue
        section_chunks = _format_section(source_type, items)
        chunks.extend(section_chunks)
    return _fit(chunks)


def format_help() -> str:
    return (
        "<b>Research Intelligence</b>\n\n"
        "Send a topic, question, paper, technology, or research area. "
        "I will search papers, technical articles, and YouTube, then return "
        "ranked, source-backed summaries.\n\n"
        "<b>Commands</b>\n"
        "/start — welcome\n"
        "/help — this message\n"
        "/search &lt;query&gt; — run cross-domain research\n"
        "/history — recent research queries\n\n"
        "Coming later: /paper /video /blog /patent /github /library, "
        "and saved resources.\n\n"
        "Research can take several minutes. You will get a confirmation "
        "immediately, then the report when it is ready."
    )


def format_welcome() -> str:
    return (
        "Welcome to Research Intelligence.\n\n"
        "Send me a topic, question, paper, technology, or research area "
        "and I'll find and analyze useful resources for you."
    )


def _format_section(source_type: SourceType, items: list[SourceItem]) -> list[str]:
    blocks = [f"<b>{TYPE_LABEL[source_type]}</b>"]
    for index, item in enumerate(items, start=1):
        blocks.append(_format_source(index, item))
    return _fit(blocks)


def _format_source(index: int, item: SourceItem) -> str:
    lines = [
        f"<b>{index}. {escape(item.title)}</b>",
        f"Relevance: {item.relevance_score:.1f}/10",
        (
            f"SOURCE TYPE: {escape(_type_name(item))}\n"
            f"SOURCE: {escape(item.source_name)}\n"
            f"RELIABILITY: {escape(item.reliability.value.title())}"
        ),
    ]
    if item.authors:
        lines.append("Authors: " + escape(", ".join(item.authors)))
    if item.channel:
        lines.append(f"Channel: {escape(item.channel)}")
    if item.duration:
        lines.append(f"Duration: {escape(item.duration)}")
    if item.published_date:
        lines.append(f"Date: {escape(item.published_date)}")
    if item.doi:
        lines.append(f"DOI: {escape(item.doi)}")
    if item.arxiv_id:
        lines.append(f"arXiv: {escape(item.arxiv_id)}")

    summary = item.summary
    if not item.verified:
        lines.append("")
        lines.append(escape(item.unavailable_reason or "Unable to verify this source."))
    else:
        lines.append("")
        lines.append(f"<b>TL;DR</b>\n{escape(summary.tldr)}")
        _add_optional(lines, "Problem", summary.problem)
        _add_optional(lines, "Approach", summary.approach)
        if summary.key_findings:
            lines.append("<b>Key findings</b>\n" + _bullets(summary.key_findings))
        _add_optional(lines, "Why it matters", summary.why_it_matters)
        _add_optional(lines, "Main argument", summary.main_argument)
        if summary.technical_takeaways:
            lines.append(
                "<b>Technical takeaways</b>\n" + _bullets(summary.technical_takeaways)
            )
        if summary.key_concepts:
            lines.append("<b>Key concepts</b>\n" + _bullets(summary.key_concepts))
        if summary.timestamps:
            stamp_lines = "\n".join(
                f"{escape(ts.time)} — {escape(ts.label)}" for ts in summary.timestamps
            )
            lines.append(f"<b>Important sections</b>\n{stamp_lines}")
        if summary.difficulty:
            lines.append(f"Difficulty: {escape(summary.difficulty.value.title())}")

    lines.append("")
    lines.append(f'<a href="{escape(item.url, quote=True)}">{TYPE_LINK[item.type]}</a>')
    return "\n".join(lines)


def _type_name(item: SourceItem) -> str:
    return {
        SourceType.PAPER: "Research Paper",
        SourceType.BLOG: "Technical Article",
        SourceType.VIDEO: "YouTube Video",
        SourceType.PATENT: "Patent",
        SourceType.REPOSITORY: "GitHub Repository",
    }[item.type]


def _add_optional(lines: list[str], title: str, value: str | None) -> None:
    if value:
        lines.append(f"<b>{title}</b>\n{escape(value)}")


def _bullets(items: list[str]) -> str:
    return "\n".join(f"• {escape(item)}" for item in items)


def _fit(blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= TELEGRAM_LIMIT:
            current = candidate
            continue
        if current:
            messages.append(current)
        if len(block) <= TELEGRAM_LIMIT:
            current = block
            continue
        messages.extend(_split_hard(block))
        current = ""
    if current:
        messages.append(current)
    return messages


def _split_hard(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        parts.append(text[start : start + TELEGRAM_LIMIT])
        start += TELEGRAM_LIMIT
    return parts
