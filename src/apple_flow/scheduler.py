"""Follow-up scheduler with SQLite-backed trigger table.

Schedules actions (follow-ups, retries, nudges) that fire at specific times.
The companion loop checks ``check_due()`` on each cycle.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger("apple_flow.scheduler")


class FollowUpScheduler:
    """Manages time-triggered actions stored in the SQLite store."""

    def __init__(self, store: Any, default_follow_up_hours: float = 2.0, max_nudges: int = 3):
        self.store = store
        self.default_follow_up_hours = default_follow_up_hours
        self.max_nudges = max_nudges
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the scheduled_actions table if it doesn't exist."""
        conn = self.store._connect()
        with self.store._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scheduled_actions (
                    action_id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    trigger_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_scheduled_trigger
                    ON scheduled_actions(status, trigger_at);
                """
            )
            conn.commit()

    def schedule(
        self,
        run_id: str,
        sender: str,
        action_type: str = "follow_up",
        payload: dict[str, Any] | None = None,
        hours_from_now: float | None = None,
    ) -> str:
        """Schedule a follow-up action.

        Args:
            run_id: Associated run ID
            sender: Sender to notify
            action_type: Type of action (follow_up, retry, nudge)
            payload: JSON-serializable payload
            hours_from_now: Hours until trigger (default: configured default)

        Returns:
            The action_id of the scheduled action.
        """
        hours = hours_from_now if hours_from_now is not None else self.default_follow_up_hours
        action_id = f"sched_{uuid4().hex[:10]}"
        trigger_at = (datetime.now() + timedelta(hours=hours)).isoformat()
        payload_data = payload or {}
        payload_data["run_id"] = run_id

        conn = self.store._connect()
        with self.store._lock:
            conn.execute(
                """
                INSERT INTO scheduled_actions(action_id, sender, action_type, trigger_at, payload_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (action_id, sender, action_type, trigger_at, json.dumps(payload_data)),
            )
            conn.commit()

        logger.info(
            "Scheduled %s for run=%s sender=%s trigger_at=%s",
            action_type, run_id, sender, trigger_at,
        )
        return action_id

    def check_due(self) -> list[dict[str, Any]]:
        """Return all pending actions whose trigger time has passed."""
        now = datetime.now().isoformat()
        conn = self.store._connect()
        with self.store._lock:
            rows = conn.execute(
                """
                SELECT action_id, sender, action_type, trigger_at, payload_json, status
                FROM scheduled_actions
                WHERE status = 'pending' AND trigger_at <= ?
                ORDER BY trigger_at ASC
                """,
                (now,),
            ).fetchall()

        results = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
            results.append({
                "action_id": row["action_id"],
                "sender": row["sender"],
                "action_type": row["action_type"],
                "trigger_at": row["trigger_at"],
                "payload": payload,
                "status": row["status"],
            })
        return results

    def mark_fired(self, action_id: str) -> None:
        """Mark a scheduled action as fired."""
        conn = self.store._connect()
        with self.store._lock:
            conn.execute(
                "UPDATE scheduled_actions SET status = 'fired' WHERE action_id = ?",
                (action_id,),
            )
            conn.commit()

    def cancel(self, action_id: str) -> None:
        """Cancel a scheduled action."""
        conn = self.store._connect()
        with self.store._lock:
            conn.execute(
                "UPDATE scheduled_actions SET status = 'cancelled' WHERE action_id = ?",
                (action_id,),
            )
            conn.commit()

    def list_pending(self, sender: str | None = None) -> list[dict[str, Any]]:
        """List all pending scheduled actions, optionally filtered by sender."""
        conn = self.store._connect()
        with self.store._lock:
            if sender:
                rows = conn.execute(
                    """
                    SELECT action_id, sender, action_type, trigger_at, payload_json
                    FROM scheduled_actions
                    WHERE status = 'pending' AND sender = ?
                    ORDER BY trigger_at ASC
                    """,
                    (sender,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT action_id, sender, action_type, trigger_at, payload_json
                    FROM scheduled_actions
                    WHERE status = 'pending'
                    ORDER BY trigger_at ASC
                    """,
                ).fetchall()

        results = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                payload = {}
            results.append({
                "action_id": row["action_id"],
                "sender": row["sender"],
                "action_type": row["action_type"],
                "trigger_at": row["trigger_at"],
                "payload": payload,
            })
        return results
