import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fncli import cli

from sesh import discover

echo = print


@dataclass
class CheckResult:
    ok: bool
    score: int
    detail: str


def _check_ci() -> CheckResult:
    just_bin = shutil.which("just")
    if not just_bin:
        return CheckResult(ok=False, score=0, detail="just not found")
    result = subprocess.run(
        [just_bin, "ci"],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if result.returncode != 0:
        return CheckResult(ok=False, score=0, detail=f"CI failed: {result.returncode}")
    return CheckResult(ok=True, score=100, detail="CI passed")


def _check_session_sources() -> CheckResult:
    sources = [
        Path.home() / ".space" / "traces",
        Path.home() / ".engine" / "traces",
        Path.home() / "Library" / "Application Support" / "Claude" / "projects",
        Path.home() / ".codex" / "sessions",
    ]
    existing = [s for s in sources if s.exists()]
    if not existing:
        return CheckResult(ok=False, score=0, detail="no session sources found")
    return CheckResult(ok=True, score=100, detail=f"{len(existing)}/{len(sources)} sources exist")


def _check_sessions_exist() -> CheckResult:
    sessions = discover.discover_sessions()
    if not sessions:
        return CheckResult(ok=False, score=0, detail="no sessions found")
    return CheckResult(ok=True, score=100, detail=f"{len(sessions)} sessions found")


_CHECKS: list[tuple[str, Callable[[], CheckResult], int]] = [
    ("ci", _check_ci, 50),
    ("sources", _check_session_sources, 30),
    ("sessions", _check_sessions_exist, 20),
]


def score() -> dict[str, Any]:
    results: dict[str, CheckResult] = {}
    total_weight = sum(w for _, _, w in _CHECKS)
    weighted_score = 0

    for name, check_fn, weight in _CHECKS:
        result = check_fn()
        results[name] = result
        weighted_score += (result.score / 100) * weight

    final_score = int((weighted_score / total_weight) * 100)
    all_ok = all(r.ok for r in results.values())

    return {
        "ok": all_ok,
        "score": final_score,
        "checks": {name: {"ok": r.ok, "detail": r.detail} for name, r in results.items()},
    }


@cli("sesh", description="health score")
def health() -> None:
    result = score()
    echo(f"health: {result['score']}/100 {'✓' if result['ok'] else '✗'}")
    for name, check in result["checks"].items():
        status = "✓" if check["ok"] else "✗"
        echo(f"  {name}: {status} {check['detail']}")
    if not result["ok"]:
        raise SystemExit(1)
