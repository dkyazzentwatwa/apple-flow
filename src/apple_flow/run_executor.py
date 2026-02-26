from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any
from uuid import uuid4

from .models import RunState

logger = logging.getLogger("apple_flow.run_executor")


class RunExecutor:
    """Durable async executor backed by store.run_jobs."""

    def __init__(
        self,
        *,
        store: Any,
        approval_handler: Any,
        worker_count: int = 4,
        lease_seconds: int = 180,
        recovery_scan_seconds: float = 30.0,
    ) -> None:
        self.store = store
        self.approval_handler = approval_handler
        self.worker_count = max(1, int(worker_count))
        self.lease_seconds = max(30, int(lease_seconds))
        self.recovery_scan_seconds = max(5.0, float(recovery_scan_seconds))
        self._worker_ids = [f"worker_{i}" for i in range(self.worker_count)]
        self._last_recovery_scan = 0.0

    def enqueue(
        self,
        *,
        run_id: str,
        sender: str,
        request_id: str,
        attempt: int,
        extra_instructions: str,
        approval_sender: str,
        plan_summary: str,
        phase: str = "executor",
    ) -> str:
        job_id = f"job_{uuid4().hex[:12]}"
        self.store.enqueue_run_job(
            job_id=job_id,
            run_id=run_id,
            sender=sender,
            phase=phase,
            attempt=int(attempt),
            payload={
                "request_id": request_id,
                "extra_instructions": extra_instructions,
                "approval_sender": approval_sender,
                "plan_summary": plan_summary,
            },
        )
        self.store.update_run_state(run_id, RunState.QUEUED.value)
        self.store.create_event(
            event_id=f"evt_{uuid4().hex[:12]}",
            run_id=run_id,
            step="executor_queue",
            event_type="execution_queued",
            payload={"job_id": job_id, "attempt": int(attempt), "phase": phase},
        )
        return job_id

    async def run_forever(self, is_shutdown: Any) -> None:
        tasks = [
            asyncio.create_task(self._worker_loop(worker_id, is_shutdown))
            for worker_id in self._worker_ids
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return

    async def _worker_loop(self, worker_id: str, is_shutdown: Any) -> None:
        try:
            while not is_shutdown():
                await self._maybe_recover_expired_jobs()
                job = self.store.claim_next_run_job(
                    worker_id=worker_id, lease_seconds=self.lease_seconds
                )
                if not job:
                    await asyncio.sleep(0.25)
                    continue
                await self._execute_job(worker_id=worker_id, job=job)
        except asyncio.CancelledError:
            return

    async def _maybe_recover_expired_jobs(self) -> None:
        now = time.monotonic()
        if (now - self._last_recovery_scan) < self.recovery_scan_seconds:
            return
        self._last_recovery_scan = now
        try:
            count = self.store.requeue_expired_run_jobs()
            if count:
                logger.warning("Recovered %d expired run job leases", count)
        except Exception as exc:
            logger.debug("Failed run job recovery scan: %s", exc)

    async def _execute_job(self, *, worker_id: str, job: dict[str, Any]) -> None:
        run_id = str(job.get("run_id", ""))
        job_id = str(job.get("job_id", ""))
        attempt = int(job.get("attempt", 1))
        sender = str(job.get("sender", ""))
        payload = job.get("payload") or {}

        # Keep the lease alive while execution is happening in a thread.
        keepalive = asyncio.create_task(self._lease_keepalive(job_id=job_id, worker_id=worker_id))
        try:
            result = await asyncio.to_thread(
                self.approval_handler.execute_queued_run,
                run_id=run_id,
                sender=sender,
                request_id=str(payload.get("request_id", job_id)),
                attempt=attempt,
                extra_instructions=str(payload.get("extra_instructions", "")),
                plan_summary=str(payload.get("plan_summary", "")),
                approval_sender=str(payload.get("approval_sender", sender)),
            )
            run = self.store.get_run(run_id) or {}
            run_state = run.get("state")
            if run_state == RunState.QUEUED.value:
                # A queued state after execution means we checkpointed/requeued.
                self.store.complete_run_job(job_id=job_id, status="completed")
            elif run_state in {
                RunState.COMPLETED.value,
                RunState.CHECKPOINTED.value,
                RunState.AWAITING_APPROVAL.value,
            }:
                self.store.complete_run_job(job_id=job_id, status="completed")
            elif run_state in {
                RunState.FAILED.value,
                RunState.DENIED.value,
                RunState.CANCELLED.value,
            }:
                self.store.complete_run_job(job_id=job_id, status="failed")
            else:
                self.store.complete_run_job(job_id=job_id, status="completed")
            logger.info(
                "Run job finished job_id=%s run_id=%s state=%s response_chars=%s",
                job_id,
                run_id,
                run_state,
                len(result.response or ""),
            )
        except Exception as exc:
            self.store.complete_run_job(
                job_id=job_id, status="failed", error_text=f"{type(exc).__name__}: {exc}"
            )
            self.store.update_run_state(run_id, RunState.FAILED.value)
            self.store.create_event(
                event_id=f"evt_{uuid4().hex[:12]}",
                run_id=run_id,
                step="executor_queue",
                event_type="execution_failed",
                payload={"job_id": job_id, "reason": f"{type(exc).__name__}: {exc}"},
            )
            logger.exception("Run job failed job_id=%s run_id=%s: %s", job_id, run_id, exc)
        finally:
            keepalive.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive

    async def _lease_keepalive(self, *, job_id: str, worker_id: str) -> None:
        interval = max(5.0, float(self.lease_seconds) / 3.0)
        while True:
            await asyncio.sleep(interval)
            ok = self.store.renew_run_job_lease(
                job_id=job_id, worker_id=worker_id, lease_seconds=self.lease_seconds
            )
            if not ok:
                return
