# Apple Flow Example

Apple Flow is the reference repo for this healer pattern.

Useful reference points:
- docs: `docs/flow-healer/`
- main loop: `src/apple_flow/healer_loop.py`
- Docker test runner: `src/apple_flow/healer_runner.py`
- verifier pass: `src/apple_flow/healer_verifier.py`
- worktree manager: `src/apple_flow/healer_workspace.py`

## Apple Flow Guarded Defaults

- healer mode: `guarded_pr`
- intake label: `healer:ready`
- PR advancement label: `healer:pr-approved`
- sandbox mode: `docker`

## Apple Flow Operator Commands

- `system: healer`
- `system: healer pause`
- `system: healer resume`
- `system: healer scan dry-run`
- `system: healer scan`

Use Apple Flow as an example of the pattern, not as a requirement for the generic skill.
