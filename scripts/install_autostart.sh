#!/bin/bash
set -e

# Apple Flow Auto-Start Installation Script
# This installs a launchd service that starts apple-flow at boot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_DEST="$HOME/Library/LaunchAgents/local.apple-flow.plist"
LOGS_DIR="$PROJECT_DIR/logs"

echo "=== Apple Flow Auto-Start Installation ==="
echo ""

# Check if virtual environment exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Error: Virtual environment not found at $PROJECT_DIR/.venv"
    echo "Please run 'python -m venv .venv' and 'pip install -e .[dev]' first"
    exit 1
fi

# Check if .env file exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Warning: .env file not found. Make sure to configure it before starting the service."
    echo "Copy .env.example to .env and fill in your settings."
fi

# Find the actual Python binary (follow symlinks)
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Python binary not found in venv"
    exit 1
fi

# Resolve to the actual Python binary (not symlink)
ACTUAL_PYTHON=$(python3 -c "import os, sys; print(os.path.realpath('$VENV_PYTHON'))")
echo "Found Python binary: $ACTUAL_PYTHON"

# Find Python version for site-packages
PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PACKAGES="$PROJECT_DIR/.venv/lib/python${PYTHON_VERSION}/site-packages"

echo "Python version: $PYTHON_VERSION"
echo "Site packages: $SITE_PACKAGES"

# Create logs directory
echo "Creating logs directory..."
mkdir -p "$LOGS_DIR"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing service if running
if launchctl list | grep -q "local.apple-flow"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Generate plist file dynamically
echo "Generating launch agent plist..."
cat > "$PLIST_DEST" << EOF
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
      <string>$PROJECT_DIR/.venv/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
      <key>PYTHONPATH</key>
      <string>$SITE_PACKAGES:$PROJECT_DIR/src</string>
      <key>VIRTUAL_ENV</key>
      <string>$PROJECT_DIR/.venv</string>
    </dict>
  </dict>
</plist>
EOF

# Load the service
echo "Loading service..."
launchctl load "$PLIST_DEST"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "IMPORTANT: Grant Full Disk Access for Messages database"
echo ""
echo "1. Open System Settings > Privacy & Security > Full Disk Access"
echo "2. Click the '+' button"
echo "3. Press Cmd+Shift+G and paste this Python binary path:"
echo ""
echo "   $ACTUAL_PYTHON"
echo ""
echo "4. Click 'Open' to add it to Full Disk Access"
echo "5. Enable the toggle for python3.14"
echo ""
echo "6. After granting access, restart the service:"
echo "   launchctl stop local.apple-flow"
echo "   launchctl start local.apple-flow"
echo ""
echo "The apple-flow daemon will start automatically at login."
echo ""
echo "Useful commands:"
echo "  Start:   launchctl start local.apple-flow"
echo "  Stop:    launchctl stop local.apple-flow"
echo "  Status:  launchctl list | grep apple-flow"
echo "  Logs:    tail -f $LOGS_DIR/apple-flow.log"
echo "  Errors:  tail -f $LOGS_DIR/apple-flow.err.log"
echo ""
echo "To uninstall:"
echo "  ./scripts/uninstall_autostart.sh"
echo ""
