from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from models import MeetingMinutes


class Repository:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()
        self.minutes_dir = self.root / "minutes"
        self.transcripts_dir = self.root / "transcripts"
        self.audio_dir = self.root / "audio"
        self.minutes_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def minutes_path_for_date(self, dt: datetime) -> Path:
        return self.minutes_dir / f"{dt.strftime('%Y%m%d')}.md"

    def append_minutes_markdown(self, dt: datetime, markdown_block: str) -> Path:
        out = self.minutes_path_for_date(dt)
        with out.open("a", encoding="utf-8") as f:
            if out.stat().st_size > 0:
                f.write("\n\n---\n\n")
            f.write(markdown_block.rstrip())
            f.write("\n")
        return out

    def write_transcript_json(self, session_id: str, payload: dict) -> Path:
        out = self.transcripts_dir / f"{session_id}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return out

    def write_minutes_json(self, session_id: str, minutes: MeetingMinutes) -> Path:
        out = self.transcripts_dir / f"{session_id}.minutes.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(asdict(minutes), f, ensure_ascii=False, indent=2)
        return out

    def delete_older_than_days(self, days: int) -> list[Path]:
        cutoff = datetime.now() - timedelta(days=days)
        removed: list[Path] = []
        for base in (self.transcripts_dir, self.audio_dir):
            for p in base.rglob("*"):
                if not p.is_file():
                    continue
                modified = datetime.fromtimestamp(p.stat().st_mtime)
                if modified < cutoff:
                    p.unlink(missing_ok=True)
                    removed.append(p)
        return removed
