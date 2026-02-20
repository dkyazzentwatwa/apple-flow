#!/bin/bash
# shared-functions.sh — Common helpers for apple-flow automation scripts
#
# Usage: source this file from other automation scripts
#   source "$(dirname "$0")/shared-functions.sh"

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Project root (parent of scripts/ directory)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# Default paths (can be overridden by env vars)
OFFICE_PATH="${APPLE_FLOW_OFFICE_PATH:-$PROJECT_ROOT/agent-office}"
ENV_FILE="${APPLE_FLOW_ENV_FILE:-$PROJECT_ROOT/.env}"
DAEMON_PID_FILE="${APPLE_FLOW_PID_FILE:-/tmp/apple-flow.pid}"
LOG_FILE="$OFFICE_PATH/90_logs/automation-log.md"

# Connector (loaded from .env, defaults to cline)
CONNECTOR="${APPLE_FLOW_CONNECTOR:-}"

# -----------------------------------------------------------------------------
# Load connector from .env
# -----------------------------------------------------------------------------

load_connector_from_env() {
    if [[ -n "$CONNECTOR" ]]; then
        return  # Already set via env var
    fi
    
    if [[ -f "$ENV_FILE" ]]; then
        local value
        value=$(grep -E "^apple_flow_connector=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d'=' -f2 | tr -d ' "' || true)
        if [[ -n "$value" ]]; then
            CONNECTOR="$value"
        fi
    fi
    
    # Default to cline if not configured
    CONNECTOR="${CONNECTOR:-cline}"
}

# -----------------------------------------------------------------------------
# Daemon check
# -----------------------------------------------------------------------------

is_daemon_running() {
    if [[ -f "$DAEMON_PID_FILE" ]]; then
        local pid
        pid=$(cat "$DAEMON_PID_FILE" 2>/dev/null || true)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

require_daemon_running() {
    if ! is_daemon_running; then
        log_run "skipped" "daemon not running"
        echo "Error: apple-flow daemon is not running (pid file: $DAEMON_PID_FILE)" >&2
        exit 0  # Exit gracefully, don't fail
    fi
}

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

log_run() {
    local action="$1"
    local result="$2"
    local notes="${3:-}"
    
    local timestamp
    timestamp=$(date "+%Y-%m-%d %H:%M")
    
    # Ensure log directory exists
    mkdir -p "$(dirname "$LOG_FILE")"
    
    # Append log entry
    local entry="- $timestamp | launchd | $action | $result"
    if [[ -n "$notes" ]]; then
        entry="$entry | $notes"
    fi
    
    echo "$entry" >> "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# AI Connector execution
# -----------------------------------------------------------------------------

run_with_connector() {
    local prompt="$1"
    local timeout="${2:-300}"  # Default 5 minute timeout
    
    load_connector_from_env
    
    case "$CONNECTOR" in
        cline)
            timeout "$timeout" cline -y --cwd "$OFFICE_PATH" "$prompt"
            ;;
        claude-cli)
            timeout "$timeout" claude -p "$prompt"
            ;;
        codex-cli)
            timeout "$timeout" codex exec "$prompt"
            ;;
        *)
            echo "Error: Unknown connector '$CONNECTOR'" >&2
            return 1
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Date helpers
# -----------------------------------------------------------------------------

get_today() {
    date "+%Y-%m-%d"
}

get_yesterday() {
    date -v-1d "+%Y-%m-%d"
}

get_daily_note_path() {
    local date_str="${1:-$(get_today)}"
    echo "$OFFICE_PATH/10_daily/${date_str}.md"
}

ensure_daily_note() {
    local note_path
    note_path=$(get_daily_note_path)
    
    if [[ ! -f "$note_path" ]]; then
        local template_path="$OFFICE_PATH/templates/daily-note.md"
        if [[ -f "$template_path" ]]; then
            sed "s/{{date}}/$(get_today)/g" "$template_path" > "$note_path"
        else
            echo "# Daily Note — $(get_today)" > "$note_path"
            echo "" >> "$note_path"
            echo "## Top 3 Priorities" >> "$note_path"
            echo "" >> "$note_path"
            echo "## Open Loops" >> "$note_path"
            echo "" >> "$note_path"
            echo "## Work Log" >> "$note_path"
            echo "" >> "$note_path"
            echo "## Memory Delta" >> "$note_path"
            echo "" >> "$note_path"
            echo "## End-of-Day Reflection" >> "$note_path"
            echo "" >> "$note_path"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Initialization
# -----------------------------------------------------------------------------

# Create log directory if needed
mkdir -p "$(dirname "$LOG_FILE")"