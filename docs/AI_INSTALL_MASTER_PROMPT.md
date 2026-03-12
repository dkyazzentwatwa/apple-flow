# AI-Led Install Master Prompt

Use this when you want an AI operator (Codex/Claude/Cline/Gemini CLI) to install Apple Flow cleanly, customize it around your setup, and verify the runtime end to end without drifting into ad hoc edits.

## How To Use

1. Clone this repo and `cd` into it.
2. Open your AI CLI.
3. Paste the prompt below.
4. Confirm each mutating action when asked.

## Master Prompt (Copy/Paste)

```text
You are my installer operator for this Apple Flow repository.

Your job: install, configure, validate, and verify Apple Flow end to end using the repo’s supported commands and current config model.

Operating rules:
1. Never run destructive commands.
2. Ask for explicit confirmation before every mutating action: file writes, setup scripts, gateway creation, service install/start/stop/restart, or app launch.
3. Prefer project-native commands (`wizard`, `config`, `service`) over ad hoc file edits.
4. When a command fails, show the important output, explain the blocker, and stop for approval before trying a different fix path.
5. Keep a short running checklist with statuses: pending, in progress, done, blocked.
6. Do not invent deprecated settings or migration-only flags. Use the current connector and memory settings only.

Workflow

Phase A - Bootstrap + Baseline
1. Ask whether this is a fresh install or an update to an existing setup.
2. After confirmation, run:
   ./scripts/setup_autostart.sh
3. Then run:
   python -m apple_flow wizard doctor --json --env-file .env
4. Summarize:
   - health errors and warnings
   - detected connector binary or API endpoint
   - whether admin token is present
   - whether Messages DB access looks healthy
   - what still needs user input

Phase B - Collect Preferences Before Writing
Collect the desired values for:
- Core:
  - `apple_flow_allowed_senders`
  - `apple_flow_allowed_workspaces`
  - `apple_flow_default_workspace`
  - `apple_flow_connector` (`codex-cli` | `claude-cli` | `gemini-cli` | `cline` | `ollama` | `kilo-cli`)
  - connector command or base URL
  - `apple_flow_timezone` if non-default
- Safety and routing:
  - `apple_flow_require_chat_prefix`
  - `apple_flow_chat_prefix` if prefix mode is enabled
  - `apple_flow_trigger_tag`
- Gateways:
  - whether to enable Mail, Reminders, Notes, Calendar
  - mailbox allowlist if Mail is enabled
  - Reminders list and archive list
  - Notes task folder, archive folder, log folder
  - Calendar name
  - Notes logging toggle
- Companion and memory:
  - `apple_flow_enable_companion`
  - `apple_flow_enable_memory`
  - `apple_flow_enable_memory_v2`
  - `apple_flow_memory_v2_migrate_on_start`
- Office:
  - whether to use `agent-office`
  - `apple_flow_soul_file`
- Admin:
  - `apple_flow_admin_api_token` or permission to generate one

Phase C - Generate a Full .env Preview
1. Build one `wizard generate-env` command with the collected values. Example:
   python -m apple_flow wizard generate-env --json \
     --phone "+15551234567" \
     --workspace "/Users/me/code" \
     --connector "claude-cli" \
     --connector-command "claude" \
     --gateways "mail,reminders,notes,calendar" \
     --mail-address "me@example.com" \
     --admin-api-token "<TOKEN>" \
     --enable-agent-office \
     --soul-file "agent-office/SOUL.md" \
     --enable-notes-logging \
     --reminders-list-name "agent-task" \
     --reminders-archive-list-name "agent-archive" \
     --notes-folder-name "agent-task" \
     --notes-archive-folder-name "agent-archive" \
     --notes-log-folder-name "agent-logs" \
     --calendar-name "agent-schedule"
2. Treat `env_preview` as the baseline.
3. Present the key values that will be written.
4. Ask for confirmation before any write.

Connector note:
- `wizard generate-env` currently validates `claude-cli`, `codex-cli`, `gemini-cli`, `cline`, and `ollama`.
- If the user chooses `kilo-cli`, generate the nearest valid baseline first, then patch the connector keys in Phase D using `config write`, followed by validation.

Phase D - Write + Validate
1. After confirmation, write the chosen settings with:
   python -m apple_flow config write --json --env-file .env --set key=value ...
2. Validate with:
   python -m apple_flow config validate --json --env-file .env
3. If validation fails, stop and explain the exact fixes needed.
4. If `kilo-cli` was chosen, patch those keys now and validate again.

Phase E - Ensure Gateway Resources
1. Ask for confirmation before resource creation.
2. Run `wizard ensure-gateways` using the chosen gateway names and toggles.
3. If any resource creation or verification fails, stop and report the exact failing resource and error detail.

Phase F - Service + Runtime Verification
1. Ask for confirmation before any service mutation.
2. Restart:
   python -m apple_flow service restart --json
3. Verify:
   python -m apple_flow service status --json
4. If unhealthy, inspect:
   python -m apple_flow service logs --json --stream stderr --lines 200
5. Summarize:
   - active connector
   - enabled gateways and resolved resource names
   - companion and memory state
   - admin API state
   - log file path

Phase G - Post-Install Smoke Check
1. Provide a short test checklist for iMessage plus any enabled gateways.
2. Show a starter command set:
   - `health`
   - `help`
   - `status`
   - `task: <something small>`

Phase H - Optional Native App
1. Ask whether to run the native macOS onboarding/dashboard app.
2. If yes, ask before each command and run:
   ./apps/macos/AppleFlowApp/scripts/export_app.sh
   ./apps/macos/AppleFlowApp/scripts/run_standalone.sh
3. Mention the optional Xcode command:
   ./apps/macos/AppleFlowApp/scripts/open_in_xcode.sh

Completion criteria:
- `.env` is fully configured
- config validation passes
- requested gateways are ensured or explicitly skipped
- service status is healthy
- final summary includes exact next commands and any remaining manual permissions steps
```

## Notes

- This prompt is designed for local-first, confirmation-gated setup.
- It is safe to use on existing installations and should reconfigure without assuming a fresh clone.
- The operator should preserve explicit user choices and avoid silent defaults for critical fields.
