# Flow Healer: Operations and Troubleshooting

## Dashboard Command

Use:

```text
system: healer
system: healer pause
system: healer resume
system: healer scan dry-run
system: healer scan
```

Dashboard includes:

- tracked issue count
- state distribution (`queued`, `running`, `pr_pending_approval`, `pr_open`, `failed`, `resolved`)
- recent attempt failure rate
- active lock lease count
- learned lesson count and recent lesson usage
- top learned failure classes when learning is enabled
- top pending issues
- latest scan-to-issue summary (when scan commands are used)

## Guardrail Checklist

Before enabling in production:

1. `apple_flow_healer_mode=guarded_pr`
2. Required issue label(s) configured
3. PR approval label configured
4. Retry budget + circuit breaker set
5. Docker available on host
6. `GITHUB_TOKEN` present with minimum required scopes
7. Keep `apple_flow_healer_learning_enabled=false` until base workflow is behaving well

## Common Issues

### "Flow Healer disabled: missing GitHub token or origin slug"

- Ensure `GITHUB_TOKEN` is exported.
- Ensure repo has `origin` remote set to GitHub.
- If launchd does not export the token, keep the project `.env` populated so healer can fall back to reading `GITHUB_TOKEN` from there.

### "PR pending approval never advances"

- Add required PR approval label (default: `healer:pr-approved`) to the issue.

### "Frequent lock conflicts"

- Lower concurrency to `1`.
- Keep issue scope tighter and include deterministic failing paths in issue body.

### "Circuit breaker keeps opening"

- Inspect recent failed attempts via logs.
- Reduce concurrency.
- Tighten issue intake labels and trusted actors.

### "Learned lessons are noisy"

- Disable `apple_flow_healer_learning_enabled` temporarily.
- Make issue titles/bodies more concrete so retrieval has better signal.
- Enable learning only after proposer/test/verifier behavior is already stable.

## Security Notes

- Issue text is untrusted.
- Do not grant wide GitHub token permissions.
- Prefer explicit intake labels over broad issue ingestion.
- Keep sandbox mode as Docker in early rollout.

## Suggested KPI Tracking

Track weekly:

1. Healer attempt success rate.
2. PR acceptance rate.
3. Regression rate after merge.
4. Circuit breaker activations.
5. Time-to-first-PR for `healer:ready` issues.
