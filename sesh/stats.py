from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sesh.discover import SessionFile, discover_sessions
from sesh.parse import TokenUsage, parse_session

echo = print

CLAUDE_PRICING = {
    "input": 3.00 / 1_000_000,
    "output": 15.00 / 1_000_000,
    "cache_read": 0.30 / 1_000_000,
    "cache_write": 3.75 / 1_000_000,
}


def format_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n / 1_000_000_000:.1f}B"


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}K"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}M"
    return f"{size / (1024 * 1024 * 1024):.1f}G"


def estimate_cost(tokens: TokenUsage) -> float:
    return (
        tokens.input * CLAUDE_PRICING["input"]
        + tokens.output * CLAUDE_PRICING["output"]
        + tokens.cache_read * CLAUDE_PRICING["cache_read"]
        + tokens.cache_write * CLAUDE_PRICING["cache_write"]
    )


def run(
    provider: str | None = None,
    tokens: bool = False,
    forks: bool = False,
    by_day: bool = False,
    by_week: bool = False,
    by_month: bool = False,
):
    files = discover_sessions(provider_filter=provider)

    if not files:
        echo("No sessions found")
        return

    session_ids: dict[str, list[SessionFile]] = defaultdict(list)
    provider_counts: Counter[str] = Counter()
    provider_sizes: Counter[str] = Counter()
    provider_tokens: dict[str, TokenUsage] = defaultdict(TokenUsage)
    time_buckets: Counter[str] = Counter()

    total_size = 0
    now = datetime.now()

    for f in files:
        session = parse_session(f.path, f.provider)
        session_ids[session.session_id].append(f)

        provider_counts[f.provider] += 1
        provider_sizes[f.provider] += f.size
        total_size += f.size

        if tokens:
            pt = provider_tokens[f.provider]
            pt.input += session.tokens.input
            pt.output += session.tokens.output
            pt.cache_read += session.tokens.cache_read
            pt.cache_write += session.tokens.cache_write

        if by_day or by_week or by_month:
            dt = datetime.fromtimestamp(f.mtime)
            if by_day:
                bucket = dt.strftime("%Y-%m-%d")
            elif by_week:
                bucket = dt.strftime("%Y-W%W")
            else:
                bucket = dt.strftime("%Y-%m")
            time_buckets[bucket] += 1

    unique_sessions = len(session_ids)
    total_files = len(files)
    forked_sessions = [(sid, fs) for sid, fs in session_ids.items() if len(fs) > 1]
    fork_count = len(forked_sessions)

    today = sum(1 for f in files if datetime.fromtimestamp(f.mtime).date() == now.date())
    this_week = sum(1 for f in files if datetime.fromtimestamp(f.mtime) > now - timedelta(days=7))
    this_month = sum(1 for f in files if datetime.fromtimestamp(f.mtime) > now - timedelta(days=30))

    echo(f"Sessions: {unique_sessions:,} unique ({total_files:,} files, {fork_count} forks)")
    echo(f"Size: {format_size(total_size)}")

    if tokens:
        totals = TokenUsage(
            input=sum(t.input for t in provider_tokens.values()),
            output=sum(t.output for t in provider_tokens.values()),
            cache_read=sum(t.cache_read for t in provider_tokens.values()),
            cache_write=sum(t.cache_write for t in provider_tokens.values()),
        )
        cost = estimate_cost(totals)
        echo(f"Tokens: {format_tokens(totals.input)} in, {format_tokens(totals.output)} out")
        echo(f"Cost: ${cost:,.2f} (Claude pricing)")

    echo()
    echo("By provider:")
    for prov in sorted(provider_counts.keys()):
        unique_for_prov = sum(1 for _, fs in session_ids.items() if fs[0].provider == prov)
        size = format_size(provider_sizes[prov])
        echo(f"  {prov:<10} {unique_for_prov:>6,} sessions    {size:>8}")

    echo()
    echo("Recent activity:")
    echo(f"  Today:      {today:>5} sessions")
    echo(f"  This week:  {this_week:>5} sessions")
    echo(f"  This month: {this_month:>5} sessions")

    if by_day or by_week or by_month:
        echo()
        label = "day" if by_day else ("week" if by_week else "month")
        echo(f"By {label}:")
        for bucket in sorted(time_buckets.keys(), reverse=True)[:20]:
            echo(f"  {bucket}: {time_buckets[bucket]:>5}")

    if forks:
        echo()
        echo(f"Forked sessions ({fork_count}):")
        for sid, fs in sorted(forked_sessions, key=lambda x: -len(x[1]))[:15]:
            echo(f"  {sid[:36]}  ({len(fs)} files)")
            for sf in fs[:3]:
                echo(f"    └─ {sf.path.name[:50]}")
            if len(fs) > 3:
                echo(f"    ... and {len(fs) - 3} more")
