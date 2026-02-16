from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .models import InboundMessage
from .utils import normalize_sender


class IMessageIngress:
    """Reads inbound message rows from the local Messages SQLite database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        # Use read-only URI mode so we never mutate Messages DB.
        uri = f"file:{self.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        self._conn = conn
        return conn

    def _reset_connection(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _query_all(self, query: str, params: list[Any]) -> list[sqlite3.Row]:
        # Retry once after reconnect for transient DB-open failures.
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                conn = self._connect()
                return conn.execute(query, params).fetchall()
            except sqlite3.OperationalError as exc:
                last_error = exc
                self._reset_connection()
                if "unable to open database file" not in str(exc).lower():
                    raise
                if attempt == 1:
                    raise
        if last_error is not None:
            raise last_error
        return []

    def fetch_new(
        self,
        since_rowid: int | None = None,
        limit: int = 100,
        sender_allowlist: list[str] | None = None,
        require_sender_filter: bool = False,
    ) -> list[InboundMessage]:
        predicate_parts: list[str] = []
        params: list[int] = []
        if since_rowid is not None:
            predicate_parts.append("m.ROWID > ?")
            params.append(since_rowid)

        sender_candidates = self._sender_candidates(sender_allowlist or [])
        if require_sender_filter and not sender_candidates:
            return []
        if sender_candidates:
            placeholders = ",".join(["?"] * len(sender_candidates))
            predicate_parts.append(f"COALESCE(h.id, m.destination_caller_id, 'unknown') IN ({placeholders})")
            params.extend(sender_candidates)

        predicate = ""
        if predicate_parts:
            predicate = f"WHERE {' AND '.join(predicate_parts)}"

        query = f"""
            SELECT
                m.ROWID as rowid,
                COALESCE(h.id, m.destination_caller_id, 'unknown') as sender,
                COALESCE(m.text, '') as text,
                datetime(m.date / 1000000000 + strftime('%s','2001-01-01'), 'unixepoch') as received_at,
                m.is_from_me as is_from_me
            FROM message m
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            {predicate}
            ORDER BY m.ROWID ASC
            LIMIT {int(limit)}
        """

        if not self.db_path.exists():
            return []

        rows = self._query_all(query, params)

        messages = []
        for row in rows:
            messages.append(
                InboundMessage(
                    id=str(row["rowid"]),
                    sender=normalize_sender(row["sender"]),
                    text=row["text"],
                    received_at=row["received_at"],
                    is_from_me=bool(row["is_from_me"]),
                )
            )
        return messages

    def latest_rowid(self) -> int | None:
        if not self.db_path.exists():
            return None
        rows = self._query_all("SELECT MAX(ROWID) AS max_rowid FROM message", [])
        if not rows:
            return None
        row = rows[0]
        if row is None or row[0] is None:
            return None
        return int(row[0])

    @staticmethod
    def _sender_candidates(senders: list[str]) -> list[str]:
        values: set[str] = set()
        for sender in senders:
            normalized = normalize_sender(sender)
            if not normalized:
                continue
            values.add(normalized)
            values.add(f"mailto:{normalized}")
            if normalized.startswith("+"):
                values.add(normalized[1:])
        return sorted(values)
