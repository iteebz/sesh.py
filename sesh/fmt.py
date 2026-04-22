"""Shared formatting utilities."""

from datetime import UTC, datetime


def ago(ts: float | str) -> str:
    """Relative time from a unix timestamp or ISO string."""
    if isinstance(ts, str):
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        secs = int((datetime.now(tz=UTC) - dt).total_seconds())
    else:
        secs = int(datetime.now().timestamp() - ts)
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / (1024 * 1024):.1f}M"


def tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}K"
    return f"{n / 1_000_000:.1f}M"
