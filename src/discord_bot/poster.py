from __future__ import annotations

import discord


class MinutesPoster:
    async def post_markdown(self, channel: discord.TextChannel, markdown: str) -> None:
        # Discord message limit (2000 chars). Keep code block style off for Google Docs copy.
        chunks = self._split_message(markdown, limit=1900)
        for idx, chunk in enumerate(chunks):
            header = "# 議事録" if idx == 0 else "(続き)"
            await channel.send(f"{header}\n\n{chunk}")

    @staticmethod
    def _split_message(text: str, limit: int) -> list[str]:
        if len(text) <= limit:
            return [text]
        lines = text.splitlines(keepends=True)
        out: list[str] = []
        buf = ""
        for line in lines:
            if len(buf) + len(line) > limit:
                out.append(buf)
                buf = line
            else:
                buf += line
        if buf:
            out.append(buf)
        return out
