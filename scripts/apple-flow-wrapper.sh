#!/bin/bash
# Apple Flow Launch Wrapper
# This wrapper script is used by launchd to start the daemon/admin service and
# ensures .env variables are exported into the process environment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODE="${1:-daemon}"
ENV_FILE="$PROJECT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

cd "$PROJECT_DIR"
exec "$PROJECT_DIR/.venv/bin/python" -m apple_flow "$MODE"
