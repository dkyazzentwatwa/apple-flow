# Codex Relay - Quick Start Guide

Get Codex Relay running in 5 steps. This guide assumes you're new to the project.

## What You'll Get

Text yourself on iMessage to:
- Chat with Claude about your code: `relay: what files handle authentication?`
- Brainstorm ideas: `idea: build a task manager app`
- Get implementation plans: `plan: add user authentication`
- Execute tasks with approval: `task: create a hello world script`

## Prerequisites

- macOS with iMessage signed in
- Python 3.11 or later
- Codex CLI installed ([claude.ai/code](https://claude.ai/code))

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/codex-flow.git
cd codex-flow
```

## Step 2: Grant Full Disk Access

The relay needs to read your iMessage database.

### macOS Ventura/Sonoma/Sequoia:
1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **🔒** to unlock (enter password)
3. Click the **+** button
4. Navigate to and add your terminal app:
   - **Terminal**: `/Applications/Utilities/Terminal.app`
   - **iTerm2**: `/Applications/iTerm.app`
   - **VS Code Terminal**: `/Applications/Visual Studio Code.app`
5. Enable the checkbox next to your terminal

### ⚠️ Important
**Fully quit and reopen your terminal app** after granting access. Just closing the window isn't enough!

```bash
# For Terminal.app, run:
osascript -e 'quit app "Terminal"'
# Then reopen Terminal
```

## Step 3: Authenticate with Codex

```bash
codex login
```

Follow the prompts in your browser to authenticate. This only needs to be done once.

**Don't have Codex CLI?** Install it first:
```bash
# Visit https://claude.ai/code for installation instructions
```

## Step 4: Configure Your Settings

The setup script will create `.env` from `.env.example` automatically. Edit it with your details:

```bash
nano .env
# Or use your preferred editor: code .env, vim .env, etc.
```

### Required Settings

Find and update these two settings:

```bash
# 1. Your phone number in E.164 format (include country code)
codex_relay_allowed_senders=+15551234567

# 2. Your workspace paths (where Codex can work)
codex_relay_allowed_workspaces=/Users/yourname/code
codex_relay_default_workspace=/Users/yourname/code/my-project
```

**Phone Number Format:**
- ✅ Correct: `+15551234567` (with country code)
- ❌ Wrong: `5551234567` (missing +1)
- ❌ Wrong: `(555) 123-4567` (with formatting)

**Workspace Path:**
- Use **absolute paths** (starting with `/`)
- This is where Codex can read/write files
- Separate multiple paths with commas

### Optional Settings

```bash
# Require 'relay:' prefix for non-command messages
codex_relay_require_chat_prefix=true

# Send startup notification
codex_relay_send_startup_intro=true

# Approval timeout (minutes)
codex_relay_approval_ttl_minutes=20
```

See `.env.example` for all available options.

## Step 5: Run the Setup Script

```bash
./scripts/start_beginner.sh
```

The script will automatically:
1. ✅ Create a Python virtual environment
2. ✅ Install all dependencies (including optimizations)
3. ✅ Create `.env` from `.env.example` if missing
4. ✅ Validate your configuration
5. ✅ Run 47 tests to ensure everything works
6. 🚀 Start the Codex Relay daemon

**What you'll see:**
```
== Codex Relay Beginner Setup ==
Creating virtual environment...
Installing dependencies...
Running tests...
===== 47 passed in 0.36s =====

Starting Codex Relay daemon...
2026-02-16 14:00:00,000 INFO Codex Relay running (foreground)
2026-02-16 14:00:00,100 INFO Ready. Waiting for inbound iMessages. Press Ctrl+C to stop.
```

---

## Using Codex Relay

### Send Your First Message

Text yourself on iMessage from your configured phone number:

```
relay: hello
```

You should get a response from Claude!

### Command Types

#### Non-Mutating (Run Immediately)

```
relay: what files handle authentication in this codebase?
```

```
idea: I want to build a task manager. What are some good approaches?
```

```
plan: Add user authentication with JWT tokens
```

#### Mutating (Require Approval)

```
task: create a hello world Python script
```

You'll get a plan and an approval request:
```
Plan for task:
1. Create hello.py with print statement
2. Make it executable

Approve with: approve req_abc123
Deny with: deny req_abc123
```

Reply with:
```
approve req_abc123
```

#### Control Commands

```
status              # Check pending approvals
clear context       # Start fresh conversation
approve req_abc123  # Approve a task
deny req_abc123     # Deny a task
```

### Security Features

- **Sender allowlist**: Only your configured phone numbers can use the relay
- **Approval workflow**: Mutating operations require your explicit approval
- **Sender verification**: Only you can approve/deny your own requests
- **Workspace restrictions**: Codex only accesses allowed directories

---

## Stopping the Daemon

Press **Ctrl+C** in the terminal. The daemon will shut down gracefully.

---

## Troubleshooting

### "Cannot read Messages DB"

**Cause**: Full Disk Access not granted or terminal not restarted.

**Fix**:
1. Double-check Full Disk Access is enabled for your terminal
2. **Fully quit** your terminal app (not just close the window)
3. Reopen terminal and try again

**Verify access**:
```bash
sqlite3 ~/Library/Messages/chat.db "SELECT COUNT(*) FROM message;" 2>&1
```
Should show a number, not an error.

### "allowed_senders is empty"

**Cause**: `.env` file not configured with your phone number.

**Fix**:
```bash
nano .env
# Set: codex_relay_allowed_senders=+15551234567
```

### "codex login not found"

**Cause**: Codex CLI not installed.

**Fix**: Install Codex CLI from [claude.ai/code](https://claude.ai/code)

### Tests Failing

**Cause**: Dependency issues or code conflicts.

**Fix**:
```bash
# Clean reinstall
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -v
```

### No Response from iMessage

**Check**:
1. Is the daemon running? (You should see "Ready. Waiting for inbound iMessages")
2. Are you texting from the configured phone number?
3. Did you include the `relay:` prefix (if `require_chat_prefix=true`)?
4. Check daemon logs for errors

### Daemon Keeps Stopping

**Cause**: Existing process or stale lock file.

**Fix**:
```bash
# Kill any existing processes
pkill -f "codex_relay daemon"

# Remove stale lock
rm -f ~/.codex/relay.daemon.lock

# Restart
./scripts/start_beginner.sh
```

---

## Next Steps

### Admin API

The relay includes a web API for monitoring:

```bash
# In another terminal:
python -m codex_relay admin
```

Visit `http://localhost:8787` for:
- `/sessions` - Active conversations
- `/approvals/pending` - Pending approvals
- `/events` - Audit log

### Run as Background Service

For always-on operation, see `CLAUDE.md` for launchd setup.

### Advanced Configuration

See `.env.example` for all settings:
- Rate limiting
- Polling intervals
- Custom workspace paths
- Admin API settings

---

## Architecture Overview

```
iMessage → Ingress → Policy → Orchestrator → Codex → Egress → iMessage
                                  ↓
                              Store (SQLite)
```

- **Ingress**: Reads from macOS Messages database
- **Policy**: Enforces sender allowlist and rate limits
- **Orchestrator**: Routes commands and manages approvals
- **Codex Connector**: Manages Codex app-server threads
- **Store**: Persists sessions, runs, and approvals
- **Egress**: Sends replies via AppleScript

### Recent Optimizations (v0.1.0)

- ⚡ Database connection caching + indexes for 10x faster queries
- 🔒 Approval sender verification (only you can approve your tasks)
- 🛡️ Graceful shutdown with signal handling
- 📝 Codex subprocess stderr logging for easier debugging
- 🧪 47 comprehensive tests with shared fixtures

For developers, see `CLAUDE.md` for architecture details.

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/yourusername/codex-flow/issues)
- **Logs**: Check terminal output for errors
- **Tests**: Run `pytest -v` to verify installation

## License

See `LICENSE` file for details.
