import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SESSIONS_ROOT = Path("~/.space/sessions").expanduser()


@dataclass
class SessionFile:
    path: Path
    provider: str
    session_id: str

    @property
    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    @property
    def mtime(self) -> float:
        return self.path.stat().st_mtime if self.path.exists() else 0

    @property
    def created_at(self) -> datetime:
        try:
            with self.path.open() as f:
                first_line = f.readline()
            raw = json.loads(first_line)
            ts = raw.get("timestamp")
            if ts:
                return datetime.fromisoformat(ts).astimezone()
        except Exception:  # noqa: S110
            pass
        return datetime.fromtimestamp(self.mtime)

    @property
    def created_at_ts(self) -> float:
        return self.created_at.timestamp()


def discover_sessions(provider_filter: str | None = None) -> list[SessionFile]:
    sessions: list[SessionFile] = []

    if not SESSIONS_ROOT.exists():
        return sessions

    for provider_dir in SESSIONS_ROOT.iterdir():
        if not provider_dir.is_dir():
            continue
        provider = provider_dir.name
        if provider_filter and provider != provider_filter:
            continue
        sessions.extend(
            SessionFile(path=jsonl, provider=provider, session_id=jsonl.stem)
            for jsonl in provider_dir.glob("*.jsonl")
        )

    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions
