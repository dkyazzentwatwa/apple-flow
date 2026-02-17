#!/bin/bash
set -e

# Apple Flow Complete Setup & Auto-Start Installation
# One script to set up everything and enable auto-start at boot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_DEST="$HOME/Library/LaunchAgents/com.apple-flow.plist"
LOGS_DIR="$PROJECT_DIR/logs"
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

echo "=========================================="
echo "  Apple Flow Complete Setup"
echo "=========================================="
echo ""

# Step 1: Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/5] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "[1/5] Virtual environment already exists"
fi

# Step 2: Install package and dependencies
echo ""
echo "[2/5] Installing apple-flow and dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$PROJECT_DIR[dev]"
echo "✓ Installation complete"

# Step 3: Check/create .env file
echo ""
echo "[3/5] Checking configuration..."
if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        echo "⚠️  No .env file found. Creating from .env.example..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  IMPORTANT: Edit .env file before starting!"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "Required settings:"
        echo "  - apple_flow_allowed_senders (phone numbers)"
        echo "  - apple_flow_allowed_workspaces (directories)"
        echo ""
        echo "Run: nano .env  (or use your preferred editor)"
        echo ""
        read -p "Press Enter after you've edited .env to continue..."
    else
        echo "❌ Error: .env.example not found"
        exit 1
    fi
else
    echo "✓ .env file exists"
fi

# Step 4: Find Python binary and generate plist
echo ""
echo "[4/5] Configuring auto-start service..."

VENV_PYTHON="$VENV_DIR/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: Python binary not found in venv"
    exit 1
fi

# Resolve to the actual Python binary (not symlink)
ACTUAL_PYTHON=$(python3 -c "import os; print(os.path.realpath('$VENV_PYTHON'))")
PYTHON_VERSION=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
SITE_PACKAGES="$VENV_DIR/lib/python${PYTHON_VERSION}/site-packages"

# Create logs directory
mkdir -p "$LOGS_DIR"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Stop existing service if running
if launchctl list 2>/dev/null | grep -q "com.apple-flow"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Generate plist file
cat > "$PLIST_DEST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.apple-flow</string>

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
      <string>$VENV_DIR/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
      <key>PYTHONPATH</key>
      <string>$SITE_PACKAGES:$PROJECT_DIR/src</string>
      <key>VIRTUAL_ENV</key>
      <string>$VENV_DIR</string>
    </dict>
  </dict>
</plist>
EOF

echo "✓ Launch agent configured"

# Step 5: Load the service
echo ""
echo "[5/5] Starting service..."
launchctl load "$PLIST_DEST"
echo "✓ Service loaded"

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FINAL STEP: Grant Full Disk Access (Required!)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "The daemon needs permission to read the Messages database."
echo ""
echo "1. Open: System Settings > Privacy & Security > Full Disk Access"
echo ""
echo "2. Click the '+' button"
echo ""
echo "3. Press Cmd+Shift+G and paste this path:"
echo ""
echo "   $ACTUAL_PYTHON"
echo ""
echo "4. Click 'Open' and enable the toggle"
echo ""
echo "5. Restart the service:"
echo "   launchctl stop com.apple-flow"
echo "   launchctl start com.apple-flow"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Useful Commands:"
echo "  Check status:  launchctl list | grep apple-flow"
echo "  View logs:     tail -f $LOGS_DIR/apple-flow.log"
echo "  View errors:   tail -f $LOGS_DIR/apple-flow.err.log"
echo "  Stop service:  launchctl stop com.apple-flow"
echo "  Start service: launchctl start com.apple-flow"
echo "  Uninstall:     ./scripts/uninstall_autostart.sh"
echo ""
echo "The daemon will now auto-start on every boot!"
echo ""
