import json
import shutil
from pathlib import Path

from fncli import cli

from sesh.discover import SESSIONS_ROOT

echo = print

JSONL_SOURCES = [
    ("~/Library/Application Support/Claude/projects", "claude"),
    ("~/.codex/sessions", "codex"),
]

GEMINI_SOURCE = "~/.gemini/tmp"


def sync_jsonl(dry_run: bool = False) -> dict[str, int]:
    stats = {"synced": 0, "skipped": 0, "failed": 0}

    for source_path, provider in JSONL_SOURCES:
        source = Path(source_path).expanduser()
        if not source.exists():
            continue

        dest_dir = SESSIONS_ROOT / provider
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        for jsonl in source.rglob("*.jsonl"):
            dest = dest_dir / jsonl.name

            if dest.exists() and dest.stat().st_size == jsonl.stat().st_size:
                stats["skipped"] += 1
                continue

            if dry_run:
                echo(f"[dry-run] {jsonl} -> {dest}")
                stats["synced"] += 1
                continue

            try:
                shutil.copy2(jsonl, dest)
                stats["synced"] += 1
            except Exception as e:
                echo(f"Failed to sync {jsonl}: {e}")
                stats["failed"] += 1

    return stats


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


def sync_gemini(dry_run: bool = False) -> dict[str, int]:
    stats = {"synced": 0, "skipped": 0, "failed": 0}

    source = Path(GEMINI_SOURCE).expanduser()
    if not source.exists():
        return stats

    dest_dir = SESSIONS_ROOT / "gemini"
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    for session_json in source.rglob("session-*.json"):
        session_id = session_json.stem.replace("session-", "")
        dest = dest_dir / f"{session_id}.jsonl"

        if dest.exists():
            stats["skipped"] += 1
            continue

        if dry_run:
            echo(f"[dry-run] {session_json} -> {dest}")
            stats["synced"] += 1
            continue

        try:
            lines = convert_gemini_to_jsonl(session_json)
            if lines:
                dest.write_text("\n".join(lines) + "\n")
                stats["synced"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            echo(f"Failed to sync {session_json}: {e}")
            stats["failed"] += 1

    return stats


def sync_sessions(dry_run: bool = False) -> dict[str, int]:
    jsonl_stats = sync_jsonl(dry_run=dry_run)
    gemini_stats = sync_gemini(dry_run=dry_run)

    return {
        "synced": jsonl_stats["synced"] + gemini_stats["synced"],
        "skipped": jsonl_stats["skipped"] + gemini_stats["skipped"],
        "failed": jsonl_stats["failed"] + gemini_stats["failed"],
    }


@cli("sesh", name="sync", description="sync sessions from native paths")
def run(dry_run: bool = False):
    echo(f"Syncing to {SESSIONS_ROOT}")
    echo()

    stats = sync_sessions(dry_run=dry_run)

    echo()
    echo(f"Synced: {stats['synced']}")
    echo(f"Skipped (already exists): {stats['skipped']}")
    if stats["failed"]:
        echo(f"Failed: {stats['failed']}")
