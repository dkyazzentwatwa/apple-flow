# Failure Modes

## Docker Gate Fails Before Tests Run

Common causes:
- missing test tool in container
- missing package install step
- unsupported language/runtime assumptions

Actions:
- inspect the exact command and container image
- confirm whether the repo needs bootstrap before tests
- fix the test gate before retrying the issue

## Patch Applies But Tests Fail

Actions:
- confirm the issue scope is narrow enough
- inspect the changed files and diff size
- verify whether targeted tests and full tests disagree
- retry only after the failure mode is understood

## Verifier Rejects The Fix

Actions:
- inspect whether the change fixes the issue but violates expected behavior
- check whether the issue description was ambiguous
- narrow the issue and retry

## PR Does Not Open

Common causes:
- push failed
- repo auth missing or invalid
- remote branch rejected
- GitHub API/token failure

Actions:
- verify branch exists locally
- verify remote push path
- verify GitHub auth separately from git auth

## Healer Appears Stuck

Check:
- paused state
- recent attempts
- active locks
- backoff window
- missing labels

If repeated failures continue, pause the healer and reduce scope before resuming.
