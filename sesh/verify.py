import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from fncli import cli

from sesh.discover import _iter_provider_files, _session_key

echo = print


@dataclass
class Issue:
    key: str
    path: Path
    kind: str
    detail: str


@dataclass
class VerifyResult:
    total: int = 0
    ok: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.issues)


def verify_file(provider: str, jsonl: Path) -> list[Issue]:
    key = _session_key(provider, jsonl)
    issues: list[Issue] = []

    try:
        size = jsonl.stat().st_size
    except OSError as e:
        return [Issue(key=key, path=jsonl, kind="unreadable", detail=str(e))]

    if size == 0:
        return [Issue(key=key, path=jsonl, kind="empty", detail="0 bytes")]

    line_count = 0
    bad_lines = 0
    has_content = False

    try:
        with jsonl.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_count += 1
                try:
                    raw = json.loads(line)
                    if isinstance(raw, dict):
                        has_content = True
                    else:
                        bad_lines += 1
                except json.JSONDecodeError:
                    bad_lines += 1
    except Exception as e:
        issues.append(Issue(key=key, path=jsonl, kind="read_error", detail=str(e)))
        return issues

    if line_count == 0:
        issues.append(
            Issue(key=key, path=jsonl, kind="no_data", detail=f"{size} bytes, 0 JSON lines")
        )

    if bad_lines > 0:
        pct = 100 * bad_lines / max(line_count, 1)
        issues.append(
            Issue(
                key=key,
                path=jsonl,
                kind="corrupt_lines",
                detail=f"{bad_lines}/{line_count} lines ({pct:.0f}%) invalid JSON",
            )
        )

    if line_count > 0 and not has_content:
        issues.append(
            Issue(key=key, path=jsonl, kind="no_dict_lines", detail="no JSON objects found")
        )

    return issues


def verify_all(provider_filter: str | None = None) -> VerifyResult:
    result = VerifyResult()

    for provider, jsonl in _iter_provider_files():
        if provider_filter and provider != provider_filter:
            continue
        result.total += 1
        issues = verify_file(provider, jsonl)
        if issues:
            result.issues.extend(issues)
        else:
            result.ok += 1

    return result


@cli("sesh", description="verify session integrity")
def verify(provider: str | None = None, verbose: bool = False):
    echo("Verifying sessions...")
    result = verify_all(provider_filter=provider)

    echo()
    echo(f"Total: {result.total:,}")
    echo(f"OK: {result.ok:,}")
    echo(f"Issues: {result.failed}")

    if result.issues:
        echo()
        by_kind: dict[str, int] = {}
        for issue in result.issues:
            by_kind[issue.kind] = by_kind.get(issue.kind, 0) + 1

        for kind, count in sorted(by_kind.items(), key=lambda x: -x[1]):
            echo(f"  {kind}: {count}")

        if verbose:
            echo()
            for issue in result.issues[:50]:
                echo(f"  [{issue.kind}] {issue.key}: {issue.detail}")
            if len(result.issues) > 50:
                echo(f"  ... and {len(result.issues) - 50} more")

    if result.failed > 0:
        sys.exit(1)
