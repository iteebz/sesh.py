import json
import sys

from fncli import cli

from sesh.discover import INDEX_PATH, SESSIONS_ROOT

echo = print


@cli("sesh", description="build session index")
def index():
    if not SESSIONS_ROOT.exists():
        echo("No sessions root found")
        return

    idx: dict[str, dict] = {}
    total = 0
    failed = 0

    for provider_dir in sorted(SESSIONS_ROOT.iterdir()):
        if not provider_dir.is_dir() or provider_dir.name.startswith("."):
            continue
        provider = provider_dir.name
        files = list(provider_dir.glob("*.jsonl"))
        echo(f"Indexing {provider} ({len(files):,} files)...")
        sys.stdout.flush()

        for jsonl in files:
            key = f"{provider}/{jsonl.stem}"
            created_at = None
            has_assistant = False
            line_count = 0
            try:
                with jsonl.open() as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        line_count += 1
                        raw = json.loads(line)
                        if created_at is None:
                            ts = raw.get("timestamp")
                            if ts:
                                created_at = ts
                        if not has_assistant and (
                            raw.get("type") == "assistant" or raw.get("role") == "assistant"
                        ):
                            has_assistant = True
            except Exception:
                failed += 1
            idx[key] = {
                "mtime": jsonl.stat().st_mtime,
                "size": jsonl.stat().st_size,
                "created_at": created_at,
                "has_assistant_turn": has_assistant,
                "line_count": line_count,
            }
            total += 1

    INDEX_PATH.write_text(json.dumps(idx))
    echo()
    echo(f"Indexed {total:,} sessions -> {INDEX_PATH}")
    if failed:
        echo(f"Failed: {failed}")
