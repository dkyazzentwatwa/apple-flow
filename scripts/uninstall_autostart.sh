#!/bin/bash
set -e

# Apple Flow Auto-Start Uninstallation Script

PLIST_DEST="$HOME/Library/LaunchAgents/com.apple-flow.plist"

echo "=== Apple Flow Auto-Start Uninstallation ==="
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
echo "The apple-flow daemon will no longer start automatically."
echo "Logs are preserved in the project's logs/ directory."
echo ""
