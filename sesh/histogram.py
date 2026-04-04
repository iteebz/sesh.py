from fncli import cli

from sesh.db import connect

echo = print


@cli("sesh", description="session count per day as a chart")
def histogram(
    days: int = 30,
    model: str | None = None,
    provider: str | None = None,
    width: int = 50,
):
    conn = connect()
    clauses = ["created_at IS NOT NULL", "created_at > datetime('now', ?)"]
    params: list[object] = [f"-{days} days"]

    if model:
        clauses.append("model LIKE ?")
        params.append(f"%{model}%")
    if provider:
        clauses.append("provider = ?")
        params.append(provider)

    where = " AND ".join(clauses)
    rows = conn.execute(
        f"""SELECT date(created_at) as day, COUNT(*) as cnt
            FROM sessions
            WHERE {where}
            GROUP BY day ORDER BY day""",  # noqa: S608
        params,
    ).fetchall()
    conn.close()

    if not rows:
        echo("No sessions found")
        return

    max_count = max(r["cnt"] for r in rows)
    total = sum(r["cnt"] for r in rows)

    for row in rows:
        day = row["day"]
        cnt = row["cnt"]
        bar_len = int((cnt / max_count) * width) if max_count else 0
        bar = "█" * bar_len
        echo(f"{day}  {bar} {cnt}")

    echo(f"\n{total} sessions over {len(rows)} days (avg {total // max(len(rows), 1)}/day)")
