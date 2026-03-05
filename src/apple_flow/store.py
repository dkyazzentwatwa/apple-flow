from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ApprovalStatus, RunState

logger = logging.getLogger("apple_flow.store")


class SQLiteStore:
    """Thread-safe SQLite storage with connection caching."""

    def __init__(self, db_path: Path, csv_audit_logger: Any | None = None):
        self.db_path = Path(db_path)
        self.csv_audit_logger = csv_audit_logger
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

                CREATE TABLE IF NOT EXISTS healer_issues (
                    issue_id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    labels_json TEXT NOT NULL DEFAULT '[]',
                    priority INTEGER NOT NULL DEFAULT 100,
                    state TEXT NOT NULL DEFAULT 'queued',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    backoff_until TEXT DEFAULT NULL,
                    lease_owner TEXT DEFAULT NULL,
                    lease_expires_at TEXT DEFAULT NULL,
                    workspace_path TEXT NOT NULL DEFAULT '',
                    branch_name TEXT NOT NULL DEFAULT '',
                    pr_number INTEGER DEFAULT NULL,
                    pr_state TEXT NOT NULL DEFAULT '',
                    last_failure_class TEXT NOT NULL DEFAULT '',
                    last_failure_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS healer_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    prediction_source TEXT NOT NULL DEFAULT '',
                    predicted_lock_set_json TEXT NOT NULL DEFAULT '[]',
                    actual_diff_set_json TEXT NOT NULL DEFAULT '[]',
                    test_summary_json TEXT NOT NULL DEFAULT '{}',
                    verifier_summary_json TEXT NOT NULL DEFAULT '{}',
                    failure_class TEXT NOT NULL DEFAULT '',
                    failure_reason TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT DEFAULT NULL,
                    FOREIGN KEY (issue_id) REFERENCES healer_issues (issue_id)
                );

                CREATE TABLE IF NOT EXISTS healer_lessons (
                    lesson_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    lesson_kind TEXT NOT NULL,
                    scope_key TEXT NOT NULL DEFAULT 'repo:*',
                    fingerprint TEXT NOT NULL DEFAULT '',
                    problem_summary TEXT NOT NULL DEFAULT '',
                    lesson_text TEXT NOT NULL,
                    test_hint TEXT NOT NULL DEFAULT '',
                    guardrail_json TEXT NOT NULL DEFAULT '{}',
                    confidence INTEGER NOT NULL DEFAULT 50,
                    outcome TEXT NOT NULL DEFAULT 'unknown',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_used_at TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (issue_id) REFERENCES healer_issues (issue_id),
                    FOREIGN KEY (attempt_id) REFERENCES healer_attempts (attempt_id)
                );

                CREATE TABLE IF NOT EXISTS healer_locks (
                    lock_key TEXT PRIMARY KEY,
                    granularity TEXT NOT NULL,
                    issue_id TEXT NOT NULL,
                    lease_owner TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (issue_id) REFERENCES healer_issues (issue_id)
                );

                CREATE TABLE IF NOT EXISTS scan_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS scan_findings (
                    fingerprint TEXT PRIMARY KEY,
                    scan_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    issue_number INTEGER DEFAULT NULL,
                    status TEXT NOT NULL DEFAULT 'detected',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                -- Performance indexes
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
                CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
                CREATE INDEX IF NOT EXISTS idx_runs_sender ON runs(sender);
                CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_status_created ON run_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_run_status ON run_jobs(run_id, status);
                CREATE INDEX IF NOT EXISTS idx_run_jobs_lease ON run_jobs(status, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_healer_issues_state_backoff ON healer_issues(state, backoff_until, priority, updated_at);
                CREATE INDEX IF NOT EXISTS idx_healer_issues_lease ON healer_issues(state, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_healer_attempts_issue_started ON healer_attempts(issue_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_healer_lessons_scope_updated ON healer_lessons(scope_key, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_healer_lessons_outcome_updated ON healer_lessons(outcome, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_healer_locks_issue ON healer_locks(issue_id);
                CREATE INDEX IF NOT EXISTS idx_healer_locks_lease ON healer_locks(lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_scan_runs_created ON scan_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_scan_findings_status ON scan_findings(status, last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_scan_findings_issue_number ON scan_findings(issue_number);
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

            for column_name, column_type in (
                ("failure_class", "TEXT NOT NULL DEFAULT ''"),
                ("failure_reason", "TEXT NOT NULL DEFAULT ''"),
            ):
                try:
                    cursor = conn.execute(f"SELECT {column_name} FROM healer_attempts LIMIT 1")
                    cursor.fetchone()
                except sqlite3.OperationalError:
                    conn.execute(f"ALTER TABLE healer_attempts ADD COLUMN {column_name} {column_type}")
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

    def create_event(self, event_id: str, run_id: str, step: str, event_type: str, payload: dict[str, Any]) -> None:
        created_at = datetime.now(UTC).isoformat()
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

        if self.csv_audit_logger is not None:
            try:
                run = self.get_run(run_id) or {}
                payload_json = json.dumps(payload)
                source_context = self.get_run_source_context(run_id) or {}
                self.csv_audit_logger.append_event(
                    {
                        "created_at": created_at,
                        "event_id": event_id,
                        "run_id": run_id,
                        "step": step,
                        "event_type": event_type,
                        "channel": payload.get("channel", source_context.get("channel", "")),
                        "sender": payload.get("sender", run.get("sender", "")),
                        "workspace": payload.get("workspace", run.get("cwd", "")),
                        "connector": payload.get("connector", ""),
                        "attempt": payload.get("attempt", ""),
                        "status": payload.get("status", ""),
                        "duration_ms": payload.get("duration_ms", ""),
                        "snippet": payload.get("snippet", ""),
                        "payload_json": payload_json,
                    }
                )
            except Exception as exc:
                # CSV analytics mirror is best-effort; SQLite event insert remains canonical.
                logger.warning("Failed to mirror event %s to CSV audit log: %s", event_id, exc)

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

    def list_run_jobs(self, *, run_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
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

    # --- Autonomous healer queue/state ---

    @staticmethod
    def _decode_healer_issue_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        try:
            data["labels"] = json.loads(data.pop("labels_json", "[]"))
        except json.JSONDecodeError:
            data["labels"] = []
        return data

    @staticmethod
    def _decode_healer_attempt_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        for key in ("predicted_lock_set_json", "actual_diff_set_json"):
            try:
                data[key.replace("_json", "")] = json.loads(data.pop(key, "[]"))
            except json.JSONDecodeError:
                data[key.replace("_json", "")] = []
        for key in ("test_summary_json", "verifier_summary_json"):
            try:
                data[key.replace("_json", "")] = json.loads(data.pop(key, "{}"))
            except json.JSONDecodeError:
                data[key.replace("_json", "")] = {}
        return data

    @staticmethod
    def _decode_healer_lesson_row(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        try:
            data["guardrail"] = json.loads(data.pop("guardrail_json", "{}"))
        except json.JSONDecodeError:
            data["guardrail"] = {}
        return data

    def upsert_healer_issue(
        self,
        *,
        issue_id: str,
        repo: str,
        title: str,
        body: str,
        author: str,
        labels: list[str],
        priority: int = 100,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_issues(
                    issue_id, repo, title, body, author, labels_json, priority, state
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, 'queued')
                ON CONFLICT(issue_id) DO UPDATE SET
                    repo = excluded.repo,
                    title = excluded.title,
                    body = excluded.body,
                    author = excluded.author,
                    labels_json = excluded.labels_json,
                    priority = excluded.priority,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    issue_id,
                    repo,
                    title,
                    body,
                    author,
                    json.dumps(labels or []),
                    int(priority),
                ),
            )
            conn.commit()

    def get_healer_issue(self, issue_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT * FROM healer_issues WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
        return self._decode_healer_issue_row(self._row_to_dict(row))

    def list_healer_issues(self, *, states: list[str] | None = None, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if states:
                placeholders = ",".join("?" for _ in states)
                query = (
                    f"SELECT * FROM healer_issues WHERE state IN ({placeholders}) "
                    "ORDER BY priority ASC, updated_at ASC LIMIT ?"
                )
                rows = conn.execute(query, [*states, int(limit)]).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM healer_issues ORDER BY updated_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            issue = self._decode_healer_issue_row(self._row_to_dict(row))
            if issue is not None:
                out.append(issue)
        return out

    def claim_next_healer_issue(self, *, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                """
                SELECT issue_id
                FROM healer_issues
                WHERE state = 'queued'
                  AND (backoff_until IS NULL OR backoff_until <= CURRENT_TIMESTAMP)
                ORDER BY priority ASC, updated_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            issue_id = str(row["issue_id"])
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET state = 'claimed',
                    lease_owner = ?,
                    lease_expires_at = datetime('now', ?),
                    updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ? AND state = 'queued'
                """,
                (worker_id, f"+{int(max(1, lease_seconds))} seconds", issue_id),
            )
            if cursor.rowcount == 0:
                conn.commit()
                return None

            claimed = conn.execute(
                "SELECT * FROM healer_issues WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            conn.commit()
        return self._decode_healer_issue_row(self._row_to_dict(claimed))

    def renew_healer_issue_lease(self, *, issue_id: str, worker_id: str, lease_seconds: int) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET lease_expires_at = datetime('now', ?), updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ? AND lease_owner = ? AND state IN ('claimed', 'running', 'verify_pending')
                """,
                (f"+{int(max(1, lease_seconds))} seconds", issue_id, worker_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def increment_healer_attempt(self, issue_id: str) -> int:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                UPDATE healer_issues
                SET attempt_count = attempt_count + 1, updated_at = CURRENT_TIMESTAMP
                WHERE issue_id = ?
                """,
                (issue_id,),
            )
            row = conn.execute(
                "SELECT attempt_count FROM healer_issues WHERE issue_id = ?",
                (issue_id,),
            ).fetchone()
            conn.commit()
            if row is None:
                return 0
            return int(row["attempt_count"])

    def set_healer_issue_state(
        self,
        *,
        issue_id: str,
        state: str,
        backoff_until: str | None = None,
        workspace_path: str | None = None,
        branch_name: str | None = None,
        pr_number: int | None = None,
        pr_state: str | None = None,
        last_failure_class: str | None = None,
        last_failure_reason: str | None = None,
        clear_lease: bool = False,
    ) -> bool:
        conn = self._connect()
        with self._lock:
            updates = ["state = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = [state]

            if backoff_until is not None:
                updates.append("backoff_until = ?")
                params.append(backoff_until)
            if workspace_path is not None:
                updates.append("workspace_path = ?")
                params.append(workspace_path)
            if branch_name is not None:
                updates.append("branch_name = ?")
                params.append(branch_name)
            if pr_number is not None:
                updates.append("pr_number = ?")
                params.append(int(pr_number))
            if pr_state is not None:
                updates.append("pr_state = ?")
                params.append(pr_state)
            if last_failure_class is not None:
                updates.append("last_failure_class = ?")
                params.append(last_failure_class)
            if last_failure_reason is not None:
                updates.append("last_failure_reason = ?")
                params.append(last_failure_reason)
            if clear_lease:
                updates.append("lease_owner = NULL")
                updates.append("lease_expires_at = NULL")

            params.append(issue_id)
            cursor = conn.execute(
                f"UPDATE healer_issues SET {', '.join(updates)} WHERE issue_id = ?",
                params,
            )
            conn.commit()
            return cursor.rowcount > 0

    def requeue_expired_healer_issue_leases(self) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_issues
                SET state = 'queued',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE state IN ('claimed', 'running', 'verify_pending')
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= CURRENT_TIMESTAMP
                """
            )
            conn.commit()
            return int(cursor.rowcount)

    def create_healer_attempt(
        self,
        *,
        attempt_id: str,
        issue_id: str,
        attempt_no: int,
        state: str,
        prediction_source: str,
        predicted_lock_set: list[str],
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_attempts(
                    attempt_id, issue_id, attempt_no, state, prediction_source, predicted_lock_set_json
                )
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt_id,
                    issue_id,
                    int(attempt_no),
                    state,
                    prediction_source,
                    json.dumps(predicted_lock_set or []),
                ),
            )
            conn.commit()

    def finish_healer_attempt(
        self,
        *,
        attempt_id: str,
        state: str,
        actual_diff_set: list[str],
        test_summary: dict[str, Any],
        verifier_summary: dict[str, Any],
        failure_class: str = "",
        failure_reason: str = "",
    ) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE healer_attempts
                SET state = ?,
                    actual_diff_set_json = ?,
                    test_summary_json = ?,
                    verifier_summary_json = ?,
                    failure_class = ?,
                    failure_reason = ?,
                    finished_at = CURRENT_TIMESTAMP
                WHERE attempt_id = ?
                """,
                (
                    state,
                    json.dumps(actual_diff_set or []),
                    json.dumps(test_summary or {}),
                    json.dumps(verifier_summary or {}),
                    (failure_class or "")[:120],
                    (failure_reason or "")[:500],
                    attempt_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def list_healer_attempts(self, *, issue_id: str, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM healer_attempts
                WHERE issue_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (issue_id, int(limit)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = self._decode_healer_attempt_row(self._row_to_dict(row))
            if data is not None:
                out.append(data)
        return out

    def list_recent_healer_attempts(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM healer_attempts
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = self._decode_healer_attempt_row(self._row_to_dict(row))
            if data is not None:
                out.append(data)
        return out

    def create_healer_lesson(
        self,
        *,
        lesson_id: str,
        issue_id: str,
        attempt_id: str,
        lesson_kind: str,
        scope_key: str,
        fingerprint: str,
        problem_summary: str,
        lesson_text: str,
        test_hint: str,
        guardrail: dict[str, Any],
        confidence: int,
        outcome: str,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO healer_lessons(
                    lesson_id, issue_id, attempt_id, lesson_kind, scope_key, fingerprint,
                    problem_summary, lesson_text, test_hint, guardrail_json, confidence, outcome
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lesson_id,
                    issue_id,
                    attempt_id,
                    lesson_kind,
                    scope_key or "repo:*",
                    fingerprint,
                    problem_summary,
                    lesson_text,
                    test_hint,
                    json.dumps(guardrail or {}, ensure_ascii=True),
                    int(max(0, min(100, confidence))),
                    outcome,
                ),
            )
            conn.commit()

    def list_healer_lessons(self, *, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM healer_lessons
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = self._decode_healer_lesson_row(self._row_to_dict(row))
            if data is not None:
                out.append(data)
        return out

    def mark_healer_lessons_used(self, lesson_ids: list[str]) -> int:
        unique_ids = [lesson_id for lesson_id in dict.fromkeys(lesson_ids) if str(lesson_id).strip()]
        if not unique_ids:
            return 0
        conn = self._connect()
        with self._lock:
            placeholders = ",".join("?" for _ in unique_ids)
            cursor = conn.execute(
                f"""
                UPDATE healer_lessons
                SET use_count = use_count + 1,
                    last_used_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lesson_id IN ({placeholders})
                """,
                unique_ids,
            )
            conn.commit()
            return int(cursor.rowcount or 0)

    def get_healer_lesson_stats(self) -> dict[str, Any]:
        lessons = self.list_healer_lessons(limit=500)
        recurring: dict[str, int] = {}
        recent_used = 0
        for lesson in lessons:
            guardrail = lesson.get("guardrail") if isinstance(lesson.get("guardrail"), dict) else {}
            failure_class = str(guardrail.get("failure_class") or "").strip()
            if failure_class:
                recurring[failure_class] = recurring.get(failure_class, 0) + 1
            if lesson.get("last_used_at"):
                recent_used += 1
        top_failure_classes = [
            {"failure_class": key, "count": count}
            for key, count in sorted(recurring.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        return {
            "total_lessons": len(lessons),
            "recently_used": recent_used,
            "top_failure_classes": top_failure_classes,
        }

    # --- Autonomous healer lock registry ---

    def cleanup_expired_healer_locks(self) -> int:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                "DELETE FROM healer_locks WHERE lease_expires_at <= CURRENT_TIMESTAMP"
            )
            conn.commit()
            return int(cursor.rowcount)

    def acquire_healer_lock(
        self,
        *,
        lock_key: str,
        granularity: str,
        issue_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        conn = self._connect()
        with self._lock:
            conn.execute(
                "DELETE FROM healer_locks WHERE lease_expires_at <= CURRENT_TIMESTAMP"
            )
            row = conn.execute(
                "SELECT * FROM healer_locks WHERE lock_key = ?",
                (lock_key,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO healer_locks(lock_key, granularity, issue_id, lease_owner, lease_expires_at)
                    VALUES(?, ?, ?, ?, datetime('now', ?))
                    """,
                    (lock_key, granularity, issue_id, lease_owner, f"+{int(max(1, lease_seconds))} seconds"),
                )
                conn.commit()
                return True

            existing_issue = str(row["issue_id"])
            if existing_issue != issue_id:
                conn.commit()
                return False

            conn.execute(
                """
                UPDATE healer_locks
                SET granularity = ?,
                    lease_owner = ?,
                    lease_expires_at = datetime('now', ?)
                WHERE lock_key = ? AND issue_id = ?
                """,
                (
                    granularity,
                    lease_owner,
                    f"+{int(max(1, lease_seconds))} seconds",
                    lock_key,
                    issue_id,
                ),
            )
            conn.commit()
            return True

    def release_healer_locks(self, *, issue_id: str, lock_keys: list[str] | None = None) -> int:
        conn = self._connect()
        with self._lock:
            if lock_keys:
                placeholders = ",".join("?" for _ in lock_keys)
                cursor = conn.execute(
                    f"DELETE FROM healer_locks WHERE issue_id = ? AND lock_key IN ({placeholders})",
                    [issue_id, *lock_keys],
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM healer_locks WHERE issue_id = ?",
                    (issue_id,),
                )
            conn.commit()
            return int(cursor.rowcount)

    def list_healer_locks(self, *, issue_id: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            if issue_id:
                rows = conn.execute(
                    "SELECT * FROM healer_locks WHERE issue_id = ? ORDER BY lock_key ASC",
                    (issue_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM healer_locks ORDER BY lock_key ASC",
                ).fetchall()
        return [self._row_to_dict(row) for row in rows if row is not None]

    # --- Scan pipeline state ---

    def create_scan_run(self, *, run_id: str, dry_run: bool) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO scan_runs(run_id, status, dry_run)
                VALUES(?, 'running', ?)
                """,
                (run_id, 1 if dry_run else 0),
            )
            conn.commit()

    def finish_scan_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> bool:
        conn = self._connect()
        with self._lock:
            cursor = conn.execute(
                """
                UPDATE scan_runs
                SET status = ?, summary_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (status, json.dumps(summary or {}), run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_scan_finding(self, fingerprint: str) -> dict[str, Any] | None:
        conn = self._connect()
        with self._lock:
            row = conn.execute(
                "SELECT * FROM scan_findings WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        data = self._row_to_dict(row)
        if data is None:
            return None
        try:
            data["payload"] = json.loads(data.pop("payload_json", "{}"))
        except json.JSONDecodeError:
            data["payload"] = {}
        return data

    def upsert_scan_finding(
        self,
        *,
        fingerprint: str,
        scan_type: str,
        severity: str,
        title: str,
        status: str,
        payload: dict[str, Any],
        issue_number: int | None = None,
    ) -> None:
        conn = self._connect()
        with self._lock:
            conn.execute(
                """
                INSERT INTO scan_findings(
                    fingerprint, scan_type, severity, title, issue_number, status, payload_json
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    scan_type = excluded.scan_type,
                    severity = excluded.severity,
                    title = excluded.title,
                    issue_number = COALESCE(excluded.issue_number, scan_findings.issue_number),
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    last_seen_at = CURRENT_TIMESTAMP
                """,
                (
                    fingerprint,
                    scan_type,
                    severity,
                    title,
                    issue_number,
                    status,
                    json.dumps(payload or {}),
                ),
            )
            conn.commit()

    def list_scan_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM scan_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = self._row_to_dict(row)
            if data is None:
                continue
            try:
                data["summary"] = json.loads(data.pop("summary_json", "{}"))
            except json.JSONDecodeError:
                data["summary"] = {}
            data["dry_run"] = bool(int(data.get("dry_run", 0) or 0))
            out.append(data)
        return out

    def list_scan_findings(self, *, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        with self._lock:
            rows = conn.execute(
                """
                SELECT * FROM scan_findings
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
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
        # Escape LIKE wildcards to prevent data disclosure via % or _ in user input
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = conn.execute(
                "SELECT * FROM messages WHERE sender = ? AND text LIKE ? ESCAPE '\\' ORDER BY received_at DESC LIMIT ?",
                (sender, f"%{escaped_query}%", limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]
