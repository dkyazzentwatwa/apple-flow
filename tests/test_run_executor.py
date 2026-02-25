from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from apple_flow.models import RunState
from apple_flow.run_executor import RunExecutor


class _StoreStub:
    def __init__(self) -> None:
        self.completed: list[tuple[str, str]] = []

    def get_run(self, _run_id: str) -> dict[str, str]:
        return {"state": RunState.COMPLETED.value}

    def complete_run_job(self, *, job_id: str, status: str, error_text: str | None = None) -> None:
        self.completed.append((job_id, status))

    def update_run_state(self, _run_id: str, _state: str) -> None:
        pass

    def create_event(self, **_kwargs) -> None:
        pass

    def claim_next_run_job(self, *, worker_id: str, lease_seconds: int):  # noqa: ARG002
        return None

    def requeue_expired_run_jobs(self) -> int:
        return 0

    def renew_run_job_lease(self, *, job_id: str, worker_id: str, lease_seconds: int) -> bool:  # noqa: ARG002
        return True


class _ApprovalStub:
    def execute_queued_run(self, **_kwargs):
        return SimpleNamespace(response="ok")


@pytest.mark.asyncio
async def test_execute_job_keepalive_cancelled_is_suppressed():
    store = _StoreStub()
    executor = RunExecutor(store=store, approval_handler=_ApprovalStub(), worker_count=1)
    job = {
        "job_id": "job_1",
        "run_id": "run_1",
        "sender": "+15550001111",
        "attempt": 1,
        "payload": {"request_id": "req_1"},
    }

    await executor._execute_job(worker_id="worker_0", job=job)
    assert store.completed == [("job_1", "completed")]


@pytest.mark.asyncio
async def test_worker_loop_cancelled_exits_cleanly():
    store = _StoreStub()
    executor = RunExecutor(store=store, approval_handler=_ApprovalStub(), worker_count=1)

    task = asyncio.create_task(executor._worker_loop("worker_0", lambda: False))
    await asyncio.sleep(0)
    task.cancel()
    await task
    assert task.done()
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_run_forever_cancellation_drains_workers():
    store = _StoreStub()
    executor = RunExecutor(store=store, approval_handler=_ApprovalStub(), worker_count=2)

    task = asyncio.create_task(executor.run_forever(lambda: False))
    await asyncio.sleep(0)
    task.cancel()
    await task
    assert task.done()
    assert not task.cancelled()
