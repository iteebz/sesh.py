from atail import StreamParser, format_entry, strip
from fncli import cli

from sesh.discover import discover_sessions


def _find_session_path(session_id: str):
    for s in discover_sessions():
        if s.session_id == session_id or s.session_id.startswith(session_id):
            return s.path
    return None


@cli("sesh", description="render a session with full color formatting")
def tail(session_id: str):
    path = _find_session_path(session_id)
    if not path:
        print(f"Session not found: {session_id}")
        return

    parser = StreamParser()
    last_rendered: str | None = None

    with path.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            for entry in parser.parse_line(line):
                rendered = format_entry(entry, quiet_system=True)
                if not rendered:
                    continue
                rendered_plain = strip(rendered).strip()
                if rendered == last_rendered and rendered_plain.startswith(("error.", "in=")):
                    continue
                print(rendered)
                last_rendered = rendered

    for entry in parser.flush():
        rendered = format_entry(entry, quiet_system=True)
        if rendered:
            print(rendered)
