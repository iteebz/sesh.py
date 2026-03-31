"""Identify garbage sessions. Never auto-deletes — reports IDs for manual review.

Categories:
  empty    — 0 bytes
  stub     — <=5 lines, no assistant response
  dead     — >5 lines but no assistant response (crashed/timed out)
  orphan   — file on disk not in index
"""

from pathlib import Path

from fncli import cli

from sesh.db import SESSIONS_ROOT, connect
from sesh.fmt import size as fmt_size

echo = print

CLAUDE_PROJECTS = Path("~/.claude/projects").expanduser()


@cli("sesh", description="identify garbage sessions (never deletes)")
def gc(
    category: str | None = None,
    ids: bool = False,
    limit: int = 50,
):
    conn = connect()

    categories = {
        "empty": "size = 0",
        "stub": "has_assistant_turn = 0 AND line_count <= 5 AND size > 0",
        "dead": "has_assistant_turn = 0 AND line_count > 5",
    }

    if category and category not in categories:
        echo(f"Unknown category: {category}")
        echo(f"Valid: {', '.join(categories)}")
        return

    echo("Garbage report")
    echo()

    total_garbage = 0
    total_bytes = 0
    all_ids: list[tuple[str, str, str, int]] = []

    for cat, where in categories.items():
        if category and cat != category:
            continue
        rows = conn.execute(
            f"SELECT session_id, path, provider, size FROM sessions WHERE {where} ORDER BY mtime DESC"
        ).fetchall()
        count = len(rows)
        size = sum(r["size"] for r in rows)
        total_garbage += count
        total_bytes += size

        echo(f"  {cat:<8} {count:>6,} sessions  {fmt_size(size):>8}")

        if ids:
            for r in rows[:limit]:
                all_ids.append((cat, r["session_id"], r["provider"], r["size"]))

    # Check for source files that could also be cleaned
    source_matches = 0
    source_bytes = 0
    if CLAUDE_PROJECTS.exists():
        garbage_ids = {
            r[0]
            for r in conn.execute(
                "SELECT session_id FROM sessions WHERE "
                "(size = 0 OR (has_assistant_turn = 0 AND line_count <= 5))"
            ).fetchall()
        }
        for jsonl in CLAUDE_PROJECTS.rglob("*.jsonl"):
            if jsonl.stem in garbage_ids:
                source_matches += 1
                try:
                    source_bytes += jsonl.stat().st_size
                except OSError:
                    pass

    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()

    echo()
    echo(f"  total    {total_garbage:>6,} sessions  {fmt_size(total_bytes):>8}")
    if source_matches:
        echo(f"  source   {source_matches:>6,} cleanable in ~/.claude/  {fmt_size(source_bytes):>8}")
    echo()
    echo(f"  {total_garbage / max(total_sessions, 1) * 100:.0f}% of {total_sessions:,} sessions are garbage")

    if ids and all_ids:
        echo()
        echo(f"IDs ({min(len(all_ids), limit)} shown):")
        for cat, sid, prov, size in all_ids[:limit]:
            echo(f"  [{cat:<5}] {prov}/{sid}  {fmt_size(size)}")

    if not ids:
        echo()
        echo("Run with --ids to list session IDs for review")
