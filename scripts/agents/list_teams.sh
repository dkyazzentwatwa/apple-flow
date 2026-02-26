#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CATALOG_FILE="$REPO_ROOT/agents/catalog.toml"

if [[ ! -f "$CATALOG_FILE" ]]; then
  echo "Error: catalog not found at $CATALOG_FILE" >&2
  exit 1
fi

awk '
  /^\[\[teams\]\]$/ { slug=""; title=""; next }
  /^slug = / { gsub(/^slug = \"|\"$/, "", $0); slug=$0; next }
  /^title = / { gsub(/^title = \"|\"$/, "", $0); title=$0; if (slug != "") print slug " - " title; next }
' "$CATALOG_FILE"
