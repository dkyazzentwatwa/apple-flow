#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Apple Flow Beginner Setup =="

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

if pgrep -f "apple_flow daemon" >/dev/null 2>&1; then
  echo
  echo "Stopping existing Apple Flow daemon process..."
  pkill -f "apple_flow daemon" || true
  sleep 1
fi

LOCK_PATH="$HOME/.apple-flow/relay.daemon.lock"
if [[ -f "$LOCK_PATH" ]] && ! pgrep -f "apple_flow daemon" >/dev/null 2>&1; then
  echo "Removing stale daemon lock: $LOCK_PATH"
  rm -f "$LOCK_PATH"
fi

echo "Installing dependencies..."
pip install -e '.[dev]' >/dev/null

if [[ ! -f ".env" ]]; then
  echo "No .env found. Running setup wizard..."
  .venv/bin/python -m apple_flow setup
  if [[ ! -f ".env" ]]; then
    echo "Setup wizard did not create .env. Exiting."
    exit 1
  fi
fi

MESSAGES_DB_LINE="$(grep -E '^apple_flow_messages_db_path=' .env || true)"
MESSAGES_DB_PATH="${MESSAGES_DB_LINE#apple_flow_messages_db_path=}"
if [[ -z "${MESSAGES_DB_PATH//[[:space:]]/}" ]]; then
  MESSAGES_DB_PATH="$HOME/Library/Messages/chat.db"
fi
if [[ ! -f "$MESSAGES_DB_PATH" ]]; then
  echo
  echo "Safety stop: Messages DB not found at: $MESSAGES_DB_PATH"
  echo "Update apple_flow_messages_db_path in .env"
  exit 1
fi

if ! sqlite3 "$MESSAGES_DB_PATH" "select 1;" >/dev/null 2>&1; then
  echo
  echo "Safety stop: cannot read Messages DB at: $MESSAGES_DB_PATH"
  echo "Grant Full Disk Access to the app hosting this shell (Terminal/iTerm/Codex),"
  echo "then fully quit and reopen that app before retrying."
  exit 1
fi

echo "Running tests..."
pytest -q

echo

echo "Starting Apple Flow daemon..."
echo "Foreground mode: this stays running and waits for iMessages. Press Ctrl+C to stop."
python -m apple_flow daemon
