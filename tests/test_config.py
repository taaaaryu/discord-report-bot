import pytest

from config import load_settings


def _set_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setenv("GUILD_ID", "1")
    monkeypatch.setenv("TARGET_VOICE_CHANNEL_ID", "2")
    monkeypatch.setenv("MINUTES_TEXT_CHANNEL_ID", "3")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")


def test_load_settings_defaults_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    settings = load_settings()

    assert settings.llm_provider == "openai"
    assert settings.gemini_api_key is None


def test_load_settings_requires_gemini_key_when_provider_is_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_base_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        load_settings()
