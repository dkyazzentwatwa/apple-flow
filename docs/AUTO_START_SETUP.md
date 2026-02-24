# Auto-Start Setup Guide

This guide explains how to configure apple-flow to start automatically when your Mac boots.

## One-Command Setup (Recommended)

Just run:

```bash
./scripts/setup_autostart.sh
```

This single script does **everything**:
1. ✓ Creates virtual environment
2. ✓ Installs apple-flow and all dependencies
3. ✓ Launches `python -m apple_flow setup` if `.env` is missing
4. ✓ Generates launchd plist with correct paths
5. ✓ Installs and starts both launchd services (daemon + admin API)
6. ✓ Pins connector command paths and runs fast readiness checks
7. ✓ Shows you the Python binary path for Full Disk Access

**Your only tasks:**
- Complete the setup wizard if `.env` is missing
- Grant Full Disk Access (one-time macOS security requirement)

## Advanced: Install-Only Script

If you've already set up the project (venv, dependencies, .env), use:

```bash
./scripts/install_autostart.sh
```

This only configures and installs the auto-start services.

## Grant Full Disk Access

**This step is REQUIRED** - the daemon needs access to read the Messages database.

1. **Open System Settings** → **Privacy & Security** → **Full Disk Access**

2. **Click the '+' button**

3. **Press Cmd+Shift+G** and paste the Python binary path shown by the installer
   - Example: `/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14/bin/python3.14`

4. **Click 'Open'** and **enable the toggle**

5. **Restart both services:**
   ```bash
   launchctl stop local.apple-flow
   launchctl start local.apple-flow
   launchctl stop local.apple-flow-admin
   launchctl start local.apple-flow-admin
   ```

## Verify It's Running

```bash
# Check service status (should show a PID number, not -)
launchctl list | grep apple-flow

# Watch logs in real-time
tail -f logs/apple-flow.log

# Check for errors
tail -f logs/apple-flow.err.log
```

## Managing the Service

```bash
# Start manually
launchctl start local.apple-flow
launchctl start local.apple-flow-admin

# Stop manually
launchctl stop local.apple-flow
launchctl stop local.apple-flow-admin

# Check status
launchctl list | grep apple-flow

# Uninstall auto-start
./scripts/uninstall_autostart.sh
```

## How It Works

The installation script:
- Follows symlinks to find the **actual** Python binary (not symlinks)
- Detects your Python version and site-packages location
- Generates a plist file with **your specific paths**
- Configures environment variables (PYTHONPATH, VIRTUAL_ENV, PATH including `~/.local/bin`)

This means the setup is **portable** - it works regardless of:
- Your username or project location
- Your Python version (3.10, 3.11, 3.14, etc.)
- Homebrew Python updates that change version numbers

## Troubleshooting

### Service shows exit code (not running)

```bash
launchctl list | grep apple-flow
# Output: -    1    local.apple-flow (- means not running, 1 is exit code)
```

**Check the error log:**
```bash
tail -30 logs/apple-flow.err.log
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
1. `.env` file is configured with correct `apple_flow_allowed_senders`
2. Messages app is signed in to iMessage
3. Database path is correct: `~/Library/Messages/chat.db`

## Security Notes

- Only the specific Python binary gets Full Disk Access
- The daemon runs as your user (not root)
- It can only access paths in `apple_flow_allowed_workspaces`
- Mutating operations require explicit approval via the approval workflow
