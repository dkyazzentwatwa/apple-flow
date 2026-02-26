# Apple Flow - Quick Start Guide

Get Apple Flow running in 5 steps. This guide assumes you're new to the project.

## Preferred Vibe-Coding Method (Recommended)

1. Clone this repo and `cd` into it
2. Paste [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) into Codex/Claude/Cline
3. Let the AI run `./scripts/setup_autostart.sh` and complete full `.env` customization, gateway setup, validation, and service health checks with explicit confirmations

## What You'll Get

Text or email yourself to:
- Chat with an AI about your code: `relay: what files handle authentication?`
- Brainstorm ideas: `idea: build a task manager app`
- Get implementation plans: `plan: add user authentication`
- Execute tasks with approval: `task: create a hello world script`

Works via **iMessage** (default), **Apple Mail**, **Apple Reminders**, **Apple Notes**, or **Apple Calendar** (all optional).

## Prerequisites

- macOS with iMessage signed in
- Python 3.11 or later
- At least one AI CLI installed and authenticated:
  - **Codex CLI** (default) -- [developers.openai.com/codex/cli](https://developers.openai.com/codex/cli/)
  - **Claude Code CLI** -- `claude` binary from [claude.ai/code](https://claude.ai/code)
  - **Gemini CLI** -- `gemini` binary from [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli)
  - **Cline CLI** -- `cline` binary, supports any model provider (OpenAI, Anthropic, Google, DeepSeek, etc.)

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
```

## Step 2: Grant Full Disk Access

The daemon needs to read your iMessage database.

### macOS Ventura/Sonoma/Sequoia:
1. Open **System Settings** > **Privacy & Security** > **Full Disk Access**
2. Click the lock to unlock (enter password)
3. Click the **+** button
4. Navigate to and add your terminal app:
   - **Terminal**: `/Applications/Utilities/Terminal.app`
   - **iTerm2**: `/Applications/iTerm.app`
   - **VS Code Terminal**: `/Applications/Visual Studio Code.app`
5. Enable the checkbox next to your terminal

### Important
**Fully quit and reopen your terminal app** after granting access. Just closing the window isn't enough!

```bash
# For Terminal.app, run:
osascript -e 'quit app "Terminal"'
# Then reopen Terminal
```

## Step 3: Authenticate with Your AI Backend

Run the login command for whichever backend you plan to use. **You only need one.**

**Option A -- Codex** (default, uses `codex exec`):
```bash
codex login
```

**Option B -- Claude Code CLI** (uses `claude -p`):
```bash
claude auth login
```

**Option C -- Cline CLI** (uses `cline -y`, supports any model):
No separate auth needed -- Cline uses its own configuration.

**Option D -- Gemini CLI** (uses `gemini -p`):
```bash
gemini auth login
```

Follow the prompts in your browser (Options A/B/D). This only needs to be done once per machine.

Then set your connector in `.env` (Step 6, if you choose manual editing):
```bash
apple_flow_connector=codex-cli   # for Codex (default)
apple_flow_connector=claude-cli  # for Claude Code
apple_flow_connector=gemini-cli  # for Gemini CLI
apple_flow_connector=cline       # for Cline
```

## Step 4: Run the Setup Script

```bash
./scripts/setup_autostart.sh
```

The script will automatically:
1. Create a Python virtual environment
2. Install dependencies
3. Generate `.env` through the setup wizard if missing
4. Pin the selected connector command to an absolute binary path
5. Run fast readiness checks (required fields, Messages DB access, connector executable)
6. Install/start launchd auto-start

**What you'll see:**
```
Apple Flow Auto-Start Setup
...
✓ Pinned connector command: apple_flow_claude_cli_command=/opt/homebrew/bin/claude
✓ Readiness checks passed
✓ Launch agent configured
✓ Service loaded
```

## Step 5: Let Your AI Finalize Setup (Recommended)

Open Codex, Claude, or Cline and paste this:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

The assistant will:
1. Run health checks (`wizard doctor --json`)
2. Ask your full customization checklist (core fields, gateways, custom names, agent-office, token)
3. Generate full `.env` preview from `.env.example` (`wizard generate-env --json`)
4. Ask for explicit confirmation before writes/mutations
5. Apply settings via `config write --json`, validate, ensure gateways, restart service
6. Verify final health (`service status --json`) and give a completion summary

Optional after this flow: build the standalone SwiftUI control board app:
- [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

You can also run it directly:

```bash
./apps/macos/AppleFlowApp/scripts/export_app.sh
./apps/macos/AppleFlowApp/scripts/run_standalone.sh
```

## Step 6: Manual `.env` Editing (Optional Fallback)

If you prefer manual config updates, edit `.env` directly any time:

```bash
nano .env
# Or use your preferred editor: code .env, vim .env, etc.
```

### Required Settings

Find and update these settings:

```bash
# 1. Your phone number in E.164 format (include country code)
apple_flow_allowed_senders=+15551234567

# 2. Your workspace paths (where the AI can work)
apple_flow_allowed_workspaces=/Users/yourname/code
apple_flow_default_workspace=/Users/yourname/code/my-project

# 3. Your AI backend connector (pick one)
apple_flow_connector=codex-cli   # default -- requires: codex login
apple_flow_connector=claude-cli  # alternative -- requires: claude auth login
apple_flow_connector=gemini-cli  # alternative -- requires: gemini auth login
apple_flow_connector=cline       # alternative -- uses its own config
```

**Phone Number Format:**
- Correct: `+15551234567` (with country code)
- Wrong: `5551234567` (missing +1)
- Wrong: `(555) 123-4567` (with formatting)

**Workspace Path:**
- Use **absolute paths** (starting with `/`)
- This is where the AI agent can read/write files
- Separate multiple paths with commas

### Optional Settings

```bash
# Require 'relay:' prefix for non-command messages
apple_flow_require_chat_prefix=true

# Send startup notification
apple_flow_send_startup_intro=true

# Approval timeout (minutes)
apple_flow_approval_ttl_minutes=20
```

See `.env.example` for all 60+ available options.

---

## Using Apple Flow

### Send Your First Message

Text yourself on iMessage from your configured phone number:

```
relay: hello
```

You should get a response from your AI backend!

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
deny all            # Deny all pending approvals
health:             # Daemon stats, uptime, session count
history:            # Recent messages
history: deploy     # Search messages
```

#### Workspace Routing

Route tasks to specific project directories using `@alias` prefixes:

```bash
# Configure aliases in .env:
apple_flow_workspace_aliases={"web-app":"/Users/me/code/web-app","api":"/Users/me/code/api"}
```

```
task: @web-app deploy the latest changes
task: @api add a health check endpoint
```

#### Companion Control

If the autonomous companion is enabled:
```
system: mute        # Silence proactive messages
system: unmute      # Re-enable proactive messages
```

### Security Features

- **Sender allowlist**: Only your configured phone numbers can use the daemon
- **Approval workflow**: Mutating operations require your explicit approval
- **Sender verification**: Only you can approve/deny your own requests
- **Workspace restrictions**: The AI agent only accesses allowed directories
- **Rate limiting**: Configurable max messages per minute per sender

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
# Set: apple_flow_allowed_senders=+15551234567
```

### "codex not found" / "claude not found" / "gemini not found" / "cline not found"

**Cause**: The CLI for your chosen connector isn't installed or not on `$PATH`.

**Fix**:
- For Codex: install from [developers.openai.com/codex/cli](https://developers.openai.com/codex/cli/), then run `codex login`
- For Claude: install the `claude` CLI from [claude.ai/code](https://claude.ai/code), then run `claude auth login`
- For Gemini: install the `gemini` CLI from [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli), then run `gemini auth login`
- For Cline: install the `cline` CLI and configure it
- Make sure `apple_flow_connector` in `.env` matches what you installed

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
pkill -f "apple_flow daemon"

# Remove stale lock
rm -f ~/.apple-flow/relay.daemon.lock

# Restart
./scripts/start_beginner.sh
```

---

## Next Steps

### Admin API

The daemon includes a web API for monitoring:

```bash
# In another terminal:
python -m apple_flow admin
```

Visit `http://localhost:8787` for:
- `/sessions` - Active conversations
- `/approvals/pending` - Pending approvals
- `/events` - Audit log
- `POST /task` - Submit tasks programmatically (Siri Shortcuts / curl)

### Run as Background Service

For always-on operation, use the one-command setup:
```bash
./scripts/setup_autostart.sh
```

Need foreground mode instead of launchd (advanced fallback)?
```bash
./scripts/start_beginner.sh
```

### Enable Apple Mail Integration (Optional)

To use email alongside iMessage, add to `.env`:

```bash
apple_flow_enable_mail_polling=true
apple_flow_mail_allowed_senders=your.email@example.com
apple_flow_mail_from_address=your.email@example.com
apple_flow_mail_max_age_days=2
```

Then restart the daemon. Emails will reply in the same thread and work seamlessly alongside iMessage.

### Enable Apple Reminders Integration (Optional)

Use Reminders.app as a task queue:

```bash
apple_flow_enable_reminders_polling=true
apple_flow_reminders_list_name=agent-task
apple_flow_reminders_archive_list_name=agent-archive
# apple_flow_reminders_auto_approve=false  # require approval by default
```

Default names are `agent-task` and `agent-archive` (auto-created/verified by setup).

### Enable Apple Notes Integration (Optional)

Use Notes.app for long-form tasks:

```bash
apple_flow_enable_notes_polling=true
apple_flow_notes_folder_name=agent-task
apple_flow_notes_archive_folder_name=agent-archive
apple_flow_notes_log_folder_name=agent-logs
```

Default folders are `agent-task`, `agent-archive`, and `agent-logs` (auto-created/verified by setup).

### Enable Apple Calendar Integration (Optional)

Use Calendar.app for scheduled tasks:

```bash
apple_flow_enable_calendar_polling=true
apple_flow_calendar_name=agent-schedule
```

Default calendar is `agent-schedule` (auto-created/verified by setup).

### Autonomous Companion (Optional)

Enable proactive observations and follow-ups:

```bash
apple_flow_enable_companion=true
apple_flow_enable_memory=true
apple_flow_companion_enable_daily_digest=true
```

The companion watches for stale approvals, upcoming calendar events, overdue reminders, and synthesizes observations via AI. It respects quiet hours (22:00-07:00 by default) and rate limits.

### Advanced Configuration

See `.env.example` for all 60+ settings including:
- Rate limiting and polling intervals
- Custom workspace aliases (`@alias` routing)
- Progress streaming for long tasks
- File attachment support
- Ambient context scanning
- Follow-up scheduling

---

## Architecture Overview

```
iMessage -> Ingress -> Policy -> Orchestrator -> Connector -> Egress -> iMessage
                                      |                         |
Email -> MailIngress ----------------+                    MailEgress -> Email
Reminders -> RemindersIngress -------+               RemindersEgress -> Reminders
Notes -> NotesIngress ---------------+                  NotesEgress -> Notes
Calendar -> CalendarIngress ---------+               CalendarEgress -> Calendar
POST /task -> FastAPI ---------------+
                                      |
                                  Store (SQLite)
                                      |
                              CompanionLoop (optional, proactive)
                                      |
                              AmbientScanner (optional, passive)
```

- **Ingress modules**: Read from macOS app databases/AppleScript
- **Policy**: Enforces sender allowlist and rate limits
- **Orchestrator**: Routes commands and manages approvals
- **Connector**: Stateless CLI per turn -- `codex exec`, `claude -p`, `gemini -p`, or `cline -y`
- **Store**: Persists sessions, runs, approvals, and scheduled actions
- **Egress modules**: Send replies via AppleScript to each Apple app
- **CompanionLoop**: Proactive observations, daily digests, weekly reviews
- **AmbientScanner**: Passive context enrichment from Notes/Calendar/Mail

For full architecture details, see [CLAUDE.md](../CLAUDE.md) or [AGENTS.md](../AGENTS.md).

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/dkyazzentwatwa/apple-flow/issues)
- **Logs**: Check terminal output for errors
- **Tests**: Run `pytest -v` to verify installation

## License

See `LICENSE` file for details.
