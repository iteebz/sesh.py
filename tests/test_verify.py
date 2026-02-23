import json
from pathlib import Path
from unittest.mock import patch

from sesh.verify import verify_all, verify_file


def _make_session(tmp: Path, provider: str, name: str, content: str) -> Path:
    root = tmp / ".sesh"
    path = root / provider / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return root


def test_verify_file_ok(tmp_path):
    root = _make_session(
        tmp_path,
        "claude",
        "ok.jsonl",
        json.dumps({"type": "user", "message": {"content": "hello"}}) + "\n",
    )
    with patch("sesh.discover.SESSIONS_ROOT", root):
        issues = verify_file("claude", root / "claude" / "ok.jsonl")
        assert issues == []


def test_verify_file_empty(tmp_path):
    root = _make_session(tmp_path, "claude", "empty.jsonl", "")
    with patch("sesh.discover.SESSIONS_ROOT", root):
        issues = verify_file("claude", root / "claude" / "empty.jsonl")
        assert len(issues) == 1
        assert issues[0].kind == "empty"


def test_verify_file_corrupt_lines(tmp_path):
    root = _make_session(
        tmp_path,
        "claude",
        "corrupt.jsonl",
        json.dumps({"type": "user"}) + "\nnot json\n" + json.dumps({"type": "assistant"}) + "\n",
    )
    with patch("sesh.discover.SESSIONS_ROOT", root):
        issues = verify_file("claude", root / "claude" / "corrupt.jsonl")
        assert len(issues) == 1
        assert issues[0].kind == "corrupt_lines"
        assert "1/3" in issues[0].detail


def test_verify_file_no_data(tmp_path):
    root = _make_session(tmp_path, "claude", "whitespace.jsonl", "\n\n\n")
    with patch("sesh.discover.SESSIONS_ROOT", root):
        issues = verify_file("claude", root / "claude" / "whitespace.jsonl")
        assert any(i.kind == "no_data" for i in issues)


def test_verify_all(tmp_path):
    root = tmp_path / ".sesh"
    for name, content in [
        ("good.jsonl", json.dumps({"type": "user"}) + "\n"),
        ("bad.jsonl", ""),
    ]:
        path = root / "claude" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    with patch("sesh.verify._iter_provider_files") as mock_iter:
        with patch("sesh.discover.SESSIONS_ROOT", root):
            mock_iter.return_value = [
                ("claude", root / "claude" / "good.jsonl"),
                ("claude", root / "claude" / "bad.jsonl"),
            ]
            result = verify_all()
            assert result.total == 2
            assert result.ok == 1
            assert result.failed == 1
