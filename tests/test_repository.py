from datetime import datetime
from pathlib import Path

from storage.repository import Repository


def test_minutes_file_is_yyyymmdd_and_appends(tmp_path: Path) -> None:
    repo = Repository(tmp_path)
    dt = datetime(2026, 2, 9, 10, 0, 0)

    p1 = repo.append_minutes_markdown(dt, "# first")
    p2 = repo.append_minutes_markdown(dt, "# second")

    assert p1 == p2
    assert p1.name == "20260209.md"
    body = p1.read_text(encoding="utf-8")
    assert "# first" in body
    assert "# second" in body
    assert "---" in body
