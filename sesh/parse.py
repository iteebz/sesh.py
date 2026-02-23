import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    type: str
    timestamp: str | None = None
    content: str | None = None
    role: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass
class Session:
    session_id: str
    provider: str
    path: Path
    events: list[Event] = field(default_factory=list)
    cwd: str | None = None
    model: str | None = None
    tokens: TokenUsage = field(default_factory=TokenUsage)

    @property
    def first_timestamp(self) -> str | None:
        for e in self.events:
            if e.timestamp:
                return e.timestamp
        return None

    @property
    def last_timestamp(self) -> str | None:
        for e in reversed(self.events):
            if e.timestamp:
                return e.timestamp
        return None

    @property
    def messages(self) -> list[Event]:
        return [e for e in self.events if e.role in ("user", "assistant")]

    @property
    def user_messages(self) -> list[Event]:
        return [e for e in self.events if e.role == "user"]

    @property
    def assistant_messages(self) -> list[Event]:
        return [e for e in self.events if e.role == "assistant"]


def extract_content(msg: dict[str, Any] | str | list[Any]) -> str:
    if isinstance(msg, str):
        return msg
    if isinstance(msg, list):
        parts = []
        for item in msg:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "text":
                    parts.append(item.get("text", ""))
                elif item_type == "tool_use":
                    parts.append(f"[tool: {item.get('name', 'unknown')}]")
                elif item_type == "tool_result":
                    content = item.get("content", "")
                    if isinstance(content, str):
                        parts.append(f"[result: {content[:100]}]")
                    else:
                        parts.append("[result]")
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    if isinstance(msg, dict):  # type: ignore[redundant-expr]
        content = msg.get("content")
        if content:
            return extract_content(content)
        text = msg.get("text")
        if text:
            return text
    return ""


def parse_event(raw: dict[str, Any]) -> Event:
    event_type = raw.get("type", "unknown")
    timestamp = raw.get("timestamp")
    content = None
    role = None

    if event_type in ("user", "assistant"):
        role = event_type
        msg = raw.get("message", {})
        content = extract_content(msg)

    if raw.get("role") == "user":
        role = "user"
        msg = raw.get("message", {})
        content = extract_content(msg)

    if raw.get("role") == "assistant":
        role = "assistant"
        msg = raw.get("message", {})
        content = extract_content(msg)

    return Event(
        type=event_type,
        timestamp=timestamp,
        content=content,
        role=role,
        raw=raw,
    )


def parse_session(path: Path, provider: str | None = None) -> Session:
    session_id = path.stem
    if provider is None:
        provider = path.parent.name

    session = Session(session_id=session_id, provider=provider, path=path)
    events = []
    tokens = TokenUsage()

    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                events.append(parse_event(raw))

                if session.session_id == path.stem and raw.get("sessionId"):
                    session.session_id = raw["sessionId"]

                if session.cwd is None:
                    session.cwd = raw.get("cwd")
                if session.model is None:
                    session.model = raw.get("model")

                usage = raw.get("usage") or raw.get("message", {}).get("usage") or {}
                tokens.input += usage.get("input_tokens", 0)
                tokens.output += usage.get("output_tokens", 0)
                tokens.cache_read += usage.get("cache_read_input_tokens", 0)
                tokens.cache_write += usage.get("cache_creation_input_tokens", 0)
            except json.JSONDecodeError:
                continue

    session.events = events
    session.tokens = tokens
    return session
