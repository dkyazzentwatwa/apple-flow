# Agent Office Scheduled Prompt Pack

Copy/paste prompt library for Apple Flow users who run their work from `agent-office/`.

This pack is the `agent-office` rewrite of a generic scheduled-task library. It assumes:

- Apple Flow command style: `plan:`, `task:`, `idea:`, `project:`
- Apple channels: iMessage, Notes, Reminders, Calendar
- Office-native storage under `agent-office/`, not a separate `~/ai-logs` tree
- Recurring prompts default to `plan:` so they are safe to schedule without constant approvals

If you want a prompt to update files directly, switch `plan:` to `task:` and keep the rest of the payload the same. Apple Flow will route it through approval before it writes anything.

## How to Use This

1. Copy one prompt card into your Apple Flow channel of choice.
2. Schedule the recurring ones in Calendar, Reminders, or Shortcuts if you want them automated.
3. Replace bracketed placeholders like `[PROJECT]`, `[PERSON]`, or `[TOPIC]`.
4. Keep the starter set small. Recommended first three:
   - Morning Desk Reset
   - Inbox Triage Sweep
   - Friday Weekly Review

## Office Map

Use these zones as the source of truth:

```text
agent-office/
  00_inbox/       quick capture, append-only
  10_daily/       daily notes and carry-forward context
  20_projects/    active project briefs and project notes
  30_areas/       ongoing responsibilities like ops, health, learning
  40_resources/   reusable research and reference material
  50_archive/     completed or inactive material after summarizing
  60_memory/      topic memory files, factual and compact
  70_playbooks/   SOPs and recurring process docs
  80_automation/  routine definitions and automation specs
  90_logs/        automation and audit trail
```

## Command Defaults

- Use `plan:` for recurring prompts that should return a draft, recommendation, or prioritized summary.
- Use `task:` only when you intentionally want Apple Flow to create or update files after approval.
- Use `!!agent` for prompts you schedule in Calendar, Reminders, or Notes.
- Respect `agent-office` guardrails: inbox is append-only, archive only after summarizing, memory updates must be factual, and automation runs belong in `90_logs/`.

## Daily Operations

### Morning Desk Reset
When to run: Weekdays 7:30 AM
Best channel: Calendar
Uses: Apple Calendar, Apple Mail, web search, `agent-office/10_daily/`, `agent-office/00_inbox/`
Saves to: Draft for `agent-office/10_daily/YYYY-MM-DD.md`
Outcome: A tight morning brief you can drop into the day’s note or promote to a write-back task

Prompt:

```text
!!agent plan: Build my morning desk reset for today using the agent-office daily note format.

Do these checks:
1. Pull today's calendar and flag any back-to-backs or prep-heavy meetings.
2. Review unread mail from the last 12 hours and surface the top 3 that actually need action.
3. Read agent-office/00_inbox/inbox.md and identify the most important untriaged items.
4. Read yesterday's daily note in agent-office/10_daily/ if it exists and extract carry-forward work.
5. Web search "[MY INDUSTRY] news today" and give me one useful headline.
6. Web search "weather [MY CITY] today" and give me a one-line summary.

Format the response to match these daily-note sections:
## Top 3 Priorities
## Calendar & Commitments
## Open Loops
## Inbox Triage (from 00_inbox)

Keep it mobile-readable. Max 9 bullets total.
End with: "Today's first move:"
```

Write-back variant: switch `plan:` to `task:` and add "Create or update agent-office/10_daily/[today].md using the daily-note template."

### Inbox Triage Sweep
When to run: Weekdays 9:00 AM
Best channel: Reminder or Calendar
Uses: `agent-office/00_inbox/inbox.md`, today's daily note
Saves to: Draft triage block for `agent-office/10_daily/YYYY-MM-DD.md`
Outcome: Turns raw captures into keep, do, delegate, and archive candidates without violating append-only rules

Prompt:

```text
!!agent plan: Triage agent-office inbox entries for today's operating plan.

Read agent-office/00_inbox/inbox.md.
Classify current open entries into:
- Keep
- Do
- Delegate
- Archive candidate

For each item, include:
- Short restatement
- Why it belongs in that bucket
- The smallest next action if it should move

Respect these rules:
- Do not recommend deleting inbox entries.
- Only recommend archive after a summary exists.
- Keep output brief and action-biased.

Format as the "Inbox Triage (from 00_inbox)" section for today's daily note.
End with: "10-minute triage move:"
```

### Open Loops Sweep
When to run: Daily 2:30 PM
Best channel: Calendar
Uses: Apple Mail, Apple Calendar, `agent-office/10_daily/`, `agent-office/00_inbox/`
Saves to: Draft open-loops update for the current daily note
Outcome: Finds unresolved commitments before they slip

Prompt:

```text
!!agent plan: Extract today's most important open loops from email, calendar, inbox, and the current daily note.

Check:
1. Sent or active mail threads from the last 10 days with no clear closure.
2. Calendar commitments in the next 72 hours that need prep or a follow-up.
3. agent-office/00_inbox/inbox.md for untriaged or waiting-for items.
4. Today's daily note in agent-office/10_daily/ if it exists.

Return only the top 5 open loops.
For each one, include:
- Owner or counterpart
- Context
- Urgency
- Next action

Format with these sections:
## Open Loops
## Deadline Pressure
## Dependencies

End with: "Loop to close before end of day:"
```

### End-of-Day Carry Forward
When to run: Weekdays 5:45 PM
Best channel: Calendar
Uses: today's daily note, tomorrow's calendar, active mail threads
Saves to: Draft reflection and carry-forward block for `agent-office/10_daily/YYYY-MM-DD.md`
Outcome: Closes the day cleanly and preps tomorrow

Prompt:

```text
!!agent plan: Draft my end-of-day carry-forward using the agent-office daily note structure.

Review:
1. Today's note in agent-office/10_daily/.
2. Tomorrow's calendar.
3. Any open mail threads I started today that still need a response or decision.

Return these sections:
## End-of-Day Reflection
- Wins
- Blockers
- Carry forward

Then add:
- Tomorrow's first priority
- One prep item for tomorrow's calendar

Keep it concise. Max 7 bullets.
```

Write-back variant: switch `plan:` to `task:` and add "Update today's daily note and create tomorrow's note if missing."

## Weekly Rhythm

### Monday Weekly Focus Brief
When to run: Mondays 8:00 AM
Best channel: Calendar
Uses: this week's calendar, recent daily notes, inbox, active project briefs
Saves to: Draft for `agent-office/10_daily/YYYY-MM-DD.md` or `agent-office/30_areas/weekly-focus-YYYY-MM-DD.md`
Outcome: Gives the week a mission before it gets reactive

Prompt:

```text
!!agent plan: Generate my Monday weekly focus brief from agent-office.

Review:
1. This week's calendar and note heavy or prep-sensitive days.
2. The last 3 daily notes in agent-office/10_daily/.
3. agent-office/00_inbox/inbox.md for unresolved captures.
4. Active project briefs in agent-office/20_projects/.

Output sections:
## Week at a Glance
## Open Commitments
## Blockers Older Than 5 Days
## Weekly Mission

Keep each section tight.
End with: "This week's one outcome that matters most:"
```

### Friday Weekly Review
When to run: Fridays 4:00 PM
Best channel: Calendar
Uses: this week's daily notes, active project briefs, inbox, next week's calendar
Saves to: Draft for a weekly review note using `agent-office/templates/weekly-review.md`
Outcome: Closes the loop on the week and pre-loads the next one

Prompt:

```text
!!agent plan: Draft my Friday weekly review using the agent-office weekly review structure.

Review:
1. This week's daily notes in agent-office/10_daily/.
2. agent-office/00_inbox/inbox.md for anything still unresolved.
3. Active project briefs in agent-office/20_projects/.
4. Monday through Wednesday on next week's calendar.

Return these sections:
## What shipped
## What stalled
## Inbox + Backlog cleanup
## Projects health check
## Next week focus
## Memory updates

Call out one thing to archive only if a summary already exists.
End with: "Best setup move for Monday:"
```

Write-back variant: switch `plan:` to `task:` and add "Create a weekly review note at agent-office/30_areas/weekly-review-[year]-[week].md or another existing area note you use for reviews."

### Weekly Reset and Waiting-For Review
When to run: Sundays 6:00 PM
Best channel: Reminder
Uses: inbox, recent daily notes, next week's calendar, waiting-for items
Saves to: Draft reset note for `agent-office/30_areas/weekly-reset-YYYY-MM-DD.md`
Outcome: Clears mental overhead before the next week starts

Prompt:

```text
!!agent plan: Run a weekly reset across my agent-office and identify what needs attention next week.

Review:
1. Open inbox items in agent-office/00_inbox/inbox.md.
2. Daily notes from the last 7 days.
3. Next week's calendar.
4. Any waiting-for or follow-up threads you can infer from recent context.

Classify open items as:
- Done
- Next action
- Scheduled
- Waiting for
- Someday

Then answer:
- Biggest win this week
- Biggest friction point
- Three priorities for next week
- One thing to drop or defer

Keep it readable in one screen first, details second.
```

## Project Governance

### Project Brief Health Check
When to run: Tuesdays 10:00 AM
Best channel: Calendar
Uses: `agent-office/20_projects/`
Saves to: Draft update recommendations for project briefs
Outcome: Keeps project briefs current enough to be useful

Prompt:

```text
!!agent plan: Review active project briefs in agent-office/20_projects/ and identify the ones that need a refresh.

For up to 5 active projects, report:
- Current status signal
- Missing or stale sections in the brief
- Risk if the brief stays stale
- Recommended update

Output sections:
## Healthy Briefs
## Needs Refresh
## At-Risk Projects
## First Update to Make

Prioritize by decision impact, not by alphabetical order.
```

### Stalled Project Nudge
When to run: Thursdays 3:00 PM
Best channel: Reminder
Uses: project briefs, recent daily notes, inbox
Saves to: Draft for the current daily note or project note
Outcome: Pulls neglected work back into focus before it quietly dies

Prompt:

```text
!!agent plan: Find stalled projects or project threads that need a nudge.

Review:
1. agent-office/20_projects/ briefs and notes.
2. The last 5 daily notes.
3. agent-office/00_inbox/inbox.md for lingering project-related captures.

Return the top 3 stalled items with:
- Why it is stalled
- What decision is missing
- The smallest next action
- Whether it should stay active, be delegated, or move toward archive after summary

End with: "Project to unstick this week:"
```

## Memory Hygiene

### MEMORY.md Delta Proposal
When to run: Mondays 8:30 AM
Best channel: Note
Uses: `agent-office/MEMORY.md`, recent daily notes, active projects
Saves to: Proposed factual edits for `agent-office/MEMORY.md`
Outcome: Keeps durable memory compact and current without introducing speculation

Prompt:

```text
!!agent plan: Propose factual delta updates for agent-office/MEMORY.md based on recent activity.

Review:
1. agent-office/MEMORY.md
2. The last 7 daily notes
3. Active project briefs in agent-office/20_projects/

Output sections:
## Add
## Refine
## Remove or De-emphasize

Rules:
- No speculation
- Keep statements factual and compact
- Only propose durable facts, preferences, priorities, or guardrails

End with: "Most important memory update this week:"
```

### Topic Memory Refresh
When to run: Wednesdays 9:15 AM
Best channel: Calendar
Uses: `agent-office/60_memory/`, `agent-office/40_resources/`, recent daily notes
Saves to: Proposed updates for topic memory files
Outcome: Prevents topic memory from turning into stale clutter

Prompt:

```text
!!agent plan: Recommend updates for topic memory files in agent-office/60_memory/.

Review:
1. All topic files in agent-office/60_memory/
2. Relevant recent daily notes
3. Any supporting references in agent-office/40_resources/

For up to 5 topics, report:
- Why this topic matters now
- Facts to add or refine
- Redundancy to compress
- Cross-links to another memory topic if useful

Output sections:
## Topics to Update
## Proposed Facts
## Cross-Topic Links
## Refresh Order
```

## Selective Prep and Reviews

### Pre-Meeting Dossier
When to run: 30 minutes before important meetings
Best channel: Calendar or text
Uses: web search, Apple Mail, relevant project brief or resources
Saves to: Draft dossier for `agent-office/40_resources/pre-meeting-[today]-[person-slug].md` or a relevant project folder
Outcome: Gives you context and talking points before a high-value conversation

Prompt:

```text
plan: Build a pre-meeting dossier for [PERSON] at [COMPANY].

Meeting purpose: [sales call / partnership / hiring / investor / internal]
Relevant project folder if any: [PROJECT OR NONE]

Do these checks:
1. Web search the person and company for role, background, and recent news.
2. Search recent mail for prior contact with the person or company.
3. If a related project exists in agent-office/20_projects/[PROJECT]/, read the brief first.

Return sections:
## Person
## Company
## Prior Context
## Smart Questions
## Risks or Landmines
## Best Opening Move

Keep it practical, not verbose.
```

### Deep Research Brief
When to run: On demand
Best channel: Note or text
Uses: web search, `agent-office/40_resources/`, optional project brief
Saves to: `agent-office/40_resources/[topic-slug]-[today].md` or a relevant project folder
Outcome: Produces a reusable research note instead of a one-off chat answer

Prompt:

```text
plan: Conduct a deep research brief on [TOPIC] for my agent-office.

Purpose: [decision to make]
Relevant project folder if any: [PROJECT OR NONE]

Research:
1. Overview or explainers
2. Criticisms, failures, or traps
3. Best practices or case studies
4. Recent benchmarks, data, or research
5. Alternatives

Return sections:
## What It Is
## Why It Matters Here
## Key Players
## Risks and Traps
## Recommendation
## Top 3 Links

Write it so it can be saved as a reusable reference note, not just read once.
```

### Monthly Tech and Ops Review
When to run: First weekday of each month
Best channel: Note
Uses: active project briefs, playbooks, automation notes, security or dependency checks
Saves to: Draft monthly review for `agent-office/30_areas/monthly-ops-review-YYYY-MM.md`
Outcome: One monthly sweep across project health, playbooks, and automation drift

Prompt:

```text
!!agent plan: Run my monthly tech and ops review across agent-office.

Review:
1. Active project briefs in agent-office/20_projects/
2. Playbooks in agent-office/70_playbooks/
3. Automation notes in agent-office/80_automation/
4. Recent logs in agent-office/90_logs/

For each major area, answer:
- What looks healthy
- What is drifting or stale
- What needs a documented process
- The single highest-value fix this month

Output sections:
## Project Health
## Playbook Gaps
## Automation Drift
## Highest-Value Fix

Keep it prioritized, not exhaustive.
```

### Codex Flow Maintainer Pulse
When to run: Weekdays 8:15 AM or before a focused maintainer session
Best channel: Calendar or text
Uses: the `codex-flow` repo, recent approvals/history, tests, `agent-office/20_projects/flow-healer/` or another active Apple Flow project note
Saves to: Draft maintainer note for `agent-office/30_areas/codex-flow-pulse-YYYY-MM-DD.md` or the relevant project folder
Outcome: Gives you a sharp repo-health read before you start coding

Prompt:

```text
!!agent plan: Produce a codex-flow maintainer pulse for today.

Focus on this repository only.

Review:
1. Recent run history, pending approvals, and any obvious operational blockers.
2. Signals from tests, failing areas, or recent churn if available.
3. Apple Flow-specific risk areas: approvals, gateway drift, memory/agent-office alignment, connector health, and noisy or stale automation.
4. Any active implementation notes in agent-office that relate to codex-flow.

Return sections:
## Repo Health
## Immediate Risks
## Top 3 Maintainer Tasks
## Verification to Run First
## Best First Move

Rules:
- Be specific to codex-flow, not generic engineering advice.
- Favor the smallest safe next actions.
- Call out missing signals explicitly instead of guessing.

Keep it under 10 bullets total.
```

## Start With These Three

If you want the fastest path to value, start here:

1. `!!agent plan: Build my morning desk reset for today using the agent-office daily note format.`
2. `!!agent plan: Triage agent-office inbox entries for today's operating plan.`
3. `!!agent plan: Draft my Friday weekly review using the agent-office weekly review structure.`

Run those for two weeks before adding more.

## Notes

- This pack intentionally leaves out generic folder systems like `pipeline/`, `content/`, `community/`, and `finance/` because `agent-office` already has stronger, more flexible zones.
- If you want sales, content, or finance automations, attach them to a project in `20_projects/` or an ongoing responsibility in `30_areas/` instead of creating a second organizational system.
- For stricter automation-card formatting, see `docs/AUTOMATION_PROMPT_BUNDLE_SHORTCUTS.md`.
