# Apple Flow Run State Machine

## Execution Flow (Mutating)
`message -> parse -> (task/project or auto-promoted mutating chat) -> planner -> awaiting approval -> approved -> queued/executing -> verifying (optional) -> completed|failed`

## Execution Flow (Non-Mutating)
`message -> parse -> chat|idea|plan -> connector turn (tools disabled) -> egress`

## Allowed Run-State Transitions

| Current State | Allowed Next State(s) | Owner | Trigger |
|---|---|---|---|
| `planning` | `awaiting_approval` | `ApprovalHandler.handle_approval_required` | Planner output captured and approval created |
| `awaiting_approval` | `queued`, `executing`, `denied`, `failed` | `ApprovalHandler.resolve` | Approve/deny/expire path |
| `queued` | `executing`, `failed`, `cancelled`, `awaiting_approval` | `RunExecutor` + `ApprovalHandler` | Worker execution, cancellation, or checkpoint |
| `executing` | `verifying`, `completed`, `failed`, `awaiting_approval` | `ApprovalHandler._execute_run_attempt` | Success, verifier enabled, failure, checkpoint |
| `verifying` | `completed`, `failed` | `ApprovalHandler._execute_run_attempt` | Verifier pass/fail |
| `cancelled` | terminal | `RelayOrchestrator._handle_system` | Manual cancellation / killswitch |
| `denied` | terminal | `ApprovalHandler.resolve`, `Store.deny_all_approvals` | User denial |
| `failed` | terminal | `ApprovalHandler`, `RunExecutor` | Error, timeout exhaustion, expired approval |
| `completed` | terminal | `ApprovalHandler._execute_run_attempt` | Execution + (optional) verification success |

## Reserved Enum States (Not Actively Emitted Today)
- `received`
- `running`
- `checkpointed`

These remain in `RunState` for compatibility and future expansion. Harness audits should flag accidental writes to these states until transition handlers are implemented.

## Invariants
1. Mutating operations require approval: every `task`/`project` run must pass through `awaiting_approval` before execution.
2. Approval actor identity is normalized: approve/deny sender must match original requester after `normalize_sender()`.
3. Workspace policy is checked before run creation: blocked workspaces fail closed.
4. Duplicate outbound suppression remains enabled in iMessage egress.
5. Retry and checkpoint behavior is bounded by `max_resume_attempts`.
6. Companion proactive output respects quiet hours, mute, and hourly rate caps.

## Guardrail File References
- `src/apple_flow/orchestrator.py`
- `src/apple_flow/approval.py`
- `src/apple_flow/run_executor.py`
- `src/apple_flow/egress.py`
- `src/apple_flow/companion.py`
