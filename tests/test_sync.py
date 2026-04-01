import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from sesh.sync import _index_file, _is_active, _is_unchanged, convert_gemini_to_jsonl


def test_is_active_recent(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text("data")
    assert _is_active(f) is True


def test_is_active_old(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text("data")
    old_time = time.time() - 120
    os.utime(f, (old_time, old_time))
    assert _is_active(f) is False


def test_is_active_missing():
    assert _is_active(Path("/nonexistent/file.jsonl")) is False


def test_is_unchanged_matching(tmp_path):
    src = tmp_path / "src.jsonl"
    dest = tmp_path / "dest.jsonl"
    src.write_text("data")
    dest.write_text("data")
    t = time.time() - 10
    os.utime(src, (t, t))
    os.utime(dest, (t + 1, t + 1))
    assert _is_unchanged(src, dest) is True


def test_is_unchanged_different_size(tmp_path):
    src = tmp_path / "src.jsonl"
    dest = tmp_path / "dest.jsonl"
    src.write_text("longer data")
    dest.write_text("data")
    assert _is_unchanged(src, dest) is False


def test_is_unchanged_no_dest(tmp_path):
    src = tmp_path / "src.jsonl"
    src.write_text("data")
    assert _is_unchanged(src, tmp_path / "nope.jsonl") is False


def test_convert_gemini_to_jsonl(tmp_path):
    source = tmp_path / "session-abc.json"
    data = {
        "sessionId": "abc",
        "startTime": "2025-01-01T00:00:00Z",
        "projectHash": "xyz",
        "messages": [
            {"type": "user", "timestamp": "2025-01-01T00:00:01Z", "content": "hello"},
            {"type": "assistant", "timestamp": "2025-01-01T00:00:02Z", "content": "hi"},
        ],
    }
    source.write_text(json.dumps(data))

    lines = convert_gemini_to_jsonl(source)
    assert len(lines) == 3

    first = json.loads(lines[0])
    assert first["type"] == "session_start"
    assert first["sessionId"] == "abc"

    user_msg = json.loads(lines[1])
    assert user_msg["message"]["role"] == "user"

    asst_msg = json.loads(lines[2])
    assert asst_msg["message"]["role"] == "assistant"


def test_convert_gemini_bad_file(tmp_path):
    source = tmp_path / "bad.json"
    source.write_text("not json")
    assert convert_gemini_to_jsonl(source) == []


def _make_session(tmp: Path, provider: str, name: str, lines: list[dict]) -> tuple[Path, Path]:
    root = tmp / ".sesh"
    path = root / provider / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item) for item in lines) + "\n")
    return root, path


def test_index_file_basic(tmp_path):
    root, path = _make_session(
        tmp_path,
        "claude",
        "abc.jsonl",
        [
            {"type": "system", "timestamp": "2025-01-01T00:00:00Z"},
            {"type": "assistant", "role": "assistant", "message": {"content": "hi"}},
        ],
    )
    with patch("sesh.sync.SESSIONS_ROOT", root):
        entry = _index_file(path)
        assert entry["line_count"] == 2
        assert entry["has_assistant_turn"] is True
        assert entry["created_at"] == "2025-01-01T00:00:00Z"
        assert entry["size"] > 0


def test_index_file_no_assistant(tmp_path):
    root, path = _make_session(
        tmp_path,
        "claude",
        "user-only.jsonl",
        [{"type": "user", "message": {"content": "hello"}}],
    )
    with patch("sesh.sync.SESSIONS_ROOT", root):
        entry = _index_file(path)
        assert entry["has_assistant_turn"] is False
