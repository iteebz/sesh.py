from collections import defaultdict
from datetime import datetime, timedelta

from fncli import cli

from sesh.discover import discover_sessions
from sesh.parse import TokenUsage, parse_session
from sesh.fmt import tokens as format_tokens
from sesh.stats import estimate_cost

echo = print


@cli("sesh", description="token burn by provider/day")
def tokens(
    provider: str | None = None,
    days: int = 30,
    by_day: bool = False,
    real: bool = False,
):
    files = discover_sessions(provider_filter=provider)
    if real:
        files = [f for f in files if f.is_real]

    cutoff = datetime.now().astimezone() - timedelta(days=days)

    by_provider: dict[str, TokenUsage] = defaultdict(TokenUsage)
    by_day_map: dict[str, TokenUsage] = defaultdict(TokenUsage)
    total = TokenUsage()
    parsed = 0

    for f in files:
        if datetime.fromtimestamp(f.mtime).astimezone() < cutoff:
            continue
        try:
            session = parse_session(f.path, f.provider)
        except Exception:  # noqa: S112
            continue

        t = session.tokens
        if t.input + t.output == 0:
            continue

        parsed += 1
        pt = by_provider[f.provider]
        pt.input += t.input
        pt.output += t.output
        pt.cache_read += t.cache_read
        pt.cache_write += t.cache_write

        total.input += t.input
        total.output += t.output
        total.cache_read += t.cache_read
        total.cache_write += t.cache_write

        if by_day:
            day = datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d")
            dt = by_day_map[day]
            dt.input += t.input
            dt.output += t.output
            dt.cache_read += t.cache_read
            dt.cache_write += t.cache_write

    if parsed == 0:
        echo(f"No token data found in the last {days} days")
        return

    echo(f"Token burn (last {days} days, {parsed:,} sessions with usage data)")
    echo()

    echo("By provider:")
    for prov in sorted(by_provider.keys()):
        t = by_provider[prov]
        cost = estimate_cost(t)
        echo(
            f"  {prov:<10}  in={format_tokens(t.input):>8}  out={format_tokens(t.output):>8}"
            f"  cache_r={format_tokens(t.cache_read):>8}  ${cost:,.2f}"
        )

    echo()
    cost = estimate_cost(total)
    echo(
        f"  {'TOTAL':<10}  in={format_tokens(total.input):>8}  out={format_tokens(total.output):>8}"
        f"  cache_r={format_tokens(total.cache_read):>8}  ${cost:,.2f}"
    )

    if by_day:
        echo()
        echo("By day (most recent first):")
        for day in sorted(by_day_map.keys(), reverse=True)[:days]:
            t = by_day_map[day]
            cost = estimate_cost(t)
            echo(
                f"  {day}  in={format_tokens(t.input):>8}  out={format_tokens(t.output):>8}  ${cost:,.2f}"
            )
