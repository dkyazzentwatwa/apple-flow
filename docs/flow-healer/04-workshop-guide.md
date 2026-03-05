# Flow Healer Workshop Guide

## A Plain-English Guide to Apple Flow's Autonomous Healing System

Version: March 5, 2026

---

## Table of Contents

1. Workshop Purpose
2. What Flow Healer Is
3. Why This System Matters
4. The Big Picture
5. Core Ideas You Need to Know
6. Safety Rules
7. What the Scanner Does
8. What the Learning System Does
9. How the Full Workflow Works
10. Setup Checklist
11. Important `.env` Settings
12. Everyday Commands
13. Reading the Healer Dashboard
14. Running a Scan
15. Creating and Healing GitHub Issues
16. Guarded PR Mode
17. Example Workshop Walkthrough
18. Operating Tips
19. Troubleshooting
20. Best Practices
21. FAQ
22. Glossary

---

## 1. Workshop Purpose

This guide is meant to help you teach, explain, demo, and operate Flow Healer with confidence.

By the end of a workshop, a beginner should understand:

- what Flow Healer is
- how it finds work
- how it stays safe
- what the scanner does
- what the new learning layer does
- how it creates and heals GitHub issues
- how humans stay in control

This guide uses plain language on purpose. It is written so a beginner can follow the system without needing to read the whole codebase first.

---

## 2. What Flow Healer Is

Flow Healer is an autonomous maintenance framework inside Apple Flow.

Its job is to help a project get healthier over time by:

- watching for maintainer-approved GitHub issues
- scanning the codebase for failures
- turning scan results into issues
- creating isolated workspaces per issue
- attempting fixes through an AI proposer
- checking those fixes through tests and a verifier
- opening or updating pull requests only when guardrails pass

In short:

Flow Healer is not “an AI that hacks on the repo.” It is a controlled repair loop with state, leases, retries, verification, and human checkpoints.

---

## 3. Why This System Matters

Most teams lose time to the same maintenance work:

- flaky tests
- regressions
- recurring bugs
- lock and concurrency issues
- small but important cleanup tasks
- reliability work that gets postponed

Flow Healer matters because it reduces that maintenance drag.

Instead of waiting for someone to notice a failure, reproduce it, create an issue, and start a careful fix, the system helps move that work forward in a repeatable way.

It saves time in three places:

1. Finding problems
2. Organizing the work
3. Starting fixes safely

That means people can spend more time on product work and less time on repetitive repair work.

---

## 4. The Big Picture

Flow Healer has two main inputs:

1. GitHub issues that are approved for healing
2. Local scan results from the codebase

It has one main goal:

Turn project problems into reviewed, trackable fixes.

You can think of the system like this:

`scan -> issue -> queue -> claim -> patch -> test -> verify -> PR -> review -> merge`

This matters:

Flow Healer is a framework, not just a model call.

It includes:

- durable queue state
- issue leases
- lock management
- isolated workspaces
- retry budgets
- exponential backoff
- circuit breaker behavior
- GitHub issue and PR integration
- dashboard visibility
- optional internal learning from prior attempts

That framework is what makes it usable in a real project.

---

## 5. Core Ideas You Need to Know

### 5.1 Scanner

The scanner is the “find work” side of Flow Healer.

It runs project checks such as:

- harness evaluation pack
- `pytest -q`

When checks fail, the scanner can create GitHub issues.

### 5.2 Deduplication

Scanner findings carry a fingerprint.

That prevents the same failure from opening the same issue again and again.

### 5.3 Healing Queue

Approved issues are stored in a tracked queue.

Flow Healer claims work from that queue using leases so multiple workers do not stomp on the same issue at once.

### 5.4 Locking

Flow Healer predicts a lock set before it starts and upgrades locks after it sees the actual diff.

This reduces concurrent edit conflicts and makes the system safer to run with more than one issue in flight.

### 5.5 Isolated Workspace

Each issue gets its own working area.

This helps prevent one attempted fix from contaminating another.

### 5.6 Proposer

The proposer is the AI step that tries to generate a patch.

It is constrained to return a unified diff, not a free-form implementation essay.

### 5.7 Verifier

The verifier is a second AI pass.

Its job is to reduce self-confirmation bias by checking whether the proposal actually appears to solve the problem.

### 5.8 Guarded PR Flow

In guarded mode, Flow Healer can do the repair work, but PR actions remain behind explicit human signals.

That keeps humans in control.

---

## 6. Safety Rules

Flow Healer is useful because it is structured, not reckless.

The main safety rules are:

- only labeled issues are ingested
- trusted actors can be enforced
- issue text is treated as untrusted input
- each issue gets an isolated workspace
- retries are capped
- exponential backoff prevents thrashing
- lock contention is tracked and surfaced
- the verifier must pass before publish steps
- PR actions can require an approval label
- a circuit breaker stops progress when recent failure rate spikes
- scans dedupe repeated findings

This is the mindset:

Autonomy is allowed, but only inside clearly defined boundaries.

---

## 7. What the Scanner Does

The scanner checks the repo and looks for failures that should become healing work.

Right now the scanner follows a practical pattern:

- run a focused harness evaluation pack
- run `pytest -q`
- convert failures into findings
- filter findings by severity
- dedupe findings by fingerprint
- optionally create GitHub issues

The scanner has two modes.

### Dry Run

`system: healer scan dry-run`

This reports what the scanner found, but does not create issues.

This is the safest way to teach or test the scanner.

### Live Scan

`system: healer scan`

This runs the same checks, but can create GitHub issues for findings that pass your threshold rules.

---

## 8. What the Learning System Does

Flow Healer now has an optional internal learning layer.

This layer is enabled with:

```env
apple_flow_healer_learning_enabled=false
```

When enabled, the learning layer does three things:

1. It records reusable lessons from prior healer attempts.
2. It retrieves relevant lessons before a new proposer or verifier pass.
3. It surfaces lesson counts and recurring failure patterns in the healer dashboard.

This is important:

The learning system does not rewrite its own code, change the repo on its own, or silently alter core policy.

It is intentionally conservative.

### What counts as a lesson

In v1, the system learns from:

- successful attempts that passed verifier
- meaningful failures such as:
  - no patch returned
  - patch apply failures
  - diff too large
  - tests failed
  - verifier failed
  - lock conflict
  - lock upgrade conflict

It does not learn from noisy external failures like network or push problems.

### What the lesson is used for

Before a new attempt, Flow Healer can inject:

`Relevant prior healer lessons:`

That short context may remind the proposer or verifier to:

- keep scope narrow
- avoid stale file paths
- respect prior lock patterns
- run targeted tests first
- avoid fixes that only silence symptoms

### What it is not

The learning layer is not:

- a self-editing prompt system
- a hidden policy mutator
- a file-based memory notebook
- an embedding system

It is an internal retrieval and guardrail system only.

That makes it safer to explain in workshops and safer to trust in production.

---

## 9. How the Full Workflow Works

Here is the full workflow from start to finish:

1. A problem is found
2. The scanner creates an issue, or a maintainer creates one
3. The issue carries the required label, usually `healer:ready`
4. Flow Healer ingests the issue into its tracked queue
5. The issue is claimed by the healer loop
6. A workspace is created for that issue
7. The system predicts a lock set
8. The system retrieves any relevant prior lessons
9. The proposer attempts a patch
10. Tests run
11. The verifier checks the result
12. The system records attempt outcomes and, if enabled, saves reusable lessons
13. If guarded PR rules are satisfied, Flow Healer opens or updates a PR
14. A human reviews the PR
15. The PR is merged or revised

This keeps the system explainable and auditable.

---

## 10. Setup Checklist

Before a workshop or live demo, check these items:

- Apple Flow is installed and working
- the daemon can run
- `.env` is configured
- `GITHUB_TOKEN` is available
- the local repo path is correct
- the GitHub repo has an `origin` remote
- Docker is available
- Pages.app can run on this Mac
- Flow Healer is enabled
- the trusted actor list is correct
- guarded mode is on for safety
- the learning flag is set the way you intend for the demo

Recommended starter setup:

```env
apple_flow_enable_autonomous_healer=true
apple_flow_healer_mode=guarded_pr
apple_flow_healer_repo_path=/Users/cypher-server/Documents/code/codex-flow
apple_flow_healer_issue_required_labels=healer:ready
apple_flow_healer_pr_actions_require_approval=true
apple_flow_healer_pr_required_label=healer:pr-approved
apple_flow_healer_trusted_actors=dkyazzentwatwa
apple_flow_healer_sandbox_mode=docker
apple_flow_healer_learning_enabled=false
apple_flow_healer_scan_enable_issue_creation=true
apple_flow_healer_scan_max_issues_per_run=5
apple_flow_healer_scan_severity_threshold=medium
apple_flow_healer_scan_default_labels=healer:ready,kind:scan
```

---

## 11. Important `.env` Settings

These are the most important settings to explain during a workshop.

### `apple_flow_enable_autonomous_healer`

Turns Flow Healer on or off.

### `apple_flow_healer_mode`

Controls how aggressive the healer is.

Current safe workshop value:

`guarded_pr`

### `apple_flow_healer_repo_path`

The local repository Flow Healer will work on.

### `apple_flow_healer_issue_required_labels`

Labels an issue must have before Flow Healer will ingest it.

Example:

`healer:ready`

### `apple_flow_healer_pr_actions_require_approval`

If true, PR actions stay behind approval rules.

### `apple_flow_healer_pr_required_label`

Label that tells Flow Healer it may move ahead with PR actions in guarded mode.

Example:

`healer:pr-approved`

### `apple_flow_healer_trusted_actors`

Limits which GitHub usernames are trusted to author healable issues.

Important:

This controls issue intake, not GitHub merge permissions.

### `apple_flow_healer_learning_enabled`

Turns internal lesson recording and retrieval on or off.

Recommended workshop default:

Keep it off for the first walkthrough, then turn it on when you want to explain how Flow Healer gets better at recurring issue patterns without changing its own policies.

### `apple_flow_healer_scan_enable_issue_creation`

Lets live scans create issues automatically.

### `apple_flow_healer_scan_max_issues_per_run`

Caps how many issues one scan can create.

This matters for flood control.

### `apple_flow_healer_scan_severity_threshold`

Sets how serious a finding must be before it becomes an issue candidate.

### `apple_flow_healer_scan_default_labels`

Labels added to scanner-created issues.

---

## 12. Everyday Commands

These are the main workshop commands.

### Dashboard

```text
system: healer
```

### Pause

```text
system: healer pause
```

### Resume

```text
system: healer resume
```

### Dry Run Scan

```text
system: healer scan dry-run
```

### Live Scan

```text
system: healer scan
```

---

## 13. Reading the Healer Dashboard

The dashboard gives a quick picture of system health.

Important parts:

- whether the healer is paused
- total tracked issues
- counts by state
- recent attempt failure rate
- active lock count
- top pending issues
- learned lesson count
- recently used lesson count
- top recurring learned failure classes

A good workshop move is to explain each state:

- `queued`: waiting for work
- `claimed`: reserved by a worker
- `running`: actively being worked on
- `pr_pending_approval`: fix exists but PR gate is waiting
- `pr_open`: pull request is open
- `failed`: attempt failed
- `resolved`: work is done

If the learning layer is on, explain that:

- `Learned lessons` means reusable internal guardrails have been stored
- `recently_used` means lessons were injected into recent healer prompts
- `top learned failure classes` shows which recurring failure shapes the healer is learning from

This is a strong teaching moment because it shows the system improving through retrieval, not through unrestricted self-editing.

---

## 14. Running a Scan

For live teaching, use this order:

1. Run `system: healer scan dry-run`
2. Read the summary out loud
3. Explain whether issues would be created
4. If the output looks good, run `system: healer scan`

The scan summary tells you:

- how many findings were found
- how many passed the severity threshold
- how many issues were created
- how many findings were deduped
- whether any checks failed

If the scan finds nothing, that is still a valid result.

It means the current checks are passing.

---

## 15. Creating and Healing GitHub Issues

There are two main ways issues appear.

### Maintainer-Created Issues

A human creates the issue, then adds:

- `healer:ready`

Later, if needed:

- `healer:pr-approved`

### Scanner-Created Issues

The scanner creates the issue automatically when:

- a check fails
- the finding is important enough
- the finding is not a duplicate
- the scan is in live mode

Scanner-created issues can include labels like:

- `healer:ready`
- `kind:scan`

After that, Flow Healer treats them like normal healing issues.

For best results, issue bodies should mention:

- the failing test name when known
- the affected file or module when known
- the symptom, not just the conclusion

That gives both the proposer and the verifier better context.

---

## 16. Guarded PR Mode

Guarded PR mode is the best teaching mode because it shows real automation without giving up control.

In guarded mode:

- Flow Healer can find work
- Flow Healer can attempt fixes
- Flow Healer can verify its work
- PR actions still wait for approval rules

This mode helps people trust the system.

It says:

“The machine can move fast, but not without guardrails.”

---

## 17. Example Workshop Walkthrough

Here is a simple live demo plan.

### Part 1: Explain the System

Say:

“Flow Healer is a monitored repair loop for our codebase. It can discover problems, turn them into issues, try fixes in isolated workspaces, verify the result, and open pull requests in a controlled way.”

### Part 2: Show the Dashboard

Run:

```text
system: healer
```

Explain:

- paused status
- issue states
- failure rate
- pending work
- learned lesson stats if the learning layer is enabled

### Part 3: Show the Scanner

Run:

```text
system: healer scan dry-run
```

Explain:

- dry-run means no issue creation
- the system is checking the repo
- findings can be deduped

### Part 4: Show Live Scan

Run:

```text
system: healer scan
```

Explain:

- only qualifying findings become issues
- issues get labels
- the same finding should not keep creating duplicates

### Part 5: Show the GitHub Side

Open the issue list and point out:

- `healer:ready`
- scan labels
- any approval labels

### Part 6: Explain the Healing Loop

Walk through:

- claim
- workspace
- lock prediction
- patch
- test
- verify
- PR

### Part 7: Explain the Learning Layer

Say:

“Flow Healer can now remember what worked or failed in similar healing attempts. It uses that memory as a short retrieval brief before the next attempt. It is learning guardrails, not granting itself extra authority.”

### Part 8: Explain Human Control

Say clearly:

“Flow Healer is autonomous inside the lane we gave it. It is not acting with unlimited freedom.”

---

## 18. Operating Tips

- start with dry-run scans
- keep concurrency low at first
- use trusted actors
- require PR approval in early rollout
- watch failure rate trends
- keep issue titles and bodies clear
- use labels consistently
- do not skip the dashboard during demos
- enable learning only after the base workflow is already stable
- treat learned lessons as operational hints, not truth

---

## 19. Troubleshooting

### Problem: Scanner does not create issues

Check:

- live scan was used instead of dry-run
- `GITHUB_TOKEN` is available
- scan issue creation is enabled
- the finding passed the severity threshold
- the finding was not deduped

### Problem: Healer is not picking up issues

Check:

- issue has `healer:ready`
- issue author is in trusted actors, if that rule is enabled
- the healer is not paused
- the repo path is correct

### Problem: PR actions are not happening

Check:

- guarded mode is enabled
- `apple_flow_healer_pr_actions_require_approval=true`
- the issue has `healer:pr-approved`

### Problem: The dashboard looks stuck

Check:

- active lock leases
- recent failures
- whether the circuit breaker opened
- whether the healer is paused

### Problem: Too many issues from scans

Check:

- `apple_flow_healer_scan_max_issues_per_run`
- `apple_flow_healer_scan_severity_threshold`
- dedupe behavior

### Problem: Learned lessons are noisy

Check:

- whether the learning layer was enabled too early
- whether issue bodies are vague or low quality
- whether failures are mostly external or transient

Remember:

The learning layer should improve guidance, not become a dumping ground for noisy outcomes.

---

## 20. Best Practices

- use `guarded_pr` during rollout
- keep `healer_max_failed_tests_allowed=0`
- keep scan budgets low
- use clear labels and trusted actors
- describe failing files or tests in issue bodies when possible
- watch lock conflicts as a signal of issue overlap
- explain the dashboard in every workshop
- introduce the learning layer only after people understand the base control loop

---

## 21. FAQ

### Is Flow Healer a replacement for engineers?

No. It is a repair workflow that helps move maintenance work forward.

### Can it edit code without limits?

No. It works inside issue intake rules, lock rules, test gates, verifier checks, and PR controls.

### Can it create issues automatically?

Yes, if scanner issue creation is enabled and you run live scan mode.

### Can it open a PR without human review?

In guarded mode, PR actions require the configured approval path.

### Does the learning system rewrite its own prompts or policies?

No. In v1 it only stores internal lessons and retrieves them as context for future attempts.

### Does it use embeddings or an external memory service?

No. The current learning layer is internal, deterministic, and stored in the main SQLite system.

### What is the safest way to demo it?

Use guarded mode, keep concurrency at `1`, start with dry-run scans, and show the dashboard before and after each step.

---

## 22. Glossary

### Healer Issue

A GitHub issue that Flow Healer is allowed to process.

### Healing Queue

The tracked internal queue of candidate issues.

### Lease

A temporary claim that says one worker currently owns an issue.

### Lock Set

A set of predicted or actual scope keys used to reduce edit conflicts.

### Proposer

The AI step that proposes a patch.

### Verifier

The AI step that checks whether the proposed fix appears valid.

### Guarded PR Mode

A safety mode where PR actions still require explicit approval signals.

### Learned Lesson

A reusable internal guardrail created from a meaningful prior attempt outcome.

### Deduplication Fingerprint

A stable identifier used to avoid creating the same issue repeatedly from the same failure.

