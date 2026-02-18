# Codex Flow Beginner Setup in 10 Minutes

This guide gets `apple-flow` running fast on macOS with the safest default path.

## What you need first

- macOS with iMessage signed in
- Python `3.11+` (`python3 --version`)
- At least one AI CLI installed:
  - **Codex** (default): `codex` binary — [developers.openai.com/codex/cli](https://developers.openai.com/codex/cli/)
  - **Claude Code CLI**: `claude` binary — [claude.ai/code](https://claude.ai/code)

## 10-minute quick path

## 1) Go to the project (30 sec)

```bash
cd /Users/cypher/Public/code/apple-flow
```

## 2) Create your local env file (30 sec)

```bash
cp .env.example .env
```

## 3) Edit `.env` with your real values (2 min)

Open `.env` and confirm these at minimum:

- `apple_flow_allowed_senders=+1YOURNUMBER`
- `apple_flow_allowed_workspaces=/Users/cypher/Public/code/apple-flow`
- `apple_flow_default_workspace=/Users/cypher/Public/code/apple-flow`
- `apple_flow_connector=codex-cli` (default) **or** `apple_flow_connector=claude-cli`

Important: your own phone number must be in `apple_flow_allowed_senders` or relay messages will be blocked.

## 4) Authenticate your AI backend once (1 min)

Run the command for whichever backend you set in `.env`:

```bash
# If using apple_flow_connector=codex-cli (default)
codex login

# If using apple_flow_connector=claude-cli
claude auth login
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

- `Safety stop: apple_flow_allowed_senders is empty`
  - Set your number in `.env` (example: `+15551234567`).
- `Messages DB not found`
  - Check `apple_flow_messages_db_path` (default should be `~/Library/Messages/chat.db`).
- No responses to your texts
  - Confirm your sender number exactly matches `apple_flow_allowed_senders`.
  - Confirm your message uses the prefix `relay:` (default safety setting).

## Optional manual run (without helper script)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m apple_flow daemon
```
