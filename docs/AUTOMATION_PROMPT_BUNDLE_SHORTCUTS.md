# Shortcut-First Flow Automation Prompt Bundle

Production-ready automation prompt library for Apple Shortcuts + Apple Flow, focused on codebase upkeep and `agent-office` upkeep.

## Quick Start

- Use explicit prefixes for deterministic behavior: `idea:`, `plan:`, `task:`, `project:`.
- Use `!!agent` in Calendar/Reminders/Notes prompts.
- Prefer `plan:` for recurring automations to reduce approval fatigue.
- Use `task:` only when you intentionally want a mutating run and approval request.

## Prompt Card Schema

Each card uses this exact schema:

- `Name`
- `Goal`
- `Best Channel` (`text`, `calendar`, `reminder`, `note`)
- `Frequency`
- `Flow Command` (exact payload to send)
- `Why This Prefix`
- `Response Contract`
- `Approval Expectation`
- `Failure Fallback`

## Output Style Invariants (apply to all cards)

- Decision-first output ordering: recommendation, evidence, next action.
- Mobile readable: 4-8 bullets in normal mode.
- Single-screen summary first, details second.
- Emoji section headers in every recurring prompt.

---

## A) Repo Upkeep Automations (24)

### Pack A1: Daily Repo Pulse (6)

#### R01
- Name: Morning Health Snapshot
- Goal: Detect operational problems early.
- Best Channel: `calendar`
- Frequency: Weekdays 08:15
- Flow Command:
```text
!!agent plan: Produce an engineering morning snapshot for this repo.
Output sections:
🏥 Health
📊 Usage Today
⏳ Pending Approvals
🚨 Immediate Risks
➡️ First Action
Max length: 9 bullets total.
```
- Why This Prefix: `plan:` gives decisioning without file mutation.
- Response Contract: Recommendation in first bullet under `➡️ First Action`, then evidence.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R02
- Name: Today Maintenance Queue
- Goal: Convert recent failures/history into a ranked maintenance queue.
- Best Channel: `text`
- Frequency: Daily 09:00
- Flow Command:
```text
plan: Build today's maintenance queue from recent errors, approvals, and history.
Output sections:
🧭 Queue Priority (P0/P1/P2)
🧪 Risk if Delayed
📌 Suggested Owner
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: planning-only backlog synthesis.
- Response Contract: Include exactly top 5 items with impact/effort confidence.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R03
- Name: Top 3 Risky Files
- Goal: Surface highest-risk files by churn + failures.
- Best Channel: `calendar`
- Frequency: Weekdays 11:30
- Flow Command:
```text
!!agent plan: Identify top 3 risky files from recent churn and failing tests.
Output sections:
🔥 Top 3 Files
🧾 Why Risky
🛠️ Guardrail to Add
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: non-mutating risk analysis.
- Response Contract: Include one test or check recommendation per risky file.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R04
- Name: Branch/PR Hygiene Summary
- Goal: Keep branches/PR workflow tidy.
- Best Channel: `text`
- Frequency: Daily 14:00
- Flow Command:
```text
plan: Summarize branch and PR hygiene.
Output sections:
🌿 Branch State
🔀 PR Backlog
🧼 Hygiene Gaps
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: status + recommendations without mutating.
- Response Contract: Flag stale branches/PRs with suggested close/merge/rebase action.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R05
- Name: Dependency Drift Watch
- Goal: Spot upgrade and security drift.
- Best Channel: `calendar`
- Frequency: Weekdays 16:00
- Flow Command:
```text
!!agent plan: Assess dependency drift and upgrade risk.
Output sections:
📦 Drift Summary
🛡️ Security-Relevant Packages
⚖️ Upgrade Risk
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: non-mutating drift plan.
- Response Contract: Distinguish urgent security drift vs routine drift.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R06
- Name: End-of-Day Engineering Recap
- Goal: Capture what moved and what's next.
- Best Channel: `calendar`
- Frequency: Weekdays 18:00
- Flow Command:
```text
!!agent plan: Draft end-of-day engineering recap.
Output sections:
✅ Completed
⚠️ Blockers
📈 Quality Signals
➡️ First Action Tomorrow
Max length: 9 bullets.
```
- Why This Prefix: recap drafting without edits.
- Response Contract: Include one carry-forward priority for tomorrow.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack A2: Code Quality & Test Reliability (6)

#### R07
- Name: Flaky Test Triage
- Goal: Isolate flaky tests and propose stabilizing strategy.
- Best Channel: `text`
- Frequency: Daily 10:30
- Flow Command:
```text
plan: Triage flaky tests and propose stabilization sequence.
Output sections:
🧪 Suspected Flakes
🧠 Root-Cause Hypothesis
🛠️ Stabilization Plan
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: diagnosis and sequence planning.
- Response Contract: Rank flakes by impact to release confidence.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R08
- Name: Critical Path Coverage Gaps
- Goal: Find critical-path areas with weak test coverage.
- Best Channel: `calendar`
- Frequency: Tue/Thu 13:00
- Flow Command:
```text
!!agent plan: Find uncovered critical paths and propose minimum high-value tests.
Output sections:
🎯 Critical Paths
📉 Coverage Gaps
🧪 Minimum Tests to Add
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: analysis-first, low approval burden.
- Response Contract: Recommend up to 3 tests with ROI rationale.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R09
- Name: Smallest Safe Refactor Candidates
- Goal: Identify low-risk refactors with high maintainability gain.
- Best Channel: `text`
- Frequency: Daily 15:00
- Flow Command:
```text
plan: Identify smallest safe refactors to reduce complexity and risk.
Output sections:
🧩 Candidate Refactors
📏 Estimated Scope
🧪 Verification Needed
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: keeps output tactical, non-mutating.
- Response Contract: Include one "do now" and one "defer" recommendation.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R10
- Name: Lint/Type Noise Reduction
- Goal: Reduce alert fatigue from lint/type noise.
- Best Channel: `reminder`
- Frequency: Daily 16:30
- Flow Command:
```text
!!agent plan: Propose lint/type noise reduction without weakening guardrails.
Output sections:
🔎 Noise Sources
🛡️ Guardrails to Keep
🧹 Cleanup Plan
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: design-level recommendations first.
- Response Contract: Separate policy/config cleanup from true bug risks.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R11
- Name: Repro Checklist Generator
- Goal: Turn failing traces into reproducible checklists.
- Best Channel: `note`
- Frequency: On-demand
- Flow Command:
```text
!!agent plan: Generate a reproducibility checklist for recent failing traces.
Output sections:
🧾 Repro Preconditions
▶️ Step Sequence
✅ Expected vs Actual
🧪 Isolation Tests
➡️ First Action
Max length: 10 bullets.
```
- Why This Prefix: artifact drafting without writing repo files.
- Response Contract: Include env assumptions and confidence level.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R12
- Name: Regression Prevention Checklist
- Goal: Build guardrails around recently touched modules.
- Best Channel: `calendar`
- Frequency: Weekdays 17:00
- Flow Command:
```text
!!agent plan: Build regression-prevention checklist for recently touched modules.
Output sections:
📦 Touched Modules
⚠️ Regression Vectors
🛡️ Preventive Checks
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: no mutation, explicit guardrail design.
- Response Contract: Include fast pre-merge and slow nightly checks.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack A3: Issue/PR Workflow (6)

#### R13
- Name: Open Issue Impact/Effort Triage
- Goal: Prioritize issue backlog.
- Best Channel: `text`
- Frequency: Daily 12:00
- Flow Command:
```text
plan: Triage open issues by impact, effort, and urgency.
Output sections:
📋 Top Queue
⚖️ Impact/Effort Notes
🚫 Items to Defer
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: structured triage without actions.
- Response Contract: Use P0/P1/P2 tags and confidence labels.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R14
- Name: Stale Issue Close-or-Advance
- Goal: Decide stale issue fate.
- Best Channel: `calendar`
- Frequency: Mon/Wed/Fri 10:00
- Flow Command:
```text
!!agent plan: For stale issues, decide close, defer, or advance with criteria.
Output sections:
🕰️ Stale Candidates
✅ Close Rationale
🚀 Advance Plan
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: policy-based recommendation.
- Response Contract: Include exact close message template suggestion.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R15
- Name: Release Readiness Gate Review
- Goal: Assess release blockers and go/no-go.
- Best Channel: `calendar`
- Frequency: Tue/Thu 18:30
- Flow Command:
```text
!!agent plan: Perform release-readiness gate review.
Output sections:
🚦 Go/No-Go Recommendation
🧪 Test Gate
🛡️ Risk Gate
📚 Docs/Comms Gate
➡️ First Action
Max length: 9 bullets.
```
- Why This Prefix: decision memo style, no file edits.
- Response Contract: Start with one-line go/no-go decision.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R16
- Name: Changelog Draft from Recent Work
- Goal: Prepare human-readable release notes.
- Best Channel: `text`
- Frequency: Daily 17:30
- Flow Command:
```text
plan: Draft today's changelog from recent work.
Output sections:
✨ User-Facing Changes
🧰 Internal Improvements
🐛 Fixes
⚠️ Breaking/Behavioral Notes
➡️ First Action
Max length: 10 bullets.
```
- Why This Prefix: content drafting without committing changes.
- Response Contract: Keep each bullet release-note ready.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R17
- Name: Reviewer-Facing Summary Generator
- Goal: Reduce reviewer time-to-context.
- Best Channel: `reminder`
- Frequency: Daily 14:30
- Flow Command:
```text
!!agent plan: Create reviewer-facing summary for active PRs.
Output sections:
🧭 What Changed
⚠️ Risk Areas
🧪 How to Validate
❓ Open Questions
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: non-mutating summary generation.
- Response Contract: Include explicit reviewer checklist.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R18
- Name: Post-Merge Verification Checklist
- Goal: Confirm merged changes are healthy.
- Best Channel: `calendar`
- Frequency: Daily 19:00
- Flow Command:
```text
!!agent plan: Produce post-merge verification checklist for today's merged work.
Output sections:
✅ Smoke Checks
📈 Observability Checks
🚨 Rollback Triggers
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: operational checklist drafting.
- Response Contract: Include pass/fail criteria for each check.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack A4: Security/Ops Hygiene (6)

#### R19
- Name: Security Best-Practice Review
- Goal: Regularly surface security hardening opportunities.
- Best Channel: `calendar`
- Frequency: Weekdays 09:30
- Flow Command:
```text
!!agent plan: Run a security best-practice review for current repo changes.
Output sections:
🛡️ Key Findings
🔥 Priority Risks
🧰 Quick Mitigations
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: review mode without applying fixes.
- Response Contract: Prioritize findings by severity and exploitability.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R20
- Name: Secrets/Config Exposure Sanity Check
- Goal: Catch accidental secret leakage and risky config drift.
- Best Channel: `text`
- Frequency: Daily 13:30
- Flow Command:
```text
plan: Check for potential secrets/config exposure and risky defaults.
Output sections:
🔐 Exposure Signals
⚙️ Config Drift
🧯 Containment Steps
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: analysis and mitigation sequencing only.
- Response Contract: Distinguish probable leak vs false positive.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R21
- Name: Approval Backlog Aging Monitor
- Goal: Keep approval queue healthy.
- Best Channel: `calendar`
- Frequency: Every weekday at 12:15 and 17:15
- Flow Command:
```text
!!agent plan: Monitor approval backlog aging and propose triage actions.
Output sections:
⏳ Aged Approvals
⚠️ Expiring Soon
🧭 Triage Recommendation
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: no mutation, queue policy recommendations.
- Response Contract: Include threshold-based intervention advice.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R22
- Name: Alert/Runbook Drift Detector
- Goal: Keep runbooks aligned with current system behavior.
- Best Channel: `note`
- Frequency: Weekly Monday 11:00
- Flow Command:
```text
!!agent plan: Detect drift between observed alerts and current runbooks.
Output sections:
🔔 Alert Patterns
📘 Runbook Gaps
🛠️ Suggested Updates
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: drift assessment and proposal only.
- Response Contract: Include one minimal runbook patch suggestion.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R23
- Name: Next Ops Automation Candidate
- Goal: Identify highest ROI operational automation.
- Best Channel: `text`
- Frequency: Weekly Tuesday 09:45
- Flow Command:
```text
idea: What is the highest-ROI ops task to automate next in this repo workflow?
Output sections:
💡 Candidate Automation
📈 ROI Rationale
🧱 Dependencies
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: exploratory ideation, no execution.
- Response Contract: Recommend one candidate and one fallback candidate.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### R24
- Name: Incident Follow-Up Synthesis
- Goal: Turn incidents into durable corrective actions.
- Best Channel: `note`
- Frequency: On-demand after incidents
- Flow Command:
```text
plan: Synthesize latest incident learnings into corrective-action plan.
Output sections:
🧠 Root Cause Summary
🧯 Immediate Fixes
🛡️ Prevention Actions
📏 Verification Criteria
➡️ First Action
Max length: 10 bullets.
```
- Why This Prefix: postmortem planning, no immediate file changes.
- Response Contract: Include owner suggestion and time horizon per action.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

---

## B) Agent-Office Upkeep Automations (24)

### Pack B1: Inbox + Daily Operations (8)

#### O01
- Name: Inbox Triage Sweep
- Goal: Keep `00_inbox/inbox.md` processed and actionable.
- Best Channel: `calendar`
- Frequency: Weekdays 08:40
- Flow Command:
```text
!!agent plan: Triage agent-office inbox entries into Keep, Do, Delegate, Archive candidates.
Output sections:
📥 Keep
⚙️ Do
🤝 Delegate
🗄️ Archive Candidates
➡️ First Action
Max length: 9 bullets.
```
- Why This Prefix: categorization without mutating files.
- Response Contract: Respect append-only inbox and summarize-before-archive rule.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O02
- Name: Daily Note Bootstrap
- Goal: Prepare `10_daily/YYYY-MM-DD.md` agenda.
- Best Channel: `calendar`
- Frequency: Weekdays 07:45
- Flow Command:
```text
!!agent plan: Draft daily note bootstrap with top 3 priorities and open loops.
Output sections:
🎯 Top 3 Priorities
📅 Calendar & Commitments
🔁 Open Loops
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: output draft first, no file write.
- Response Contract: Priorities must be concrete and time-bound.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O03
- Name: Open Loops Extractor
- Goal: Consolidate unresolved commitments.
- Best Channel: `text`
- Frequency: Daily 12:30
- Flow Command:
```text
plan: Extract open loops from inbox, reminders, and calendar context.
Output sections:
🔁 Open Loops
⏱️ Deadline Pressure
🧩 Dependencies
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: synthesis and prioritization only.
- Response Contract: Include top 5 loops max with urgency tags.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O04
- Name: Archive Candidates with Rationale
- Goal: Identify what can be archived safely.
- Best Channel: `reminder`
- Frequency: Weekdays 17:40
- Flow Command:
```text
!!agent plan: Recommend what can be archived today with summary-first rationale.
Output sections:
🗄️ Archive Candidates
📝 Required Summary Before Archive
⚠️ Keep Active
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: policy-safe archive recommendations.
- Response Contract: Never recommend deletion; archive only after summary.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O05
- Name: End-of-Day Reflection Draft
- Goal: Build concise reflection and carry-forward list.
- Best Channel: `calendar`
- Frequency: Weekdays 19:15
- Flow Command:
```text
!!agent plan: Draft end-of-day reflection for agent-office daily note.
Output sections:
✅ Wins
⛔ Blockers
➡️ Carry Forward
Max length: 7 bullets.
```
- Why This Prefix: draft reflection without file mutation.
- Response Contract: Include at least one blocker mitigation suggestion.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O06
- Name: Next-Day Prep Checklist
- Goal: Pre-stage tomorrow's focus.
- Best Channel: `calendar`
- Frequency: Weekdays 20:00
- Flow Command:
```text
!!agent plan: Prepare next-day checklist from current open loops and calendar.
Output sections:
📋 Prep Checklist
🧠 Context to Preserve
🚫 Risks to Avoid
➡️ First Action Tomorrow
Max length: 8 bullets.
```
- Why This Prefix: planning and checklist generation only.
- Response Contract: Include first 30-minute startup action.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O07
- Name: Untriaged Inbox Nudge
- Goal: Prevent inbox stagnation.
- Best Channel: `calendar`
- Frequency: Weekdays 11:45
- Flow Command:
```text
!!agent plan: Nudge me on untriaged inbox items and suggest 10-minute triage move.
Output sections:
📥 Untriaged Count
⚠️ Oldest Items
⏲️ 10-Minute Triage Sprint
➡️ First Action
Max length: 6 bullets.
```
- Why This Prefix: low-friction nudge; no changes.
- Response Contract: Keep short and action-biased.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O08
- Name: Context Handoff Summary
- Goal: Create handoff summary for interrupted days.
- Best Channel: `text`
- Frequency: Daily 18:45
- Flow Command:
```text
plan: Generate context handoff summary for tomorrow or delegate.
Output sections:
🧭 Current State
🔁 In-Flight Items
📌 Next Decision Needed
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: handoff drafting without mutation.
- Response Contract: Include one "resume here" line.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack B2: Memory Hygiene (8)

#### O09
- Name: MEMORY.md Delta Proposal
- Goal: Keep durable memory current and factual.
- Best Channel: `note`
- Frequency: Weekly Monday 08:30
- Flow Command:
```text
!!agent plan: Propose factual delta updates for agent-office/MEMORY.md from recent activity.
Output sections:
🧠 Add
✏️ Refine
🗑️ Remove or De-emphasize
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: change proposal only.
- Response Contract: No speculation; factual compact statements.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O10
- Name: Topic Memory Update Recs
- Goal: Keep `60_memory/*.md` useful and fresh.
- Best Channel: `calendar`
- Frequency: Weekly Wednesday 09:15
- Flow Command:
```text
!!agent plan: Recommend updates for topic memory files in 60_memory.
Output sections:
📂 Topics to Update
🧾 Proposed Facts
🔗 Cross-Topic Links
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: recommendation mode only.
- Response Contract: One bullet per topic, max five topics.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O11
- Name: Memory Contradiction Detector
- Goal: Identify conflicting facts/preferences.
- Best Channel: `reminder`
- Frequency: Weekly Friday 10:45
- Flow Command:
```text
!!agent plan: Detect contradictions across MEMORY.md and 60_memory files.
Output sections:
⚠️ Contradictions
🔎 Evidence
🧭 Resolution Suggestion
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: analytical QA, no edits.
- Response Contract: Include conflict confidence for each contradiction.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O12
- Name: Memory Staleness Alert
- Goal: Highlight stale sections that need refresh.
- Best Channel: `calendar`
- Frequency: Weekly Thursday 16:15
- Flow Command:
```text
!!agent plan: Identify stale memory sections and propose refresh order.
Output sections:
🕰️ Stale Sections
📈 Impact of Staleness
🛠️ Refresh Order
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: non-mutating hygiene prioritization.
- Response Contract: Prioritize by decision impact, not file age alone.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O13
- Name: Preference Extraction from Decisions
- Goal: Convert repeated decisions into explicit preferences.
- Best Channel: `text`
- Frequency: Weekly Tuesday 15:30
- Flow Command:
```text
idea: Extract likely stable preferences from recent decisions for memory hardening.
Output sections:
🧭 Candidate Preferences
🧾 Evidence
✅ Confidence
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: exploratory inference before acceptance.
- Response Contract: Mark each preference as confirmed or needs validation.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O14
- Name: Guardrail Drift Checker
- Goal: Verify behavior against SCAFFOLD non-negotiables.
- Best Channel: `calendar`
- Frequency: Weekly Monday 14:00
- Flow Command:
```text
!!agent plan: Check drift against agent-office/SCAFFOLD.md non-negotiables.
Output sections:
🛡️ Guardrails Compliant
⚠️ Guardrails at Risk
🧯 Corrective Suggestions
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: compliance review without mutation.
- Response Contract: Explicitly call out append-only and summarize-before-archive compliance.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O15
- Name: Weekly Memory Compacting Plan
- Goal: Reduce noise and redundancy in memory system.
- Best Channel: `note`
- Frequency: Weekly Sunday 17:00
- Flow Command:
```text
!!agent plan: Create weekly memory compacting plan for MEMORY.md and 60_memory.
Output sections:
🧹 Redundancy Hotspots
📦 Merge Candidates
🚫 Do-Not-Compact Items
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: planning mode for controlled consolidation.
- Response Contract: Preserve critical context and confidence caveats.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O16
- Name: Promote-or-Prune Candidates
- Goal: Decide what to promote to durable memory or prune from active focus.
- Best Channel: `calendar`
- Frequency: Weekly Friday 18:10
- Flow Command:
```text
!!agent plan: Recommend promote-or-prune candidates from current notes/memory.
Output sections:
📈 Promote
🪶 Keep as Ephemeral
🗂️ Prune/Archive Candidate
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: curation without direct file edits.
- Response Contract: Tie each recommendation to expected utility.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack B3: Project Brief Governance (8)

#### O17
- Name: Project Brief Status Normalizer
- Goal: Keep `20_projects/*/brief.md` statuses coherent.
- Best Channel: `note`
- Frequency: Weekly Monday 10:30
- Flow Command:
```text
!!agent plan: Normalize project brief statuses and suggest status corrections.
Output sections:
📂 Projects Reviewed
🔄 Status Corrections
📌 Missing Brief Fields
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: governance recommendations only.
- Response Contract: Require evidence for each status correction.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O18
- Name: Milestone Aging Checker
- Goal: Catch slipping milestones early.
- Best Channel: `calendar`
- Frequency: Tue/Thu 11:15
- Flow Command:
```text
!!agent plan: Check milestone aging across active project briefs.
Output sections:
⏳ Aging Milestones
⚠️ Slippage Risk
🧭 Recovery Option
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: timeline risk analysis only.
- Response Contract: Include one fast recovery move per high-risk milestone.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O19
- Name: Risk Register Refresh
- Goal: Keep project risk register current.
- Best Channel: `reminder`
- Frequency: Weekly Wednesday 17:20
- Flow Command:
```text
!!agent plan: Refresh risk register suggestions for active projects.
Output sections:
🔥 New Risks
🛡️ Mitigations
📏 Trigger Conditions
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: planning and risk framing.
- Response Contract: Provide probability/impact hints for each risk.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O20
- Name: Blocked Project Escalation Summary
- Goal: Escalate blocked work with clarity.
- Best Channel: `text`
- Frequency: Daily 16:50
- Flow Command:
```text
plan: Summarize blocked projects and produce escalation-ready notes.
Output sections:
⛔ Blocked Projects
🧱 Blocking Dependency
📣 Escalation Draft
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: communication planning without mutation.
- Response Contract: Include one escalation message template.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O21
- Name: Priority Rebalance Across Projects
- Goal: Reallocate attention based on impact and deadlines.
- Best Channel: `calendar`
- Frequency: Weekly Monday 13:30
- Flow Command:
```text
!!agent plan: Rebalance priorities across active projects.
Output sections:
🎯 Priority Order
⚖️ Tradeoff Notes
🧩 Capacity Fit
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: strategic planning output.
- Response Contract: Include what to pause to protect top priority.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O22
- Name: Weekly Portfolio Snapshot
- Goal: Produce one-screen project portfolio health view.
- Best Channel: `calendar`
- Frequency: Friday 15:45
- Flow Command:
```text
!!agent plan: Generate weekly portfolio snapshot for active projects.
Output sections:
🟢 Green
🟡 Yellow
🔴 Red
➡️ First Action
Max length: 9 bullets.
```
- Why This Prefix: reporting/synthesis only.
- Response Contract: Exactly one priority action per color band.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O23
- Name: Completion/Archive Recommendation
- Goal: Identify projects ready to close/archive correctly.
- Best Channel: `reminder`
- Frequency: Weekly Thursday 18:30
- Flow Command:
```text
!!agent plan: Recommend project completion/archive candidates requiring summary first.
Output sections:
✅ Ready to Complete
📝 Required Completion Summary
🗄️ Archive Candidate
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: governance decision support.
- Response Contract: Never skip summary-before-archive requirement.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### O24
- Name: Next-Action Generator per Brief
- Goal: Convert each active brief into immediate next action.
- Best Channel: `text`
- Frequency: Daily 09:20
- Flow Command:
```text
plan: For each active project brief, generate one concrete next action.
Output sections:
📂 Project
➡️ Next Action
📏 Definition of Done
⏱️ Estimated Effort
Max length: 8 bullets.
```
- Why This Prefix: tactical planning with no file mutation.
- Response Contract: One action per project, max 5 projects.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

---

## C) Meta-Automation / Flow Control (12)

### Pack C1: Mute/Unmute Guardrails (2)

#### M01
- Name: Focus Window Mute Guard
- Goal: Automatically enforce focus quieting behavior.
- Best Channel: `calendar`
- Frequency: Weekdays 09:55 and 13:55
- Flow Command:
```text
!!agent system: mute
```
- Why This Prefix: direct control command.
- Response Contract: Confirm mute state and next unmute checkpoint.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M02
- Name: Focus Window Unmute Guard
- Goal: Resume proactive companion messages after focus blocks.
- Best Channel: `calendar`
- Frequency: Weekdays 12:05 and 17:05
- Flow Command:
```text
!!agent system: unmute
```
- Why This Prefix: direct control command.
- Response Contract: Confirm unmuted and summarize missed critical events if available.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack C2: Approval Backlog Interventions (2)

#### M03
- Name: Approval Backlog Sweep
- Goal: Keep pending approvals actionable.
- Best Channel: `calendar`
- Frequency: Weekdays 12:10
- Flow Command:
```text
!!agent status
```
- Why This Prefix: built-in command for pending approvals.
- Response Contract: Return concise list with aging + suggested triage order.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M04
- Name: Approval Intervention Advisor
- Goal: Decide what to approve now vs deny/defer.
- Best Channel: `text`
- Frequency: Weekdays 12:20
- Flow Command:
```text
plan: Based on pending approvals, recommend approve/deny/defer with rationale.
Output sections:
✅ Approve Now
🚫 Deny
⏳ Defer
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: decision support without executing approvals.
- Response Contract: Include risk of delay and confidence tags.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack C3: Automation Effectiveness Review (2)

#### M05
- Name: Weekly Automation Keep/Remove/Tune
- Goal: Keep automation set high-signal.
- Best Channel: `calendar`
- Frequency: Sunday 18:30
- Flow Command:
```text
!!agent plan: Review automation effectiveness and classify each as keep/remove/tune.
Output sections:
✅ Keep
🗑️ Remove
🎛️ Tune
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: policy review and tuning guidance.
- Response Contract: Include reason and expected impact per recommendation.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M06
- Name: Noise Budget Audit
- Goal: Prevent automation spam.
- Best Channel: `reminder`
- Frequency: Weekly Friday 17:50
- Flow Command:
```text
!!agent plan: Audit message noise budget and propose cadence reductions where needed.
Output sections:
📣 High-Noise Automations
📉 Reduction Suggestions
🧪 Measurement Plan
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: non-mutating optimization.
- Response Contract: Quantify expected signal/noise improvement.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack C4: Prompt Quality Auditor (2)

#### M07
- Name: Prompt Quality Scorecard
- Goal: Score prompts for clarity and execution reliability.
- Best Channel: `note`
- Frequency: Weekly Tuesday 18:00
- Flow Command:
```text
!!agent plan: Audit current automation prompts for verbosity, specificity, and ambiguity.
Output sections:
🧪 Scorecard
✂️ Simplify
🎯 Clarify
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: quality analysis only.
- Response Contract: Score each dimension from 1-5 with one fix per low score.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M08
- Name: Prefix Intent Auditor
- Goal: Ensure prefixes match intent and approval profile.
- Best Channel: `text`
- Frequency: Weekly Wednesday 12:40
- Flow Command:
```text
plan: Audit whether prompt prefixes match intent (idea/plan/task/project).
Output sections:
🧭 Prefix Mismatches
🛡️ Approval Risk
🔄 Recommended Prefix Changes
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: classification audit only.
- Response Contract: Highlight high-risk `task:` misuses.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack C5: Cost/Usage Governance (2)

#### M09
- Name: Daily Usage Pulse
- Goal: Monitor day-level consumption.
- Best Channel: `calendar`
- Frequency: Weekdays 16:10
- Flow Command:
```text
!!agent usage today
```
- Why This Prefix: built-in usage command.
- Response Contract: Include quick interpretation: on-track or elevated.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M10
- Name: Monthly Usage Governance Review
- Goal: Control cost trends and block hotspots.
- Best Channel: `calendar`
- Frequency: 1st of month 09:10
- Flow Command:
```text
!!agent plan: Analyze monthly usage and block-level hotspots; suggest cost controls.
Output sections:
💰 Monthly Trend
🧱 Cost Hotspots
🎛️ Control Levers
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: analytical governance, no mutation.
- Response Contract: Include one low-risk cost optimization.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

### Pack C6: Trigger Integrity Check (2)

#### M11
- Name: Trigger Tag Coverage Check
- Goal: Ensure recurring automations include `!!agent` where required.
- Best Channel: `calendar`
- Frequency: Weekly Monday 09:05
- Flow Command:
```text
!!agent plan: Check trigger integrity for calendar/reminder/note automations and tag coverage.
Output sections:
🏷️ Missing Tag Risks
✅ Valid Triggers
🛠️ Repair Suggestions
➡️ First Action
Max length: 7 bullets.
```
- Why This Prefix: integrity audit without changes.
- Response Contract: Flag likely silent-failure automations first.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

#### M12
- Name: Cadence Conflict Checker
- Goal: Detect overlapping schedule conflicts and collision windows.
- Best Channel: `note`
- Frequency: Weekly Sunday 19:00
- Flow Command:
```text
!!agent plan: Detect cadence conflicts across automations and suggest conflict-free schedule.
Output sections:
🕒 Collision Windows
⚠️ Potential Redundancy
🎯 Proposed Cadence
➡️ First Action
Max length: 8 bullets.
```
- Why This Prefix: schedule optimization analysis.
- Response Contract: Provide one simplified weekly cadence map.
- Approval Expectation: No
- Failure Fallback: If data unavailable, report `No signal` and list what was missing.

---

## Rollout Activation Plan

### Phase 1 (Pilot: week 1, 12 prompts)

- Repo: `R01`, `R02`, `R03`, `R07`, `R15`, `R21`
- Agent-office: `O01`, `O02`, `O03`, `O09`, `O14`, `O24`

Target outcomes:
- Detect drift earlier.
- Keep approval queue manageable.
- Improve daily focus and context continuity.

### Phase 2 (Expansion: week 2)

- Add remaining Repo and Agent-office prompts (`R04-R24`, `O04-O23`).
- Tune noisy prompts by adjusting cadence and output max bullets.

### Phase 3 (Optimization: week 3+)

- Activate all Meta prompts (`M01-M12`).
- Run monthly prune of low-value automations.

---

## Validation Checklist

1. Classification correctness
- Verify each prompt lands in expected mode (`idea/plan/task/project` or control command).

2. Approval safety
- Verify any intentional mutating prompt triggers approval and is sender-attributable.

3. Channel trigger validity
- Verify `!!agent`-tagged calendar/reminder/note prompts are ingested and untagged ones are ignored.

4. Signal quality
- Verify each prompt returns actionable structured output under sparse data.

5. Noise control
- Verify no redundant overlapping proactive messages in daily windows.

6. Agent-office integrity
- Verify inbox append-only and summarize-before-archive behavior are preserved.

7. Readability acceptance
- Verify iMessage outputs remain concise with emoji headers and scannable bullets.
