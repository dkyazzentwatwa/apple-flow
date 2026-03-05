from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .healer_locks import canonicalize_lock_keys, lock_granularity
from .store import SQLiteStore


@dataclass(slots=True, frozen=True)
class LockAcquireResult:
    acquired: bool
    keys: list[str]
    reason: str


class HealerDispatcher:
    def __init__(self, *, store: SQLiteStore, worker_id: str, lease_seconds: int) -> None:
        self.store = store
        self.worker_id = worker_id
        self.lease_seconds = max(30, int(lease_seconds))

    def claim_next_issue(self) -> dict[str, Any] | None:
        return self.store.claim_next_healer_issue(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )

    def acquire_prediction_locks(self, *, issue_id: str, lock_keys: list[str]) -> LockAcquireResult:
        keys = canonicalize_lock_keys(lock_keys)
        acquired: list[str] = []
        for key in keys:
            ok = self.store.acquire_healer_lock(
                lock_key=key,
                granularity=lock_granularity(key),
                issue_id=issue_id,
                lease_owner=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if not ok:
                if acquired:
                    self.store.release_healer_locks(issue_id=issue_id, lock_keys=acquired)
                return LockAcquireResult(acquired=False, keys=acquired, reason=f"lock_conflict:{key}")
            acquired.append(key)
        return LockAcquireResult(acquired=True, keys=acquired, reason="")

    def upgrade_locks(self, *, issue_id: str, lock_keys: list[str]) -> LockAcquireResult:
        existing = {entry.get("lock_key", "") for entry in self.store.list_healer_locks(issue_id=issue_id)}
        to_add = [key for key in canonicalize_lock_keys(lock_keys) if key not in existing]
        if not to_add:
            return LockAcquireResult(acquired=True, keys=[], reason="")
        return self.acquire_prediction_locks(issue_id=issue_id, lock_keys=to_add)

    def release_issue(self, *, issue_id: str) -> None:
        self.store.release_healer_locks(issue_id=issue_id)
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            clear_lease=True,
        )
