from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import discord

from config import Settings
from discord_bot.poster import MinutesPoster
from minutes.generator import MinutesGenerator
from minutes.markdown_renderer import MarkdownRenderer
from models import MeetingSession
from storage.repository import Repository
from stt.transcriber import Transcriber
from voice.recorder import ActiveRecording, DiscordVoiceRecorder

logger = logging.getLogger(__name__)


@dataclass
class RuntimeSession:
    meeting: MeetingSession
    recording: ActiveRecording


class SessionManager:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        recorder: DiscordVoiceRecorder,
        transcriber: Transcriber,
        minutes_generator: MinutesGenerator,
        renderer: MarkdownRenderer,
        poster: MinutesPoster,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.recorder = recorder
        self.transcriber = transcriber
        self.minutes_generator = minutes_generator
        self.renderer = renderer
        self.poster = poster
        self.active: RuntimeSession | None = None
        self._lock = asyncio.Lock()

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
        guild: discord.Guild,
    ) -> None:
        target_id = self.settings.target_voice_channel_id
        if (before.channel and before.channel.id == target_id) or (after.channel and after.channel.id == target_id):
            target_channel = guild.get_channel(target_id)
            if not isinstance(target_channel, discord.VoiceChannel):
                return

            humans = [m for m in target_channel.members if not m.bot]
            if self.settings.auto_start:
                if self.active is None and len(humans) >= self.settings.min_participants:
                    await self.start_manual(target_channel, humans)
                    return

            if self.active is not None:
                for participant in humans:
                    self.active.meeting.participant_ids.add(participant.id)
                    self.active.meeting.participant_names[participant.id] = participant.display_name
                self.active.recording.participant_names = dict(self.active.meeting.participant_names)

                if len(humans) == 0:
                    await self.stop_manual(guild)

    async def start_manual(self, channel: discord.VoiceChannel, participants: list[discord.Member]) -> bool:
        async with self._lock:
            if self.active is not None:
                return False
            await self._start_session(channel, participants)
            return True

    async def stop_manual(self, guild: discord.Guild) -> bool:
        async with self._lock:
            if self.active is None:
                return False
            await self._finish_session(guild)
            return True

    async def _start_session(self, channel: discord.VoiceChannel, participants: list[discord.Member]) -> None:
        started_at = datetime.now(self.settings.tzinfo)
        session_id = started_at.strftime("%Y%m%d_%H%M%S")
        meeting = MeetingSession(
            session_id=session_id,
            started_at=started_at,
            voice_channel_id=channel.id,
            participant_ids={m.id for m in participants},
            participant_names={m.id: m.display_name for m in participants},
        )
        recording = await self.recorder.start(
            channel=channel,
            session_id=session_id,
            chunk_minutes=self.settings.audio_chunk_minutes,
        )
        recording.participant_names = dict(meeting.participant_names)
        self.active = RuntimeSession(meeting=meeting, recording=recording)
        logger.info("Started session %s", session_id)

    async def _finish_session(self, guild: discord.Guild) -> None:
        if self.active is None:
            return

        runtime = self.active
        self.active = None

        chunk_paths = await self.recorder.stop(runtime.recording)
        runtime.meeting.chunk_paths = list(chunk_paths)

        utterances, metadata = self.transcriber.transcribe_chunks(
            runtime.meeting.chunk_paths,
            runtime.meeting.participant_names,
        )

        participant_names = sorted(set(runtime.meeting.participant_names.values()))
        minutes = self.minutes_generator.generate(
            title=self.settings.meeting_title,
            dt=runtime.meeting.started_at,
            participant_names=participant_names,
            utterances=utterances,
        )
        markdown = self.renderer.render(minutes)
        saved_path = self.repository.append_minutes_markdown(runtime.meeting.started_at, markdown)

        self.repository.write_transcript_json(
            runtime.meeting.session_id,
            {
                "session_id": runtime.meeting.session_id,
                "utterances": [u.__dict__ for u in utterances],
                "metadata": metadata,
                "minutes_markdown_path": str(saved_path),
            },
        )
        self.repository.write_minutes_json(runtime.meeting.session_id, minutes)

        text_channel = guild.get_channel(self.settings.minutes_text_channel_id)
        if isinstance(text_channel, discord.TextChannel):
            await self.poster.post_markdown(text_channel, markdown)
