from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
import wave
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import discord

try:
    from discord.ext import voice_recv  # type: ignore
except Exception:  # noqa: BLE001
    voice_recv = None

logger = logging.getLogger(__name__)


@dataclass
class ActiveRecording:
    session_id: str
    started_at: datetime
    voice_client: Any
    chunk_seconds: int
    output_dir: Path
    participant_names: dict[int, str] = field(default_factory=dict)
    chunk_paths: list[Path] = field(default_factory=list)
    rotate_task: asyncio.Task | None = None
    current_offset_sec: int = 0
    running: bool = False
    sink: Any | None = None
    chunk_index: int = 0
    writers: dict[int, wave.Wave_write] = field(default_factory=dict)
    writer_paths: dict[int, Path] = field(default_factory=dict)
    writer_sizes: dict[int, int] = field(default_factory=dict)
    io_lock: threading.Lock = field(default_factory=threading.Lock)


class DiscordVoiceRecorder:
    def __init__(self, audio_root: Path) -> None:
        self.audio_root = audio_root
        self.audio_root.mkdir(parents=True, exist_ok=True)

    async def start(self, channel: discord.VoiceChannel, session_id: str, chunk_minutes: int) -> ActiveRecording:
        if voice_recv is None:
            raise RuntimeError("discord-ext-voice-recv is required for recording")

        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        rec = ActiveRecording(
            session_id=session_id,
            started_at=datetime.now(),
            voice_client=voice_client,
            chunk_seconds=chunk_minutes * 60,
            output_dir=self.audio_root / session_id,
        )
        rec.output_dir.mkdir(parents=True, exist_ok=True)
        rec.running = True

        rec.sink = voice_recv.BasicSink(self._build_callback(rec))
        if hasattr(voice_client, "listen"):
            voice_client.listen(rec.sink)
        rec.rotate_task = asyncio.create_task(self._rotate_loop(rec))
        return rec

    async def stop(self, rec: ActiveRecording) -> list[Path]:
        rec.running = False

        if rec.rotate_task:
            rec.rotate_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await rec.rotate_task

        if hasattr(rec.voice_client, "stop_listening"):
            with contextlib.suppress(Exception):
                rec.voice_client.stop_listening()

        self._close_current_chunk(rec)

        if rec.voice_client and rec.voice_client.is_connected():
            await rec.voice_client.disconnect(force=True)

        return rec.chunk_paths

    async def _rotate_loop(self, rec: ActiveRecording) -> None:
        while rec.running:
            await asyncio.sleep(rec.chunk_seconds)
            if not rec.running:
                return
            self._close_current_chunk(rec)
            rec.current_offset_sec += rec.chunk_seconds
            rec.chunk_index += 1

    def _build_callback(self, rec: ActiveRecording):
        def on_voice(user: discord.Member | discord.User | None, data: Any) -> None:
            if not rec.running or user is None or getattr(user, "bot", False):
                return
            pcm = getattr(data, "pcm", None)
            if pcm is None:
                return

            user_id = int(user.id)
            display_name = getattr(user, "display_name", None) or getattr(user, "name", None) or f"user{user_id}"
            rec.participant_names[user_id] = display_name

            with rec.io_lock:
                writer = rec.writers.get(user_id)
                if writer is None:
                    path = self._chunk_path(rec, user_id, display_name)
                    writer = wave.open(str(path), "wb")
                    writer.setnchannels(2)
                    writer.setsampwidth(2)
                    writer.setframerate(48000)
                    rec.writers[user_id] = writer
                    rec.writer_paths[user_id] = path
                    rec.writer_sizes[user_id] = 0

                writer.writeframes(pcm)
                rec.writer_sizes[user_id] = rec.writer_sizes.get(user_id, 0) + len(pcm)

        return on_voice

    def _close_current_chunk(self, rec: ActiveRecording) -> None:
        with rec.io_lock:
            for uid, writer in list(rec.writers.items()):
                with contextlib.suppress(Exception):
                    writer.close()
                path = rec.writer_paths.get(uid)
                if path and rec.writer_sizes.get(uid, 0) > 0:
                    rec.chunk_paths.append(path)
                elif path:
                    with contextlib.suppress(FileNotFoundError):
                        path.unlink()
            rec.writers.clear()
            rec.writer_paths.clear()
            rec.writer_sizes.clear()

    def _chunk_path(self, rec: ActiveRecording, user_id: int, display_name: str) -> Path:
        safe_name = self._safe_name(display_name)
        filename = f"{rec.session_id}_u{user_id}_{safe_name}_off{rec.current_offset_sec}.wav"
        return rec.output_dir / filename

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r"[^0-9A-Za-z_\-]+", "_", name).strip("_") or "unknown"
