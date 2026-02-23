import json
import re
from pathlib import Path
from typing import Any

from fncli import cli

from sesh.discover import discover_sessions

echo = print


def search_file(path: Path, pattern: re.Pattern[str], context: int = 0) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    try:
        with path.open() as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if pattern.search(line):
                try:
                    event = json.loads(line.strip())
                    event_type = event.get("type", "unknown")

                    content = ""
                    msg = event.get("message", {})
                    if isinstance(msg, dict):
                        c = msg.get("content", "")
                        if isinstance(c, str):
                            content = c
                        elif isinstance(c, list):
                            for item in c:
                                if isinstance(item, dict) and item.get("type") == "text":
                                    content += item.get("text", "")

                    match_preview = pattern.search(content or line)
                    if match_preview:
                        start = max(0, match_preview.start() - 50)
                        end = min(len(content or line), match_preview.end() + 50)
                        preview = (content or line)[start:end].strip()
                    else:
                        preview = (content or line)[:100].strip()

                    matches.append(
                        {
                            "line": i + 1,
                            "type": event_type,
                            "preview": preview,
                        }
                    )
                except json.JSONDecodeError:
                    matches.append(
                        {
                            "line": i + 1,
                            "type": "raw",
                            "preview": line[:100].strip(),
                        }
                    )
    except Exception:  # noqa: S110
        pass

    return matches


@cli("sesh", description="search sessions by content")
def search(
    query: str,
    provider: str | None = None,
    limit: int = 20,
    context: int = 0,
    case_insensitive: bool = True,
):
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        pattern = re.compile(query, flags)
    except re.error as e:
        echo(f"Invalid regex: {e}")
        return

    sessions = discover_sessions(provider_filter=provider)

    if not sessions:
        echo("No sessions found")
        return

    total_matches = 0
    sessions_with_matches = 0

    for s in sessions:
        matches = search_file(s.path, pattern, context)
        if matches:
            sessions_with_matches += 1
            if total_matches < limit:
                echo(f"\n{s.provider}/{s.session_id[:20]}...")
                for m in matches[:3]:
                    echo(f"  L{m['line']:4} [{m['type']:10}] {m['preview'][:80]}")
                if len(matches) > 3:
                    echo(f"  ... and {len(matches) - 3} more matches")
            total_matches += len(matches)

    echo("\n---")
    echo(f"Found {total_matches} matches in {sessions_with_matches} sessions")
