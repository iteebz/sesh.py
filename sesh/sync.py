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


# Pricing per million tokens (API rates)
_PRICING = {
    "opus": (15.0, 75.0, 1.50, 18.75),
    "sonnet": (3.0, 15.0, 0.30, 3.75),
    "haiku": (0.80, 4.0, 0.08, 1.0),
}


def _estimate_cost(model: str | None, inp: int, out: int, cr: int, cc: int) -> float:
    if not model:
        return 0.0
    m = model.lower()
    for key, (pi, po, pcr, pcc) in _PRICING.items():
        if key in m:
            return (inp * pi + out * po + cr * pcr + cc * pcc) / 1_000_000
    return 0.0


def _index_file(jsonl: Path) -> dict:
    created_at = None
    has_assistant = False
    line_count = 0
    model = None
    input_tokens = 0
    output_tokens = 0
    cache_read = 0
    cache_create = 0
    tool_calls = 0
    parent_session_id = None
    file_stem = jsonl.stem
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
                if parent_session_id is None:
                    sid = raw.get("sessionId")
                    if sid and sid != file_stem:
                        parent_session_id = sid
                msg_type = raw.get("type", "")
                if not has_assistant and (msg_type == "assistant" or raw.get("role") == "assistant"):
                    has_assistant = True
                msg = raw.get("message", {})
                if isinstance(msg, dict):
                    if model is None:
                        m = raw.get("model") or msg.get("model")
                        if m and not m.startswith("<"):
                            model = m
                    usage = msg.get("usage")
                    if usage:
                        input_tokens += usage.get("input_tokens", 0)
                        output_tokens += usage.get("output_tokens", 0)
                        cache_read += usage.get("cache_read_input_tokens", 0)
                        cache_create += usage.get("cache_creation_input_tokens", 0)
                    for block in msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls += 1
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
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read": cache_read,
        "cache_create": cache_create,
        "tool_calls": tool_calls,
        "cost_usd": _estimate_cost(model, input_tokens, output_tokens, cache_read, cache_create),
        "parent_session_id": parent_session_id,
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


def _copy(dry_run: bool = False) -> tuple[list[Path], dict[str, int]]:
    """Phase 1: copy session files from native paths into ~/.sesh/."""
    jsonl_files = _collect_jsonl()
    gemini_files = _collect_gemini()
    total = len(jsonl_files) + len(gemini_files)
    done = 0
    tty = sys.stdout.isatty()
    counts = {"copied": 0, "skipped": 0, "deferred": 0, "failed": 0}
    copied: list[Path] = []

    def _tick():
        nonlocal done
        done += 1
        if tty and total:
            progress(total, done, "copy")

    if tty and total:
        progress(total, 0, "copy")

    for jsonl, dest in jsonl_files:
        if _is_unchanged(jsonl, dest):
            counts["skipped"] += 1
            _tick()
            continue
        if _is_active(jsonl):
            counts["deferred"] += 1
            _tick()
            continue
        if dry_run:
            counts["copied"] += 1
            _tick()
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(jsonl, dest)
            counts["copied"] += 1
            copied.append(dest)
        except Exception:
            counts["failed"] += 1
        _tick()

    dest_dir = SESSIONS_ROOT / "gemini"
    if not dry_run and gemini_files:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for session_json, dest in gemini_files:
        if dest.exists():
            counts["skipped"] += 1
            _tick()
            continue
        if _is_active(session_json):
            counts["deferred"] += 1
            _tick()
            continue
        if dry_run:
            counts["copied"] += 1
            _tick()
            continue
        try:
            lines = convert_gemini_to_jsonl(session_json)
            if lines:
                dest.write_text("\n".join(lines) + "\n")
                counts["copied"] += 1
                copied.append(dest)
            else:
                counts["failed"] += 1
        except Exception:
            counts["failed"] += 1
        _tick()

    if tty and total:
        progress_done("copy")

    return copied, counts


def _index(copied: list[Path], force: bool = False) -> tuple[int, int]:
    """Phase 2: index copied files into sessions.db. Returns (total, reindexed)."""
    conn = connect()

    if force:
        all_files = _iter_provider_files()
        current_keys = {_session_key(p, f) for p, f in all_files}
        existing_keys = {r[0] for r in conn.execute("SELECT key FROM sessions").fetchall()}
        removed = existing_keys - current_keys
        if removed:
            conn.executemany("DELETE FROM sessions WHERE key = ?", [(k,) for k in removed])
        to_index = [(p, f, _session_key(p, f)) for p, f in all_files]
    elif copied:
        to_index = []
        for dest in copied:
            provider = dest.relative_to(SESSIONS_ROOT).parts[0]
            key = _session_key(provider, dest)
            to_index.append((provider, dest, key))
    else:
        total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn.close()
        return total, 0

    tty = sys.stdout.isatty()
    n = len(to_index)
    if tty and n > 100:
        progress(n, 0, "index")

    reindexed = 0
    for i, (provider, jsonl, key) in enumerate(to_index):
        if force:
            st = jsonl.stat()
            row = conn.execute(
                "SELECT mtime, size FROM sessions WHERE key = ?", (key,)
            ).fetchone()
            if row and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
                if tty and n > 100:
                    progress(n, i + 1, "index")
                continue

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
        reindexed += 1
        if tty and n > 100:
            progress(n, i + 1, "index")

    if tty and n > 100:
        progress_done("index")

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()
    return total, reindexed


@cli("sesh", description="copy sessions from native paths and index into sessions.db")
def sync(dry_run: bool = False, force: bool = False):
    # Phase 1: copy
    copied, counts = _copy(dry_run=dry_run)
    echo(f"Copied: {counts['copied']}  Skipped: {counts['skipped']}  Deferred: {counts['deferred']}", end="")
    if counts["failed"]:
        echo(f"  Failed: {counts['failed']}", end="")
    echo()

    if dry_run:
        return

    # Phase 2: index
    total, reindexed = _index(copied, force=force)
    echo(f"Indexed: {total:,} sessions ({reindexed} updated)")
