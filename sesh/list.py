from datetime import datetime

from fncli import cli

from sesh.discover import discover_sessions

echo = print


@cli("sesh", name="list", description="list sessions with filters")
def list_(
    model: str | None = None,
    provider: str | None = None,
    days: int | None = None,
    real: bool = False,
    n: int = 20,
):
    sessions = discover_sessions(
        provider_filter=provider,
        model_filter=model,
        limit=n,
        real_only=real,
        days=days,
    )

    if not sessions:
        echo("No sessions found")
        return

    for s in sessions:
        dt = datetime.fromtimestamp(s.mtime).strftime("%Y-%m-%d %H:%M")
        m = s.model or "?"
        short_model = m.split("/")[-1]
        if len(short_model) > 30:
            short_model = short_model[:30]
        echo(
            f"{dt}  {s.provider:<7} {short_model:<32} {s.session_id[:12]}  {s.line_count:>5} lines"
        )
