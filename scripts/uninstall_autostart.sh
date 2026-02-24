#!/bin/bash
set -e

# Apple Flow Auto-Start Uninstallation Script

PLIST_DEST="$HOME/Library/LaunchAgents/local.apple-flow.plist"
PLIST_DEST_ADMIN="$HOME/Library/LaunchAgents/local.apple-flow-admin.plist"

echo "=== Apple Flow Auto-Start Uninstallation ==="
echo ""

if [ ! -f "$PLIST_DEST" ] && [ ! -f "$PLIST_DEST_ADMIN" ]; then
    echo "Services are not installed."
    exit 0
fi

# Unload services
echo "Unloading services..."
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl unload "$PLIST_DEST_ADMIN" 2>/dev/null || true

# Remove plist files
echo "Removing launch agents..."
rm -f "$PLIST_DEST" "$PLIST_DEST_ADMIN"

echo ""
echo "=== Uninstallation Complete ==="
echo ""
echo "The apple-flow daemon and admin API will no longer start automatically."
echo "Logs are preserved in the project's logs/ directory."
echo ""
