"""Seed spawn event files from sesh-synced sessions.

Source of truth: space.db spawns table (spawn_id → session_id).
File store: ~/.sesh/<provider>/ (synced from ~/.claude/projects/).

The seed command looks up each DB spawn's session_id in sesh,
copies the matching JSONL to ~/.space/traces/<provider>/<spawn_id>.jsonl.
"""

import shutil
import sqlite3
import sys
from pathlib import Path

from fncli import cli

from sesh.db import SESSIONS_ROOT
from sesh.display import progress, progress_done

SPACE_DB = Path("~/.engine/space.db").expanduser()
SEED_ROOT = Path("~/.space/traces").expanduser()

echo = print


def _load_spawns_from_db() -> list[tuple[str, str]]:
    """Return (spawn_id, session_id) pairs from space.db."""
    if not SPACE_DB.exists():
        return []
    conn = sqlite3.connect(str(SPACE_DB), timeout=5)
    try:
        rows = conn.execute(
            "SELECT id, session_id FROM spawns WHERE session_id IS NOT NULL AND session_id != ''"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def seed_spawns(dry_run: bool = False) -> dict[str, int]:
    """Seed spawn files from DB → sesh lookup."""
    db_spawns = _load_spawns_from_db()
    if not db_spawns:
        echo("No spawns in space.db")
        return {"seeded": 0, "skipped": 0, "missing": 0}

    stats = {"seeded": 0, "skipped": 0, "missing": 0}
    tty = sys.stdout.isatty()
    to_seed: list[tuple[Path, Path]] = []

    # Build sesh file index once (session_uuid → path)
    # Handles both plain UUID filenames and codex rollout-<date>-<uuid> filenames
    sesh_index: dict[str, Path] = {}
    for provider_dir in SESSIONS_ROOT.iterdir():
        if (
            not provider_dir.is_dir()
            or provider_dir.name.startswith(".")
            or provider_dir.name == "spawns"
        ):
            continue
        for jsonl in provider_dir.rglob("*.jsonl"):
            stem = jsonl.stem
            sesh_index[stem] = jsonl
            # Codex: rollout-<datetime>-<uuid> — extract the UUID suffix
            if stem.startswith("rollout-") and stem.count("-") >= 6:
                # UUID is last 5 hyphen-separated segments
                parts = stem.split("-")
                uuid = "-".join(parts[-5:])
                sesh_index[uuid] = jsonl
            # Gemini: <datetime>-<short_id> — match against UUID prefix
            if provider_dir.name == "gemini" and "-" in stem:
                short_id = stem.rsplit("-", 1)[-1]
                if len(short_id) == 8:
                    sesh_index[short_id] = jsonl

    for spawn_id, session_id in db_spawns:
        # Determine provider from sesh location
        sesh_file = sesh_index.get(session_id)
        # Gemini: DB stores full UUID, sesh indexes by 8-char prefix
        if not sesh_file and "-" in session_id:
            sesh_file = sesh_index.get(session_id.split("-", 1)[0])
        if not sesh_file:
            stats["missing"] += 1
            continue

        # Use provider dir from sesh path (claude/, codex/, gemini/)
        provider = sesh_file.relative_to(SESSIONS_ROOT).parts[0]
        dst = SEED_ROOT / provider / f"{spawn_id}.jsonl"
        if dst.exists():
            stats["skipped"] += 1
            continue
        to_seed.append((sesh_file, dst))

    total = len(to_seed)
    if tty and total:
        progress(total, 0, "seed")

    for i, (src, dst) in enumerate(to_seed):
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        stats["seeded"] += 1
        if tty and total:
            progress(total, i + 1, "seed")

    if tty and total:
        progress_done("seed")

    return stats


@cli("sesh", description="seed spawn files from space.db + sesh sessions")
def seed(dry_run: bool = False):
    result = seed_spawns(dry_run=dry_run)
    prefix = "[dry-run] " if dry_run else ""
    echo(f"{prefix}Seeded: {result['seeded']}")
    echo(f"Skipped (already seeded): {result['skipped']}")
    echo(f"Missing (no sesh file): {result['missing']}")
    total = result["seeded"] + result["skipped"] + result["missing"]
    echo(f"Coverage: {result['seeded'] + result['skipped']}/{total}")
    if result["seeded"]:
        echo(f"\nOutput: {SEED_ROOT}")
