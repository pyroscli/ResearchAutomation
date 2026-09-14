from researchbot.config import Settings
from researchbot.research.playbook import build_research_prompt, load_playbook_text


def _settings() -> Settings:
    return Settings(telegram_bot_token="test-token", cursor_api_key="test-key")


def test_playbook_loads() -> None:
    text = load_playbook_text(_settings())
    assert "Research Intelligence Agent" in text
    assert "Paper researcher" in text
    assert "artifacts/research-result.json" in text


def test_research_prompt_includes_query() -> None:
    prompt = build_research_prompt(_settings(), "How does continuous batching work?")
    assert "How does continuous batching work?" in prompt
    assert "artifacts/research-result.json" in prompt
