import subprocess
from datetime import datetime, timedelta

from fncli import cli

from sesh.db import DB_PATH, SESSIONS_ROOT, connect
from sesh.fmt import ago
from sesh.fmt import size as fmt_size

echo = print

PLIST_LABEL = "com.iteebz.sesh-sync"


def _daemon_running() -> bool:
    try:
        r = subprocess.run(
            ["launchctl", "list", PLIST_LABEL],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _last_sync() -> tuple[str, float] | None:
    log = SESSIONS_ROOT / "sync.log"
    if not log.exists():
        return None
    try:
        mtime = log.stat().st_mtime
        return ago(mtime), mtime
    except Exception:
        return None


def _db_size() -> str:
    if not DB_PATH.exists():
        return "missing"
    return fmt_size(DB_PATH.stat().st_size)


@cli("sesh", description="daemon health and sync status")
def status():
    running = _daemon_running()
    sync_info = _last_sync()

    echo(f"Daemon:    {'running' if running else 'NOT RUNNING'}")
    if sync_info:
        rel, _ = sync_info
        echo(f"Last sync: {rel}")
    else:
        echo("Last sync: never")
    echo(f"DB:        {DB_PATH} ({_db_size()})")

    conn = connect()
    total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    real = conn.execute("SELECT COUNT(*) FROM sessions WHERE has_assistant_turn = 1").fetchone()[0]
    models = conn.execute(
        "SELECT model, COUNT(*) as cnt FROM sessions WHERE model IS NOT NULL GROUP BY model ORDER BY cnt DESC LIMIT 5"
    ).fetchall()
    providers = conn.execute(
        "SELECT provider, COUNT(*) as cnt FROM sessions GROUP BY provider ORDER BY cnt DESC"
    ).fetchall()

    oldest = conn.execute(
        "SELECT MIN(created_at) FROM sessions WHERE created_at IS NOT NULL"
    ).fetchone()[0]
    newest = conn.execute(
        "SELECT MAX(created_at) FROM sessions WHERE created_at IS NOT NULL"
    ).fetchone()[0]

    cost = conn.execute("SELECT SUM(cost_usd) FROM sessions").fetchone()[0] or 0
    tokens_in = conn.execute("SELECT SUM(input_tokens) FROM sessions").fetchone()[0] or 0
    tokens_out = conn.execute("SELECT SUM(output_tokens) FROM sessions").fetchone()[0] or 0

    # Gap detection: days with zero sessions in the last 30 days
    gap_rows = conn.execute("""
        SELECT date(created_at) as day FROM sessions
        WHERE created_at > datetime('now', '-30 days')
        GROUP BY day
    """).fetchall()
    conn.close()

    echo(f"\nSessions:  {total:,} total ({real:,} real)")
    echo(f"Span:      {oldest[:10] if oldest else '?'} → {newest[:10] if newest else '?'}")

    echo("\nProviders:")
    for r in providers:
        echo(f"  {r['provider']:<10} {r['cnt']:>6,}")

    echo("\nModels:")
    for r in models:
        short = (r["model"] or "?").split("/")[-1]
        echo(f"  {short:<35} {r['cnt']:>6,}")

    echo(f"\nTokens:    {tokens_in + tokens_out:,} ({tokens_in:,} in / {tokens_out:,} out)")
    echo(f"Cost:      ${cost:,.2f}")

    days_covered = {r["day"] for r in gap_rows}
    today = datetime.now()
    gaps = []
    for i in range(30):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if day not in days_covered:
            gaps.append(day)
    if gaps:
        echo(f"\nGaps (last 30d): {len(gaps)} days missing")
        for g in gaps[:5]:
            echo(f"  {g}")
        if len(gaps) > 5:
            echo(f"  ... and {len(gaps) - 5} more")
    else:
        echo("\nGaps: none (last 30d)")
