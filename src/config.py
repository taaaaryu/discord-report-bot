from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timezone
from zoneinfo import ZoneInfo


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    discord_bot_token: str
    guild_id: int
    target_voice_channel_id: int
    minutes_text_channel_id: int
    min_participants: int
    auto_start: bool
    start_on_boot: bool
    meeting_title: str
    openai_api_key: str
    openai_transcribe_model: str
    llm_provider: str
    openai_summary_model: str
    gemini_api_key: str | None
    gemini_summary_model: str
    audio_chunk_minutes: int
    retention_days: int
    timezone_name: str

    @property
    def tzinfo(self) -> timezone | ZoneInfo:
        try:
            return ZoneInfo(self.timezone_name)
        except Exception:
            return timezone.utc


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    llm_provider = os.getenv("LLM_PROVIDER", "openai").strip().lower() or "openai"
    if llm_provider not in {"openai", "gemini"}:
        raise ValueError("LLM_PROVIDER must be 'openai' or 'gemini'")

    return Settings(
        discord_bot_token=_require("DISCORD_BOT_TOKEN"),
        guild_id=int(_require("GUILD_ID")),
        target_voice_channel_id=int(_require("TARGET_VOICE_CHANNEL_ID")),
        minutes_text_channel_id=int(_require("MINUTES_TEXT_CHANNEL_ID")),
        min_participants=int(os.getenv("MIN_PARTICIPANTS", "2")),
        auto_start=_parse_bool(os.getenv("AUTO_START", "false"), default=False),
        start_on_boot=_parse_bool(os.getenv("START_ON_BOOT", "false"), default=False),
        meeting_title=os.getenv("MEETING_TITLE", "日次会議").strip() or "日次会議",
        openai_api_key=_require("OPENAI_API_KEY"),
        openai_transcribe_model=os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1"),
        llm_provider=llm_provider,
        openai_summary_model=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini"),
        gemini_api_key=_require("GEMINI_API_KEY") if llm_provider == "gemini" else None,
        gemini_summary_model=os.getenv("GEMINI_SUMMARY_MODEL", "gemini-1.5-flash"),
        audio_chunk_minutes=int(os.getenv("AUDIO_CHUNK_MINUTES", "10")),
        retention_days=int(os.getenv("RETENTION_DAYS", "7")),
        timezone_name=os.getenv("TZ", "Asia/Tokyo"),
    )
