from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("apple_flow.healer_workspace")


@dataclass(slots=True, frozen=True)
class WorkspaceInfo:
    issue_id: str
    branch: str
    path: Path


class HealerWorkspaceManager:
    """Manage deterministic per-issue git worktrees under a safe root."""

    def __init__(self, *, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self.worktrees_root = self.repo_path / ".apple-flow-healer" / "worktrees"
        self.worktrees_root.mkdir(parents=True, exist_ok=True)

    def ensure_workspace(self, *, issue_id: str, title: str) -> WorkspaceInfo:
        slug = self._slugify(title)
        path = self.worktrees_root / f"issue-{issue_id}-{slug}"
        branch = f"healer/issue-{issue_id}-{slug}"
        if path.exists():
            return WorkspaceInfo(issue_id=issue_id, branch=branch, path=path)

        cmd = [
            "git",
            "-C",
            str(self.repo_path),
            "worktree",
            "add",
            "-f",
            "-b",
            branch,
            str(path),
            "HEAD",
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            # Branch may already exist from previous attempt; retry by reusing branch.
            retry = [
                "git",
                "-C",
                str(self.repo_path),
                "worktree",
                "add",
                "-f",
                str(path),
                branch,
            ]
            proc_retry = subprocess.run(retry, check=False, capture_output=True, text=True, timeout=60)
            if proc_retry.returncode != 0:
                raise RuntimeError(
                    f"Failed to create worktree for issue {issue_id}: {stderr or proc_retry.stderr or 'unknown error'}"
                )
        return WorkspaceInfo(issue_id=issue_id, branch=branch, path=path)

    def remove_workspace(self, *, workspace_path: Path) -> None:
        ws = Path(workspace_path).resolve()
        if not self._is_under_root(ws):
            raise ValueError(f"Refusing to remove workspace outside healer root: {ws}")
        if not ws.exists():
            return
        proc = subprocess.run(
            ["git", "-C", str(self.repo_path), "worktree", "remove", "-f", str(ws)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            logger.warning("git worktree remove failed for %s: %s", ws, (proc.stderr or "").strip())
            shutil.rmtree(ws, ignore_errors=True)

    def list_workspaces(self) -> list[Path]:
        if not self.worktrees_root.exists():
            return []
        return sorted([p for p in self.worktrees_root.iterdir() if p.is_dir()])

    def is_safe_workspace_path(self, path: Path) -> bool:
        return self._is_under_root(Path(path).resolve())

    def _is_under_root(self, path: Path) -> bool:
        try:
            path.relative_to(self.worktrees_root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _slugify(title: str, max_len: int = 40) -> str:
        if not title.strip():
            return "untitled"
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", title).strip("-").lower()
        if not slug:
            slug = "untitled"
        return slug[:max_len]
