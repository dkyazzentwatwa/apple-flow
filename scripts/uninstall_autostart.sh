#!/bin/bash
set -e

# Codex Relay Auto-Start Uninstallation Script

PLIST_DEST="$HOME/Library/LaunchAgents/com.codex.relay.plist"

echo "=== Codex Relay Auto-Start Uninstallation ==="
echo ""

if [ ! -f "$PLIST_DEST" ]; then
    echo "Service is not installed."
    exit 0
fi

# Unload the service
echo "Unloading service..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# Remove plist file
echo "Removing launch agent..."
rm "$PLIST_DEST"

echo ""
echo "=== Uninstallation Complete ==="
echo ""
echo "The codex-relay daemon will no longer start automatically."
echo "Logs are preserved in the project's logs/ directory."
echo ""
