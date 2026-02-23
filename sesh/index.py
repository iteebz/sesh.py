import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fncli import cli

from sesh.discover import INDEX_PATH, SESSIONS_ROOT, IndexEntry

WORKERS = 16
BAR_WIDTH = 30


def _render_bar(done: int, total: int, width: int = BAR_WIDTH) -> str:
    frac = done / total if total else 0
    filled = int(frac * width)
    return "█" * filled + "░" * (width - filled)


def _index_file(jsonl: Path, provider: str) -> tuple[str, IndexEntry]:
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
    except Exception:  # noqa: S110
        pass
    return key, {
        "mtime": jsonl.stat().st_mtime,
        "size": jsonl.stat().st_size,
        "created_at": created_at,
        "has_assistant_turn": has_assistant,
        "line_count": line_count,
    }


@cli("sesh", description="build session index")
def index():
    if not SESSIONS_ROOT.exists():
        print("No sessions root found")
        return

    providers: list[tuple[str, list[Path]]] = []
    for provider_dir in sorted(SESSIONS_ROOT.iterdir()):
        if not provider_dir.is_dir() or provider_dir.name.startswith("."):
            continue
        files = list(provider_dir.glob("*.jsonl"))
        if files:
            providers.append((provider_dir.name, files))

    all_files: list[tuple[Path, str]] = [
        (f, provider) for provider, files in providers for f in files
    ]
    total = len(all_files)

    provider_totals = {p: len(files) for p, files in providers}
    provider_done: dict[str, int] = {p: 0 for p, _ in providers}
    done = 0
    lock = threading.Lock()
    idx: dict[str, IndexEntry] = {}

    provider_labels = "  ".join(f"{p}({n:,})" for p, n in provider_totals.items())
    sys.stdout.write(f"Indexing {provider_labels}\n")

    def _progress() -> None:
        bar = _render_bar(done, total)
        provider_status = "  ".join(
            f"{p} {provider_done[p]:,}/{provider_totals[p]:,}" for p, _ in providers
        )
        sys.stdout.write(f"\r  [{bar}] {done:,}/{total:,}  {provider_status}  ")
        sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_index_file, f, p): p for f, p in all_files}
        for future in as_completed(futures):
            provider = futures[future]
            key, entry = future.result()
            with lock:
                idx[key] = entry
                done += 1
                provider_done[provider] += 1
                if done % 100 == 0 or done == total:
                    _progress()

    sys.stdout.write("\n")
    INDEX_PATH.write_text(json.dumps(idx))
    print(f"Indexed {total:,} sessions -> {INDEX_PATH}")
