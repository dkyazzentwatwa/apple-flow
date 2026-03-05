from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .config import RelaySettings
from .healer_dispatcher import HealerDispatcher
from .healer_locks import diff_paths_to_lock_keys, predict_lock_set
from .healer_memory import HealerMemoryService
from .healer_reconciler import HealerReconciler
from .healer_runner import HealerRunner
from .healer_tracker import GitHubHealerTracker, HealerIssue
from .healer_verifier import HealerVerifier
from .protocols import ConnectorProtocol
from .store import SQLiteStore

logger = logging.getLogger("apple_flow.healer_loop")

_TARGETED_TEST_RE = re.compile(r"\btests/[A-Za-z0-9_./\-]*test[A-Za-z0-9_./\-]*\.py\b")


class AutonomousHealerLoop:
    def __init__(
        self,
        *,
        settings: RelaySettings,
        store: SQLiteStore,
        connector: ConnectorProtocol,
    ) -> None:
        self.settings = settings
        self.store = store
        self.connector = connector
        self.repo_path = Path(settings.healer_repo_path).expanduser().resolve()
        self.worker_id = f"healer_{uuid4().hex[:8]}"

        from .healer_workspace import HealerWorkspaceManager

        self.workspace_manager = HealerWorkspaceManager(repo_path=self.repo_path)
        self.tracker = GitHubHealerTracker(repo_path=self.repo_path)
        self.dispatcher = HealerDispatcher(
            store=store,
            worker_id=self.worker_id,
            lease_seconds=max(60, int(settings.healer_poll_interval_seconds * 3)),
        )
        self.runner = HealerRunner(
            connector=connector,
            timeout_seconds=settings.healer_max_wall_clock_seconds_per_issue,
        )
        self.verifier = HealerVerifier(connector=connector)
        self.reconciler = HealerReconciler(
            store=store,
            workspace_manager=self.workspace_manager,
        )
        self.memory = HealerMemoryService(
            store=store,
            enabled=settings.healer_learning_enabled,
        )

    @property
    def enabled(self) -> bool:
        if not self.settings.enable_autonomous_healer:
            return False
        if not self.repo_path.exists():
            logger.warning("Autonomous healer repo path does not exist: %s", self.repo_path)
            return False
        if not self.tracker.repo_slug:
            logger.warning("Autonomous healer disabled: missing GitHub origin slug.")
            return False
        if not self.tracker.background_auth_available:
            logger.warning(
                "Autonomous healer disabled: missing background GitHub token (auth_source=%s).",
                self.tracker.auth_source,
            )
            return False
        return True

    async def run_forever(self, is_shutdown: Callable[[], bool]) -> None:
        if not self.enabled:
            return
        logger.info(
            "Autonomous healer loop enabled (repo=%s, mode=%s, poll=%.0fs, auth_source=%s)",
            self.repo_path,
            self.settings.healer_mode,
            self.settings.healer_poll_interval_seconds,
            self.tracker.auth_source,
        )
        while not is_shutdown():
            try:
                await asyncio.to_thread(self._tick_once)
            except Exception as exc:
                logger.exception("Autonomous healer tick failed: %s", exc)
            await asyncio.sleep(max(5.0, self.settings.healer_poll_interval_seconds))

    def _tick_once(self) -> None:
        if self.store.get_state("healer_paused") == "true":
            logger.info("Autonomous healer paused via system command; skipping cycle.")
            return
        self.reconciler.reconcile()
        self._ingest_ready_issues()
        if self._circuit_breaker_open():
            logger.warning("Healer circuit breaker open; skipping this cycle.")
            return
        processed = 0
        while processed < max(1, self.settings.healer_max_concurrent_issues):
            issue = self.dispatcher.claim_next_issue()
            if not issue:
                break
            self._process_claimed_issue(issue)
            processed += 1

    def _ingest_ready_issues(self) -> None:
        issues = self.tracker.list_ready_issues(
            required_labels=self.settings.healer_issue_required_labels,
            trusted_actors=self.settings.healer_trusted_actors,
            limit=max(10, self.settings.healer_max_concurrent_issues * 5),
        )
        for issue in issues:
            self.store.upsert_healer_issue(
                issue_id=issue.issue_id,
                repo=issue.repo,
                title=issue.title,
                body=issue.body,
                author=issue.author,
                labels=issue.labels,
                priority=issue.priority,
            )

    def _process_claimed_issue(self, row: dict[str, object]) -> None:
        issue = HealerIssue(
            issue_id=str(row.get("issue_id") or ""),
            repo=str(row.get("repo") or ""),
            title=str(row.get("title") or ""),
            body=str(row.get("body") or ""),
            author=str(row.get("author") or ""),
            labels=list(row.get("labels") or []),  # type: ignore[arg-type]
            priority=int(row.get("priority") or 100),
            html_url="",
        )
        self.store.set_healer_issue_state(issue_id=issue.issue_id, state="running")
        attempt_no = self.store.increment_healer_attempt(issue.issue_id)
        prediction = predict_lock_set(issue_text=f"{issue.title}\n{issue.body}")
        lock_result = self.dispatcher.acquire_prediction_locks(issue_id=issue.issue_id, lock_keys=prediction.keys)
        if not lock_result.acquired:
            self._backoff_or_fail(
                issue_id=issue.issue_id,
                attempt_no=attempt_no,
                failure_class="lock_conflict",
                failure_reason=lock_result.reason,
            )
            return

        attempt_id = f"hat_{uuid4().hex[:10]}"
        self.store.create_healer_attempt(
            attempt_id=attempt_id,
            issue_id=issue.issue_id,
            attempt_no=attempt_no,
            state="running",
            prediction_source=prediction.source,
            predicted_lock_set=prediction.keys,
        )
        actual_diff: list[str] = []
        test_summary: dict[str, object] = {}
        verifier_summary: dict[str, object] = {}
        failure_class = ""
        failure_reason = ""
        final_state = "failed"
        try:
            workspace = self.workspace_manager.ensure_workspace(
                issue_id=issue.issue_id,
                title=issue.title,
            )
            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="running",
                workspace_path=str(workspace.path),
                branch_name=workspace.branch,
            )
            targeted_tests = sorted(set(_TARGETED_TEST_RE.findall(issue.body or "")))
            learned_context = self.memory.build_prompt_context(
                issue_text=f"{issue.title}\n{issue.body}",
                predicted_lock_set=prediction.keys,
                last_failure_class=str(row.get("last_failure_class") or ""),
            )
            run_result = self.runner.run_attempt(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                learned_context=learned_context,
                workspace=workspace.path,
                max_diff_files=self.settings.healer_max_diff_files,
                max_diff_lines=self.settings.healer_max_diff_lines,
                max_failed_tests_allowed=self.settings.healer_max_failed_tests_allowed,
                targeted_tests=targeted_tests,
            )
            actual_diff = run_result.diff_paths
            test_summary = run_result.test_summary
            if not run_result.success:
                failure_class = run_result.failure_class
                failure_reason = run_result.failure_reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class=run_result.failure_class,
                    failure_reason=run_result.failure_reason,
                )
                final_state = "failed"
                return

            upgrade = self.dispatcher.upgrade_locks(
                issue_id=issue.issue_id,
                lock_keys=diff_paths_to_lock_keys(run_result.diff_paths),
            )
            if not upgrade.acquired:
                failure_class = "lock_upgrade_conflict"
                failure_reason = upgrade.reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="lock_upgrade_conflict",
                    failure_reason=upgrade.reason,
                )
                final_state = "failed"
                return

            verification = self.verifier.verify(
                issue_id=issue.issue_id,
                issue_title=issue.title,
                issue_body=issue.body,
                diff_paths=run_result.diff_paths,
                test_summary=run_result.test_summary,
                proposer_output=run_result.proposer_output,
                learned_context=learned_context,
            )
            verifier_summary = {"passed": verification.passed, "summary": verification.summary}
            if not verification.passed:
                failure_class = "verifier_failed"
                failure_reason = verification.summary
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="verifier_failed",
                    failure_reason=verification.summary,
                )
                final_state = "failed"
                return

            if (
                self.settings.healer_pr_actions_require_approval
                and not self.tracker.issue_has_label(
                    issue_id=issue.issue_id,
                    label=self.settings.healer_pr_required_label,
                )
            ):
                self.store.set_healer_issue_state(
                    issue_id=issue.issue_id,
                    state="pr_pending_approval",
                    clear_lease=True,
                )
                final_state = "pr_pending_approval"
                return

            commit_ok, commit_reason = self._commit_and_push(workspace.path, issue_id=issue.issue_id, branch=workspace.branch)
            if not commit_ok:
                failure_class = "push_failed"
                failure_reason = commit_reason
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="push_failed",
                    failure_reason=commit_reason,
                )
                final_state = "failed"
                return

            pr = self.tracker.open_or_update_pr(
                issue_id=issue.issue_id,
                branch=workspace.branch,
                title=f"healer: fix issue #{issue.issue_id} - {issue.title[:80]}",
                body=(
                    f"Automated healer proposal for issue #{issue.issue_id}.\n\n"
                    f"- Verifier: passed\n"
                    f"- Targeted/full test gates: {run_result.test_summary}\n"
                ),
            )
            if pr is None:
                failure_class = "pr_open_failed"
                failure_reason = "Failed to create/update pull request."
                self._backoff_or_fail(
                    issue_id=issue.issue_id,
                    attempt_no=attempt_no,
                    failure_class="pr_open_failed",
                    failure_reason="Failed to create/update pull request.",
                )
                final_state = "failed"
                return

            self.store.set_healer_issue_state(
                issue_id=issue.issue_id,
                state="pr_open",
                pr_number=pr.number,
                pr_state=pr.state,
                clear_lease=True,
            )
            final_state = "pr_open"
        finally:
            self.store.finish_healer_attempt(
                attempt_id=attempt_id,
                state=final_state,
                actual_diff_set=actual_diff,
                test_summary=test_summary,
                verifier_summary=verifier_summary,
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            self.memory.maybe_record_lesson(
                issue=issue,
                attempt_id=attempt_id,
                final_state=final_state,
                predicted_lock_set=prediction.keys,
                actual_diff_set=actual_diff,
                test_summary=test_summary,
                verifier_summary=verifier_summary,
                failure_class=failure_class,
                failure_reason=failure_reason,
            )
            self.store.release_healer_locks(issue_id=issue.issue_id)

    def _backoff_or_fail(
        self,
        *,
        issue_id: str,
        attempt_no: int,
        failure_class: str,
        failure_reason: str,
    ) -> None:
        if attempt_no >= self.settings.healer_retry_budget:
            self.store.set_healer_issue_state(
                issue_id=issue_id,
                state="failed",
                last_failure_class=failure_class,
                last_failure_reason=failure_reason[:500],
                clear_lease=True,
            )
            return

        delay = min(
            self.settings.healer_backoff_max_seconds,
            self.settings.healer_backoff_initial_seconds * (2 ** max(0, attempt_no - 1)),
        )
        backoff_until = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        self.store.set_healer_issue_state(
            issue_id=issue_id,
            state="queued",
            backoff_until=backoff_until,
            last_failure_class=failure_class,
            last_failure_reason=failure_reason[:500],
            clear_lease=True,
        )

    def _circuit_breaker_open(self) -> bool:
        window = max(5, self.settings.healer_circuit_breaker_window)
        attempts = self.store.list_recent_healer_attempts(limit=window)
        if len(attempts) < window:
            return False
        failures = 0
        for attempt in attempts:
            state = str(attempt.get("state") or "").lower()
            if state not in {"pr_open", "resolved", "pr_pending_approval"}:
                failures += 1
        failure_rate = failures / float(max(1, len(attempts)))
        return failure_rate >= self.settings.healer_circuit_breaker_failure_rate

    @staticmethod
    def _commit_and_push(workspace: Path, *, issue_id: str, branch: str) -> tuple[bool, str]:
        add = subprocess.run(
            ["git", "-C", str(workspace), "add", "-A"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if add.returncode != 0:
            return False, (add.stderr or add.stdout or "git add failed").strip()

        diff = subprocess.run(
            ["git", "-C", str(workspace), "diff", "--cached", "--quiet"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if diff.returncode == 0:
            return False, "No staged changes to commit."

        commit = subprocess.run(
            ["git", "-C", str(workspace), "commit", "-m", f"healer: fix issue #{issue_id}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
        if commit.returncode != 0:
            return False, (commit.stderr or commit.stdout or "git commit failed").strip()

        push = subprocess.run(
            ["git", "-C", str(workspace), "push", "-u", "origin", branch],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if push.returncode != 0:
            return False, (push.stderr or push.stdout or "git push failed").strip()
        return True, ""
