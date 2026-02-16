# Codex Flow Beginner Setup in 10 Minutes

This guide gets `codex-flow` running fast on macOS with the safest default path.

## What you need first

- macOS with iMessage signed in
- Python `3.11+` (`python3 --version`)
- Codex CLI installed and available as `codex`

## 10-minute quick path

## 1) Go to the project (30 sec)

```bash
cd /Users/cypher/Public/code/codex-flow
```

## 2) Create your local env file (30 sec)

```bash
cp .env.example .env
```

## 3) Edit `.env` with your real values (2 min)

Open `.env` and confirm these at minimum:

- `codex_relay_allowed_senders=+1YOURNUMBER`
- `codex_relay_allowed_workspaces=/Users/cypher/Public/code/codex-flow`
- `codex_relay_default_workspace=/Users/cypher/Public/code/codex-flow`

Important: your own phone number must be in `codex_relay_allowed_senders` or relay messages will be blocked.

## 4) Authenticate Codex once (1 min)

```bash
codex login
```

## 5) Run beginner setup + tests + daemon (3-4 min)

```bash
./scripts/start_beginner.sh
```

What this script does for you:

- Creates `.venv` if needed
- Installs dependencies
- Validates `.env` safety fields
- Runs `pytest -q`
- Starts the relay daemon in foreground mode

## 6) Send your first iMessage command (1 min)

From your allowed sender number, text one of:

- `relay: hello`
- `idea: build a tiny todo app`
- `plan: add login to my project`
- `task: create a README section`

## 7) Stop when done (5 sec)

In the terminal running the daemon, press `Ctrl+C`.

## Fast troubleshooting

- `Safety stop: codex_relay_allowed_senders is empty`
  - Set your number in `.env` (example: `+15551234567`).
- `Messages DB not found`
  - Check `codex_relay_messages_db_path` (default should be `~/Library/Messages/chat.db`).
- No responses to your texts
  - Confirm your sender number exactly matches `codex_relay_allowed_senders`.
  - Confirm your message uses the prefix `relay:` (default safety setting).

## Optional manual run (without helper script)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m codex_relay daemon
```
