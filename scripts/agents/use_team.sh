#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <team-slug>" >&2
  exit 1
fi

SLUG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRESET_FILE="$REPO_ROOT/agents/teams/$SLUG/preset.toml"

if [[ ! -f "$PRESET_FILE" ]]; then
  echo "Error: team preset not found for slug '$SLUG'" >&2
  echo "Try: $REPO_ROOT/scripts/agents/list_teams.sh" >&2
  exit 1
fi

if [[ -n "${CODEX_CONFIG_PATH:-}" ]]; then
  CONFIG_FILE="$CODEX_CONFIG_PATH"
  CONFIG_DIR="$(dirname "$CONFIG_FILE")"
else
  CONFIG_DIR="$REPO_ROOT/.codex"
  CONFIG_FILE="$CONFIG_DIR/config.toml"
fi

mkdir -p "$CONFIG_DIR"

BEGIN_MARK="# BEGIN APPLE_FLOW_TEAM_PRESET"
END_MARK="# END APPLE_FLOW_TEAM_PRESET"
BACKUP_PATH=""

if [[ -f "$CONFIG_FILE" ]]; then
  TS="$(date +%Y%m%d-%H%M%S)"
  BACKUP_PATH="$CONFIG_FILE.bak.$TS"
  cp "$CONFIG_FILE" "$BACKUP_PATH"
fi

TMP_FILE="$(mktemp)"
if [[ -f "$CONFIG_FILE" ]]; then
  awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
    BEGIN { skip=0 }
    index($0, begin) == 1 { skip=1; next }
    index($0, end) == 1 { skip=0; next }
    skip == 0 { print }
  ' "$CONFIG_FILE" > "$TMP_FILE"
fi

if [[ -s "$TMP_FILE" ]]; then
  printf "\n" >> "$TMP_FILE"
fi

{
  echo "$BEGIN_MARK"
  echo "# source: agents/teams/$SLUG/preset.toml"
  cat "$PRESET_FILE"
  echo "$END_MARK"
} >> "$TMP_FILE"

mv "$TMP_FILE" "$CONFIG_FILE"

if [[ -n "$BACKUP_PATH" ]]; then
  echo "Backup created: $BACKUP_PATH"
fi

echo "Activated team: $SLUG"
echo "Updated config: $CONFIG_FILE"
