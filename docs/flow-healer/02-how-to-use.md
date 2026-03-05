# Flow Healer: How To Use It

## Beginner Quickstart

### 1) Set core config in `.env`

Use safe defaults first:

```env
apple_flow_enable_autonomous_healer=true
apple_flow_healer_mode=guarded_pr
apple_flow_healer_repo_path=/absolute/path/to/your/repo
apple_flow_healer_issue_required_labels=healer:ready
apple_flow_healer_pr_actions_require_approval=true
apple_flow_healer_pr_required_label=healer:pr-approved
apple_flow_healer_sandbox_mode=docker
apple_flow_healer_learning_enabled=false
```

### 2) Ensure GitHub auth exists

Flow Healer uses `GITHUB_TOKEN` for issue/PR API operations.

If you want scanner-created issues, the token also needs permission to create issues in the repo.

### 3) Add issue labels

For an issue to be processed:

1. Add `healer:ready`.
2. Add `healer:pr-approved` when you want PR actions to proceed in guarded mode.

### 4) Start Apple Flow daemon

```bash
python -m apple_flow daemon
```

### 5) Check dashboard from iMessage

```text
system: healer
```

This returns queue state, attempt/failure snapshot, and pending top issues.

If learning is enabled, the dashboard also shows:

- learned lesson count
- recently used lesson count
- top recurring learned failure classes

### 6) Pause or resume from iMessage

```text
system: healer pause
system: healer resume
```

### 7) Run scan-to-issue mode (optional)

```text
system: healer scan dry-run
system: healer scan
```

Use dry-run first, then live mode to create deduped `healer:ready` issues.

Dry-run checks the repo and reports findings without creating GitHub issues.

Live mode:

1. Runs the local scan checks.
2. Filters findings by severity threshold.
3. Deduplicates repeated findings by fingerprint.
4. Creates GitHub issues with `healer:ready` plus your configured scan labels.

## Advanced Configuration

Use these when tuning reliability and throughput:

```env
apple_flow_healer_max_concurrent_issues=2
apple_flow_healer_retry_budget=8
apple_flow_healer_backoff_initial_seconds=60
apple_flow_healer_backoff_max_seconds=3600
apple_flow_healer_circuit_breaker_failure_rate=0.5
apple_flow_healer_circuit_breaker_window=20
apple_flow_healer_max_wall_clock_seconds_per_issue=1800
apple_flow_healer_max_diff_files=20
apple_flow_healer_max_diff_lines=1200
apple_flow_healer_max_failed_tests_allowed=0
apple_flow_healer_trusted_actors=dkyazzentwatwa
apple_flow_healer_learning_enabled=false
apple_flow_healer_scan_enable_issue_creation=true
apple_flow_healer_scan_max_issues_per_run=5
apple_flow_healer_scan_severity_threshold=medium
apple_flow_healer_scan_default_labels=healer:ready,kind:scan
```

### Recommended Advanced Defaults

- Start with `healer_max_concurrent_issues=1` if your repo is busy.
- Keep `healer_max_failed_tests_allowed=0` in early rollout.
- Set `healer_trusted_actors` when you want strict author-based gating.
- Keep `healer_learning_enabled=false` until the base healer workflow is stable.
- Keep `healer_scan_severity_threshold=medium` until you trust the scanner quality.
- Keep `healer_scan_max_issues_per_run` low so one bad run cannot flood your repo.

## Typical Workflow

1. Triage and label issue `healer:ready`.
2. Flow Healer claims and attempts remediation.
3. If guarded PR gate is enabled, add `healer:pr-approved`.
4. Flow Healer opens/updates PR.
5. Human reviews and merges.

## Typical Scanner Workflow

1. Send `system: healer scan dry-run`.
2. Review the summary in iMessage.
3. Send `system: healer scan` when the output looks useful.
4. New issues appear on GitHub with scan labels.
5. Flow Healer picks up those issues like any other `healer:ready` issue.
