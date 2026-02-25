# GEMINI.md

## Project Overview
**Apple Flow** is a local-first macOS daemon that bridges Apple-native apps (iMessage, Mail, Reminders, Notes, and Calendar) to AI assistants (Claude, Codex, and Cline). It allows users to control AI directly through their everyday Apple apps, emphasizing privacy and security by keeping data local to the Mac.

### Key Features
- **Multi-Channel Ingress/Egress:** Interact via iMessage, Mail, Reminders, Notes, and Calendar.
- **Proactive Companion:** An autonomous AI layer that provides daily digests, reminders, and stale approval alerts.
- **Security-First:** Includes sender allowlists, workspace restrictions, and a mandatory approval workflow for mutating operations.
- **Modular AI Backends:** Supports Claude CLI, Codex CLI, and Cline for agentic or stateless execution.
- **Admin API:** A FastAPI-based interface for health monitoring, session management, and programmatic task submission.

### Tech Stack
- **Language:** Python 3.11+
- **Web Framework:** FastAPI (for Admin API)
- **Configuration:** Pydantic Settings
- **Persistence:** SQLite (for session, approval, and event storage)
- **Integration:** AppleScript (for communication with macOS apps)
- **Service Management:** Launchd (via `local.apple-flow.plist`)

---

## Building and Running

### Prerequisites
- macOS with iMessage signed in.
- Python 3.11+ and Node.js installed.
- AI CLI (Claude, Codex, or Cline) installed and authenticated.

### Key Commands
- **Setup & Installation:**
  ```bash
  ./scripts/setup_autostart.sh  # Main installer and auto-start setup
  python -m apple_flow setup    # Manual configuration wizard
  ```
- **Running the Daemon:**
  ```bash
  python -m apple_flow daemon   # Run the daemon in the foreground
  launchctl start local.apple-flow # Start via launchd
  ```
- **Running the Admin API:**
  ```bash
  python -m apple_flow admin    # Run the FastAPI admin server (port 8787)
  ```
- **Testing:**
  ```bash
  pytest                        # Run the comprehensive test suite
  bash scripts/smoke_test.sh    # End-to-end verification of all channels
  ```
- **Linting and Type Checking:**
  ```bash
  ruff check .                  # Lint the codebase
  mypy src                      # Run static type analysis
  ```

---

## Architecture and Design

### Core Components
1.  **`RelayDaemon` (`src/apple_flow/daemon.py`):** The central orchestrator that manages polling loops for all active ingress channels and the companion loop.
2.  **`RelayOrchestrator` (`src/apple_flow/orchestrator.py`):** Handles message parsing, command routing, and execution flow. It manages the transition from natural language to actionable tasks.
3.  **`ConnectorProtocol` (`src/apple_flow/protocols.py`):** Defines the interface for AI backends. Implementations include `ClaudeCliConnector`, `CodexCliConnector`, and `ClineConnector`.
4.  **`Gateway` Modules:** Specialized ingress and egress handlers for iMessage, Mail, Reminders, Notes, and Calendar.
5.  **`Companion` (`src/apple_flow/companion.py`):** Implements proactive logic using `SOUL.md` for personality and `MEMORY.md` for persistent context.
6.  **`Store` (`src/apple_flow/store.py`):** A SQLite-backed repository for tracking conversation state, pending approvals, and system events.

### Development Conventions
- **Code Style:** Strictly adheres to Python 3.11+ idioms, using `from __future__ import annotations`.
- **Formatting:** Managed by `ruff` with a line length of 100.
- **Testing:** New features should include unit and/or integration tests in the `tests/` directory.
- **Configuration:** All settings are managed via `RelaySettings` in `src/apple_flow/config.py`, which loads from `.env`.
- **Security:** Mutating operations (e.g., file edits) *must* go through the `ApprovalHandler`.

---

## Key Files
- `src/apple_flow/main.py`: Entry point for the Admin API.
- `src/apple_flow/daemon.py`: Core daemon logic and loop management.
- `src/apple_flow/orchestrator.py`: Message routing and command execution.
- `src/apple_flow/config.py`: Centralized configuration management.
- `agent-office/SOUL.md`: Personality definition for the AI companion.
- `.env.example`: Template for system configuration.
