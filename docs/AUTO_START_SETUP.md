# Auto-Start Setup Guide

This guide explains how to configure codex-relay to start automatically when your Mac boots.

## One-Command Setup (Recommended)

Just run:

```bash
./scripts/setup_autostart.sh
```

This single script does **everything**:
1. ✓ Creates virtual environment
2. ✓ Installs codex-relay and all dependencies
3. ✓ Creates .env from template (prompts you to edit it)
4. ✓ Generates launchd plist with correct paths
5. ✓ Installs and starts the service
6. ✓ Shows you the Python binary path for Full Disk Access

**Your only tasks:**
- Edit the .env file when prompted
- Grant Full Disk Access (one-time macOS security requirement)

## Advanced: Install-Only Script

If you've already set up the project (venv, dependencies, .env), use:

```bash
./scripts/install_autostart.sh
```

This only configures and installs the auto-start service.

## Grant Full Disk Access

**This step is REQUIRED** - the daemon needs access to read the Messages database.

1. **Open System Settings** → **Privacy & Security** → **Full Disk Access**

2. **Click the '+' button**

3. **Press Cmd+Shift+G** and paste the Python binary path shown by the installer
   - Example: `/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14/bin/python3.14`

4. **Click 'Open'** and **enable the toggle**

5. **Restart the service:**
   ```bash
   launchctl stop com.codex.relay
   launchctl start com.codex.relay
   ```

## Verify It's Running

```bash
# Check service status (should show a PID number, not -)
launchctl list | grep codex.relay

# Watch logs in real-time
tail -f logs/codex-relay.log

# Check for errors
tail -f logs/codex-relay.err.log
```

## Managing the Service

```bash
# Start manually
launchctl start com.codex.relay

# Stop manually
launchctl stop com.codex.relay

# Check status
launchctl list | grep codex.relay

# Uninstall auto-start
./scripts/uninstall_autostart.sh
```

## How It Works

The installation script:
- Follows symlinks to find the **actual** Python binary (not symlinks)
- Detects your Python version and site-packages location
- Generates a plist file with **your specific paths**
- Configures environment variables (PYTHONPATH, VIRTUAL_ENV, PATH)

This means the setup is **portable** - it works regardless of:
- Your username or project location
- Your Python version (3.10, 3.11, 3.14, etc.)
- Homebrew Python updates that change version numbers

## Troubleshooting

### Service shows exit code (not running)

```bash
launchctl list | grep codex.relay
# Output: -    1    com.codex.relay (- means not running, 1 is exit code)
```

**Check the error log:**
```bash
tail -30 logs/codex-relay.err.log
```

**Common issues:**
- **"unable to open database file"** → Grant Full Disk Access to Python binary
- **"ModuleNotFoundError"** → Reinstall dependencies: `pip install -e .[dev]`
- **"Operation not permitted"** → Python binary doesn't have Full Disk Access

### After Python update, service stops working

When Homebrew updates Python, the binary path changes. Re-run the installer:

```bash
./scripts/install_autostart.sh
```

Then re-grant Full Disk Access to the **new** Python binary path.

### Service runs but doesn't respond to messages

Check that:
1. `.env` file is configured with correct `codex_relay_allowed_senders`
2. Messages app is signed in to iMessage
3. Database path is correct: `~/Library/Messages/chat.db`

## Security Notes

- Only the specific Python binary gets Full Disk Access
- The daemon runs as your user (not root)
- It can only access paths in `codex_relay_allowed_workspaces`
- Mutating operations require explicit approval via the approval workflow
