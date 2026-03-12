# Codex Flow Repo Maintenance Prompt Pack

Copy/paste prompt library for automated repo maintenance, health checks, and maintainer checkups for `codex-flow` through Apple Flow.

This pack is for recurring repo upkeep on this codebase. It assumes:

- You want prompts that are specific to `codex-flow`, not generic software-team templates
- You are using Apple Flow command styles like `plan:`, `task:`, `idea:`, and `!!agent`
- Most recurring prompts should stay non-mutating by default, so they use `plan:`
- If you want Apple Flow to write files or change repo state, switch to `task:` and approve it

## How to Use This

1. Copy a prompt into your Apple Flow channel of choice.
2. Use Calendar or Reminders for recurring maintainer prompts.
3. Keep recurring prompts in `plan:` mode unless you intentionally want file updates.
4. Start with these three:
   - Morning Maintainer Snapshot
   - Today Maintenance Queue
   - Flaky or Failing Test Triage

## What This Pack Optimizes For

- Fast repo-health reads before coding
- Good defaults for approval-gated work
- Focus on real Apple Flow risk surfaces: approvals, gateways, connectors, daemon health, memory, and logs
- Smallest safe next actions instead of giant cleanup lists
- Maintenance automation you can run on a schedule without creating repo churn

## Command Defaults

- Use `plan:` for snapshots, triage, readiness reviews, and checklists.
- Use `task:` only when you want Apple Flow to make repo or note changes after approval.
- Use `!!agent` for Calendar, Reminder, or Note scheduled prompts.
- Favor `pytest -q` as the default verification target when suggesting test validation, because this repo requires it after behavior changes.

## Daily Maintainer Loop

### Morning Maintainer Snapshot
When to run: Weekdays 8:15 AM
Best channel: Calendar
Uses: repo status, recent run history, pending approvals, daemon/log signals
Saves to: Draft note for `agent-office/30_areas/codex-flow-snapshot-YYYY-MM-DD.md`
Outcome: A fast read on whether you should code, debug, or unblock operations first

Prompt:

```text
!!agent plan: Produce a codex-flow morning maintainer snapshot.

Focus on this repository only.

Review:
1. Any obvious daemon, log, or health issues.
2. Pending approvals or aged approval backlog.
3. Recent failures, stalled runs, or suspicious runtime signals.
4. Any active project notes in agent-office related to codex-flow.

Return sections:
## Health
## Pending Approvals
## Immediate Risks
## Best First Move

Keep it under 9 bullets total and decision-first.
```

### Today Maintenance Queue
When to run: Weekdays 9:00 AM
Best channel: Text
Uses: recent failures, approvals, logs, recent repo context
Saves to: Draft queue for `agent-office/30_areas/codex-flow-maintenance-YYYY-MM-DD.md`
Outcome: Converts noise into a ranked list of maintainer work

Prompt:

```text
plan: Build today's codex-flow maintenance queue from recent errors, approvals, logs, and obvious drift.

Output sections:
## Queue Priority
## Risk if Delayed
## Suggested Owner
## Best First Move

Rules:
- Include only the top 5 items.
- Use P0/P1/P2 tags.
- Be specific to this repo's architecture and workflows.
```

### End-of-Day Engineering Recap
When to run: Weekdays 6:00 PM
Best channel: Calendar
Uses: recent work, tests, approvals, open blockers
Saves to: Draft recap for `agent-office/30_areas/codex-flow-recap-YYYY-MM-DD.md`
Outcome: Captures what moved, what is risky, and where to resume tomorrow

Prompt:

```text
!!agent plan: Draft an end-of-day codex-flow engineering recap.

Summarize:
1. What moved today.
2. What remains blocked.
3. What quality or operational signals changed.
4. What should be the first move tomorrow.

Return sections:
## Completed
## Blockers
## Quality Signals
## First Action Tomorrow

Keep it concise and mobile-readable.
```

### Dependency Drift Watch
When to run: Weekdays 4:00 PM
Best channel: Calendar
Uses: dependency manifests, security drift, upgrade risk, release confidence
Saves to: Draft drift note for `agent-office/30_areas/codex-flow-dependency-drift-YYYY-MM-DD.md`
Outcome: Spots quiet package drift before it becomes a production or release problem

Prompt:

```text
!!agent plan: Assess dependency drift and upgrade risk in codex-flow.

Return sections:
## Drift Summary
## Security-Relevant Packages
## Upgrade Risk
## Best First Move

Rules:
- Separate urgent security drift from routine maintenance drift.
- Keep it focused on packages or tooling that materially affect codex-flow reliability.
```

## Code Quality and Reliability

### Flaky or Failing Test Triage
When to run: Daily 10:30 AM or on demand after failures
Best channel: Text
Uses: failing tests, recent churn, likely regression areas
Saves to: Draft triage note for `agent-office/30_areas/codex-flow-test-triage-YYYY-MM-DD.md`
Outcome: Turns noisy failures into a stabilization sequence

Prompt:

```text
plan: Triage flaky or failing tests in codex-flow and propose a stabilization sequence.

Return sections:
## Suspected Failing Areas
## Root-Cause Hypotheses
## Stabilization Plan
## Verification to Run First

Rules:
- Rank by impact to release confidence.
- Distinguish flaky tests from likely product regressions.
- Favor the smallest safe next action.
```

### Critical Path Coverage Gaps
When to run: Tue/Thu 1:00 PM
Best channel: Calendar
Uses: orchestrator, approvals, ingress/egress, connectors, admin API, companion paths
Saves to: Draft test-gap note for `agent-office/30_areas/codex-flow-coverage-gaps-YYYY-MM-DD.md`
Outcome: Surfaces the highest-ROI missing tests

Prompt:

```text
!!agent plan: Find critical path coverage gaps in codex-flow and propose the minimum high-value tests to add.

Prioritize these areas:
1. Approval workflow and sender verification
2. Orchestrator command routing
3. Gateway ingress/egress behavior
4. Connector execution and failure handling
5. Companion, scheduler, and memory interactions

Return sections:
## Critical Paths
## Coverage Gaps
## Minimum Tests to Add
## Best First Move

Recommend up to 3 tests only.
```

### Top 3 Risky Files
When to run: Weekdays 11:30 AM
Best channel: Calendar
Uses: recent churn, failure patterns, complex modules
Saves to: Draft risk note for `agent-office/30_areas/codex-flow-risky-files-YYYY-MM-DD.md`
Outcome: Keeps attention on modules most likely to bite during active work

Prompt:

```text
!!agent plan: Identify the top 3 risky files in codex-flow from recent churn, failure signals, and architectural complexity.

Return sections:
## Top 3 Files
## Why Risky
## Guardrail to Add
## Best First Move

Include one validation or test recommendation per file.
```

### Smallest Safe Refactor Candidates
When to run: Weekdays 3:00 PM
Best channel: Text
Uses: code complexity, large files, repeated patterns, validation burden
Saves to: Draft refactor candidate note for `agent-office/30_areas/codex-flow-refactors-YYYY-MM-DD.md`
Outcome: Finds maintainability wins that do not blow up risk

Prompt:

```text
plan: Identify the smallest safe refactors in codex-flow that would reduce complexity or maintenance risk.

Return sections:
## Candidate Refactors
## Estimated Scope
## Verification Needed
## Do Now vs Defer

Rules:
- Favor low-risk, high-leverage changes.
- Avoid unrelated cleanup.
- Call out if a file is large but still not worth touching yet.
```

## Workflow and Review

### Branch and PR Hygiene Summary
When to run: Weekdays 2:00 PM
Best channel: Text
Uses: branch state, PR backlog, stale work, review friction
Saves to: Draft hygiene note for `agent-office/30_areas/codex-flow-pr-hygiene-YYYY-MM-DD.md`
Outcome: Prevents branch and review drift from becoming invisible tax

Prompt:

```text
plan: Summarize codex-flow branch and PR hygiene.

Return sections:
## Branch State
## PR Backlog
## Hygiene Gaps
## Best First Move

Flag stale branches or reviews with a suggested close, merge, rebase, or revive action.
```

### Reviewer Summary Draft
When to run: Before requesting review
Best channel: Text or Note
Uses: current changes, likely reviewer concerns
Saves to: Draft reviewer note for `agent-office/40_resources/codex-flow-review-summary-YYYY-MM-DD.md`
Outcome: Cuts reviewer time-to-context and makes risk visible up front

Prompt:

```text
plan: Create a reviewer-facing summary for current codex-flow changes.

Return sections:
## What Changed
## Risk Areas
## How to Validate
## Open Questions

Rules:
- Write for a reviewer, not the implementer.
- Include an explicit validation checklist.
- Highlight behavior changes before internal refactors.
```

### Release Readiness Gate Review
When to run: Before releases or merges with broad impact
Best channel: Calendar or Note
Uses: tests, docs, approvals, runtime risk, backwards compatibility
Saves to: Draft release gate review for `agent-office/30_areas/codex-flow-release-gate-YYYY-MM-DD.md`
Outcome: Produces a go/no-go memo instead of gut-feel shipping

Prompt:

```text
!!agent plan: Perform a codex-flow release-readiness gate review.

Review for:
1. Test confidence
2. Approval and policy safety
3. Gateway and connector risk
4. Docs or setup drift
5. Runtime rollback or containment concerns

Return sections:
## Go or No-Go
## Test Gate
## Safety Gate
## Docs and Setup Gate
## Best First Move

Start with a one-line go/no-go recommendation.
```

### Post-Merge Verification Checklist
When to run: After merges or deploy-adjacent changes
Best channel: Calendar
Uses: merged work, smoke checks, logs, health endpoints, rollback signals
Saves to: Draft verification note for `agent-office/30_areas/codex-flow-post-merge-YYYY-MM-DD.md`
Outcome: Turns “it merged” into a real health check

Prompt:

```text
!!agent plan: Produce a post-merge verification checklist for recent codex-flow work.

Return sections:
## Smoke Checks
## Observability Checks
## Rollback Triggers
## Best First Move

Rules:
- Include pass/fail criteria.
- Prefer checks that catch runtime regressions quickly.
- Call out missing signals explicitly.
```

## Runtime and Operations

### Approval Backlog Aging Monitor
When to run: Weekdays 12:15 PM and 5:15 PM
Best channel: Calendar
Uses: pending approvals, approval TTL risk, stalled work
Saves to: Draft backlog note for `agent-office/30_areas/codex-flow-approvals-YYYY-MM-DD.md`
Outcome: Prevents valid work from dying quietly in the queue

Prompt:

```text
!!agent plan: Monitor codex-flow approval backlog aging and recommend triage actions.

Return sections:
## Aged Approvals
## Expiring Soon
## Triage Recommendation
## Best First Move

Use threshold-based recommendations and call out approval-sender or workflow risks if relevant.
```

### Connector and Gateway Drift Check
When to run: Mondays and Thursdays 4:00 PM
Best channel: Calendar
Uses: connector setup, gateway resources, logs, setup drift, service behavior
Saves to: Draft ops note for `agent-office/30_areas/codex-flow-drift-YYYY-MM-DD.md`
Outcome: Catches the boring operational drift that breaks automation later

Prompt:

```text
!!agent plan: Check codex-flow for connector and gateway drift.

Focus on:
1. Connector command/config mismatches
2. Gateway resource drift for Mail, Reminders, Notes, and Calendar
3. Daemon health and helper-process concerns
4. Agent-office alignment and memory-related drift if relevant

Return sections:
## Connector Health
## Gateway Drift
## Runtime Risks
## Best First Move

If a signal is missing, say so explicitly instead of guessing.
```

### Security and Config Exposure Check
When to run: Weekdays 9:30 AM or before merges touching config/runtime behavior
Best channel: Text
Uses: config defaults, secrets handling, risky flags, exposed behavior
Saves to: Draft security note for `agent-office/30_areas/codex-flow-security-YYYY-MM-DD.md`
Outcome: Surfaces quiet security mistakes before they spread

Prompt:

```text
plan: Run a codex-flow security and config exposure sanity check for current work.

Look for:
1. Potential secrets exposure
2. Risky defaults or guardrail weakening
3. Approval or sender-verification regressions
4. Unsafe workspace or connector behavior

Return sections:
## Key Findings
## Priority Risks
## Quick Mitigations
## Best First Move

Prioritize by severity and exploitability.
```

### Incident Follow-Up Synthesis
When to run: After outages, regressions, or confusing runtime failures
Best channel: Note
Uses: incident context, logs, failing behavior, corrective actions
Saves to: Draft follow-up note for `agent-office/40_resources/codex-flow-incident-[today].md`
Outcome: Turns painful incidents into durable prevention work

Prompt:

```text
plan: Synthesize the latest codex-flow incident or runtime failure into a corrective-action plan.

Return sections:
## Root Cause Summary
## Immediate Fixes
## Prevention Actions
## Verification Criteria
## Best First Move

Include suggested owner and time horizon when possible.
```

## Start With These Three

If you want a lean default set, start here:

1. `!!agent plan: Produce a codex-flow morning maintainer snapshot.`
2. `plan: Build today's codex-flow maintenance queue from recent errors, approvals, logs, and obvious drift.`
3. `plan: Triage flaky or failing tests in codex-flow and propose a stabilization sequence.`

Run those for a week before adding more.

## Notes

- This pack is intentionally maintainer-focused. It is for automated repo maintenance, debugging, testing, release confidence, and workflow hygiene.
- If you want broader office routines, use `docs/AGENT_OFFICE_PROMPT_PACK.md`.
- If you want stricter automation-card formatting, use `docs/AUTOMATION_PROMPT_BUNDLE_SHORTCUTS.md`.
