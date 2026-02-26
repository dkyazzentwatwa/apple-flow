# Changelog

All notable changes to Apple Flow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-26

### Added
- **Codex agent-team library**: Added `/agents` with cataloged multi-agent team presets (ops, software/GTM, and business ops categories), plus activation/list scripts under `scripts/agents/`.
- **Kilo CLI connector**: Added `kilo_cli_connector.py` and wired it through config, daemon selection, and connector tests.
- **iMessage help command**: Added an in-chat help command with usage tips and documentation pointers.
- **Emergency stop controls**: Added a process-registry-backed killswitch and run-level cancellation support across CLI connectors.
- **Companion startup observability**: Added companion startup greeting and health visibility signals.
- **Mail owner forwarding**: Added automatic iMessage forwarding of Apple Mail responses to the configured owner sender.
- **AI-led onboarding flow**: Added install master prompt docs and onboarding-driven setup flows in CLI/setup paths.

### Changed
- **System restart behavior**: Updated `system: restart` flows to use `launchctl stop`/`kickstart` semantics for cleaner auto-restart behavior with startup feedback.
- **Approval execution lifecycle**: Improved approval execution reliability and live status visibility across daemon/orchestrator/store/admin paths.
- **Provider and connector controls**: Expanded provider controls and connector configuration handling (including Gemini-oriented config improvements).
- **Auto-start service management**: Updated setup/install/uninstall scripts to manage daemon and admin launchd services more reliably.
- **Help output UX**: Enhanced help output with system command guidance and richer formatting.
- **Ingress performance**: Optimized Calendar and Reminders ingress parsing paths.
- **Apple Mail tooling updates**: Updated Apple Mail-related tool plumbing and command handling in app tools/entry flow.
- **Distribution refresh**: Refreshed packaged macOS app artifacts and onboarding assets/screenshots.

### Fixed
- **Mail gateway JSON handling**: Fixed mail gateway payload parsing and iMessage feedback behavior.
- **Mail echo loop and signatures**: Fixed outbound mail echo-loop behavior and corrected `\n` signature rendering.
- **Long-task stability**: Improved long-running task reliability and status responsiveness.
- **Python 3.14 shutdown handling**: Fixed shutdown-time cancellation handling for newer Python runtime behavior.
- **Restart echo side-effect**: Fixed restart echo messages incorrectly triggering health auto-replies.
- **Gemini approval mode**: Fixed Gemini CLI approval-mode wiring and validation behavior.
- **Gemini response leakage**: Fixed Gemini replies leaking planning narration into user-facing responses.
- **CI lint ordering**: Fixed Ruff import-order issues affecting CI consistency.
- **Type hygiene**: Applied additional type-level cleanups in connector and office-sync paths.

### Documentation
- Added prompt-pack documentation for multiple user levels.
- Added `!!agent` trigger-tag guidance for non-iMessage prompt packs.
- Expanded and refreshed README/Quickstart/ENV/setup guidance across recent onboarding and provider updates.
- Added/updated macOS GUI export docs and onboarding screenshots.
- Added docs for Codex agent teams and project-level team activation workflow.

## [0.2.1] - 2026-02-20

### Fixed
- **Cross-gateway approval verification**: Approvals from non-iMessage gateways (Notes, Reminders, Calendar) silently failed when the user tried to approve via iMessage due to sender format mismatch. Both sides of the approval sender comparison now use `normalize_sender()` for consistent E.164 matching.
- **Owner sender normalization at ingress**: `notes_ingress.py`, `reminders_ingress.py`, and `calendar_ingress.py` now normalize `owner_sender` at construction time (defense in depth).
- **Approval mismatch debug logging**: Added debug log in `approval.py` showing raw and normalized senders when verification fails, making format mismatches visible in daemon logs.

### Changed
- **Branding cleanup**: Replaced remaining Codex product-name artifacts with Apple Flow across codebase.

### Added
- **GitHub Actions CI**: Added CI workflow with ruff linting.
- **Cross-gateway approval tests**: 4 new tests in `test_approval_security.py` covering Notes/Reminders/Calendar approval via iMessage and rejection of genuinely different senders.

## [0.2.0] - 2026-02-20

### Security
- **Admin API authentication**: new `admin_api_token` config field adds `Authorization: Bearer` token auth to all admin endpoints except `/health`
- **iMessage egress AppleScript injection fix**: added newline escaping (`.replace("\n", "\\n")`) to `egress.py` `_osascript_send()`, matching all other egress modules
- **Mail ingress AppleScript injection fix**: escape double-quotes in message IDs in `mail_ingress.py` `_mark_as_read()`
- **SQL LIKE wildcard escaping**: `store.py` `search_messages()` and `apple_tools.py` `messages_search()` now escape `%` and `_` in user queries
- **PII scrubbed from tracked files**: replaced real phone number and email in `scripts/smoke_test.sh` with placeholders

### Fixed
- **Version consistency**: unified version to `0.2.0` across `pyproject.toml`, `__init__.py`, `main.py`, `codex_connector.py`, and `__main__.py`
- **CLAUDE.md stale defaults**: corrected 8 documented config defaults that diverged from actual `config.py` values (`require_chat_prefix`, `codex_cli_context_window`, `claude_cli_context_window`, `auto_context_messages`, `reminders_list_name`, `notes_folder_name`, `calendar_name`, `mail_signature`)
- **Silent exception logging**: added `logger.debug` to memory context injection failure in `orchestrator.py`

### Removed
- Unused `import re` in `mail_ingress.py`
- Unused `_ESCAPE_JSON_HANDLER` constant in `apple_tools.py`

### Documentation
- Fixed CONTRIBUTING.md table of contents link mismatch
- Added `cline_act_mode` and `admin_api_token` to `.env.example`
- Comprehensive security documentation (SECURITY.md)
- Contribution guidelines (CONTRIBUTING.md)
- PyPI package configuration

## [0.1.0] - 2026-02-19

### Added

#### Core Features
- **iMessage Integration**: Send and receive messages via iMessage using SQLite (read) and AppleScript (write)
- **Multi-Channel Support**: Apple Mail, Reminders, Notes, and Calendar integrations
- **AI Backend Support**: Claude CLI, Codex CLI, and Cline CLI connectors
- **Approval Workflow**: Explicit approval required for mutating operations (`task:`, `project:`)
- **Sender Verification**: Only original requesters can approve their own requests

#### Security Features
- **Sender Allowlist**: Only process messages from authorized phone numbers
- **Workspace Restrictions**: AI can only access designated directories
- **Rate Limiting**: Per-sender message throttling (default: 30/minute)
- **Approval Expiration**: TTL on pending approvals (default: 20 minutes)
- **Read-Only iMessage Access**: Database opened in read-only mode
- **Echo Suppression**: Prevents iMessage loops from outbound echoes

#### Companion Features
- **Proactive Observations**: Companion monitors calendar, reminders, and approvals
- **Daily Digest**: Morning briefing via iMessage
- **Weekly Review**: Comprehensive weekly summary
- **File-Based Memory**: Persistent memory in `agent-office/MEMORY.md`
- **SOUL.md Identity**: Customizable companion personality

#### Commands
- Natural language chat (no prefix required)
- `idea:` - Brainstorming and options
- `plan:` - Implementation planning
- `task:` - Queued execution with approval
- `project:` - Multi-step pipeline with approval
- `approve <id>` / `deny <id>` - Approval management
- `status` - View pending approvals
- `health:` - Daemon health check
- `history:` - Message history
- `usage` - Token usage statistics (ccusage)
- `system: mute/unmute/stop/restart` - System controls

#### Infrastructure
- **launchd Service**: Auto-start on boot via `scripts/setup_autostart.sh`
- **SQLite State**: Persistent storage for sessions, approvals, and events
- **Comprehensive Logging**: All activity logged to `logs/apple-flow.err.log`

### Documentation
- README.md with beginner-friendly setup guide
- QUICKSTART.md for rapid onboarding
- ENV_SETUP.md with full configuration reference
- AUTO_START_SETUP.md for launchd configuration
- SKILLS_AND_MCP.md for skills and MCP integration

### Testing
- 42 test files with ~7,856 lines of test code
- Security tests for approval workflow and sender verification
- Integration tests for all Apple app channels
- Connector tests for CLI backends

---

## Version History Summary

| Version | Date | Highlights |
|---------|------|------------|
| 0.3.0 | 2026-02-26 | Codex agent teams, Kilo connector, reliability/ops improvements |
| 0.2.1 | 2026-02-20 | Cross-gateway approval fix, CI, branding cleanup |
| 0.2.0 | 2026-02-20 | Security hardening, admin API auth, version unification |
| 0.1.0 | 2026-02-19 | Initial public release |

---

[Unreleased]: https://github.com/dkyazzentwatwa/apple-flow/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/dkyazzentwatwa/apple-flow/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/dkyazzentwatwa/apple-flow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/dkyazzentwatwa/apple-flow/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dkyazzentwatwa/apple-flow/releases/tag/v0.1.0
