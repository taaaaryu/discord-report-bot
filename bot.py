import os
import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from discord.sinks import WaveSink

import openai
from pydub import AudioSegment

def transcribe_audio(audio_path: Path) -> str:
    """Transcribe audio using OpenAI Whisper API."""
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    with audio_path.open("rb") as f:
        transcript = openai.Audio.transcribe("whisper-1", f)
    return transcript["text"]


def summarize_text(text: str) -> str:
    """Summarize text using ChatGPT."""
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    messages = [
        {
            "role": "system",
            "content": (
                "You summarize Discord voice channel conversation "
                "into meeting minutes grouped by topic in Markdown format."
            ),
        },
        {"role": "user", "content": text},
    ]
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    return response["choices"][0]["message"]["content"]


def write_markdown(text: str, path: Path) -> None:
    path.write_text(text, encoding="utf-8")


async def send_to_google_docs(text: str, title: str = "Discord Meeting Minutes"):
    """Send text to Google Docs using service account credentials."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    scopes = ["https://www.googleapis.com/auth/documents"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    service = build("docs", "v1", credentials=creds)
    doc = service.documents().create(body={"title": title}).execute()
    doc_id = doc.get("documentId")
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": text,
            }
        }
    ]
    service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


class Recorder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sink = None

    @commands.command(name="start")
    async def start_record(self, ctx: commands.Context):
        if not ctx.author.voice:
            await ctx.send("Please join a voice channel first.")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        vc: discord.VoiceClient = ctx.voice_client
        if vc.is_recording():
            await ctx.send("Already recording.")
            return
        self.sink = WaveSink()
        await vc.start_recording(self.sink, self.finished_callback, ctx)
        await ctx.send("Started recording.")

    async def finished_callback(self, sink: WaveSink, ctx: commands.Context):
        recording_dir = Path("recordings")
        recording_dir.mkdir(exist_ok=True)
        combined = None
        for user, audio in sink.audio_data.items():
            filename = recording_dir / f"{user.id}.wav"
            with filename.open("wb") as f:
                f.write(audio.file.getbuffer())
            seg = AudioSegment.from_file(filename)
            combined = seg if combined is None else combined.overlay(seg)
        if combined is None:
            await ctx.send("No audio recorded.")
            return
        combined_path = recording_dir / "combined.wav"
        combined.export(combined_path, format="wav")
        text = transcribe_audio(combined_path)
        summary = summarize_text(text)
        md_path = recording_dir / "minutes.md"
        write_markdown(summary, md_path)
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            await send_to_google_docs(summary)
        await ctx.send("Recording processed.")
        await sink.vc.disconnect()

    @commands.command(name="stop")
    async def stop_record(self, ctx: commands.Context):
        vc: discord.VoiceClient = ctx.voice_client
        if vc and vc.is_recording():
            await vc.stop_recording()
            await ctx.send("Stopping recording...")
        else:
            await ctx.send("Not recording.")


def main():
    token = os.environ.get("DISCORD_TOKEN")
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.add_cog(Recorder(bot))

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")

    bot.run(token)


if __name__ == "__main__":
    main()
