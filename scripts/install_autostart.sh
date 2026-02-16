#!/bin/bash
set -e

# Codex Relay Auto-Start Installation Script
# This installs a launchd service that starts codex-relay at boot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SOURCE="$PROJECT_DIR/docs/launchd/com.codex.relay.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.codex.relay.plist"
LOGS_DIR="$PROJECT_DIR/logs"

echo "=== Codex Relay Auto-Start Installation ==="
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Error: Virtual environment not found at $PROJECT_DIR/.venv"
    echo "Please run 'python -m venv .venv' and 'pip install -e .' first"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Warning: .env file not found. Make sure to configure it before starting the service."
    echo "Copy .env.example to .env and fill in your settings."
fi

# Create logs directory
echo "Creating logs directory..."
mkdir -p "$LOGS_DIR"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing service if running
if launchctl list | grep -q "com.codex.relay"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist file
echo "Installing launch agent..."
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Load the service
echo "Loading service..."
launchctl load "$PLIST_DEST"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "The codex-relay daemon will now start automatically at login."
echo ""
echo "Useful commands:"
echo "  Start:   launchctl start com.codex.relay"
echo "  Stop:    launchctl stop com.codex.relay"
echo "  Status:  launchctl list | grep codex.relay"
echo "  Logs:    tail -f $LOGS_DIR/codex-relay.log"
echo "  Errors:  tail -f $LOGS_DIR/codex-relay.err.log"
echo ""
echo "To uninstall:"
echo "  launchctl unload $PLIST_DEST"
echo "  rm $PLIST_DEST"
echo ""
