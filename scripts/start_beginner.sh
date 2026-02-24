#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$ROOT_DIR/.env"

resolve_binary() {
  local name="$1"
  local found
  if found="$(command -v "$name" 2>/dev/null)"; then
    printf '%s\n' "$found"
    return 0
  fi
  for dir in "$HOME/.local/bin" "/opt/homebrew/bin" "/usr/local/bin"; do
    if [[ -x "$dir/$name" ]]; then
      printf '%s\n' "$dir/$name"
      return 0
    fi
  done
  return 1
}

env_get() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n 1 || true)"
  printf '%s' "${line#*=}"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')"
  if grep -q -E "^${key}=" "$ENV_FILE"; then
    sed -i '' "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

expand_path() {
  local value="$1"
  if [[ "$value" == ~/* ]]; then
    printf '%s\n' "$HOME/${value#~/}"
    return 0
  fi
  printf '%s\n' "$value"
}

pin_selected_connector_binary() {
  local connector
  local key
  local default_cmd
  local current_cmd
  local binary
  local resolved

  connector="$(env_get apple_flow_connector)"
  if [[ -z "${connector//[[:space:]]/}" ]]; then
    local use_codex_cli
    use_codex_cli="$(env_get apple_flow_use_codex_cli)"
    if [[ "${use_codex_cli,,}" == "false" ]]; then
      connector="codex-app-server"
    else
      connector="codex-cli"
    fi
  fi

  case "$connector" in
    claude-cli)
      key="apple_flow_claude_cli_command"
      default_cmd="claude"
      ;;
    codex-cli)
      key="apple_flow_codex_cli_command"
      default_cmd="codex"
      ;;
    cline)
      key="apple_flow_cline_command"
      default_cmd="cline"
      ;;
    codex-app-server)
      key="apple_flow_codex_app_server_cmd"
      default_cmd="codex app-server"
      ;;
    *)
      echo "❌ Unsupported connector in .env: $connector"
      exit 1
      ;;
  esac

  current_cmd="$(env_get "$key")"
  if [[ -z "${current_cmd//[[:space:]]/}" ]]; then
    current_cmd="$default_cmd"
  fi

  binary="${current_cmd%% *}"
  resolved=""
  if [[ "$binary" = /* && -x "$binary" ]]; then
    resolved="$binary"
  elif resolved="$(resolve_binary "$binary" 2>/dev/null || true)"; then
    :
  fi

  if [[ -z "$resolved" ]]; then
    echo "❌ Could not resolve connector binary for '$connector' (expected '$binary')."
    exit 1
  fi

  if [[ "$connector" == "codex-app-server" ]]; then
    local rest
    rest="${current_cmd#"$binary"}"
    set_env_value "$key" "$resolved$rest"
    SELECTED_CONNECTOR_COMMAND="$resolved$rest"
  else
    set_env_value "$key" "$resolved"
    SELECTED_CONNECTOR_COMMAND="$resolved"
  fi

  SELECTED_CONNECTOR="$connector"
  export SELECTED_CONNECTOR SELECTED_CONNECTOR_COMMAND
  echo "✓ Pinned connector command ($key)"
}

run_fast_readiness_checks() {
  local senders
  local workspaces
  local messages_db

  senders="$(env_get apple_flow_allowed_senders)"
  workspaces="$(env_get apple_flow_allowed_workspaces)"
  if [[ -z "${senders//[[:space:]]/}" || "$senders" == *"REPLACE_WITH"* ]]; then
    echo "❌ apple_flow_allowed_senders is missing in .env"
    exit 1
  fi
  if [[ -z "${workspaces//[[:space:]]/}" || "$workspaces" == *"REPLACE_WITH"* ]]; then
    echo "❌ apple_flow_allowed_workspaces is missing in .env"
    exit 1
  fi

  IFS=',' read -r -a workspace_array <<< "$workspaces"
  for workspace in "${workspace_array[@]}"; do
    workspace="${workspace## }"
    workspace="${workspace%% }"
    [[ -z "$workspace" ]] && continue
    workspace="$(expand_path "$workspace")"
    if [[ ! -d "$workspace" ]]; then
      echo "❌ Workspace path does not exist: $workspace"
      exit 1
    fi
  done

  messages_db="$(env_get apple_flow_messages_db_path)"
  if [[ -z "${messages_db//[[:space:]]/}" ]]; then
    messages_db="$HOME/Library/Messages/chat.db"
  fi
  messages_db="$(expand_path "$messages_db")"

  if [[ ! -f "$messages_db" ]]; then
    echo "❌ Messages DB not found at: $messages_db"
    exit 1
  fi

  MESSAGES_DB_PATH="$messages_db" "$VENV_PYTHON" - <<'PY'
import os
from pathlib import Path

path = Path(os.environ["MESSAGES_DB_PATH"])
try:
    with path.open("rb") as handle:
        handle.read(32)
except PermissionError:
    raise SystemExit("❌ Messages DB is not readable. Grant Full Disk Access to your terminal app and relaunch it.")
except OSError as exc:
    raise SystemExit(f"❌ Cannot read Messages DB: {exc}")
PY

  if [[ "$SELECTED_CONNECTOR" != "codex-app-server" && ! -x "$SELECTED_CONNECTOR_COMMAND" ]]; then
    echo "❌ Selected connector command is not executable: $SELECTED_CONNECTOR_COMMAND"
    exit 1
  fi

  echo "✓ Readiness checks passed"
}

cd "$ROOT_DIR"
echo "== Apple Flow Foreground Runner =="

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$ROOT_DIR[dev]"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env found. Launching setup wizard..."
  PYTHONPATH="$ROOT_DIR/src" "$VENV_PYTHON" -m apple_flow setup --script-safe --non-interactive-safe
fi

if pgrep -f "apple_flow daemon" >/dev/null 2>&1; then
  echo "Stopping existing Apple Flow daemon process..."
  pkill -f "apple_flow daemon" || true
  sleep 1
fi

LOCK_PATH="$(PYTHONPATH="$ROOT_DIR/src" "$VENV_PYTHON" - <<'PY'
from pathlib import Path
from apple_flow.config import RelaySettings
settings = RelaySettings()
print(Path(settings.db_path).with_suffix('.daemon.lock'))
PY
)"

if [[ -f "$LOCK_PATH" ]] && ! pgrep -f "apple_flow daemon" >/dev/null 2>&1; then
  echo "Removing stale daemon lock: $LOCK_PATH"
  rm -f "$LOCK_PATH"
fi

pin_selected_connector_binary
run_fast_readiness_checks

echo
echo "Starting Apple Flow daemon in foreground..."
echo "Press Ctrl+C to stop."
PYTHONPATH="$ROOT_DIR/src" "$VENV_PYTHON" -m apple_flow daemon
