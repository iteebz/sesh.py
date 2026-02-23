import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SESSIONS_ROOT = Path("~/.sesh").expanduser()
INDEX_PATH = SESSIONS_ROOT / "index.json"


@dataclass
class SessionFile:
    path: Path
    provider: str
    session_id: str
    _line_count: int | None = field(default=None, repr=False, compare=False)
    _has_assistant_turn: bool | None = field(default=None, repr=False, compare=False)

    @property
    def size(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    @property
    def mtime(self) -> float:
        return self.path.stat().st_mtime if self.path.exists() else 0

    @property
    def line_count(self) -> int:
        if self._line_count is not None:
            return self._line_count
        try:
            with self.path.open() as f:
                count = sum(1 for line in f if line.strip())
            self._line_count = count
            return count
        except Exception:
            self._line_count = 0
            return 0

    @property
    def has_assistant_turn(self) -> bool:
        if self._has_assistant_turn is not None:
            return self._has_assistant_turn
        try:
            with self.path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    raw = json.loads(line)
                    if raw.get("type") == "assistant" or raw.get("role") == "assistant":
                        self._has_assistant_turn = True
                        return True
            self._has_assistant_turn = False
            return False
        except Exception:
            self._has_assistant_turn = False
            return False

    @property
    def is_real(self) -> bool:
        return self.has_assistant_turn

    @property
    def created_at(self) -> datetime:
        try:
            with self.path.open() as f:
                for _ in range(5):
                    line = f.readline()
                    if not line:
                        break
                    raw = json.loads(line)
                    ts = raw.get("timestamp")
                    if ts:
                        return datetime.fromisoformat(ts).astimezone()
        except Exception:  # noqa: S110
            pass
        return datetime.fromtimestamp(self.mtime).astimezone()

    @property
    def created_at_ts(self) -> float:
        return self.created_at.timestamp()


def _load_index() -> dict[str, dict] | None:
    if not INDEX_PATH.exists():
        return None
    try:
        with INDEX_PATH.open() as f:
            return json.load(f)
    except Exception:
        return None


def build_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    if not SESSIONS_ROOT.exists():
        return index

    for provider_dir in SESSIONS_ROOT.iterdir():
        if not provider_dir.is_dir() or provider_dir.name.startswith("."):
            continue
        provider = provider_dir.name
        for jsonl in provider_dir.glob("*.jsonl"):
            key = f"{provider}/{jsonl.stem}"
            created_at: str | None = None
            has_assistant = False
            line_count = 0
            try:
                with jsonl.open() as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        line_count += 1
                        raw = json.loads(line)
                        if created_at is None:
                            ts = raw.get("timestamp")
                            if ts:
                                created_at = ts
                        if not has_assistant and (
                            raw.get("type") == "assistant" or raw.get("role") == "assistant"
                        ):
                            has_assistant = True
            except Exception:  # noqa: S110
                pass
            index[key] = {
                "mtime": jsonl.stat().st_mtime,
                "size": jsonl.stat().st_size,
                "created_at": created_at,
                "has_assistant_turn": has_assistant,
                "line_count": line_count,
            }

    INDEX_PATH.write_text(json.dumps(index))
    return index


def discover_sessions(provider_filter: str | None = None) -> list[SessionFile]:
    sessions: list[SessionFile] = []

    if not SESSIONS_ROOT.exists():
        return sessions

    index = _load_index()

    for provider_dir in SESSIONS_ROOT.iterdir():
        if not provider_dir.is_dir() or provider_dir.name.startswith("."):
            continue
        provider = provider_dir.name
        if provider_filter and provider != provider_filter:
            continue
        for jsonl in provider_dir.glob("*.jsonl"):
            key = f"{provider}/{jsonl.stem}"
            sf = SessionFile(path=jsonl, provider=provider, session_id=jsonl.stem)
            if index and key in index:
                entry = index[key]
                sf._line_count = entry.get("line_count")
                sf._has_assistant_turn = entry.get("has_assistant_turn")
            sessions.append(sf)

    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions
