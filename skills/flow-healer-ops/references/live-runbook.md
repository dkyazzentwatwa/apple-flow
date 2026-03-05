# Live Runbook

## Standard GitHub Healer Flow

1. Confirm preflight on the target repo.
2. Confirm the repo is low-risk enough for the current rollout mode.
3. Create or select one narrow issue.
4. Apply the required intake labels.
5. Start or resume the healer loop.
6. Observe:
   - issue ingestion
   - worktree creation
   - patch application
   - Docker test gate
   - verifier pass
   - branch push
   - PR creation
7. Review the PR and decide whether to move it forward.

## What To Capture During A Live Run

- issue URL
- worktree path
- branch name
- test gate result
- verifier result
- PR URL

## Human Review Handoff

After PR open:
- review the diff
- review test/verifier output
- confirm branch has no unexpected files
- convert draft PR to reviewable state if appropriate
- merge only after normal repo policy is satisfied
