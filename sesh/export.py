from pathlib import Path

from sesh.discover import SessionFile, discover_sessions
from sesh.parse import Session, parse_session

echo = print


def find_session(session_id: str) -> SessionFile | None:
    for s in discover_sessions():
        if s.session_id == session_id or s.session_id.startswith(session_id):
            return s
    return None


def export_markdown(session: Session) -> str:
    lines = []
    lines.append(f"# Session: {session.session_id}")
    lines.append("")
    lines.append(f"- **Provider:** {session.provider}")
    if session.cwd:
        lines.append(f"- **CWD:** {session.cwd}")
    if session.model:
        lines.append(f"- **Model:** {session.model}")
    if session.first_timestamp:
        lines.append(f"- **Started:** {session.first_timestamp}")
    if session.last_timestamp:
        lines.append(f"- **Ended:** {session.last_timestamp}")
    lines.append(f"- **Messages:** {len(session.messages)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for event in session.messages:
        role = event.role or "unknown"
        content = event.content or "(no content)"
        ts = f" ({event.timestamp[:19]})" if event.timestamp else ""

        if role == "user":
            lines.append(f"## User{ts}")
        else:
            lines.append(f"## Assistant{ts}")

        lines.append("")
        lines.append(content)
        lines.append("")

    return "\n".join(lines)


def export_text(session: Session) -> str:
    lines = []
    lines.append(f"Session: {session.session_id}")
    lines.append(f"Provider: {session.provider}")
    if session.cwd:
        lines.append(f"CWD: {session.cwd}")
    if session.model:
        lines.append(f"Model: {session.model}")
    if session.first_timestamp:
        lines.append(f"Started: {session.first_timestamp}")
    if session.last_timestamp:
        lines.append(f"Ended: {session.last_timestamp}")
    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    for event in session.messages:
        role = (event.role or "unknown").upper()
        content = event.content or "(no content)"
        ts = f" [{event.timestamp[:19]}]" if event.timestamp else ""

        lines.append(f"[{role}]{ts}")
        lines.append(content)
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    return "\n".join(lines)


def run(session_id: str, format: str = "markdown", output: str | None = None):
    sf = find_session(session_id)
    if not sf:
        echo(f"Session not found: {session_id}")
        return

    session = parse_session(sf.path, sf.provider)

    if format == "markdown":
        content = export_markdown(session)
    elif format == "text":
        content = export_text(session)
    else:
        echo(f"Unknown format: {format}")
        return

    if output:
        Path(output).write_text(content)
        echo(f"Exported to {output}")
    else:
        echo(content)
