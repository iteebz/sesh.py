from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sesh.db import SESSIONS_ROOT, connect


@dataclass
class SessionFile:
    path: Path
    provider: str
    session_id: str
    _line_count: int | None = field(default=None, repr=False, compare=False)
    _has_assistant_turn: bool | None = field(default=None, repr=False, compare=False)
    _model: str | None = field(default=None, repr=False, compare=False)
    _mtime: float | None = field(default=None, repr=False, compare=False)
    _size: int | None = field(default=None, repr=False, compare=False)
    _created_at_str: str | None = field(default=None, repr=False, compare=False)

    @property
    def size(self) -> int:
        if self._size is not None:
            return self._size
        return self.path.stat().st_size if self.path.exists() else 0

    @property
    def mtime(self) -> float:
        if self._mtime is not None:
            return self._mtime
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
        return False

    @property
    def model(self) -> str | None:
        return self._model

    @property
    def is_real(self) -> bool:
        return self.has_assistant_turn

    @property
    def created_at(self) -> datetime:
        if self._created_at_str:
            try:
                return datetime.fromisoformat(self._created_at_str).astimezone()
            except Exception:
                pass
        return datetime.fromtimestamp(self.mtime).astimezone()

    @property
    def created_at_ts(self) -> float:
        return self.created_at.timestamp()



def _sf_from_row(row) -> SessionFile:
    return SessionFile(
        path=Path(row["path"]),
        provider=row["provider"],
        session_id=row["session_id"],
        _line_count=row["line_count"],
        _has_assistant_turn=bool(row["has_assistant_turn"]),
        _model=row["model"],
        _mtime=row["mtime"],
        _size=row["size"],
        _created_at_str=row["created_at"],
    )


def discover_sessions(
    provider_filter: str | None = None,
    model_filter: str | None = None,
    limit: int | None = None,
    real_only: bool = False,
    days: int | None = None,
) -> list[SessionFile]:
    conn = connect()
    clauses = []
    params: list[object] = []

    if provider_filter:
        clauses.append("provider = ?")
        params.append(provider_filter)
    if model_filter:
        clauses.append("model LIKE ?")
        params.append(f"%{model_filter}%")
    if real_only:
        clauses.append("has_assistant_turn = 1")
    if days:
        clauses.append("created_at > datetime('now', ?)")
        params.append(f"-{days} days")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM sessions {where} ORDER BY mtime DESC"
    if limit:
        sql += f" LIMIT {limit}"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_sf_from_row(r) for r in rows]
