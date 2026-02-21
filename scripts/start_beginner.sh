#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Apple Flow Beginner Setup =="

# Helper: find a binary by name, checking common macOS install locations
find_binary() {
    local name="$1"
    local found
    found=$(command -v "$name" 2>/dev/null) && echo "$found" && return
    for dir in "$HOME/.local/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
        [ -x "$dir/$name" ] && echo "$dir/$name" && return
    done
    echo "$name"  # fallback: bare name
}

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
  cp .env.example .env
  echo "Created .env from .env.example"

  # Auto-detect CLI binary paths and patch .env
  CLAUDE_BIN=$(find_binary claude)
  CODEX_BIN=$(find_binary codex)
  sed -i '' "s|apple_flow_claude_cli_command=claude$|apple_flow_claude_cli_command=$CLAUDE_BIN|" .env
  sed -i '' "s|apple_flow_codex_cli_command=codex$|apple_flow_codex_cli_command=$CODEX_BIN|" .env
  echo "Auto-detected: claude → $CLAUDE_BIN"
  echo "Auto-detected: codex  → $CODEX_BIN"
fi

if grep -q "REPLACE_WITH_YOUR" .env; then
  echo
  echo "Please edit .env with your phone and workspace before first run."
  echo "Open: $ROOT_DIR/.env"
  exit 1
fi

ALLOWED_SENDERS_LINE="$(grep -E '^apple_flow_allowed_senders=' .env || true)"
ALLOWED_SENDERS_VALUE="${ALLOWED_SENDERS_LINE#apple_flow_allowed_senders=}"
if [[ -z "${ALLOWED_SENDERS_VALUE//[[:space:]]/}" ]]; then
  echo
  echo "Safety stop: apple_flow_allowed_senders is empty in .env"
  echo "Set your number first, e.g. apple_flow_allowed_senders=+15551234567"
  exit 1
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
