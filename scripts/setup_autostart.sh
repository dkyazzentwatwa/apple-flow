#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_DEST="$HOME/Library/LaunchAgents/local.apple-flow.plist"
LOGS_DIR="$PROJECT_DIR/logs"
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_FILE="$PROJECT_DIR/.env"

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
      echo "Set apple_flow_connector to one of: codex-cli, claude-cli, cline, codex-app-server"
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
    echo "Install/auth the connector first, then rerun setup:"
    echo "  - codex-cli: npm install -g @openai/codex && codex login"
    echo "  - claude-cli: curl -fsSL https://claude.ai/install.sh | bash && claude auth login"
    echo "  - cline: npm install -g cline && cline auth"
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
  SELECTED_CONNECTOR_KEY="$key"
  export SELECTED_CONNECTOR SELECTED_CONNECTOR_COMMAND SELECTED_CONNECTOR_KEY
  echo "✓ Pinned connector command: $key=$SELECTED_CONNECTOR_COMMAND"
}

run_fast_readiness_checks() {
  local senders
  local workspaces
  local messages_db

  senders="$(env_get apple_flow_allowed_senders)"
  workspaces="$(env_get apple_flow_allowed_workspaces)"
  if [[ -z "${senders//[[:space:]]/}" || "$senders" == *"REPLACE_WITH"* ]]; then
    echo "❌ apple_flow_allowed_senders is missing in .env"
    echo "Set your phone number in E.164 format, e.g. +15551234567"
    exit 1
  fi
  if [[ -z "${workspaces//[[:space:]]/}" || "$workspaces" == *"REPLACE_WITH"* ]]; then
    echo "❌ apple_flow_allowed_workspaces is missing in .env"
    echo "Set at least one workspace path, e.g. /Users/you/code"
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
    echo "Update apple_flow_messages_db_path or sign into Messages on this Mac."
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

  if [[ "$SELECTED_CONNECTOR" != "codex-app-server" ]]; then
    if [[ ! -x "$SELECTED_CONNECTOR_COMMAND" ]]; then
      echo "❌ Selected connector command is not executable: $SELECTED_CONNECTOR_COMMAND"
      exit 1
    fi
  fi

  echo "✓ Readiness checks passed"
}

echo "=========================================="
echo "  Apple Flow Auto-Start Setup"
echo "=========================================="
echo ""

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[1/6] Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
  echo "✓ Virtual environment created"
else
  echo "[1/6] Virtual environment already exists"
fi

echo ""
echo "[2/6] Installing apple-flow and dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$PROJECT_DIR[dev]"
echo "✓ Installation complete"

echo ""
echo "[3/6] Preparing configuration..."
if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env found. Launching setup wizard to generate one..."
  PYTHONPATH="$PROJECT_DIR/src" "$VENV_PYTHON" -m apple_flow setup --script-safe --non-interactive-safe
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ .env file was not created. Aborting setup."
  exit 1
fi

echo ""
echo "[4/6] Pinning connector command + readiness checks..."
pin_selected_connector_binary
run_fast_readiness_checks

echo ""
echo "[5/6] Installing launchd service..."
ACTUAL_PYTHON="$($VENV_PYTHON -c "import os; print(os.path.realpath('$VENV_PYTHON'))")"
PYTHON_VERSION="$($VENV_PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"
SITE_PACKAGES="$VENV_DIR/lib/python${PYTHON_VERSION}/site-packages"

mkdir -p "$LOGS_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

if launchctl list 2>/dev/null | grep -q "local.apple-flow"; then
  launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

cat > "$PLIST_DEST" <<EOF2
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>local.apple-flow</string>

    <key>ProgramArguments</key>
    <array>
      <string>$ACTUAL_PYTHON</string>
      <string>-m</string>
      <string>apple_flow</string>
      <string>daemon</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOGS_DIR/apple-flow.log</string>

    <key>StandardErrorPath</key>
    <string>$LOGS_DIR/apple-flow.err.log</string>

    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>$VENV_DIR/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
      <key>PYTHONPATH</key>
      <string>$SITE_PACKAGES:$PROJECT_DIR/src</string>
      <key>VIRTUAL_ENV</key>
      <string>$VENV_DIR</string>
    </dict>
  </dict>
</plist>
EOF2

echo "✓ Launch agent configured"

echo ""
echo "[6/6] Starting service..."
launchctl load "$PLIST_DEST"
echo "✓ Service loaded"

echo ""
echo "=========================================="
echo "  Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Grant Full Disk Access to this Python binary:"
echo "   $ACTUAL_PYTHON"
echo "2. Restart service after granting access:"
echo "   launchctl stop local.apple-flow"
echo "   launchctl start local.apple-flow"
echo ""
echo "Useful commands:"
echo "  launchctl list | grep apple-flow"
echo "  tail -f $LOGS_DIR/apple-flow.err.log"
echo "  ./scripts/uninstall_autostart.sh"
