from collections import Counter
from datetime import datetime, timedelta

from fncli import cli

from sesh.discover import discover_sessions

echo = print


@cli("sesh", description="activity timeline")
def timeline(weeks: int = 12, provider: str | None = None):
    files = discover_sessions(provider_filter=provider)

    if not files:
        echo("No sessions found")
        return

    now = datetime.now().astimezone()
    cutoff = now - timedelta(weeks=weeks)

    by_day: Counter[str] = Counter()
    by_hour: Counter[int] = Counter()
    by_provider: dict[str, Counter[str]] = {}

    for f in files:
        dt = f.created_at
        if dt < cutoff:
            continue

        day = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        by_day[day] += 1
        by_hour[hour] += 1

        if f.provider not in by_provider:
            by_provider[f.provider] = Counter()
        by_provider[f.provider][day] += 1

    if not by_day:
        echo("No sessions in the last {weeks} weeks")
        return

    max_per_day = max(by_day.values()) if by_day else 1
    days = sorted(by_day.keys())

    echo(f"Session Timeline (last {weeks} weeks)")
    echo()

    current_week: str | None = None
    for day in days:
        dt = datetime.strptime(day, "%Y-%m-%d")
        week = dt.strftime("%Y-W%W")

        if week != current_week:
            if current_week is not None:
                echo()
            current_week = week

        count = by_day[day]
        bar_len = int((count / max_per_day) * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        dow = dt.strftime("%a")
        echo(f"  {day} {dow} │{bar}│ {count:>3}")

    echo()
    echo("By hour of day:")
    max_per_hour = max(by_hour.values()) if by_hour else 1
    for hour in range(24):
        count = by_hour.get(hour, 0)
        bar_len = int((count / max_per_hour) * 20)
        bar = "█" * bar_len
        echo(f"  {hour:02d}:00 │{bar:<20}│ {count:>4}")

    if len(by_provider) > 1:
        echo()
        echo(f"By provider (last {weeks} weeks):")
        for prov in sorted(by_provider.keys()):
            total = sum(by_provider[prov].values())
            echo(f"  {prov:<10} {total:>5} sessions")
