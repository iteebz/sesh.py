import json
import tempfile
from pathlib import Path

from sesh.parse import extract_content, parse_event, parse_session


def _write_session(lines: list[dict], tmp: Path) -> Path:
    path = tmp / "test.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in lines) + "\n")
    return path


def test_extract_content_string():
    assert extract_content("hello") == "hello"


def test_extract_content_list():
    content = [{"type": "text", "text": "foo"}, {"type": "text", "text": "bar"}]
    assert extract_content(content) == "foo\nbar"


def test_extract_content_tool_use():
    content = [{"type": "tool_use", "name": "bash"}]
    assert "bash" in extract_content(content)


def test_extract_content_nested_dict():
    assert extract_content({"content": "nested"}) == "nested"


def test_parse_event_user():
    raw = {"type": "user", "timestamp": "2025-01-01T00:00:00Z", "message": {"content": "hi"}}
    event = parse_event(raw)
    assert event.role == "user"
    assert event.content == "hi"


def test_parse_event_assistant():
    raw = {"type": "assistant", "timestamp": "2025-01-01T00:00:00Z", "message": {"content": "yo"}}
    event = parse_event(raw)
    assert event.role == "assistant"
    assert event.content == "yo"


def test_parse_event_role_field():
    raw = {"role": "user", "message": {"content": "test"}}
    event = parse_event(raw)
    assert event.role == "user"


def test_parse_session_basic():
    lines = [
        {"type": "system", "timestamp": "2025-01-01T00:00:00Z", "sessionId": "abc-123"},
        {"type": "user", "timestamp": "2025-01-01T00:00:01Z", "message": {"content": "hello"}},
        {"type": "assistant", "timestamp": "2025-01-01T00:00:02Z", "message": {"content": "hi"}},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_session(lines, Path(tmp))
        session = parse_session(path, "test")
        assert session.session_id == "abc-123"
        assert session.provider == "test"
        assert len(session.events) == 3
        assert len(session.messages) == 2
        assert len(session.user_messages) == 1
        assert len(session.assistant_messages) == 1
        assert session.first_timestamp == "2025-01-01T00:00:00Z"
        assert session.last_timestamp == "2025-01-01T00:00:02Z"


def test_parse_session_with_usage():
    lines = [
        {
            "type": "assistant",
            "timestamp": "2025-01-01T00:00:00Z",
            "message": {"content": "hi"},
            "usage": {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10},
        },
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_session(lines, Path(tmp))
        session = parse_session(path, "test")
        assert session.tokens.input == 100
        assert session.tokens.output == 50
        assert session.tokens.cache_read == 10


def test_parse_session_skips_bad_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        path.write_text('{"type":"user","message":{"content":"ok"}}\nnot json\n')
        session = parse_session(path, "test")
        assert len(session.events) == 1


def test_parse_session_empty_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.jsonl"
        path.write_text("")
        session = parse_session(path, "test")
        assert len(session.events) == 0


def test_parse_session_extracts_cwd_and_model():
    lines = [
        {"type": "system", "cwd": "/home/user", "model": "claude-3-opus"},
        {"type": "user", "message": {"content": "test"}},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_session(lines, Path(tmp))
        session = parse_session(path, "test")
        assert session.cwd == "/home/user"
        assert session.model == "claude-3-opus"
