from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

from config import Settings, load_settings
from discord_bot.poster import MinutesPoster
from jobs.cleanup import CleanupJob
from minutes.generator import MinutesGenerator
from minutes.markdown_renderer import MarkdownRenderer
from storage.repository import Repository
from stt.transcriber import Transcriber
from voice.recorder import DiscordVoiceRecorder
from voice.session_manager import SessionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class MeetingBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)

        self.settings = settings
        self.tree = app_commands.CommandTree(self)

        repository = Repository(Path.cwd())
        recorder = DiscordVoiceRecorder(repository.audio_dir)
        transcriber = Transcriber(settings.openai_api_key, settings.openai_transcribe_model)
        generator = MinutesGenerator(
            llm_provider=settings.llm_provider,
            openai_api_key=settings.openai_api_key,
            openai_model=settings.openai_summary_model,
            gemini_api_key=settings.gemini_api_key,
            gemini_model=settings.gemini_summary_model,
        )
        renderer = MarkdownRenderer()
        poster = MinutesPoster()

        self.manager = SessionManager(
            settings=settings,
            repository=repository,
            recorder=recorder,
            transcriber=transcriber,
            minutes_generator=generator,
            renderer=renderer,
            poster=poster,
        )
        self.cleanup = CleanupJob(repository, settings.retention_days)
        self.synced = False

    async def setup_hook(self) -> None:
        @self.tree.command(name="meeting_status", description="録音状態を表示")
        async def meeting_status(interaction: discord.Interaction) -> None:
            active = self.manager.active
            if not active:
                await interaction.response.send_message("録音中の会議はありません", ephemeral=True)
                return
            await interaction.response.send_message(
                f"録音中: session={active.meeting.session_id}, participants={len(active.meeting.participant_ids)}",
                ephemeral=True,
            )

        @self.tree.command(name="meeting_force_stop", description="録音を強制終了")
        async def meeting_force_stop(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Guild内で実行してください", ephemeral=True)
                return
            if not self.manager.active:
                await interaction.response.send_message("録音中セッションはありません", ephemeral=True)
                return
            await self.manager.stop_manual(interaction.guild)
            await interaction.response.send_message("録音を終了して議事録処理を開始しました", ephemeral=True)

        @self.tree.command(name="meeting_start", description="対象VCで録音を開始（手動）")
        async def meeting_start(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Guild内で実行してください", ephemeral=True)
                return
            channel = interaction.guild.get_channel(self.settings.target_voice_channel_id)
            if not isinstance(channel, discord.VoiceChannel):
                await interaction.response.send_message("対象ボイスチャンネルが見つかりません", ephemeral=True)
                return
            humans = [m for m in channel.members if not m.bot]
            if len(humans) < self.settings.min_participants:
                await interaction.response.send_message(
                    f"参加者が{self.settings.min_participants}人未満のため開始しません（現在 {len(humans)} 人）",
                    ephemeral=True,
                )
                return
            started = await self.manager.start_manual(channel, humans)
            if not started:
                await interaction.response.send_message("すでに録音中です", ephemeral=True)
                return
            await interaction.response.send_message("録音を開始しました", ephemeral=True)

        @self.tree.command(name="meeting_stop", description="録音を停止して議事録処理（手動）")
        async def meeting_stop(interaction: discord.Interaction) -> None:
            if interaction.guild is None:
                await interaction.response.send_message("Guild内で実行してください", ephemeral=True)
                return
            stopped = await self.manager.stop_manual(interaction.guild)
            if not stopped:
                await interaction.response.send_message("録音中の会議はありません", ephemeral=True)
                return
            await interaction.response.send_message("録音を終了して議事録処理を開始しました", ephemeral=True)

        @self.tree.command(name="meeting_health", description="依存状態を確認")
        async def meeting_health(interaction: discord.Interaction) -> None:
            recorder_ok = "start_recording" if hasattr(discord.VoiceClient, "start_recording") else "no-start_recording"
            await interaction.response.send_message(
                f"ok: guild={self.settings.guild_id}, recorder={recorder_ok}, auto_start={self.settings.auto_start}",
                ephemeral=True,
            )

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)
        if not self.synced:
            guild = discord.Object(id=self.settings.guild_id)
            await self.tree.sync(guild=guild)
            self.synced = True
            logger.info("Slash commands synced for guild=%s", self.settings.guild_id)
        self.cleanup.start()
        if self.settings.start_on_boot:
            asyncio.create_task(self._start_recording_on_boot())

    async def _start_recording_on_boot(self) -> None:
        await asyncio.sleep(2)
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            logger.error("start_on_boot: guild not found in cache")
            return

        channel = guild.get_channel(self.settings.target_voice_channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            logger.error("start_on_boot: target voice channel not found")
            return

        deadline = asyncio.get_running_loop().time() + 60.0
        while True:
            humans = [m for m in channel.members if not m.bot]
            if len(humans) >= self.settings.min_participants:
                started = await self.manager.start_manual(channel, humans)
                logger.info("start_on_boot: start_manual=%s humans=%d", started, len(humans))
                return
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning(
                    "start_on_boot: not enough participants (need %d, have %d), giving up",
                    self.settings.min_participants,
                    len(humans),
                )
                return
            await asyncio.sleep(5)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        guild = self.get_guild(self.settings.guild_id)
        if guild is None:
            return
        await self.manager.on_voice_state_update(member, before, after, guild)

    async def close(self) -> None:
        await self.cleanup.stop()
        await super().close()


def main() -> None:
    load_dotenv()
    settings = load_settings()
    bot = MeetingBot(settings)
    bot.run(settings.discord_bot_token)


if __name__ == "__main__":
    main()
