#!/bin/bash
# Codex Relay Launch Wrapper
# This wrapper script is used by launchd to start the daemon

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m codex_relay daemon
