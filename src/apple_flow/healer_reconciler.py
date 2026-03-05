from __future__ import annotations

import logging
from pathlib import Path

from .healer_workspace import HealerWorkspaceManager
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_reconciler")


class HealerReconciler:
    def __init__(self, *, store: SQLiteStore, workspace_manager: HealerWorkspaceManager) -> None:
        self.store = store
        self.workspace_manager = workspace_manager

    def reconcile(self) -> dict[str, int]:
        recovered_leases = self.store.requeue_expired_healer_issue_leases()
        expired_locks = self.store.cleanup_expired_healer_locks()
        removed_orphans = self._sweep_orphan_workspaces()
        return {
            "recovered_leases": recovered_leases,
            "expired_locks": expired_locks,
            "removed_orphans": removed_orphans,
        }

    def _sweep_orphan_workspaces(self) -> int:
        active_rows = self.store.list_healer_issues(
            states=["queued", "claimed", "running", "verify_pending", "pr_pending_approval", "pr_open", "blocked"],
            limit=2000,
        )
        active_paths = {
            str(Path(row.get("workspace_path") or "").resolve())
            for row in active_rows
            if (row.get("workspace_path") or "").strip()
        }
        removed = 0
        for workspace in self.workspace_manager.list_workspaces():
            if str(workspace.resolve()) in active_paths:
                continue
            try:
                self.workspace_manager.remove_workspace(workspace_path=workspace)
                removed += 1
            except Exception as exc:
                logger.warning("Failed to remove orphan workspace %s: %s", workspace, exc)
        return removed
