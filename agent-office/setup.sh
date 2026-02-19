#!/usr/bin/env bash
# setup.sh — Agent Office workspace bootstrap
# Idempotently scaffolds all folders, intro stubs, canonical files, and templates.
# Safe to run on an existing workspace: never overwrites existing files.

set -euo pipefail

ROOT="$PWD"
CREATED=()
SKIPPED=()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
write_if_missing() {
  local path="$1"
  local content="$2"
  if [[ -e "$path" ]]; then
    SKIPPED+=("$path")
  else
    mkdir -p "$(dirname "$path")"
    printf '%s' "$content" > "$path"
    CREATED+=("$path")
  fi
}

make_dir() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    SKIPPED+=("$dir/")
  else
    mkdir -p "$dir"
    CREATED+=("$dir/")
  fi
}

# ---------------------------------------------------------------------------
# 1. Folders
# ---------------------------------------------------------------------------
for folder in 00_inbox 10_daily 20_projects 30_areas 40_resources \
              50_archive 60_memory 70_playbooks 80_automation 90_logs templates; do
  make_dir "$ROOT/$folder"
done

# ---------------------------------------------------------------------------
# 2. intro.md stubs
# ---------------------------------------------------------------------------
write_if_missing "$ROOT/00_inbox/intro.md" \
'# 00_inbox

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
'

write_if_missing "$ROOT/10_daily/intro.md" \
'# 10_daily

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
'

write_if_missing "$ROOT/20_projects/intro.md" \
'# 20_projects

## Purpose
Active project folders. One subfolder per project with a brief.md.

## What Goes Here
- `brief.md` created from `templates/project-brief.md`.
- Supporting task notes within the project subfolder.

## What Does Not Go Here
- Completed or abandoned projects (move to 50_archive/).

## Maintenance Cadence
- Review during weekly run; move stale projects to archive.
'

write_if_missing "$ROOT/30_areas/intro.md" \
'# 30_areas

## Purpose
Ongoing life and work responsibilities.

## What Goes Here
- Baseline notes for stable domains: health, finance, ops, learning.

## What Does Not Go Here
- Project-specific deliverables or time-boxed work.

## Maintenance Cadence
- Review and update during weekly run.
'

write_if_missing "$ROOT/40_resources/intro.md" \
'# 40_resources

## Purpose
Reference material and reusable notes.

## What Goes Here
- Research notes, references, reusable how-tos.

## What Does Not Go Here
- Active project work or daily notes.

## Maintenance Cadence
- Add as needed; review during weekly run.
'

write_if_missing "$ROOT/50_archive/intro.md" \
'# 50_archive

## Purpose
Completed or inactive material.

## What Goes Here
- Notes moved from active zones after summarizing or categorizing.

## What Does Not Go Here
- Live work; nothing deleted directly here.

## Maintenance Cadence
- Receive items during weekly archive hygiene run.
'

write_if_missing "$ROOT/60_memory/intro.md" \
'# 60_memory

## Purpose
Modular long-term memory pages, one file per topic.

## What Goes Here
- Topic memory files created from `templates/memory-entry.md`.

## What Does Not Go Here
- Session-specific context or speculative notes.

## Maintenance Cadence
- Update when durable facts are confirmed; deduplicate weekly.
'

write_if_missing "$ROOT/70_playbooks/intro.md" \
'# 70_playbooks

## Purpose
SOPs and checklists for recurring processes.

## What Goes Here
- Step-by-step procedures for repeatable operations.

## What Does Not Go Here
- One-off notes or daily logs.

## Maintenance Cadence
- Update when a process changes; review quarterly.
'

write_if_missing "$ROOT/80_automation/intro.md" \
'# 80_automation

## Purpose
Home for automation specs and routine definitions.

## What Goes Here
- Automation specs and routine definitions.
- Notes about automation behavior and expected outputs.

## What Does Not Go Here
- Manual-only process notes better suited for playbooks.

## Maintenance Cadence
- Update with each automation change; verify behavior in logs.
'

write_if_missing "$ROOT/90_logs/intro.md" \
'# 90_logs

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
'

# ---------------------------------------------------------------------------
# 3. Canonical files
# ---------------------------------------------------------------------------
write_if_missing "$ROOT/00_inbox/inbox.md" \
'# Inbox

Use this as append-only capture. Newest entries at bottom.

## Entry Format
- [ ] YYYY-MM-DD HH:MM | source | note

## Entries
'

write_if_missing "$ROOT/90_logs/automation-log.md" \
'# Automation Log

## Run Format
- YYYY-MM-DD HH:MM | schedule(hourly|daily|weekly) | action | result | notes

## Runs
'

write_if_missing "$ROOT/MEMORY.md" \
'# Memory (Durable)

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
'

# ---------------------------------------------------------------------------
# 4. Templates
# ---------------------------------------------------------------------------
write_if_missing "$ROOT/templates/capture-item.md" \
'- [ ] {{timestamp}} | {{source}} | {{note}}
'

write_if_missing "$ROOT/templates/daily-note.md" \
'# Daily Note — {{date}}

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
'

write_if_missing "$ROOT/templates/automation-run-log.md" \
'- {{timestamp}} | {{schedule}} | {{action}} | {{result}} | {{notes}}
'

write_if_missing "$ROOT/templates/weekly-review.md" \
'# Weekly Review — {{week_of}}

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
'

write_if_missing "$ROOT/templates/project-brief.md" \
'# Project Brief — {{project_name}}

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
'

write_if_missing "$ROOT/templates/memory-entry.md" \
'# Memory: {{topic}}

Last Updated: {{YYYY-MM-DD}}

## {{section}}
- {{fact_or_preference}}

## Notes
-

---
<!-- Usage: one file per topic in 60_memory/. Keep entries factual and compact. Reference from MEMORY.md if promoted to durable status. -->
'

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Agent Office setup.sh ==="
echo ""

if [[ ${#CREATED[@]} -gt 0 ]]; then
  echo "Created (${#CREATED[@]}):"
  for f in "${CREATED[@]}"; do
    echo "  + $f"
  done
else
  echo "Created: none"
fi

echo ""

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  echo "Skipped — already exists (${#SKIPPED[@]}):"
  for f in "${SKIPPED[@]}"; do
    echo "  ~ $f"
  done
else
  echo "Skipped: none"
fi

echo ""
echo "Done. Workspace is ready."
