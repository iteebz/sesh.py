import json
from pathlib import Path
from unittest.mock import patch

from sesh.db import connect
from sesh.discover import SessionFile, discover_sessions
from sesh.sync import _index_file, _iter_provider_files, _session_key


def _make_store(tmp: Path, structure: dict[str, list[str]]) -> Path:
    root = tmp / ".sesh"
    for provider, files in structure.items():
        for name in files:
            path = root / provider / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "role": "assistant",
                        "timestamp": "2025-01-01T00:00:00Z",
                        "message": {"content": "hi", "model": "claude-test"},
                    }
                )
                + "\n"
            )
    return root


def _index_store(root: Path):
    """Index all files in a test store into a temp db."""
    conn = connect()
    for provider, jsonl in _iter_provider_files():
        key = _session_key(provider, jsonl)
        info = _index_file(jsonl)
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (key, provider, session_id, path, mtime, size, created_at,
                has_assistant_turn, line_count, model,
                input_tokens, output_tokens, cache_read, cache_create, tool_calls, cost_usd,
                parent_session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                key,
                provider,
                jsonl.stem,
                str(jsonl),
                info["mtime"],
                info["size"],
                info["created_at"],
                int(info["has_assistant_turn"]),
                info["line_count"],
                info["model"],
                info["input_tokens"],
                info["output_tokens"],
                info["cache_read"],
                info["cache_create"],
                info["tool_calls"],
                info["cost_usd"],
                info["parent_session_id"],
            ),
        )
    conn.commit()
    conn.close()


def test_iter_provider_files_finds_nested(tmp_path):
    root = _make_store(
        tmp_path,
        {
            "claude": ["a.jsonl", "sub/b.jsonl", "deep/nested/c.jsonl"],
            "codex": ["d.jsonl"],
        },
    )
    with patch("sesh.sync.SESSIONS_ROOT", root):
        files = _iter_provider_files()
        providers = {p for p, _ in files}
        assert providers == {"claude", "codex"}
        assert len(files) == 4


def test_session_key_flat(tmp_path):
    root = _make_store(tmp_path, {"claude": ["abc.jsonl"]})
    with patch("sesh.sync.SESSIONS_ROOT", root):
        key = _session_key("claude", root / "claude" / "abc.jsonl")
        assert key == "claude/abc"


def test_session_key_nested(tmp_path):
    root = _make_store(tmp_path, {"claude": ["project-dir/abc.jsonl"]})
    with patch("sesh.sync.SESSIONS_ROOT", root):
        key = _session_key("claude", root / "claude" / "project-dir" / "abc.jsonl")
        assert key == "claude/project-dir/abc"


def test_discover_sessions_all(tmp_path):
    root = _make_store(
        tmp_path,
        {"claude": ["a.jsonl", "sub/b.jsonl"], "codex": ["c.jsonl"]},
    )
    db_path = root / "sessions.db"
    with (
        patch("sesh.sync.SESSIONS_ROOT", root),
        patch("sesh.db.SESSIONS_ROOT", root),
        patch("sesh.db.DB_PATH", db_path),
        patch("sesh.discover.connect", connect),
    ):
        _index_store(root)
        sessions = discover_sessions()
        assert len(sessions) == 3


def test_discover_sessions_filter(tmp_path):
    root = _make_store(
        tmp_path,
        {"claude": ["a.jsonl"], "codex": ["b.jsonl"]},
    )
    db_path = root / "sessions.db"
    with (
        patch("sesh.sync.SESSIONS_ROOT", root),
        patch("sesh.db.SESSIONS_ROOT", root),
        patch("sesh.db.DB_PATH", db_path),
        patch("sesh.discover.connect", connect),
    ):
        _index_store(root)
        sessions = discover_sessions(provider_filter="codex")
        assert len(sessions) == 1
        assert sessions[0].provider == "codex"


def test_session_file_properties(tmp_path):
    root = _make_store(tmp_path, {"claude": ["test.jsonl"]})
    path = root / "claude" / "test.jsonl"
    sf = SessionFile(path=path, provider="claude", session_id="test")
    assert sf.size > 0
    assert sf.line_count == 1
    assert sf.is_real is False  # no db data, _has_assistant_turn defaults to False


def test_discover_skips_hidden_dirs(tmp_path):
    root = _make_store(tmp_path, {"claude": ["a.jsonl"], ".hidden": ["b.jsonl"]})
    with patch("sesh.sync.SESSIONS_ROOT", root):
        files = _iter_provider_files()
        providers = {p for p, _ in files}
        assert ".hidden" not in providers
