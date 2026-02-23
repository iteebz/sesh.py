from fncli import cli

from sesh.discover import SessionFile, discover_sessions
from sesh.parse import parse_session

echo = print


def find_session(session_id: str) -> SessionFile | None:
    for s in discover_sessions():
        if s.session_id == session_id or s.session_id.startswith(session_id):
            return s
    return None


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


@cli("sesh", name="show", description="inspect a session")
def run(session_id: str, raw: bool = False, events: bool = False):
    sf = find_session(session_id)
    if not sf:
        echo(f"Session not found: {session_id}")
        return

    if raw:
        with sf.path.open() as f:
            echo(f.read())
        return

    session = parse_session(sf.path, sf.provider)

    echo(f"Session: {session.session_id}")
    echo(f"Provider: {session.provider}")
    echo(f"Path: {session.path}")
    if session.cwd:
        echo(f"CWD: {session.cwd}")
    if session.model:
        echo(f"Model: {session.model}")
    if session.first_timestamp:
        echo(f"Started: {session.first_timestamp}")
    if session.last_timestamp:
        echo(f"Ended: {session.last_timestamp}")

    echo(f"\nEvents: {len(session.events)}")
    echo(
        f"Messages: {len(session.messages)} "
        f"({len(session.user_messages)} user, {len(session.assistant_messages)} assistant)"
    )

    if events:
        echo("\n--- Events ---")
        for i, event in enumerate(session.events):
            ts = event.timestamp or ""
            echo(f"{i:4} | {event.type:<15} | {ts[:19]}")
    else:
        echo("\n--- Conversation ---")
        for event in session.messages:
            role = event.role.upper() if event.role else "?"
            content = event.content or "(no content)"
            content = truncate(content, 500)
            echo(f"\n[{role}]")
            echo(content)
