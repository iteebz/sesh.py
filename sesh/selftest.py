import json
import sys
import tempfile
from pathlib import Path

from fncli import cli

from sesh.discover import SESSIONS_ROOT, _iter_provider_files, discover_sessions
from sesh.parse import parse_session
from sesh.search import search_file

echo = print

SAMPLE_SESSION = [
    {"type": "system", "timestamp": "2025-01-01T00:00:00Z", "sessionId": "test-000"},
    {
        "type": "user",
        "timestamp": "2025-01-01T00:00:01Z",
        "role": "user",
        "message": {"role": "user", "content": "hello"},
    },
    {
        "type": "assistant",
        "timestamp": "2025-01-01T00:00:02Z",
        "role": "assistant",
        "message": {"role": "assistant", "content": "hi there"},
    },
]


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "ok" if ok else "FAIL"
    msg = f"  {name}: {status}"
    if detail:
        msg += f"  ({detail})"
    echo(msg)
    return ok


@cli("sesh", description="end-to-end pipeline self-test")
def selftest():
    echo("sesh selftest")
    echo()
    passed = 0
    failed = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if _check(name, ok, detail):
            passed += 1
        else:
            failed += 1

    check("sessions_root", SESSIONS_ROOT.exists(), str(SESSIONS_ROOT))

    files = _iter_provider_files()
    check("files_discoverable", len(files) > 0, f"{len(files)} files")

    sessions = discover_sessions()
    check("discover_works", len(sessions) > 0, f"{len(sessions)} sessions")

    if sessions:
        sample = sessions[0]
        try:
            parsed = parse_session(sample.path, sample.provider)
            check("parse_works", len(parsed.events) > 0, f"{len(parsed.events)} events")
        except Exception as e:
            check("parse_works", False, str(e))

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.jsonl"
        test_file.write_text("\n".join(json.dumps(e) for e in SAMPLE_SESSION) + "\n")

        parsed = parse_session(test_file, "test")
        check("parse_synthetic", parsed.session_id == "test-000", parsed.session_id)
        check("parse_messages", len(parsed.messages) == 2, f"{len(parsed.messages)} messages")
        check(
            "parse_roles",
            parsed.user_messages[0].content == "hello"
            and parsed.assistant_messages[0].content == "hi there",
        )

        import re

        matches = search_file(test_file, re.compile("hello"))
        check("search_works", len(matches) > 0, f"{len(matches)} matches")

    providers = {p for p, _ in files}
    check("multi_provider", len(providers) > 1, ", ".join(sorted(providers)))

    echo()
    echo(f"passed: {passed}  failed: {failed}")
    if failed:
        sys.exit(1)
