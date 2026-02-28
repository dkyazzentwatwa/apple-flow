from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .memory import FileMemory

logger = logging.getLogger("apple_flow.memory_v2")


@dataclass(frozen=True)
class MemoryContextEntry:
    topic: str
    content: str
    source: str
    salience: int
    updated_ts: int


class CanonicalMemoryStore:
    """SQLite-backed canonical memory store.

    This store is intentionally conservative:
    - Real-time retrieval uses recency + salience only.
    - Expired rows are cleaned by maintenance jobs.
    - Storage cap enforcement is best-effort and non-blocking.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def bootstrap(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    salience INTEGER NOT NULL DEFAULT 50,
                    created_ts INTEGER NOT NULL,
                    updated_ts INTEGER NOT NULL,
                    expires_ts INTEGER,
                    dedupe_key TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(project_id, dedupe_key)
                );

                CREATE INDEX IF NOT EXISTS idx_memory_project_scope_updated
                ON memory_entries(project_id, scope, updated_ts DESC);

                CREATE INDEX IF NOT EXISTS idx_memory_project_expiry
                ON memory_entries(project_id, expires_ts);
                """
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def upsert(
        self,
        *,
        project_id: str,
        scope: str,
        topic: str,
        content: str,
        source: str,
        salience: int = 50,
        ttl_seconds: int | None = None,
        dedupe_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = int(time.time())
        expires_ts = now + int(ttl_seconds) if ttl_seconds else None
        normalized_topic = (topic or "general").strip() or "general"
        normalized_scope = (scope or "global").strip() or "global"
        normalized_content = (content or "").strip()
        if not normalized_content:
            return

        if dedupe_key is None:
            key_basis = f"{normalized_scope}|{normalized_topic}|{source}|{normalized_content[:256]}"
            dedupe_key = hashlib.sha256(key_basis.encode("utf-8")).hexdigest()

        metadata_json = json.dumps(metadata or {}, ensure_ascii=True, separators=(",", ":"))

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memory_entries (
                    id, project_id, scope, topic, content, source, salience,
                    created_ts, updated_ts, expires_ts, dedupe_key, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, dedupe_key) DO UPDATE SET
                    scope=excluded.scope,
                    topic=excluded.topic,
                    content=excluded.content,
                    source=excluded.source,
                    salience=excluded.salience,
                    updated_ts=excluded.updated_ts,
                    expires_ts=excluded.expires_ts,
                    metadata_json=excluded.metadata_json
                """,
                (
                    str(uuid4()),
                    project_id,
                    normalized_scope,
                    normalized_topic,
                    normalized_content,
                    source,
                    int(max(0, min(100, salience))),
                    now,
                    now,
                    expires_ts,
                    dedupe_key,
                    metadata_json,
                ),
            )
            self._conn.commit()

    def retrieve(
        self,
        *,
        project_id: str,
        scope: str,
        query: str = "",
        limit: int = 24,
    ) -> list[MemoryContextEntry]:
        now = int(time.time())
        normalized_scope = (scope or "global").strip() or "global"

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT topic, content, source, salience, updated_ts
                FROM memory_entries
                WHERE project_id = ?
                  AND (scope = ? OR scope = 'global')
                  AND (expires_ts IS NULL OR expires_ts > ?)
                ORDER BY (salience * 1000000000 + updated_ts) DESC
                LIMIT ?
                """,
                (project_id, normalized_scope, now, int(limit)),
            ).fetchall()

        if not query.strip():
            return [
                MemoryContextEntry(
                    topic=row["topic"],
                    content=row["content"],
                    source=row["source"],
                    salience=int(row["salience"]),
                    updated_ts=int(row["updated_ts"]),
                )
                for row in rows
            ]

        terms = [t for t in query.lower().split() if t]
        filtered: list[MemoryContextEntry] = []
        for row in rows:
            haystack = f"{row['topic']}\n{row['content']}\n{row['source']}".lower()
            if all(term in haystack for term in terms):
                filtered.append(
                    MemoryContextEntry(
                        topic=row["topic"],
                        content=row["content"],
                        source=row["source"],
                        salience=int(row["salience"]),
                        updated_ts=int(row["updated_ts"]),
                    )
                )
        return filtered

    def prune_expired(self, *, project_id: str) -> int:
        now = int(time.time())
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM memory_entries WHERE project_id = ? AND expires_ts IS NOT NULL AND expires_ts <= ?",
                (project_id, now),
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def enforce_storage_cap(self, *, project_id: str, max_storage_mb: int) -> int:
        if max_storage_mb <= 0:
            return 0
        if not self.db_path.exists():
            return 0

        max_bytes = int(max_storage_mb) * 1024 * 1024
        deleted_total = 0

        # Best-effort cleanup loop. Keep this conservative to avoid long locks.
        for _ in range(20):
            current_size = self.db_path.stat().st_size
            if current_size <= max_bytes:
                break
            with self._lock:
                victims = self._conn.execute(
                    """
                    SELECT id
                    FROM memory_entries
                    WHERE project_id = ?
                    ORDER BY salience ASC, updated_ts ASC
                    LIMIT 200
                    """,
                    (project_id,),
                ).fetchall()
                if not victims:
                    break
                ids = [row["id"] for row in victims]
                placeholders = ",".join("?" for _ in ids)
                cur = self._conn.execute(
                    f"DELETE FROM memory_entries WHERE id IN ({placeholders})",
                    ids,
                )
                self._conn.commit()
                deleted = int(cur.rowcount or 0)
                deleted_total += deleted
                if deleted == 0:
                    break

        # VACUUM only when we actually deleted rows and are still above cap.
        try:
            if deleted_total > 0 and self.db_path.exists() and self.db_path.stat().st_size > max_bytes:
                with self._lock:
                    self._conn.execute("VACUUM")
        except sqlite3.DatabaseError:
            logger.debug("Skipping VACUUM after storage-cap enforcement", exc_info=True)

        return deleted_total


class MemoryService:
    """Memory service with safe rollout semantics.

    Active mode:
      - Use canonical DB context for prompt injection.
    Shadow mode:
      - Compute canonical context but keep legacy prompt injection unchanged.
      - Logs divergence metrics for rollout validation.
    """

    def __init__(
        self,
        *,
        office_path: Path,
        db_path: Path,
        max_context_chars: int = 2000,
        enabled: bool = False,
        shadow_mode: bool = False,
        max_storage_mb: int = 256,
        include_legacy_fallback: bool = True,
        default_scope: str = "global",
    ):
        self.office_path = Path(office_path)
        self.project_id = resolve_or_create_project_id(self.office_path)
        self.max_context_chars = max(256, int(max_context_chars))
        self.enabled = bool(enabled)
        self.shadow_mode = bool(shadow_mode)
        self.max_storage_mb = max(16, int(max_storage_mb))
        self.include_legacy_fallback = bool(include_legacy_fallback)
        self.default_scope = (default_scope or "global").strip() or "global"

        self.legacy = FileMemory(self.office_path, max_context_chars=self.max_context_chars)
        self.store = CanonicalMemoryStore(Path(db_path))
        self.store.bootstrap()

    def close(self) -> None:
        self.store.close()

    def backfill_from_legacy(self) -> None:
        durable = self.legacy.read_durable().strip()
        if durable:
            self.store.upsert(
                project_id=self.project_id,
                scope="global",
                topic="durable-memory",
                content=durable,
                source="legacy:MEMORY.md",
                salience=90,
                dedupe_key="legacy:durable-memory",
            )

        for topic in self.legacy.list_topics():
            content = self.legacy.read_topic(topic).strip()
            if not content:
                continue
            self.store.upsert(
                project_id=self.project_id,
                scope="global",
                topic=topic,
                content=content,
                source=f"legacy:60_memory/{topic}.md",
                salience=60,
                dedupe_key=f"legacy:topic:{topic}",
            )

    def write_observation(
        self,
        *,
        scope: str,
        topic: str,
        content: str,
        source: str,
        salience: int = 50,
        ttl_seconds: int | None = None,
        dedupe_key: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.store.upsert(
            project_id=self.project_id,
            scope=scope,
            topic=topic,
            content=content,
            source=source,
            salience=salience,
            ttl_seconds=ttl_seconds,
            dedupe_key=dedupe_key,
            metadata=metadata,
        )

    def get_canonical_context(self, query: str = "", scope: str | None = None) -> str:
        effective_scope = (scope or self.default_scope).strip() or "global"
        entries = self.store.retrieve(
            project_id=self.project_id,
            scope=effective_scope,
            query=query,
            limit=32,
        )
        if not entries:
            return ""

        blocks: list[str] = []
        for entry in entries:
            blocks.append(f"### {entry.topic}\n{entry.content.strip()}")

        context = "\n\n".join(blocks).strip()
        if not context:
            return ""

        if len(context) <= self.max_context_chars:
            return context
        truncated = context[: self.max_context_chars].rstrip()
        return f"{truncated}\n[...truncated]"

    def get_context_for_prompt(self, query: str = "", scope: str | None = None) -> str:
        canonical = self.get_canonical_context(query=query, scope=scope)
        if canonical:
            return canonical
        if self.include_legacy_fallback:
            return self.legacy.get_context_for_prompt(query=query)
        return ""

    def run_maintenance(self) -> dict[str, int]:
        expired_deleted = self.store.prune_expired(project_id=self.project_id)
        cap_deleted = self.store.enforce_storage_cap(
            project_id=self.project_id,
            max_storage_mb=self.max_storage_mb,
        )
        return {
            "expired_deleted": expired_deleted,
            "cap_deleted": cap_deleted,
        }

    def log_shadow_diff(self, *, legacy_context: str, canonical_context: str) -> None:
        # Keep shadow mode signal lightweight to avoid log spam and PII leakage.
        logger.info(
            "memory-shadow: legacy_chars=%d canonical_chars=%d canonical_nonempty=%s",
            len(legacy_context),
            len(canonical_context),
            bool(canonical_context.strip()),
        )


def resolve_or_create_project_id(office_path: Path) -> str:
    marker = Path(office_path) / ".apple-flow-project"

    if marker.exists():
        try:
            existing = marker.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            logger.debug("Failed reading project marker at %s", marker, exc_info=True)

    generated = uuid4().hex
    try:
        marker.write_text(f"{generated}\n", encoding="utf-8")
    except OSError:
        logger.debug("Failed writing project marker at %s", marker, exc_info=True)

    return generated
