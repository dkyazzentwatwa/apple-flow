# Demo Flow

## Goal

Prove the healer path in the safest realistic environment possible.

## Recommended Sequence

1. Create a disposable repo.
2. Seed it with one tiny failing Python test.
3. Push the baseline `main` branch.
4. Open one narrow GitHub issue.
5. Run the healer path.
6. Observe:
   - isolated worktree
   - patch application
   - Docker test gate
   - verifier pass
   - branch push
   - PR creation
7. Review the PR and decide whether to merge.

## Why This Works

This path proves the core moving parts without mixing in product risk:
- repo hosting
- git branch/worktree behavior
- containerized tests
- remote push
- PR publication

## Demo Hygiene

- keep the repo disposable
- keep the issue narrow
- keep artifacts easy to inspect
- do not hide failures; record the failing checkpoint explicitly
