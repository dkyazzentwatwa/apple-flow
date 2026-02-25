# Security Policy

## Supported Versions

Apple Flow is currently in active development. Security updates are applied to the latest release only.

| Version | Supported          |
| ------- | ------------------ |
| latest  | ✅                 |
| older   | ❌ (upgrade recommended) |

## Security Model

Apple Flow is designed with **security-first principles** for local-first AI assistance on macOS.

### Core Security Features

#### 1. Sender Allowlist
- Only messages from `apple_flow_allowed_senders` are processed
- All other senders are silently ignored (optional notification available)
- Phone numbers should be in `+1...` format

#### 2. Workspace Restrictions
- AI can only access paths in `apple_flow_allowed_workspaces`
- Path traversal attempts are blocked
- Workspace aliases are resolved against the allowlist

#### 3. Approval Workflow
- **Mutating commands** (`task:`, `project:`) require explicit approval
- Each approval has a unique ID and expiration time (default: 20 minutes)
- Only the original requester can approve their own requests
- Use `deny all` to cancel all pending approvals at once

#### 4. Rate Limiting
- Per-sender message rate limiting (default: 30/minute)
- Prevents abuse and accidental spam

#### 5. Read-Only iMessage Access
- Messages database is opened in read-only mode (`mode=ro` URI)
- No writes to the iMessage database
- Full Disk Access is required but used safely

#### 6. Stateless AI Execution
- CLI connectors (`claude-cli`, `codex-cli`, `gemini-cli`, `cline`) spawn fresh processes per turn
- No persistent state that could be corrupted
- Conversation context is managed in-memory with configurable history

#### 7. Admin API Authentication
- Admin API requires a Bearer token when `apple_flow_admin_api_token` is set
- All endpoints except `/health` are protected
- Token is a shared secret configured in `.env` and never logged

#### 8. Echo Suppression
- Outbound messages are fingerprinted to prevent echo loops
- Configurable suppression window (default: 90 seconds)

### Threat Model

#### What Apple Flow Protects Against

| Threat | Mitigation |
|--------|------------|
| Unauthorized senders | Sender allowlist verification |
| Path traversal | Workspace path validation |
| Unapproved file changes | Approval workflow with sender verification |
| Message loops | Echo suppression + duplicate detection |
| Rate abuse | Per-sender rate limiting |
| Stale approvals | Approval TTL expiration |
| State corruption | Stateless CLI execution |
| Admin API abuse | Bearer token authentication |
| AppleScript injection | String escaping on all Apple app egress paths |

#### What Apple Flow Does NOT Protect Against

| Threat | Reason |
|--------|--------|
| Compromised macOS account | Apple Flow runs with user privileges |
| Malicious AI model outputs | AI behavior depends on the model provider |
| Physical device access | Local-first means data is on disk |
| Network interception | No network traffic (local-only by default) |
| Prompt injection via Apple apps | Mail/Notes/Reminders content is passed to the AI as-is |

### Data Handling

- **All data stays local** — No telemetry, no cloud uploads
- **iMessage database** — Read-only access, never modified
- **SQLite state** — Stored in `~/.codex/relay.db`
- **Agent office files** — User-editable markdown in `agent-office/` (gitignored except scaffold)
- **Memory files** — `agent-office/MEMORY.md` and `agent-office/60_memory/*.md` stay on disk
- **Attachments** — Processed in a temp directory (`/tmp/apple_flow_attachments` by default) and never persisted
- **Phone numbers** — Scrubbed from logs; stored only in SQLite sessions table
- **Logs** — Written to `logs/` directory (user-controlled)

### Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Email**: Open a GitHub Security Advisory at https://github.com/dkyazzentwatwa/apple-flow/security/advisories
2. **Do not** open a public issue for security vulnerabilities
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

#### Response Timeline

- **Initial response**: Within 48 hours
- **Triage**: Within 7 days
- **Fix timeline**: Depends on severity (critical: 7 days, high: 14 days, medium: 30 days)

### Security Best Practices for Users

1. **Limit allowed senders** — Only add your own phone number
2. **Restrict workspaces** — Only add directories the AI should access
3. **Review approvals** — Read the plan before approving `task:` or `project:` commands
4. **Keep updated** — Run `git pull` regularly for security fixes
5. **Audit logs** — Check `logs/apple-flow.err.log` periodically
6. **Secure your Mac** — Enable FileVault, use a strong password, keep macOS updated

### Security Configuration Checklist

```env
# Required for security
apple_flow_allowed_senders=+15551234567        # Your phone only
apple_flow_allowed_workspaces=/Users/you/code  # Limit AI access
apple_flow_only_poll_allowed_senders=true      # Default: true

# Recommended
apple_flow_require_chat_prefix=false           # Natural mode (or true for strict)
apple_flow_approval_ttl_minutes=20             # Shorter = more secure
apple_flow_max_messages_per_minute=30          # Prevent abuse
apple_flow_admin_api_token=<strong-random-secret>  # Protect admin API

# Optional integrations — restrict allowed senders/addresses separately
apple_flow_mail_allowed_senders=you@example.com
apple_flow_reminders_auto_approve=false        # Require approval for reminder tasks
apple_flow_notes_auto_approve=false            # Require approval for note tasks
apple_flow_calendar_auto_approve=false         # Require approval for calendar tasks
```

## Security Audit

AppleScript injection has been addressed across all egress paths (v0.2.0). All user-controlled strings are escaped before interpolation into AppleScript.

**Hardened egress modules:**

| Module | Escaping applied |
|--------|-----------------|
| `egress.py` | iMessage text: backslash + quote + newline |
| `mail_egress.py` | Body, subject, recipient, from-address |
| `notes_egress.py` | Folder name, note text, note ID |
| `reminders_egress.py` | Reminder title and annotation |
| `calendar_egress.py` | Event description and annotation |
| `apple_tools.py` | CLI tool invocation via AppleScript |

A formal third-party audit is still recommended before production use at scale.

---

**Last updated**: 2026-02-20
