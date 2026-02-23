default:
    @just --list

install:
    @uv sync
    @just hooks
    @just launchd

launchd:
    #!/bin/sh
    PLIST="com.iteebz.sesh-sync"
    SRC="$(pwd)/scripts/${PLIST}.plist"
    DEST="$HOME/Library/LaunchAgents/${PLIST}.plist"
    cp "$SRC" "$DEST"
    launchctl unload "$DEST" 2>/dev/null || true
    launchctl load "$DEST"
    echo "  sesh-sync agent loaded"

uninstall-launchd:
    #!/bin/sh
    PLIST="com.iteebz.sesh-sync"
    DEST="$HOME/Library/LaunchAgents/${PLIST}.plist"
    launchctl unload "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "  sesh-sync agent removed"

hooks:
    @cp scripts/hooks/pre-commit .git/hooks/pre-commit
    @chmod +x .git/hooks/pre-commit

lint:
    #!/bin/bash
    set -e
    uv run ruff format .
    uv run ruff check . --fix
    uv run pyright || true

ci: lint
    @uv run pytest tests --tb=short
    @uv run sesh selftest

test:
    @uv run pytest tests

build:
    @uv build

clean:
    @rm -rf dist build .pytest_cache .ruff_cache __pycache__ .venv
    @find . -type d -name "__pycache__" -exec rm -rf {} +

commits:
    @git --no-pager log --pretty=format:"%h | %ar | %s"
