# Preflight

Use this before enabling healer activity on a repo.

## Minimum Checks

- Git repo exists and is readable.
- `origin` remote exists.
- Default branch can be inferred.
- Docker CLI is installed and callable.
- Auth path is plausible for the repo host.
- The repo has a test signal that the healer can exercise.

## Recommended Early-Rollout Defaults

- one repo
- one issue at a time
- guarded PR mode
- no auto-merge
- low retry budget until test gates are stable

## Python Repo Heuristic

If any of these are present, treat it as a likely Python project:
- `pyproject.toml`
- `setup.py`
- `setup.cfg`
- `requirements.txt`
- `tests/`

For Python repos, confirm the Docker gate can bootstrap:
- `pytest`
- editable install when the repo is a package

## Red Flags

Do not proceed to a live healer run when:
- Docker is unavailable
- remote auth is broken
- repo has no meaningful test path
- target issue is broad or multi-part
- branch protections or CI expectations are unknown
