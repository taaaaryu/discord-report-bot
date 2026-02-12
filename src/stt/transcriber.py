from __future__ import annotations

import re
from pathlib import Path

from openai import OpenAI

from models import Utterance


class Transcriber:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def transcribe_chunks(self, chunk_paths: list[Path], display_names: dict[int, str]) -> tuple[list[Utterance], dict]:
        utterances: list[Utterance] = []
        errors: list[dict] = []

        for path in sorted(chunk_paths):
            meta = self._parse_chunk_name(path)
            speaker_id = meta["speaker_id"]
            base_offset = float(meta["offset_sec"])
            speaker_name = display_names.get(speaker_id, meta["speaker_name"] or f"user-{speaker_id}")

            try:
                with path.open("rb") as audio_fp:
                    result = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_fp,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                    )

                segments = getattr(result, "segments", None) or []
                if not segments:
                    text = getattr(result, "text", "")
                    if text:
                        utterances.append(
                            Utterance(
                                speaker_id=speaker_id,
                                speaker_name=speaker_name,
                                started_at_sec=base_offset,
                                ended_at_sec=base_offset + 1,
                                text=text,
                            )
                        )
                    continue

                for s in segments:
                    utterances.append(
                        Utterance(
                            speaker_id=speaker_id,
                            speaker_name=speaker_name,
                            started_at_sec=base_offset + float(s.start),
                            ended_at_sec=base_offset + float(s.end),
                            text=s.text.strip(),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append({"file": str(path), "error": str(exc)})
                utterances.append(
                    Utterance(
                        speaker_id=speaker_id,
                        speaker_name=speaker_name,
                        started_at_sec=base_offset,
                        ended_at_sec=base_offset + 1,
                        text=f"[文字起こし失敗: {path.name}]",
                    )
                )

        return utterances, {"errors": errors}

    @staticmethod
    def _parse_chunk_name(path: Path) -> dict:
        # expected: <session>_u<id>_<name>_off<sec>.wav
        m = re.match(r".+_u(?P<uid>\d+)_(?P<name>.+)_off(?P<off>\d+)\.wav", path.name)
        if not m:
            return {"speaker_id": 0, "speaker_name": "unknown", "offset_sec": 0}
        return {
            "speaker_id": int(m.group("uid")),
            "speaker_name": m.group("name").replace("_", " "),
            "offset_sec": int(m.group("off")),
        }
