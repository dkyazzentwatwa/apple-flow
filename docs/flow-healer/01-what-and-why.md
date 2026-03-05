# Flow Healer: What It Is and Why It Matters
## What Is Flow Healer?

Flow Healer is Apple Flow's autonomous remediation framework for engineering maintenance work.

It continuously:

1. Ingests maintainer-approved GitHub issues.
2. Can scan the codebase and create deduplicated healing issues.
2. Creates isolated per-issue workspaces.
3. Proposes fixes, runs verification gates, and retries safely.
4. Opens/updates PRs only when guardrails pass.

Flow Healer is intentionally **control-plane first**:

- durable queue + lease ownership
- deterministic state transitions
- explicit safety boundaries
- reconciliation after crashes/restarts

## Why It Is Important

Flow Healer is designed to remove repetitive reliability toil without removing human control.

Benefits:

- Faster mean time to repair for recurring defects.
- Consistent remediation process with auditable state.
- Reduced manual triage overhead.
- Faster issue discovery through scanner-based check failures.
- Safer automation via gating, retry budgets, and circuit breaker logic.

## The Framework Model

Flow Healer follows a "monitor -> claim -> fix -> verify -> publish" loop:

1. **Monitor**
   - Polls GitHub issues that match required labels.
   - Optionally scans the repo for failing checks and opens `healer:ready` issues.
2. **Claim**
   - Claims one issue lease at a time from the queue.
3. **Fix**
   - Runs a proposer pass to generate a patch.
4. **Verify**
   - Runs tests + independent verifier pass.
5. **Publish**
   - In guarded mode, waits for PR approval signal before PR actions.

## Safety Design

- Trust boundary: issue text is treated as untrusted input.
- Scan dedupe: repeated failures are fingerprinted so the same issue is not opened over and over.
- Locking: deterministic path/module locks reduce concurrent conflict risk.
- Backoff: exponential retries with hard budget.
- Circuit breaker: auto-pauses healing when failure rate spikes.
- Sandboxing: Docker-based execution path for test gates.

## Rollout Strategy

Flow Healer is built for staged rollout:

1. Shadow mode (observe/score only)
2. Draft fix mode (no PR)
3. Guarded PR mode (current default target)
4. Auto-merge (future, only after strong KPI evidence)
