# Harness Engineering for Apple Flow

## Objective
Run Apple Flow as a deterministic system with explicit state transitions, policy invariants, and eval gates.

## Core Principles
1. Systems over prompts: safety and reliability are encoded in stateful workflows, not only prompt wording.
2. State-machine workflows: mutating work follows explicit run and approval transitions.
3. Architecture and taste guardrails: local-first, approval-gated, low-noise companion behavior are non-negotiable.
4. Eval-first iteration: high-risk behaviors are continuously tested and tied to release gates.

## System-Over-Prompts Map
| Principle | Canonical implementation |
|---|---|
| Mutating safety gates | `src/apple_flow/orchestrator.py`, `src/apple_flow/approval.py` |
| Sender verification | `src/apple_flow/approval.py` + `tests/test_approval_security.py` |
| Durable queue + retry recovery | `src/apple_flow/run_executor.py`, `tests/test_approval_lifecycle.py` |
| Duplicate outbound suppression | `src/apple_flow/egress.py`, `tests/test_egress_chunking.py` |
| Companion noise limits | `src/apple_flow/companion.py`, `tests/test_companion.py` |

## How to Use This Harness
1. Read the state contract: [State Machine](./state-machine.md).
2. Run the risk eval bundle: `python scripts/harness_eval_pack.py --json-out dist/harness-eval-pack.json`.
3. Feed output into the weekly KPI process in `agent-office/docs/AGENT_EVAL_SCORECARD.md`.
4. Run the pilot protocol for behavior changes: [Two-Week Pilot](./pilot.md).

## Documents in This Folder
- [State Machine](./state-machine.md): run lifecycle transitions and invariants.
- [Eval Pack](./evals.md): risk-to-test mapping and CI integration.
- [Two-Week Pilot](./pilot.md): baseline, rollout, and decision template.
