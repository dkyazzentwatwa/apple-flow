# Agent Office

A local-first workspace for Apple Flow's autonomous companion layer. This directory serves as a second-brain for your AI companion, storing durable memory, daily notes, project briefs, and automation logs.

## What is Agent Office?

Agent Office is a structured workspace that your Apple Flow companion uses to:

- **Remember** important facts and preferences about you (MEMORY.md)
- **Track** daily work and priorities (daily notes)
- **Organize** active projects (project briefs)
- **Log** automation runs and outcomes (automation logs)
- **Capture** quick thoughts and ideas (inbox)

Everything stays local on your Mac. No cloud uploads, no external services.

## Directory Structure

| Folder | Purpose |
|--------|---------|
| `00_inbox/` | Fast capture queue for untriaged notes and ideas |
| `10_daily/` | Daily command center — one file per day (YYYY-MM-DD.md) |
| `20_projects/` | Active project work with briefs and task notes |
| `30_areas/` | Ongoing responsibilities (health, finance, ops, learning) |
| `40_resources/` | Reference material and reusable notes |
| `50_archive/` | Completed or inactive material |
| `60_memory/` | Modular long-term memory — one file per topic |
| `70_playbooks/` | SOPs and checklists for recurring processes |
| `80_automation/` | Automation specs and routine definitions |
| `90_logs/` | Audit trail of automation runs |
| `templates/` | Starter templates for daily notes, projects, etc. |

## Key Files

| File | Purpose |
|------|---------|
| `SOUL.md` | Companion identity, personality, and behavioral rules |
| `MEMORY.md` | Durable memory — important facts about you and your preferences |
| `SCAFFOLD.md` | Complete specification for recreating this workspace |
| `setup.sh` | Bootstrap script to initialize the directory structure |
| `CLAUDE.md` | AI operating instructions (if present) |

## Quick Start

Run the setup script to initialize all directories and files:

```bash
./setup.sh
```

This creates:
- All 10 numbered folders plus `templates/`
- Intro files explaining each folder's purpose
- Empty templates for daily notes, project briefs, and memory entries
- Canonical files (inbox.md, automation-log.md, MEMORY.md)

## Usage Patterns

### Daily Workflow
1. **Morning**: Companion creates a daily note from the template
2. **Throughout the day**: Capture quick notes to inbox, log work in daily note
3. **End of day**: Companion completes reflection, identifies memory updates

### Memory Management
- Companion reads MEMORY.md before each interaction
- Topic-specific memories live in `60_memory/*.md`
- Memories are factual and compact

### Automation Logging
Every automation run appends to `90_logs/automation-log.md` with:
- Timestamp
- Schedule type (hourly/daily/weekly)
- Action performed
- Result
- Notes

## Rules

1. **Timestamps**: Always use `YYYY-MM-DD HH:MM` format
2. **Inbox is append-only**: Never hard-delete entries
3. **Archive after summarizing**: Move items from active zones only after processing
4. **Memory updates must be factual**: No speculation in memory files
5. **Every run gets logged**: Automation appends to the log, always
6. **Files are the source of truth**: Not chat context

## Git

Only these files are tracked by git:
- `SCAFFOLD.md`
- `setup.sh`
- `SOUL.md`

All other content (daily notes, memory, logs) is gitignored. This is your personal workspace.

## See Also

- [Apple Flow documentation](../README.md)
- [AGENTS.md](../AGENTS.md) for complete agent instructions
- `SCAFFOLD.md` for the full recreation specification
