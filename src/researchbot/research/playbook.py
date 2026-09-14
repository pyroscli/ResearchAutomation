from pathlib import Path

from researchbot.config import Settings, resolve_playbook_dir

PLAYBOOK_FILES = (
    "AGENTS.md",
    "schema/research-result.schema.json",
    "researchers/paper.md",
    "researchers/blog.md",
    "researchers/youtube.md",
)


def load_playbook_text(settings: Settings) -> str:
    root = resolve_playbook_dir(settings)
    parts: list[str] = []
    for relative in PLAYBOOK_FILES:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Missing playbook file: {path}")
        parts.append(f"----- {relative} -----\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def researcher_prompt(settings: Settings, name: str) -> str:
    path = resolve_playbook_dir(settings) / "researchers" / f"{name}.md"
    return path.read_text(encoding="utf-8")


def build_research_prompt(settings: Settings, query: str) -> str:
    playbook = load_playbook_text(settings)
    workspace_note = (
        "The playbook is already in this repository under playbook/. "
        "Read those files. Do not edit application code."
        if settings.playbook_repo_url
        else "There is no application repository in this workspace. "
        "Follow the playbook text inlined below."
    )
    return f"""Run a cross-domain research investigation for this user query:

{query}

{workspace_note}

Do the paper, blog, and YouTube research yourself in this run.
Do not wait for subagents. Deduplicate, rank, read the best sources,
and write the report.

Write the complete JSON report to artifacts/research-result.json
and also include that same JSON in your final message inside one json fence.

{playbook}
"""


def playbook_schema_path(settings: Settings) -> Path:
    return resolve_playbook_dir(settings) / "schema" / "research-result.schema.json"
