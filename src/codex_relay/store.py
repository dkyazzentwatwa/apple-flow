from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import ApprovalStatus, RunState


class SQLiteStore:
    """Thread-safe SQLite storage with connection caching."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        """Get or create a cached database connection (thread-safe)."""
        with self._lock:
            if self._conn is not None:
                return self._conn
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._conn = conn
            return conn

    def close(self) -> None:
        """Close the cached database connection."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def bootstrap(self) -> None:
        conn = self._connect()
        with self._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    sender TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    dedupe_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    state TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    request_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    command_preview TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );

                CREATE TABLE IF NOT EXISTS kv_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                -- Performance indexes
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
                CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
                CREATE INDEX IF NOT EXISTS idx_runs_sender ON runs(sender);
                CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
                """
            )
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {k: row[k] for k in row.keys()}

    def upsert_session(self, sender: str, thread_id: str, mode: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO sessions(sender, thread_id, mode, last_seen_at)
                VALUES(?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(sender) DO UPDATE SET
                    thread_id=excluded.thread_id,
                    mode=excluded.mode,
                    last_seen_at=CURRENT_TIMESTAMP
                """,
                (sender, thread_id, mode),
            )
            conn.commit()

    def get_session(self, sender: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM sessions WHERE sender = ?", (sender,)).fetchone()
            return self._row_to_dict(row)

    def list_sessions(self) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute("SELECT * FROM sessions ORDER BY last_seen_at DESC").fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def record_message(self, message_id: str, sender: str, text: str, received_at: str, dedupe_hash: str) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO messages(message_id, sender, text, received_at, dedupe_hash)
                VALUES(?, ?, ?, ?, ?)
                """,
                (message_id, sender, text, received_at, dedupe_hash),
            )
            conn.commit()
            return cursor.rowcount == 1

    def create_run(self, run_id: str, sender: str, intent: str, state: str, cwd: str, risk_level: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO runs(run_id, sender, intent, state, cwd, risk_level)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (run_id, sender, intent, state, cwd, risk_level),
            )
            conn.commit()

    def update_run_state(self, run_id: str, state: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                "UPDATE runs SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (state, run_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return self._row_to_dict(row)

    def create_approval(
        self, request_id: str, run_id: str, summary: str, command_preview: str, expires_at: str, sender: str
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO approvals(request_id, run_id, sender, summary, command_preview, expires_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (request_id, run_id, sender, summary, command_preview, expires_at),
            )
            conn.commit()

    def get_approval(self, request_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
            return self._row_to_dict(row)

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING.value,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def resolve_approval(self, request_id: str, status: str) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "UPDATE approvals SET status = ? WHERE request_id = ?",
                (status, request_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_event(self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO events(event_id, run_id, step, event_type, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (event_id, run_id, step, event_type, json.dumps(payload)),
            )
            conn.commit()

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def set_state(self, key: str, value: str) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO kv_state(key, value)
                VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
            conn.commit()

    def get_state(self, key: str) -> str | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT value FROM kv_state WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            return str(row["value"])

    # --- Feature 2: Health Dashboard ---

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate stats for the health dashboard."""
        conn = self._connect()
        with self._lock:
            session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            message_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM approvals WHERE status = 'pending'"
            ).fetchone()[0]

            # Runs by state
            rows = conn.execute(
                "SELECT state, COUNT(*) as cnt FROM runs GROUP BY state"
            ).fetchall()
            runs_by_state = {row["state"]: row["cnt"] for row in rows}

            # Most recent event
            last_event_row = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            last_event = self._row_to_dict(last_event_row)

            return {
                "active_sessions": session_count,
                "total_messages": message_count,
                "pending_approvals": pending_count,
                "runs_by_state": runs_by_state,
                "last_event": last_event,
            }

    # --- Feature 3: Conversation Memory ---

    def recent_messages(self, sender: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch the most recent messages from a sender."""
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM messages WHERE sender = ? ORDER BY received_at DESC LIMIT ?",
                (sender, limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def search_messages(self, sender: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search messages from a sender by text content."""
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM messages WHERE sender = ? AND text LIKE ? ORDER BY received_at DESC LIMIT ?",
                (sender, f"%{query}%", limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]
