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

                CREATE TABLE IF NOT EXISTS run_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    lease_owner TEXT DEFAULT NULL,
                    lease_expires_at TEXT DEFAULT NULL,
                    error_text TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs (run_id)
                );

                -- Performance indexes
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
                CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
                CREATE INDEX IF NOT EXISTS idx_runs_sender ON runs(sender);
                CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_status_created ON run_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_run_status ON run_jobs(run_id, status);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_lease ON run_jobs(status, lease_expires_at);
                """
            )
            conn.commit()

            # Migration: Add source_context column if it doesn't exist
            try:
                cursor = conn.execute("SELECT source_context FROM runs LIMIT 1")
                cursor.fetchone()
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE runs ADD COLUMN source_context TEXT DEFAULT NULL")
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

    def record_message(
        self, message_id: str, sender: str, text: str, received_at: str, dedupe_hash: str
    ) -> bool:
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

    def create_run(
        self,
        run_id: str,
        sender: str,
        intent: str,
        state: str,
        cwd: str,
        risk_level: str,
        source_context: dict[str, Any] | None = None,
    ) -> None:
        conn = self._connect()
        with self._lock:
            source_context_json = json.dumps(source_context) if source_context else None
            conn.execute(
                """
                INSERT INTO runs(run_id, sender, intent, state, cwd, risk_level, source_context)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, sender, intent, state, cwd, risk_level, source_context_json),
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

    def list_active_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """List active (non-terminal) runs sorted by most recently updated."""
        conn = self._connect()
        active_states = (
            RunState.PLANNING.value,
            RunState.AWAITING_APPROVAL.value,
            RunState.QUEUED.value,
            RunState.RUNNING.value,
            RunState.EXECUTING.value,
            RunState.VERIFYING.value,
        )
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM runs
                WHERE state IN (?, ?, ?, ?, ?, ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (*active_states, limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def get_run_source_context(self, run_id: str) -> dict[str, Any] | None:
        """Get the source context for a run (reminder_id, note_id, etc.)"""
        run = self.get_run(run_id)
        if not run:
            return None
        source_context_json = run.get("source_context")
        if not source_context_json:
            return None
        try:
            return json.loads(source_context_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def create_approval(
        self,
        request_id: str,
        run_id: str,
        summary: str,
        command_preview: str,
        expires_at: str,
        sender: str,
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
            row = conn.execute(
                "SELECT * FROM approvals WHERE request_id = ?", (request_id,)
            ).fetchone()
            return self._row_to_dict(row)

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
                (ApprovalStatus.PENDING.value,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]

    def deny_all_approvals(self) -> int:
        """Mark all pending approvals as denied and their runs as denied.

        Returns the number of approvals cancelled.
        """
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT request_id, run_id FROM approvals WHERE status = ?",
                (ApprovalStatus.PENDING.value,),
            ).fetchall()
            if not rows:
                return 0
            ids = [row["request_id"] for row in rows]
            run_ids = [row["run_id"] for row in rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE approvals SET status = 'denied' WHERE request_id IN ({placeholders})",
                ids,
            )
            run_placeholders = ",".join("?" * len(run_ids))
            conn.execute(
                f"UPDATE runs SET state = '{RunState.DENIED.value}', updated_at = CURRENT_TIMESTAMP "
                f"WHERE run_id IN ({run_placeholders})",
                run_ids,
            )
            conn.commit()
            return len(ids)

    def resolve_approval(self, request_id: str, status: str) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "UPDATE approvals SET status = ? WHERE request_id = ?",
                (status, request_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def create_event(
        self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO events(event_id, run_id, step, event_type, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (event_id, run_id, step, event_type, json.dumps(payload)),
            )
            conn.execute(
                "UPDATE runs SET updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()

    def list_events(self, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            events = []
            for row in rows:
                data = self._row_to_dict(row)
                if data is None:
                    continue
                try:
                    data["payload"] = json.loads(data.pop("payload_json", "{}"))
                except json.JSONDecodeError:
                    data["payload"] = {}
                events.append(data)
            return events

    def list_events_for_run(self, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
            events = []
            for row in rows:
                data = self._row_to_dict(row)
                if data is None:
                    continue
                try:
                    data["payload"] = json.loads(data.pop("payload_json", "{}"))
                except json.JSONDecodeError:
                    data["payload"] = {}
                events.append(data)
            return events

    def get_latest_event_for_run(self, run_id: str) -> dict[str, Any] | None:
        events = self.list_events_for_run(run_id, limit=1)
        if not events:
            return None
        return events[0]

    def count_run_events(self, run_id: str, event_type: str | None = None) -> int:
        conn = self._connect()
        with self._lock:
            if event_type:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE run_id = ? AND event_type = ?",
                    (run_id, event_type),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
            return int(row[0]) if row is not None else 0

    # --- Durable run job queue ---

    def enqueue_run_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sender: str,
        phase: str,
        attempt: int,
        payload: dict[str, Any] | None = None,
        status: str = "queued",
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO run_jobs(job_id, run_id, sender, phase, attempt, payload_json, status)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    run_id,
                    sender,
                    phase,
                    int(attempt),
                    json.dumps(payload or {}),
                    status,
                ),
            )
            conn.commit()

    def claim_next_run_job(self, *, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        """Atomically claim the oldest queued job for a worker lease window."""
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                """
                SELECT job_id
                FROM run_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            job_id = str(row["job_id"])
            cursor = conn.execute(
                """
                UPDATE run_jobs
                SET status = 'running',
                    lease_owner = ?,
                    lease_expires_at = datetime('now', ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND status = 'queued'
                """,
                (worker_id, f"+{int(max(1, lease_seconds))} seconds", job_id),
            )
            if cursor.rowcount == 0:
                conn.commit()
                return None

            claimed = conn.execute("SELECT * FROM run_jobs WHERE job_id = ?", (job_id,)).fetchone()
            conn.commit()
            data = self._row_to_dict(claimed)
            if data is None:
                return None
            try:
                data["payload"] = json.loads(data.pop("payload_json", "{}"))
            except json.JSONDecodeError:
                data["payload"] = {}
            return data

    def renew_run_job_lease(self, *, job_id: str, worker_id: str, lease_seconds: int) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE run_jobs
                SET lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ? AND status = 'running' AND lease_owner = ?
                """,
                (f"+{int(max(1, lease_seconds))} seconds", job_id, worker_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def complete_run_job(self, *, job_id: str, status: str, error_text: str | None = None) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE run_jobs
                SET status = ?,
                    error_text = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = ?
                """,
                (status, error_text, job_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_run_jobs(
        self, *, run_id: str | None = None, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            query = "SELECT * FROM run_jobs WHERE 1=1"
            params: list[Any] = []
            if run_id is not None:
                query += " AND run_id = ?"
                params.append(run_id)
            if status is not None:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(query, params).fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_dict(row)
            if data is None:
                continue
            try:
                data["payload"] = json.loads(data.pop("payload_json", "{}"))
            except json.JSONDecodeError:
                data["payload"] = {}
            out.append(data)
        return out

    def cancel_run_jobs(self, run_id: str) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE run_jobs
                SET status = 'cancelled',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ? AND status IN ('queued', 'running')
                """,
                (run_id,),
            )
            conn.commit()
            return int(cursor.rowcount)

    def requeue_expired_run_jobs(self) -> int:
        """Requeue running jobs whose lease has expired."""
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE run_jobs
                SET status = 'queued',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE status = 'running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return int(cursor.rowcount)

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
            rows = conn.execute("SELECT state, COUNT(*) as cnt FROM runs GROUP BY state").fetchall()
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
        # Escape LIKE wildcards to prevent data disclosure via % or _ in user input
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM messages WHERE sender = ? AND text LIKE ? ESCAPE '\\' ORDER BY received_at DESC LIMIT ?",
                (sender, f"%{escaped_query}%", limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]
