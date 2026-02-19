# Apple Flow

A local-first daemon that bridges iMessage, Apple Mail, Apple Reminders, Apple Notes, and Apple Calendar on macOS to Claude (or Codex). Text yourself to chat with an AI, brainstorm ideas, and execute tasks in your workspace — no apps, no subscriptions beyond the AI backend.

The optional **Autonomous Companion Layer** goes further: it proactively watches your approvals, calendar, reminders, and office inbox, synthesizes observations with AI, and sends you proactive iMessage updates — like a persistent personal assistant that checks in on you, not just one that waits to be asked.

<table>
  <tr>
    <td><img src="docs/screenshots/dashboard.png" alt="Apple Flow Dashboard" width="200"/></td>
    <td><img src="docs/screenshots/ai-policy-log.png" alt="Agent Log" width="200"/></td>
    <td><img src="docs/screenshots/task-management.png" alt="Task Management" width="200"/></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/calendar-event.png" alt="Calendar Automation" width="200"/></td>
    <td><img src="docs/screenshots/office-brainstorm.png" alt="Office Brainstorm" width="200"/></td>
    <td></td>
  </tr>
</table>

---

## Complete Beginner Setup

### What you need before starting

- A Mac with iMessage signed in and working
- About 10 minutes

---

### Step 1 — Install Homebrew

Homebrew is the package manager for macOS. Open **Terminal** and run:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts. When it finishes, close and reopen Terminal.

---

### Step 2 — Install Python and Node

```bash
brew install python@3.11 node
```

---

### Step 3 — Install an AI CLI and authenticate

Pick one (or both — you can switch later via `.env`):

**Option A — Claude CLI (recommended)**
```bash
curl -fsSL https://claude.ai/install.sh | bash
claude auth login
```

**Option B — Codex CLI**
```bash
npm install -g @openai/codex
codex login
```

Both open a browser window to authenticate. Claude uses your Anthropic account; Codex uses your OpenAI account.

---

### Step 4 — Clone the repo

```bash
git clone https://github.com/your-org/apple-flow.git
cd apple-flow
```

---

### Step 4b — Bootstrap the agent-office workspace (optional, for Companion)

If you plan to use the Autonomous Companion Layer, run this once after cloning:

```bash
cd agent-office && bash setup.sh && cd ..
```

This creates the folder structure for memory, daily notes, project briefs, and automation playbooks. Personal content is gitignored — only the scaffold and `SOUL.md` are tracked.

---

### Step 5 — Run the one-command setup

```bash
./scripts/setup_autostart.sh
```

The script will:
1. Create a Python virtual environment and install dependencies
2. Copy `.env.example` → `.env` and auto-detect your `claude` binary
3. **Pause and ask you to edit `.env`** (do this now — see next step)
4. Install a background service that auto-starts apple-flow on every boot

---

### Step 6 — Edit `.env`

When the script pauses, open `.env` in any text editor. The only two fields you must set:

```env
apple_flow_allowed_senders=+15551234567       # your own phone number in +1... format
apple_flow_allowed_workspaces=/Users/you/     # folder(s) the AI can read/write
apple_flow_connector=claude-cli               # use Claude (not Codex)
```

Save and press Enter in the terminal to continue.

---

### Step 7 — Grant Full Disk Access

Apple Flow needs permission to read your iMessage database. The script will print the exact Python binary path at the end. Use it here:

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click **+**
3. Press `Cmd+Shift+G`, paste the path the script printed, click **Open**
4. Enable the toggle next to it

Then restart the service:

```bash
launchctl stop local.apple-flow
launchctl start local.apple-flow
```

---

### Step 8 — Text yourself

Open Messages on your Mac or iPhone and send yourself any message — no special prefix needed:

```
what files are in my home directory?
```

You should get a reply within a few seconds.

---

### Verify it's running

```bash
launchctl list | grep apple-flow      # should show a PID
tail -f logs/apple-flow.err.log       # watch live activity
```

---

## Commands

Send any of these to yourself via iMessage (or email, if mail integration is enabled):

| Command | What it does |
|---------|-------------|
| `<anything>` | Chat — just talk, no prefix needed |
| `idea: <prompt>` | Brainstorming and options |
| `plan: <goal>` | Implementation plan, no file changes |
| `task: <instruction>` | Queues a task, asks for approval before executing |
| `project: <spec>` | Full project pipeline with approval gate |
| `approve <id>` | Execute a queued task |
| `deny <id>` | Cancel a queued task |
| `deny all` | Cancel all pending approvals at once |
| `status` | Show pending approvals |
| `health:` | Daemon uptime, session count, run states |
| `history: [query]` | Recent messages or keyword search |
| `clear context` | Reset conversation and start fresh |
| `system: mute` | Silence companion proactive messages |
| `system: unmute` | Re-enable companion proactive messages |
| `system: stop` | Gracefully shut down the daemon |
| `system: restart` | Shut down (launchd auto-restarts) |

**Multi-workspace routing** — prefix any command with `@alias` to target a specific workspace:
```
task: @web-app deploy to staging
@api show recent errors
```

---

## Service Management

```bash
# Start / stop / restart
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl stop local.apple-flow && launchctl start local.apple-flow

# Check status
launchctl list local.apple-flow

# View logs
tail -f logs/apple-flow.err.log    # all daemon output
tail -f logs/apple-flow.log        # stdout

# Uninstall auto-start
./scripts/uninstall_autostart.sh
```

---

## Optional Integrations

### Apple Mail

Reply to emails with Claude:

```env
apple_flow_enable_mail_polling=true
apple_flow_mail_allowed_senders=you@example.com
apple_flow_mail_from_address=you@example.com
```

### Apple Reminders

Incomplete reminders in a list become tasks:

```env
apple_flow_enable_reminders_polling=true
apple_flow_reminders_list_name=agent-task
```

### Apple Notes

Notes tagged `!!agent` in a folder become tasks:

```env
apple_flow_enable_notes_polling=true
apple_flow_notes_folder_name=Codex Inbox
```

### Apple Calendar

Events in a calendar become scheduled tasks when due:

```env
apple_flow_enable_calendar_polling=true
apple_flow_calendar_name=agent-schedule
```

### Notes response logging

Log every AI response as a new Note for easy review:

```env
apple_flow_enable_notes_logging=true
apple_flow_notes_log_folder_name=agent-logs
```

### Autonomous Companion

A proactive companion that checks in on you: stale approvals, upcoming calendar events, overdue reminders, and office inbox items. Synthesizes observations with AI and sends you iMessages. Respects quiet hours (22:00–07:00) and a configurable rate limit (default: 4 per hour).

First, bootstrap the workspace (one-time):

```bash
cd agent-office && bash setup.sh && cd ..
```

Then enable in `.env`:

```env
apple_flow_enable_companion=true
apple_flow_companion_poll_interval_seconds=300
apple_flow_companion_quiet_hours_start=22:00
apple_flow_companion_quiet_hours_end=07:00
apple_flow_companion_max_proactive_per_hour=4

# Optional: daily digest note written to agent-office/10_daily/
apple_flow_companion_enable_daily_digest=true
apple_flow_companion_digest_time=08:00
```

**Memory** — inject durable memory into every AI prompt:

```env
apple_flow_enable_memory=true
apple_flow_memory_max_context_chars=2000
```

**Follow-up scheduler** — automatically nudge you after task completions:

```env
apple_flow_enable_follow_ups=true
apple_flow_default_follow_up_hours=2.0
apple_flow_max_follow_up_nudges=3
```

**Ambient scanner** — passively reads Notes/Calendar/Mail every 15 min and enriches memory topics (never sends messages):

```env
apple_flow_enable_ambient_scanning=true
apple_flow_ambient_scan_interval_seconds=900
```

---

## Choosing an AI backend

Set `apple_flow_connector` in `.env`:

```env
apple_flow_connector=claude-cli    # Claude Code CLI — uses `claude -p` (recommended)
apple_flow_connector=codex-cli     # Codex — uses `codex exec` (requires `codex login`)
```

Both are stateless (one process per turn). Authenticate once:

```bash
claude auth login   # for claude-cli
codex login         # for codex-cli
```

---

## Security Defaults

- Only messages from `apple_flow_allowed_senders` are processed
- AI can only access paths in `apple_flow_allowed_workspaces`
- Mutating commands (`task:`, `project:`) require explicit approval before executing
- iMessage database is opened read-only
- Per-sender rate limiting

---

## Documentation

- **[CLAUDE.md](CLAUDE.md)** — Architecture, module reference, development guide
- **[.env.example](.env.example)** — Every config option with defaults and comments
- **[docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md)** — Detailed launchd service setup
- **[docs/ENV_SETUP.md](docs/ENV_SETUP.md)** — Full environment variable reference
- **[docs/SKILLS_AND_MCP.md](docs/SKILLS_AND_MCP.md)** — Installing global skills and MCP servers for Claude Code CLI and Codex CLI

### Skills & MCP quick reference

| | Claude Code CLI | Codex CLI |
|---|---|---|
| Global skills | `~/.claude/skills/` | `~/.agents/skills/` |
| Global MCP config | `~/.claude/settings.json` (`mcpServers`) | `~/.codex/config.toml` (`[mcp_servers.*]`) |
| Add MCP via CLI | `claude mcp add --scope user` | `codex mcp add` |

The **apple-tools MCP** (`apple-tools-mcp`) adds semantic search over Apple Mail, Messages, and Calendar to both CLIs. Install it globally — see [docs/SKILLS_AND_MCP.md](docs/SKILLS_AND_MCP.md) for step-by-step setup.
