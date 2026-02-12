from pathlib import Path

from stt.transcriber import Transcriber


def test_parse_chunk_name() -> None:
    data = Transcriber._parse_chunk_name(Path("20260209_100000_u1234_alice_off600.wav"))
    assert data["speaker_id"] == 1234
    assert data["speaker_name"] == "alice"
    assert data["offset_sec"] == 600
