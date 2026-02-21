# Skills & MCP Configuration

This page covers how to install global skills (slash commands) and MCP servers for both **Claude Code CLI** and **Codex CLI**, and documents the apple-tools MCP used by Apple Flow.

---

## Skills (Slash Commands)

Skills are `SKILL.md` files that define custom slash commands. The directory name becomes the command name (e.g. `~/.claude/skills/deploy/SKILL.md` → `/deploy`).

### Claude Code CLI

| Scope | Path | Tracked in Git |
|-------|------|---------------|
| Global (all projects) | `~/.claude/skills/<name>/SKILL.md` | No |
| Project-level | `.claude/skills/<name>/SKILL.md` | Yes |
| Legacy commands | `.claude/commands/<name>.md` | Yes |

```bash
# Create a global skill
mkdir -p ~/.claude/skills/my-command
cat > ~/.claude/skills/my-command/SKILL.md << 'EOF'
# My Command

Description of what this slash command does.

## Steps
1. Do thing one
2. Do thing two
EOF
```

### Codex CLI

| Scope | Path |
|-------|------|
| Global (all projects) | `~/.agents/skills/<name>/SKILL.md` |
| Repo root | `$REPO_ROOT/.agents/skills/<name>/SKILL.md` |
| Local directory | `.agents/skills/<name>/SKILL.md` |
| System-wide | `/etc/codex/skills/` |

Same `SKILL.md` format as Claude Code. To disable a skill without deleting it, add to `~/.codex/config.toml` (Codex CLI only):

```toml
[[skills.config]]
path = "/path/to/skill/SKILL.md"
enabled = false
```

---

## MCP Servers

MCP (Model Context Protocol) servers give the AI access to external tools and data sources.

### Claude Code CLI

| Scope | Location |
|-------|----------|
| Global (all projects) | `mcpServers` key in `~/.claude/settings.json` |
| Project-level | `.mcp.json` at project root |

```bash
# Add a global MCP server via CLI
claude mcp add --scope user --transport stdio my-server -- npx -y my-mcp-package

# Add an HTTP-based MCP server
claude mcp add --scope user --transport http my-server https://my-server.example.com

# Add a project-scoped MCP (written to .mcp.json)
claude mcp add --scope project --transport stdio my-server -- npx -y my-mcp-package

# List configured MCP servers
claude mcp list
```

Or edit `~/.claude/settings.json` directly:

```json
{
  "mcpServers": {
    "apple-tools": {
      "command": "npx",
      "args": ["-y", "apple-tools-mcp"]
    }
  }
}
```

### Codex CLI

| Scope | Location |
|-------|----------|
| Global (all projects) | `~/.codex/config.toml` (Codex CLI only) |
| Project-level | `.codex/config.toml` (trusted projects only, Codex CLI only) |

```bash
# Add via CLI
codex mcp add apple-tools
```

Or edit `~/.codex/config.toml` directly (Codex CLI only):

```toml
[mcp_servers.apple-tools]
command = "npx"
args = ["-y", "apple-tools-mcp"]

# HTTP-based server example
[mcp_servers.my-http-server]
url = "https://my-server.example.com"
bearer_token_env_var = "MY_TOKEN"
```

---

## Side-by-Side Summary

| Feature | Claude Code CLI | Codex CLI |
|---------|----------------|-----------|
| Global skills | `~/.claude/skills/` | `~/.agents/skills/` |
| Project skills | `.claude/skills/` | `.agents/skills/` |
| Global MCP config | `~/.claude/settings.json` | `~/.codex/config.toml` (Codex CLI only) |
| Project MCP config | `.mcp.json` | `.codex/config.toml` (Codex CLI only) |
| Add MCP via CLI | `claude mcp add --scope user` | `codex mcp add` |
| MCP config format | JSON | TOML |

---

## apple-tools MCP (Global Setup)

[`apple-tools-mcp`](https://github.com/sfls1397/apple-tools-mcp) provides semantic search across Apple Mail, Messages, and Calendar — giving the AI real-time access to your local Apple data.

**Important:** Install it globally (not just project-scoped) so it's available whenever you invoke Claude or Codex from any directory.

### Install & configure for Claude Code CLI

```bash
# Install globally
npm install -g apple-tools-mcp

# Add to Claude Code global config
claude mcp add --scope user --transport stdio apple-tools -- npx -y apple-tools-mcp
```

Or add manually to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "apple-tools": {
      "command": "npx",
      "args": ["-y", "apple-tools-mcp"]
    }
  }
}
```

### Install & configure for Codex CLI

Add to `~/.codex/config.toml` (Codex CLI only):

```toml
[mcp_servers.apple-tools]
command = "npx"
args = ["-y", "apple-tools-mcp"]
```

### What apple-tools provides

| Tool | Description |
|------|-------------|
| `search_mail` | Semantic search across Apple Mail |
| `search_messages` | Semantic search across iMessages |
| `search_calendar` | Semantic search across Calendar events |

> **Note:** First run may take a few minutes to build the local vector index. The index is stored locally and is never sent to any external service.
