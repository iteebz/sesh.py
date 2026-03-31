import sqlite3
from pathlib import Path

SESSIONS_ROOT = Path("~/.sesh").expanduser()
DB_PATH = SESSIONS_ROOT / "sessions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT,
    has_assistant_turn INTEGER NOT NULL DEFAULT 0,
    line_count INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_create INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_provider ON sessions(provider);
CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model);
CREATE INDEX IF NOT EXISTS idx_sessions_mtime ON sessions(mtime);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
"""

MIGRATIONS = [
    # v1 → v2: add token/cost columns
    [
        "ALTER TABLE sessions ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN cache_read INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN cache_create INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN tool_calls INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sessions ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0",
    ],
]


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    for migration in MIGRATIONS:
        for stmt in migration:
            # Extract column name from ALTER TABLE ... ADD COLUMN <name> ...
            col = stmt.split("ADD COLUMN")[1].strip().split()[0]
            if col not in cols:
                conn.execute(stmt)
    conn.commit()
