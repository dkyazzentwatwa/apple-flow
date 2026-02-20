# Apple Flow Automation Launchd Agents

This directory contains launchd plist templates for automated agent-office routines. These are **templates** — the actual plists are generated dynamically by `scripts/install_automation.sh` with paths specific to your system.

## Overview

Three automation agents are provided:

| Agent | Schedule | Purpose |
|-------|----------|---------|
| `local.apple-flow-hourly` | Every hour at :05 | Capture + triage, work log update, memory candidates |
| `local.apple-flow-daily-am` | Daily 08:30 | Morning planning, inbox triage, memory consolidation |
| `local.apple-flow-daily-pm` | Daily 18:00 | Shutdown reflection, missed captures, tomorrow prep |

## Prerequisites

1. **Apple Flow daemon must be running** — automation scripts check for the daemon and skip if not running
2. **AI connector configured** — set `apple_flow_connector` in your `.env` (cline, claude-cli, or codex-cli)
3. **Agent-office workspace** — default is `agent-office/` in the project root

## Installation

```bash
# Install all automation agents
./scripts/install_automation.sh

# Uninstall
./scripts/install_automation.sh --uninstall
```

The installation script:
1. Reads `apple_flow_connector` from your `.env` for consistency
2. Generates plists with correct paths in `~/Library/LaunchAgents/`
3. Loads all agents

## Manual Commands

```bash
# Check agent status
launchctl list local.apple-flow-hourly

# Run an agent manually (for testing)
launchctl start local.apple-flow-hourly

# Stop a running agent
launchctl stop local.apple-flow-hourly

# Reload after config changes
launchctl unload ~/Library/LaunchAgents/local.apple-flow-hourly.plist
launchctl load ~/Library/LaunchAgents/local.apple-flow-hourly.plist
```

## Logs

Each agent writes to two places:

1. **launchd logs** (raw output):
   - `logs/automation-hourly.log`
   - `logs/automation-daily-am.log`
   - `logs/automation-daily-pm.log`

2. **agent-office automation log** (structured):
   - `agent-office/90_logs/automation-log.md`

Log format:
```
- YYYY-MM-DD HH:MM | launchd | <action> | <result> | <notes>
```

## Customization

### Change Schedule Times

Edit the `StartCalendarInterval` in the plist templates:

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>8</integer>
    <key>Minute</key>
    <integer>30</integer>
</dict>
```

For hourly, just set the minute:
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Minute</key>
    <integer>5</integer>
</dict>
```

### Change Office Path

Set environment variable before installing:
```bash
APPLE_FLOW_OFFICE_PATH=/path/to/your/office ./scripts/install_automation.sh
```

### Use Different Connector

The scripts read `apple_flow_connector` from your `.env` file. Options:
- `cline` (default) — agentic CLI with any model provider
- `claude-cli` — Anthropic's Claude CLI
- `codex-cli` — OpenAI's Codex CLI

## How It Works

1. **launchd** triggers the wrapper script at the scheduled time
2. **Wrapper script** checks if apple-flow daemon is running
3. If daemon is running, wrapper calls the AI connector with a structured prompt
4. **AI connector** performs the routine tasks (file reads/writes)
5. Results are logged to `90_logs/automation-log.md`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Agent not running | Check `launchctl list <label>` for error codes |
| Scripts skipped | Ensure apple-flow daemon is running (`python -m apple_flow daemon`) |
| Permission denied | Run `chmod +x scripts/automation/*.sh` |
| Wrong connector | Check `apple_flow_connector` in `.env` |
| PATH issues | The install script captures your current PATH; reinstall if needed |

## Related Files

- `scripts/automation/shared-functions.sh` — Common helpers (daemon check, logging, connector selection)
- `scripts/automation/hourly-capture.sh` — Hourly routine
- `scripts/automation/daily-planning.sh` — Morning routine
- `scripts/automation/daily-shutdown.sh` — Evening routine
- `agent-office/80_automation/apple-flow-routines.md` — Routine definitions