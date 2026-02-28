#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/../../.." && pwd)"
APP_BUNDLE="$REPO_ROOT/dist/AppleFlowApp.app"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "No exported app found at $APP_BUNDLE"
  echo "Building one now..."
  "$SCRIPT_DIR/export_app.sh"
fi

open "$APP_BUNDLE"
echo "Launched: $APP_BUNDLE"
