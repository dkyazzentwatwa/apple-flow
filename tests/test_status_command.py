"""Status command visibility tests for pending + active + targeted lookups."""

from conftest import FakeConnector, FakeEgress, FakeStore

from apple_flow.commanding import CommandKind
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(store: FakeStore) -> RelayOrchestrator:
    return RelayOrchestrator(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=store,
        allowed_workspaces=["/workspace/default"],
        default_workspace="/workspace/default",
        require_chat_prefix=False,
    )


def test_status_overview_includes_pending_approvals_and_active_runs():
    store = FakeStore()
    store.create_run(
        run_id="run_alpha",
        sender="+15551234567",
        intent="task",
        state="executing",
        cwd="/workspace/default",
        risk_level="execute",
    )
    store.create_event(
        event_id="evt_1",
        run_id="run_alpha",
        step="executor",
        event_type="heartbeat",
        payload={"snippet": "still working"},
    )
    store.create_approval(
        request_id="req_alpha",
        run_id="run_alpha",
        summary="needs approval",
        command_preview="PLAN: do work",
        expires_at="2030-01-01T00:00:00Z",
        sender="+15551234567",
    )

    orch = _make_orchestrator(store)
    msg = InboundMessage(
        id="status_1",
        sender="+15551234567",
        text="status",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert result.kind is CommandKind.STATUS
    assert "Pending approvals (1):" in (result.response or "")
    assert "Active runs (1):" in (result.response or "")
    assert "run_alpha" in (result.response or "")
    assert "Use `status <run_id>` or `status <request_id>` for details." in (result.response or "")


def test_status_request_id_lookup_returns_run_timeline():
    store = FakeStore()
    store.create_run(
        run_id="run_beta",
        sender="+15551234567",
        intent="task",
        state="awaiting_approval",
        cwd="/workspace/default",
        risk_level="execute",
    )
    store.create_approval(
        request_id="req_beta",
        run_id="run_beta",
        summary="checkpoint",
        command_preview="checkpoint details",
        expires_at="2030-01-01T00:00:00Z",
        sender="+15551234567",
    )
    store.create_event(
        event_id="evt_2",
        run_id="run_beta",
        step="executor",
        event_type="checkpoint_created",
        payload={"reason": "connector timeout"},
    )

    orch = _make_orchestrator(store)
    msg = InboundMessage(
        id="status_2",
        sender="+15551234567",
        text="status req_beta",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert "Run: run_beta" in (result.response or "")
    assert "Approval: req_beta (pending" in (result.response or "")
    assert "Recent events:" in (result.response or "")
    assert "checkpoint_created" in (result.response or "")


def test_status_run_id_lookup_reports_latest_event_reason():
    store = FakeStore()
    store.create_run(
        run_id="run_gamma",
        sender="+15551234567",
        intent="project",
        state="failed",
        cwd="/workspace/default",
        risk_level="execute",
    )
    store.create_event(
        event_id="evt_3",
        run_id="run_gamma",
        step="executor",
        event_type="execution_failed",
        payload={"reason": "connector timeout"},
    )

    orch = _make_orchestrator(store)
    msg = InboundMessage(
        id="status_3",
        sender="+15551234567",
        text="status run_gamma",
        received_at="2026-02-17T12:00:00Z",
        is_from_me=False,
    )
    result = orch.handle_message(msg)

    assert "Run: run_gamma" in (result.response or "")
    assert "State: failed" in (result.response or "")
    assert "execution_failed connector timeout" in (result.response or "")
