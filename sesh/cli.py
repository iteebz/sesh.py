"""Sessions CLI — sync and analyze LLM session traces."""

import argparse

from . import analyze as analyze_cmd
from . import export as export_cmd
from . import health as health_cmd
from . import search as search_cmd
from . import show as show_cmd
from . import stats as stats_cmd
from . import sync as sync_cmd
from . import timeline as timeline_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sesh",
        description="Sync and analyze LLM session traces",
    )
    subs = parser.add_subparsers(dest="cmd", help="command")

    sync_p = subs.add_parser("sync", help="sync sessions from native paths")
    sync_p.add_argument("--dry-run", action="store_true", help="show what would be synced")

    stats_p = subs.add_parser("stats", help="session analytics")
    stats_p.add_argument("--provider", "-p", help="filter by provider")
    stats_p.add_argument("--tokens", "-t", action="store_true", help="include token usage")
    stats_p.add_argument("--forks", "-f", action="store_true", help="show forked sessions")
    stats_p.add_argument("--by-day", action="store_true", help="breakdown by day")
    stats_p.add_argument("--by-week", action="store_true", help="breakdown by week")
    stats_p.add_argument("--by-month", action="store_true", help="breakdown by month")

    search_p = subs.add_parser("search", help="search sessions by content")
    search_p.add_argument("query", help="search pattern (regex)")
    search_p.add_argument("--provider", "-p", help="filter by provider")
    search_p.add_argument("--limit", "-n", type=int, default=20, help="max results")
    search_p.add_argument("-i", action="store_true", help="case sensitive")

    show_p = subs.add_parser("show", help="inspect a session")
    show_p.add_argument("session_id", help="session ID (or prefix)")
    show_p.add_argument("--raw", action="store_true", help="show raw JSONL")
    show_p.add_argument("--events", action="store_true", help="show event timeline")

    export_p = subs.add_parser("export", help="export session to file")
    export_p.add_argument("session_id", help="session ID (or prefix)")
    export_p.add_argument("--format", "-f", choices=["markdown", "text"], default="markdown")
    export_p.add_argument("--output", "-o", help="output file (stdout if not specified)")

    timeline_p = subs.add_parser("timeline", help="activity timeline")
    timeline_p.add_argument("--weeks", "-w", type=int, default=12, help="weeks to show")
    timeline_p.add_argument("--provider", "-p", help="filter by provider")

    analyze_p = subs.add_parser("analyze", help="analyze prompting patterns")
    analyze_p.add_argument("--provider", "-p", help="filter by provider")
    analyze_p.add_argument("--limit", "-n", type=int, help="limit sessions to analyze")

    subs.add_parser("health", help="health score")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.cmd:
        stats_cmd.run()
        return

    if args.cmd == "sync":
        sync_cmd.run(dry_run=args.dry_run)
    elif args.cmd == "stats":
        stats_cmd.run(
            provider=args.provider,
            tokens=args.tokens,
            forks=args.forks,
            by_day=args.by_day,
            by_week=args.by_week,
            by_month=args.by_month,
        )
    elif args.cmd == "search":
        search_cmd.run(
            args.query,
            provider=args.provider,
            limit=args.limit,
            case_insensitive=not args.i,
        )
    elif args.cmd == "show":
        show_cmd.run(args.session_id, raw=args.raw, events=args.events)
    elif args.cmd == "export":
        export_cmd.run(args.session_id, format=args.format, output=args.output)
    elif args.cmd == "timeline":
        timeline_cmd.run(weeks=args.weeks, provider=args.provider)
    elif args.cmd == "analyze":
        analyze_cmd.run(provider=args.provider, limit=args.limit)
    elif args.cmd == "health":
        health_cmd.cli()
