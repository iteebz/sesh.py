import json
import shutil
import sys
import time
from pathlib import Path

from fncli import cli

from sesh.db import SESSIONS_ROOT, connect
from sesh.discover import _iter_provider_files, _session_key
from sesh.display import progress, progress_done

echo = print

JSONL_SOURCES = [
    ("~/.claude/projects", "claude"),
    ("~/.codex/sessions", "codex"),
    ("~/.sessions/claude", "claude"),
    ("~/.sessions/codex", "codex"),
    ("~/.sessions/gemini", "gemini"),
]

GEMINI_SOURCE = "~/.gemini/tmp"

ACTIVE_THRESHOLD = 60


def _is_active(path: Path) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) < ACTIVE_THRESHOLD
    except OSError:
        return False


def _is_unchanged(src: Path, dest: Path) -> bool:
    if not dest.exists():
        return False
    try:
        ss = src.stat()
        ds = dest.stat()
        return ss.st_size == ds.st_size and ss.st_mtime <= ds.st_mtime
    except OSError:
        return False


def _index_file(jsonl: Path) -> dict:
    created_at = None
    has_assistant = False
    line_count = 0
    model = None
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
                if model is None:
                    model = raw.get("model") or raw.get("message", {}).get("model")
    except Exception:  # noqa: S110
        pass
    stat = jsonl.stat()
    return {
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "created_at": created_at,
        "has_assistant_turn": has_assistant,
        "line_count": line_count,
        "model": model,
    }


def convert_gemini_to_jsonl(source: Path) -> list[str]:
    try:
        with source.open() as f:
            data = json.load(f)

        lines = []
        session_id = data.get("sessionId", source.stem)
        start_time = data.get("startTime")

        lines.append(
            json.dumps(
                {
                    "type": "session_start",
                    "sessionId": session_id,
                    "timestamp": start_time,
                    "projectHash": data.get("projectHash"),
                }
            )
        )

        lines.extend(
            json.dumps(
                {
                    "type": msg.get("type", "unknown"),
                    "sessionId": session_id,
                    "timestamp": msg.get("timestamp"),
                    "message": {"role": msg.get("type"), "content": msg.get("content")},
                }
            )
            for msg in data.get("messages", [])
        )

        return lines
    except Exception:
        return []


def _collect_jsonl() -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for source_path, provider in JSONL_SOURCES:
        source = Path(source_path).expanduser()
        if not source.exists():
            continue
        dest_dir = SESSIONS_ROOT / provider
        files.extend(
            (jsonl, dest_dir / jsonl.relative_to(source)) for jsonl in source.rglob("*.jsonl")
        )
    return files


def _collect_gemini() -> list[tuple[Path, Path]]:
    files = []
    source = Path(GEMINI_SOURCE).expanduser()
    if not source.exists():
        return files
    dest_dir = SESSIONS_ROOT / "gemini"
    for session_json in source.rglob("session-*.json"):
        session_id = session_json.stem.replace("session-", "")
        files.append((session_json, dest_dir / f"{session_id}.jsonl"))
    return files


@cli("sesh", description="sync sessions from native paths")
def sync(dry_run: bool = False, force: bool = False):
    echo(f"Syncing to {SESSIONS_ROOT}")
    echo()

    jsonl_files = _collect_jsonl()
    gemini_files = _collect_gemini()
    total = len(jsonl_files) + len(gemini_files)
    done = 0
    tty = sys.stdout.isatty()
    stats = {"synced": 0, "skipped": 0, "deferred": 0, "failed": 0}

    new_synced: list[Path] = []

    def _tick():
        nonlocal done
        done += 1
        if tty and total:
            progress(total, done, "sync")

    if tty and total:
        progress(total, 0, "sync")

    for jsonl, dest in jsonl_files:
        if _is_unchanged(jsonl, dest):
            stats["skipped"] += 1
            _tick()
            continue
        if _is_active(jsonl):
            stats["deferred"] += 1
            _tick()
            continue
        if dry_run:
            echo(f"[dry-run] {jsonl} -> {dest}")
            stats["synced"] += 1
            _tick()
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jsonl, dest)
            stats["synced"] += 1
            new_synced.append(dest)
        except Exception as e:
            echo(f"Failed to sync {jsonl}: {e}")
            stats["failed"] += 1
        _tick()

    dest_dir = SESSIONS_ROOT / "gemini"
    if not dry_run and gemini_files:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for session_json, dest in gemini_files:
        if dest.exists():
            stats["skipped"] += 1
            _tick()
            continue
        if _is_active(session_json):
            stats["deferred"] += 1
            _tick()
            continue
        if dry_run:
            echo(f"[dry-run] {session_json} -> {dest}")
            stats["synced"] += 1
            _tick()
            continue
        try:
            lines = convert_gemini_to_jsonl(session_json)
            if lines:
                dest.write_text("\n".join(lines) + "\n")
                stats["synced"] += 1
                new_synced.append(dest)
            else:
                stats["failed"] += 1
        except Exception as e:
            echo(f"Failed to sync {session_json}: {e}")
            stats["failed"] += 1
        _tick()

    if tty and total:
        progress_done("sync")

    echo(f"Synced: {stats['synced']}")
    echo(f"Skipped (unchanged): {stats['skipped']}")
    if stats["deferred"]:
        echo(f"Deferred (active): {stats['deferred']}")
    if stats["failed"]:
        echo(f"Failed: {stats['failed']}")

    if dry_run:
        return

    # Index into sqlite — only newly synced files unless --force
    conn = connect()

    if force:
        # Full reindex: scan all files
        all_files = _iter_provider_files()
        current_keys = {_session_key(p, f) for p, f in all_files}
        existing_keys = {r[0] for r in conn.execute("SELECT key FROM sessions").fetchall()}
        removed = existing_keys - current_keys
        if removed:
            conn.executemany("DELETE FROM sessions WHERE key = ?", [(k,) for k in removed])
        to_index = [(p, f, _session_key(p, f)) for p, f in all_files]
    elif new_synced:
        # Incremental: only index what we just copied
        to_index = []
        for dest in new_synced:
            provider = dest.relative_to(SESSIONS_ROOT).parts[0]
            key = _session_key(provider, dest)
            to_index.append((provider, dest, key))
    else:
        total_rows = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        echo(f"Indexed: {total_rows:,} sessions (0 updated)")
        return

    reindexed = 0
    for provider, jsonl, key in to_index:
        if not force:
            # Always index new synced files
            pass
        else:
            st = jsonl.stat()
            row = conn.execute(
                "SELECT mtime, size FROM sessions WHERE key = ?", (key,)
            ).fetchone()
            if row and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                continue

        info = _index_file(jsonl)
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (key, provider, session_id, path, mtime, size, created_at, has_assistant_turn, line_count, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        reindexed += 1

    conn.commit()
    total_rows = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()

    echo(f"Indexed: {total_rows:,} sessions ({reindexed} updated)")
