from collections.abc import Sequence

from fncli import cli

from sesh.discover import discover_sessions
from sesh.fmt import size as format_size

echo = print


def percentile(data: Sequence[int | float], p: float) -> float:
    if not data:
        return 0
    s = sorted(data)
    idx = int(len(s) * p)
    return s[min(idx, len(s) - 1)]


def histogram(
    data: Sequence[int | float], buckets: list[tuple[str, float, float]], total: int
) -> None:
    for label, lo, hi in buckets:
        count = sum(1 for v in data if lo <= v < hi)
        bar_len = int((count / max(total, 1)) * 25)
        bar = "█" * bar_len
        pct = 100 * count / max(total, 1)
        echo(f"  {label:<18} │{bar:<25}│ {count:>6,}  ({pct:.1f}%)")


@cli("sesh", description="file size / line count distribution")
def distribution(provider: str | None = None, real: bool = False):
    files = discover_sessions(provider_filter=provider)
    if real:
        files = [f for f in files if f.is_real]

    if not files:
        echo("No sessions found")
        return

    sizes = [f.size for f in files]
    lines = [f.line_count for f in files]
    n = len(files)

    echo(f"Distribution ({n:,} sessions)")
    echo()

    echo("File size:")
    echo(f"  median  {format_size(int(percentile(sizes, 0.5)))}")
    echo(f"  p90     {format_size(int(percentile(sizes, 0.9)))}")
    echo(f"  p99     {format_size(int(percentile(sizes, 0.99)))}")
    echo(f"  max     {format_size(int(max(sizes)))}")
    echo(f"  total   {format_size(sum(sizes))}")
    echo()

    size_buckets: list[tuple[str, float, float]] = [
        ("<1K", 0, 1_024),
        ("1K-10K", 1_024, 10_240),
        ("10K-100K", 10_240, 102_400),
        ("100K-1M", 102_400, 1_048_576),
        ("1M+", 1_048_576, float("inf")),
    ]
    histogram(sizes, size_buckets, n)
    echo()

    echo("Line count:")
    echo(f"  median  {int(percentile(lines, 0.5))}")
    echo(f"  p90     {int(percentile(lines, 0.9))}")
    echo(f"  p99     {int(percentile(lines, 0.99))}")
    echo(f"  max     {max(lines)}")
    echo()

    line_buckets: list[tuple[str, float, float]] = [
        ("1-2 lines", 1, 3),
        ("3-10 lines", 3, 11),
        ("11-50 lines", 11, 51),
        ("51-200 lines", 51, 201),
        ("200+ lines", 201, float("inf")),
    ]
    histogram(lines, line_buckets, n)
