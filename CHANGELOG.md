# Changelog

All notable changes to Apple Flow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release preparation
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
| 0.1.0 | 2026-02-19 | Initial public release |

---

[Unreleased]: https://github.com/dkyazzentwatwa/apple-flow/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dkyazzentwatwa/apple-flow/releases/tag/v0.1.0