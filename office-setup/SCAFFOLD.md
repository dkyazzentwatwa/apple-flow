# SCAFFOLD.md — Codex Office AI Recreation Spec

An AI reads this document and follows the numbered Recreation Steps at the end to rebuild the workspace from scratch.

---

## Workspace Identity

| Field | Value |
|---|---|
| Owner | `cypher-server` |
| Path | `/Users/Shared/codex-office` |
| Purpose | Local-first second-brain: fast capture, daily execution, durable memory, automation audit trail |

**Non-Negotiables**
1. Timestamps always in `YYYY-MM-DD HH:MM` format.
2. Inbox is append-only — never hard-delete.
3. Archive only after summarizing or categorizing.
4. Memory updates must be factual and compact.
5. Every automation run logs to `90_logs/automation-log.md`.
6. Source of truth is files, not chat context.

---

## Folder Manifest

| Folder | Purpose | Canonical Files | What Belongs | What Doesn't |
|---|---|---|---|---|
| `00_inbox/` | Fast capture queue | `inbox.md` | Raw appended entries, untriaged captures | Finalized plans, archived notes, deletions |
| `10_daily/` | Daily command center | `YYYY-MM-DD.md` | Top 3, open loops, work log, reflection, inbox triage | Long-form project docs, reference material |
| `20_projects/` | Active project work | `<project>/brief.md` | Project brief, task notes per project | Completed/abandoned projects (move to archive) |
| `30_areas/` | Ongoing responsibilities | area baseline notes | Health, finance, ops, learning domains | Project-specific deliverables |
| `40_resources/` | Reference material | — | Reusable notes, research, references | Active project work or daily notes |
| `50_archive/` | Completed/inactive | — | Anything moved out of active zones after summarizing | Live work; nothing deleted directly here |
| `60_memory/` | Modular long-term memory | topic `.md` files | One file per memory topic, factual and compact | Session-specific or speculative notes |
| `70_playbooks/` | SOPs and checklists | — | Repeatable operating procedures, checklists | One-off notes or daily logs |
| `80_automation/` | Automation specs | `codex-app-routines.md` | Automation specs, routine definitions | Manual-only process notes (use playbooks) |
| `90_logs/` | Automation audit trail | `automation-log.md` | Timestamped run results, actions, blockers | Planning notes or durable memory |
| `templates/` | Note templates | 6 template files | Starter templates only | Filled-in notes or live content |

---

## Canonical File Initial States

### `00_inbox/inbox.md`
```markdown
# Inbox

Use this as append-only capture. Newest entries at bottom.

## Entry Format
- [ ] YYYY-MM-DD HH:MM | source | note

## Entries
```

### `90_logs/automation-log.md`
```markdown
# Automation Log

## Run Format
- YYYY-MM-DD HH:MM | schedule(hourly|daily|weekly) | action | result | notes

## Runs
```

### `MEMORY.md`
```markdown
# Memory (Durable)

Last Updated: YYYY-MM-DD

## Identity & Preferences
-

## Active Goals
-

## Projects Snapshot
-

## Working Style
-

## Constraints / Guardrails
- Use local timestamps in `YYYY-MM-DD HH:MM` format.
- Keep inbox append-only; do not auto-delete captured items.

## Open Questions
-
```

---

## Template Contents

### `templates/capture-item.md`
```markdown
- [ ] {{timestamp}} | {{source}} | {{note}}
```

### `templates/daily-note.md`
```markdown
# Daily Note — {{date}}

## Top 3 Priorities
1.
2.
3.

## Calendar & Commitments
-

## Open Loops
-

## Inbox Triage (from 00_inbox)
- Keep:
- Do:
- Delegate:
- Archive:

## Work Log
- HH:MM -

## Memory Delta (candidate durable updates)
-

## End-of-Day Reflection
- Wins:
- Blockers:
- Carry forward:
```

### `templates/automation-run-log.md`
```markdown
- {{timestamp}} | {{schedule}} | {{action}} | {{result}} | {{notes}}
```

### `templates/weekly-review.md`
```markdown
# Weekly Review — {{week_of}}

## What shipped
-

## What stalled
-

## Inbox + Backlog cleanup
-

## Projects health check
- Green:
- Yellow:
- Red:

## Next week focus
1.
2.
3.

## Memory updates
- Add:
- Remove:
- Refine:
```

### `templates/project-brief.md`
```markdown
# Project Brief — {{project_name}}

Status: active
Last Updated: {{YYYY-MM-DD}}

## Outcome

## Why Now

## Scope
- In:
- Out:

## Milestones
- [ ] M1:
- [ ] M2:
- [ ] M3:

## Risks
-

## Next Actions
- [ ]
```

### `templates/memory-entry.md`
```markdown
# Memory: {{topic}}

Last Updated: {{YYYY-MM-DD}}

## {{section}}
- {{fact_or_preference}}

## Notes
-

---
<!-- Usage: one file per topic in 60_memory/. Keep entries factual and compact. Reference from MEMORY.md if promoted to durable status. -->
```

---

## Governing Documents

Copy the following files verbatim from the source workspace. Do not auto-generate their content — they are maintained by the owner and define the operating contract for the workspace:

- `CLAUDE.md` — AI operating instructions, automation schedule, working style
- `AGENTS.md` — agent mission, non-negotiables, file responsibilities, automation schedules
- `README.md` — human-readable workspace overview and quick start

---

## Recreation Steps

Follow these steps in order to rebuild the workspace from zero:

1. **Create root directory** at the target path (e.g. `/Users/Shared/codex-office`).

2. **Create all 10 numbered folders** plus `templates/`:
   ```
   00_inbox/
   10_daily/
   20_projects/
   30_areas/
   40_resources/
   50_archive/
   60_memory/
   70_playbooks/
   80_automation/
   90_logs/
   templates/
   ```

3. **Create intro.md in each numbered folder** using the content below. Do not create one in `templates/`.

   `00_inbox/intro.md`:
   ```markdown
   # 00_inbox

   ## Purpose
   Fast capture zone for unprocessed notes and ideas.

   Canonical file: `inbox.md`

   ## What Goes Here
   - Raw entries appended to `00_inbox/inbox.md`.
   - Untriaged captures from automation or manual entry.

   ## What Does Not Go Here
   - Finalized project plans, durable memory, or archived notes.
   - Deletions of old items (inbox is append-only).

   ## Maintenance Cadence
   - Hourly append.
   - Daily triage into keep/do/delegate/archive in the daily note.
   ```

   `10_daily/intro.md`:
   ```markdown
   # 10_daily

   ## Purpose
   Daily command center. One file per day named YYYY-MM-DD.md.

   ## What Goes Here
   - Daily notes created from `templates/daily-note.md`.
   - Top 3 priorities, open loops, work log, inbox triage, reflection.

   ## What Does Not Go Here
   - Long-form project docs or reference material.

   ## Maintenance Cadence
   - Create at 08:30 daily automation run.
   - Update hourly with work log and open loops.
   - Complete reflection at 18:00 shutdown run.
   ```

   `20_projects/intro.md`:
   ```markdown
   # 20_projects

   ## Purpose
   Active project folders. One subfolder per project with a brief.md.

   ## What Goes Here
   - `brief.md` created from `templates/project-brief.md`.
   - Supporting task notes within the project subfolder.

   ## What Does Not Go Here
   - Completed or abandoned projects (move to 50_archive/).

   ## Maintenance Cadence
   - Review during weekly run; move stale projects to archive.
   ```

   `30_areas/intro.md`:
   ```markdown
   # 30_areas

   ## Purpose
   Ongoing life and work responsibilities.

   ## What Goes Here
   - Baseline notes for stable domains: health, finance, ops, learning.

   ## What Does Not Go Here
   - Project-specific deliverables or time-boxed work.

   ## Maintenance Cadence
   - Review and update during weekly run.
   ```

   `40_resources/intro.md`:
   ```markdown
   # 40_resources

   ## Purpose
   Reference material and reusable notes.

   ## What Goes Here
   - Research notes, references, reusable how-tos.

   ## What Does Not Go Here
   - Active project work or daily notes.

   ## Maintenance Cadence
   - Add as needed; review during weekly run.
   ```

   `50_archive/intro.md`:
   ```markdown
   # 50_archive

   ## Purpose
   Completed or inactive material.

   ## What Goes Here
   - Notes moved from active zones after summarizing or categorizing.

   ## What Does Not Go Here
   - Live work; nothing deleted directly here.

   ## Maintenance Cadence
   - Receive items during weekly archive hygiene run.
   ```

   `60_memory/intro.md`:
   ```markdown
   # 60_memory

   ## Purpose
   Modular long-term memory pages, one file per topic.

   ## What Goes Here
   - Topic memory files created from `templates/memory-entry.md`.

   ## What Does Not Go Here
   - Session-specific context or speculative notes.

   ## Maintenance Cadence
   - Update when durable facts are confirmed; deduplicate weekly.
   ```

   `70_playbooks/intro.md`:
   ```markdown
   # 70_playbooks

   ## Purpose
   SOPs and checklists for recurring processes.

   ## What Goes Here
   - Step-by-step procedures for repeatable operations.

   ## What Does Not Go Here
   - One-off notes or daily logs.

   ## Maintenance Cadence
   - Update when a process changes; review quarterly.
   ```

   `80_automation/intro.md`:
   ```markdown
   # 80_automation

   ## Purpose
   Home for automation specs and routine definitions.

   ## What Goes Here
   - Automation specs and routine definitions.
   - Notes about automation behavior and expected outputs.

   ## What Does Not Go Here
   - Manual-only process notes better suited for playbooks.

   ## Maintenance Cadence
   - Update with each automation change; verify behavior in logs.
   ```

   `90_logs/intro.md`:
   ```markdown
   # 90_logs

   ## Purpose
   Audit trail of automation runs and outcomes.

   Canonical file: `automation-log.md`

   ## What Goes Here
   - `90_logs/automation-log.md` entries with timestamped run results.
   - Concise outcomes, actions, and blockers.

   ## What Does Not Go Here
   - Long-form planning notes or durable memory content.

   ## Maintenance Cadence
   - Append at every run (hourly/daily/weekly/manual).
   ```

4. **Create canonical files** using the verbatim initial states in the Canonical File Initial States section above:
   - `00_inbox/inbox.md`
   - `90_logs/automation-log.md`
   - `MEMORY.md`

5. **Create all 6 template files** using verbatim content from the Template Contents section above:
   - `templates/capture-item.md`
   - `templates/daily-note.md`
   - `templates/automation-run-log.md`
   - `templates/weekly-review.md`
   - `templates/project-brief.md`
   - `templates/memory-entry.md`

6. **Copy governing documents** from the source workspace verbatim:
   - `CLAUDE.md`
   - `AGENTS.md`
   - `README.md`

7. **Verify** the workspace matches this manifest:
   - All 10 numbered folders exist plus `templates/`.
   - Each numbered folder has an `intro.md`.
   - `00_inbox/inbox.md`, `90_logs/automation-log.md`, and `MEMORY.md` exist with correct headers.
   - All 6 template files exist in `templates/`.
   - `CLAUDE.md`, `AGENTS.md`, `README.md`, and `SCAFFOLD.md` exist at root.
   - No live user content was overwritten.
