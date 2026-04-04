from fncli import cli

from sesh.db import connect
from sesh.fmt import size as fmt_size
from sesh.fmt import tokens as fmt_tokens
from sesh.parse import TokenUsage

echo = print

CLAUDE_PRICING = {
    "input": 3.00 / 1_000_000,
    "output": 15.00 / 1_000_000,
    "cache_read": 0.30 / 1_000_000,
    "cache_write": 3.75 / 1_000_000,
}


def estimate_cost(tokens: TokenUsage) -> float:
    return (
        tokens.input * CLAUDE_PRICING["input"]
        + tokens.output * CLAUDE_PRICING["output"]
        + tokens.cache_read * CLAUDE_PRICING["cache_read"]
        + tokens.cache_write * CLAUDE_PRICING["cache_write"]
    )


@cli("sesh", description="session analytics")
def stats(
    provider: str | None = None,
    tokens: bool = False,
    forks: bool = False,
    by_day: bool = False,
    by_week: bool = False,
    by_month: bool = False,
):
    conn = connect()

    prov_clause = "WHERE provider = ?" if provider else ""
    prov_params: tuple = (provider,) if provider else ()

    total = conn.execute(f"SELECT COUNT(*) FROM sessions {prov_clause}", prov_params).fetchone()[0]  # noqa: S608
    if not total:
        echo("No sessions found")
        conn.close()
        return

    total_size = (
        conn.execute(f"SELECT SUM(size) FROM sessions {prov_clause}", prov_params).fetchone()[0]  # noqa: S608
        or 0
    )
    fork_count = conn.execute(
        f"SELECT COUNT(*) FROM sessions WHERE parent_session_id IS NOT NULL {('AND provider = ?' if provider else '')}",  # noqa: S608
        prov_params,
    ).fetchone()[0]

    echo(f"Sessions: {total:,} ({fork_count} forks)")
    echo(f"Size: {fmt_size(total_size)}")

    if tokens:
        row = conn.execute(
            f"SELECT SUM(input_tokens), SUM(output_tokens), SUM(cache_read), SUM(cache_create), SUM(cost_usd) FROM sessions {prov_clause}",  # noqa: S608
            prov_params,
        ).fetchone()
        echo(f"Tokens: {fmt_tokens(row[0] or 0)} in, {fmt_tokens(row[1] or 0)} out")
        echo(f"Cost: ${row[4] or 0:,.2f}")

    echo()
    echo("By provider:")
    for r in conn.execute(
        f"SELECT provider, COUNT(*) as cnt, SUM(size) as sz FROM sessions {prov_clause} GROUP BY provider ORDER BY cnt DESC",  # noqa: S608
        prov_params,
    ).fetchall():
        echo(f"  {r['provider']:<10} {r['cnt']:>6,} sessions    {fmt_size(r['sz'] or 0):>8}")

    echo()
    echo("Recent activity:")
    today = conn.execute(
        f"SELECT COUNT(*) FROM sessions WHERE date(created_at) = date('now') {('AND provider = ?' if provider else '')}",  # noqa: S608
        prov_params,
    ).fetchone()[0]
    week = conn.execute(
        f"SELECT COUNT(*) FROM sessions WHERE created_at > datetime('now', '-7 days') {('AND provider = ?' if provider else '')}",  # noqa: S608
        prov_params,
    ).fetchone()[0]
    month = conn.execute(
        f"SELECT COUNT(*) FROM sessions WHERE created_at > datetime('now', '-30 days') {('AND provider = ?' if provider else '')}",  # noqa: S608
        prov_params,
    ).fetchone()[0]
    echo(f"  Today:      {today:>5} sessions")
    echo(f"  This week:  {week:>5} sessions")
    echo(f"  This month: {month:>5} sessions")

    if by_day or by_week or by_month:
        if by_day:
            fmt, label = "%Y-%m-%d", "day"
        elif by_week:
            fmt, label = "%Y-W%W", "week"
        else:
            fmt, label = "%Y-%m", "month"
        echo()
        echo(f"By {label}:")
        rows = conn.execute(
            f"SELECT strftime('{fmt}', created_at) as bucket, COUNT(*) as cnt FROM sessions WHERE created_at IS NOT NULL {('AND provider = ?' if provider else '')} GROUP BY bucket ORDER BY bucket DESC LIMIT 20",  # noqa: S608
            prov_params,
        ).fetchall()
        for r in rows:
            echo(f"  {r['bucket']}: {r['cnt']:>5}")

    if forks:
        echo()
        rows = conn.execute(
            f"SELECT parent_session_id, COUNT(*) as cnt FROM sessions WHERE parent_session_id IS NOT NULL {('AND provider = ?' if provider else '')} GROUP BY parent_session_id ORDER BY cnt DESC LIMIT 15",  # noqa: S608
            prov_params,
        ).fetchall()
        echo(f"Forked sessions ({fork_count}):")
        for r in rows:
            echo(f"  {r['parent_session_id'][:36]}  ({r['cnt']} forks)")

    conn.close()
