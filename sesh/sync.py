import json
import shutil
import sys
import time
from pathlib import Path

from fncli import cli

from sesh.discover import INDEX_PATH, SESSIONS_ROOT, IndexEntry, _iter_provider_files, _session_key
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


def _index_file(jsonl: Path) -> IndexEntry:
    created_at = None
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
    stat = jsonl.stat()
    return {
        "mtime": stat.st_mtime,
        "size": stat.st_size,
        "created_at": created_at,
        "has_assistant_turn": has_assistant,
        "line_count": line_count,
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


def _load_existing_index() -> dict[str, IndexEntry]:
    if not INDEX_PATH.exists():
        return {}
    try:
        with INDEX_PATH.open() as f:
            return json.load(f)
    except Exception:
        return {}


@cli("sesh", description="sync sessions from native paths")
def sync(dry_run: bool = False):
    echo(f"Syncing to {SESSIONS_ROOT}")
    echo()

    jsonl_files = _collect_jsonl()
    gemini_files = _collect_gemini()
    total = len(jsonl_files) + len(gemini_files)
    done = 0
    tty = sys.stdout.isatty()
    stats = {"synced": 0, "skipped": 0, "deferred": 0, "failed": 0}

    existing_index = _load_existing_index()
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

    idx = dict(existing_index)
    all_files = _iter_provider_files()
    current_keys = {_session_key(p, f) for p, f in all_files}
    new_synced_set = set(new_synced)

    for old_key in list(idx.keys()):
        if old_key not in current_keys:
            del idx[old_key]

    reindexed = 0
    for provider, jsonl in all_files:
        key = _session_key(provider, jsonl)
        prev = idx.get(key)
        if prev and jsonl not in new_synced_set:
            st = jsonl.stat()
            if prev["mtime"] == st.st_mtime and prev["size"] == st.st_size:
                continue
        idx[key] = _index_file(jsonl)
        reindexed += 1

    INDEX_PATH.write_text(json.dumps(idx))
    echo(f"Indexed: {len(idx):,} sessions ({reindexed} updated)")
