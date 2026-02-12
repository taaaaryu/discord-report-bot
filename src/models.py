from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Utterance:
    speaker_id: int
    speaker_name: str
    started_at_sec: float
    ended_at_sec: float
    text: str


@dataclass(frozen=True)
class MeetingDecision:
    text: str


@dataclass(frozen=True)
class MeetingTodo:
    task: str
    owner: str
    due: str


@dataclass(frozen=True)
class MemberReport:
    speaker_name: str
    progress: str
    concerns: str
    discussion: str
    action: str


@dataclass(frozen=True)
class MeetingMinutes:
    title: str
    date_text: str
    participants: list[str]
    decisions: list[MeetingDecision]
    todos: list[MeetingTodo]
    reports: list[MemberReport]


@dataclass
class MeetingSession:
    session_id: str
    started_at: datetime
    voice_channel_id: int
    participant_ids: set[int] = field(default_factory=set)
    participant_names: dict[int, str] = field(default_factory=dict)
    chunk_paths: list[Path] = field(default_factory=list)
