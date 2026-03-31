import sys

from fncli import cli

from sesh.db import connect

echo = print

CHART_WIDTH = 60
CHART_HEIGHT = 12

_BRAILLE_BASE = 0x2800
_DOT_MAP = [
    [0x01, 0x08],  # row 0
    [0x02, 0x10],  # row 1
    [0x04, 0x20],  # row 2
    [0x40, 0x80],  # row 3
]

# Purple → pink gradient (matches ccmeter/sesh display.py)
_GRAD_START = (140, 120, 220)
_GRAD_END = (210, 140, 190)
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _grad(i: int, width: int) -> str:
    t = i / max(width - 1, 1)
    r = int(_GRAD_START[0] + (_GRAD_END[0] - _GRAD_START[0]) * t)
    g = int(_GRAD_START[1] + (_GRAD_END[1] - _GRAD_START[1]) * t)
    b = int(_GRAD_START[2] + (_GRAD_END[2] - _GRAD_START[2]) * t)
    return f"\033[38;2;{r};{g};{b}m"


def _braille(values: list[float], width: int = CHART_WIDTH, height: int = CHART_HEIGHT) -> list[str]:
    if not values:
        return []

    lo, hi = min(values), max(values)
    span = hi - lo if hi > lo else 1.0
    dot_w = width * 2
    dot_h = height * 4

    n = len(values)
    points: list[int] = []
    for i in range(dot_w):
        t = i / max(dot_w - 1, 1) * (n - 1)
        lo_idx = int(t)
        hi_idx = min(lo_idx + 1, n - 1)
        frac = t - lo_idx
        v = values[lo_idx] * (1 - frac) + values[hi_idx] * frac
        y = int((v - lo) / span * (dot_h - 1) + 0.5)
        points.append(y)

    grid: set[tuple[int, int]] = set()
    for i in range(len(points)):
        grid.add((i, points[i]))
        if i > 0:
            y0, y1 = points[i - 1], points[i]
            steps = max(abs(y1 - y0), 1)
            for s in range(steps + 1):
                t = s / steps
                y = int(y0 + (y1 - y0) * t + 0.5)
                x = int((i - 1) + t + 0.5)
                grid.add((x, y))

    tty = sys.stdout.isatty()
    rows = []
    for row in range(height):
        chars = []
        for col in range(width):
            code = _BRAILLE_BASE
            for dr in range(4):
                for dc in range(2):
                    dx = col * 2 + dc
                    dy = (height - 1 - row) * 4 + (3 - dr)
                    if (dx, dy) in grid:
                        code |= _DOT_MAP[dr][dc]
            if tty:
                chars.append(f"{_grad(col, width)}{chr(code)}{RESET}")
            else:
                chars.append(chr(code))
        rows.append("".join(chars))
    return rows


@cli("sesh", description="braille chart of sessions over time")
def trend(
    days: int = 90,
    model: str | None = None,
    provider: str | None = None,
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
            GROUP BY day ORDER BY day""",
        params,
    ).fetchall()
    conn.close()

    if not rows:
        echo("No sessions found")
        return

    values = [float(r["cnt"]) for r in rows]
    days_list = [r["day"] for r in rows]
    total = sum(values)
    peak = max(values)
    avg = total / len(values)

    # Clip outliers at p95 for chart rendering so spikes don't flatten everything
    sorted_vals = sorted(values)
    p95 = sorted_vals[int(len(sorted_vals) * 0.95)]
    chart_values = [min(v, p95) for v in values] if peak > p95 * 2 else values
    chart_ceiling = p95 if peak > p95 * 2 else peak

    tty = sys.stdout.isatty()
    dim = DIM if tty else ""
    bold = BOLD if tty else ""
    reset = RESET if tty else ""

    label = "sessions"
    if model:
        label = f"{model} sessions"
    echo()
    echo(f"  {bold}{label}{reset}  {dim}{len(days_list)}d  avg {avg:.0f}/day  peak {peak:.0f}{reset}")
    echo()

    chart = _braille(chart_values)
    for i, row in enumerate(chart):
        label = ""
        if i == 0:
            label = f" {dim}{chart_ceiling:.0f}{reset}"
        elif i == len(chart) - 1:
            label = f" {dim}{min(values):.0f}{reset}"
        echo(f"    {row}{label}")

    padding = CHART_WIDTH - len(days_list[0][5:]) - len(days_list[-1][5:])
    echo(f"    {dim}{days_list[0][5:]}{' ' * max(padding, 1)}{days_list[-1][5:]}{reset}")
    echo()
    echo(f"  {dim}{int(total):,} total{reset}")
