<div align="center">

# Apple Flow

**Your Apple-Native AI Assistant**

Control AI from iMessage, Mail, Reminders, Notes, and Calendar on macOS.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos)
[![GitHub release](https://img.shields.io/github/v/release/dkyazzentwatwa/apple-flow?include_prereleases)](https://github.com/dkyazzentwatwa/apple-flow/releases)

**[apple-flow-site.vercel.app](https://apple-flow-site.vercel.app/)**

</div>

Apple Flow is a local-first macOS daemon that bridges Apple apps to AI CLIs (Codex, Claude, Gemini, Cline, and Kilo). It enforces sender allowlists, approval gates for mutating work, and workspace restrictions by default.

## Start Here

Choose one setup path:

| Path | Best for | Time | Entry point |
|---|---|---:|---|
| **AI-guided setup (recommended)** | Most users, safest onboarding | ~10 min | [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md) |
| **One-command script** | Fast local install/autostart | ~5-10 min | `./scripts/setup_autostart.sh` |
| **Manual setup** | Advanced/custom environments | ~15+ min | [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md), [docs/ENV_SETUP.md](docs/ENV_SETUP.md) |

## Quick Start (AI-Guided)

### 1) Prerequisites

- macOS with iMessage signed in
- 10 minutes
- Homebrew + Python 3.11 + Node

```bash
# Install Homebrew (if needed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python + Node
brew install python@3.11 node
```

### 2) Install One AI CLI Connector

Pick one:

- Claude CLI

```bash
curl -fsSL https://claude.ai/install.sh | bash
claude auth login
```

- Codex CLI

```bash
npm install -g @openai/codex
codex login
```

- Gemini CLI

```bash
npm install -g @google/gemini-cli
gemini auth login
```

- Cline CLI

```bash
npm install -g cline
cline auth
```

- Kilo CLI (optional advanced connector)

```bash
npm install -g @kilocode/cli
kilo auth login
```

### 3) Clone + Bootstrap

```bash
git clone https://github.com/dkyazzentwatwa/apple-flow.git
cd apple-flow
./scripts/setup_autostart.sh
```

### 4) Finalize Config with the Master Prompt

Open your AI CLI and paste:

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)

That flow handles:

- health checks (`wizard doctor --json`)
- full `.env` generation from `.env.example`
- explicit confirmation gates before writes/restarts
- gateway resource setup (Reminders/Notes/Calendar)
- validation + service status verification

### 5) Grant Full Disk Access

1. Open `System Settings -> Privacy & Security -> Full Disk Access`
2. Add the Python binary used by Apple Flow (the setup output shows the path)
3. Enable the toggle

### 6) Smoke Test

Text yourself in iMessage:

```text
what files are in my home directory?
```

You should receive a reply within seconds.

## Setup Paths (Detailed)

### A) One-command script only

If you do not want AI-guided setup:

```bash
./scripts/setup_autostart.sh
```

If `.env` is missing, it launches `python -m apple_flow setup` to generate one.

### B) Manual setup

Edit `.env` directly:

```bash
nano .env
```

Minimum keys:

```env
apple_flow_allowed_senders=+15551234567
apple_flow_allowed_workspaces=/Users/you/code
apple_flow_default_workspace=/Users/you/code
apple_flow_connector=claude-cli
apple_flow_admin_api_token=<long-random-secret>
```

Then validate and restart:

```bash
python -m apple_flow config validate --json --env-file .env
python -m apple_flow service restart --json
python -m apple_flow service status --json
```

## Core Commands

| Command | What it does |
|---|---|
| `<anything>` | Natural chat |
| `idea: <prompt>` | Brainstorming |
| `plan: <goal>` | Plan only (no changes) |
| `task: <instruction>` | Mutating task (approval required) |
| `project: <spec>` | Multi-step task (approval required) |
| `approve <id>` / `deny <id>` / `deny all` | Approval controls |
| `status` / `status <run_or_request_id>` | Run/request status |
| `health` | Daemon health |
| `history: [query]` | Message history |
| `usage` | Usage stats |
| `help` | Help + practical tips |
| `system: mute` / `system: unmute` | Companion controls |
| `system: stop` / `system: restart` / `system: kill provider` | Runtime controls |
| `system: cancel run <run_id>` | Cancel one run |
| `system: killswitch` | Kill all active provider processes |

### Multi-workspace routing

Prefix with `@alias`:

```text
task: @web-app deploy to staging
@api show recent errors
```

## Optional Integrations

All optional gateways are off by default.

Trigger behavior:

- Default trigger tag is `!!agent`
- For Mail/Reminders/Notes/Calendar, only items containing that tag are processed
- Tag is stripped before prompt execution
- Configure via `apple_flow_trigger_tag`

Enable examples:

```env
apple_flow_enable_mail_polling=true
apple_flow_enable_reminders_polling=true
apple_flow_enable_notes_polling=true
apple_flow_enable_calendar_polling=true
```

Companion + memory examples:

```env
apple_flow_enable_companion=true
apple_flow_enable_memory=true

# Canonical memory v2 rollout (safe defaults)
apple_flow_enable_memory_v2=false
apple_flow_memory_v2_shadow_mode=true
apple_flow_memory_v2_migrate_on_start=true
```

See full settings in [docs/ENV_SETUP.md](docs/ENV_SETUP.md).

## AI Backends

| Connector | Key |
|---|---|
| Claude CLI | `apple_flow_connector=claude-cli` |
| Codex CLI | `apple_flow_connector=codex-cli` |
| Gemini CLI | `apple_flow_connector=gemini-cli` |
| Cline CLI | `apple_flow_connector=cline` |
| Kilo CLI | `apple_flow_connector=kilo-cli` |

Notes:

- `codex-cli`, `claude-cli`, and `gemini-cli` run stateless commands.
- `cline` is agentic and supports multiple providers.
- `kilo-cli` is supported as a connector, but setup wizard `generate-env` currently validates only `claude-cli`, `codex-cli`, `gemini-cli`, and `cline`. For `kilo-cli`, set connector fields via manual config write after generation.

## Agent Teams

Apple Flow includes codex-native multi-agent presets under `agents/teams/`.

Natural iMessage usage:

- `list available agent teams`
- `load up the codebase-exploration-team and research new features`
- `what team is active`
- `unload team`

Explicit forms:

- `system: teams list`
- `system: team load <slug>`
- `system: team current`
- `system: team unload`

Details: [docs/AGENT_TEAMS.md](docs/AGENT_TEAMS.md)

## Optional macOS App

A local Swift onboarding/dashboard app is bundled:

- app bundle: `dashboard-app/AppleFlow.app`
- distributable zip: `dashboard-app/AppleFlowApp-macOS.zip`

Or build/export from source docs: [docs/MACOS_GUI_APP_EXPORT.md](docs/MACOS_GUI_APP_EXPORT.md)

## Security Defaults

- Sender allowlist enforcement
- Workspace restrictions
- Approval workflow for mutating tasks
- Approval sender verification
- Rate limiting
- Read-only iMessage DB access
- Duplicate outbound suppression

Details: [SECURITY.md](SECURITY.md)

## Service Management

```bash
launchctl start local.apple-flow
launchctl stop local.apple-flow
launchctl list local.apple-flow
tail -f logs/apple-flow.err.log
./scripts/uninstall_autostart.sh
```

## Documentation

- [docs/AI_INSTALL_MASTER_PROMPT.md](docs/AI_INSTALL_MASTER_PROMPT.md)
- [docs/AUTO_START_SETUP.md](docs/AUTO_START_SETUP.md)
- [docs/BEGINNER_SETUP_10_MIN.md](docs/BEGINNER_SETUP_10_MIN.md)
- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/ENV_SETUP.md](docs/ENV_SETUP.md)
- [docs/AGENT_TEAMS.md](docs/AGENT_TEAMS.md)
- [docs/SKILLS_AND_MCP.md](docs/SKILLS_AND_MCP.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
