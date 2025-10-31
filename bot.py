import os
from pathlib import Path

import discord
from discord.ext import commands
from discord.sinks import WaveSink

import whisper
import openai
from pydub import AudioSegment

DISCORD_TOKEN = ""
OPENAI_API_KEY = ""
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")



def summarize_text(text: str) -> str:
    """Summarize text using ChatGPT."""
    openai.api_key = OPENAI_API_KEY
    messages = [
        {
            "role": "system",
            "content": (
                "You summarize Discord voice channel conversation "
                "into meeting minutes grouped by topic in Markdown format in Japanese."
            ),
        },
        {"role": "user", "content": text},
    ]
    response = openai.ChatCompletion.create(model="gpt-5-mini", messages=messages)
    return response["choices"][0]["message"]["content"]


def write_markdown(text: str, path: Path) -> None:
    path.write_text(text, encoding="utf-8")


async def send_to_google_docs(text: str, title: str = "Discord Meeting Minutes"):
    """Send text to Google Docs using service account credentials."""
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds_path = GOOGLE_APPLICATION_CREDENTIALS
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
        # sink holds the active WaveSink instance; recording is a flag
        # to prevent multiple concurrent recordings started by repeated
        # `start` commands (which caused `stop` to become ineffective).
        self.sink = None
        self.recording = False

    @commands.command(name="start")
    async def start_record(self, ctx: commands.Context):
        if not ctx.author.voice:
            await ctx.send("Please join a voice channel first.")
            return
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        vc: discord.VoiceClient = ctx.voice_client
        # Prevent multiple starts: use our recording flag as the primary
        # guard. vc.is_recording() might not reflect intermediate states
        # if commands are invoked quickly, so both checks are used.
        if self.recording or vc.is_recording():
            await ctx.send("Already recording.")
            return

        self.sink = WaveSink()
        try:
            await vc.start_recording(self.sink, self.finished_callback, ctx)
        except Exception as e:
            # If starting fails, clear state and report
            self.sink = None
            await ctx.send(f"Failed to start recording: {e}")
            return

        self.recording = True
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
            # Clear our state even when nothing was recorded
            self.recording = False
            self.sink = None
            return
        combined_path = recording_dir / "combined.wav"
        combined.export(combined_path, format="wav")
        model = whisper.load_model("base")
        result = model.transcribe(combined_path)
        text = result["text"]
        summary = summarize_text(text)
        md_path = recording_dir / "minutes.md"
        write_markdown(summary, md_path)
        if GOOGLE_APPLICATION_CREDENTIALS:
            await send_to_google_docs(summary)
        await ctx.send("Recording processed.")
        # Ensure we clear our recording state before disconnecting.
        self.recording = False
        self.sink = None

        # Try to disconnect the voice client that performed the recording.
        # Prefer the context's voice client if available.
        try:
            vc = ctx.voice_client
            if vc is None and hasattr(sink, "vc"):
                vc = sink.vc
            if vc is not None:
                await vc.disconnect()
        except Exception:
            # Non-fatal: we already processed the audio and notified users.
            pass

    @commands.command(name="stop")
    async def stop_record(self, ctx: commands.Context):
        vc: discord.VoiceClient = ctx.voice_client
        # Attempt to stop any active recording. Use our recording flag
        # to determine whether we've started recording; fall back to the
        # voice client's state as an extra check.
        if vc and (self.recording or vc.is_recording()):
            try:
                await vc.stop_recording()
                await ctx.send("Stopping recording...")
            except Exception as e:
                # Make best-effort to clear local state if stop fails
                self.recording = False
                self.sink = None
                await ctx.send(f"Failed to stop recording cleanly: {e}")
        else:
            await ctx.send("Not recording.")


def main():
    token = DISCORD_TOKEN
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is required")
    
    intents = discord.Intents.default()
    # Only enable voice_states, which might be sufficient for voice functionality
    intents.voice_states = True  # Required to access voice channel information
    # Remove privileged intents for now
    # intents.members = True  # This is privileged
    # intents.message_content = True  # This is privileged
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.add_cog(Recorder(bot))

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user}")

    bot.run(token)


if __name__ == "__main__":
    main()
