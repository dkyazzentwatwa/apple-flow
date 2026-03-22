"""Unit tests for ApprovalHandler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from conftest import FakeConnector, FakeEgress, FakeStore
from apple_flow.approval import ApprovalHandler, OrchestrationResult
from apple_flow.commanding import CommandKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler(
    store: FakeStore | None = None,
    egress: FakeEgress | None = None,
    connector: FakeConnector | None = None,
    *,
    checkpoint_on_timeout: bool = False,
    auto_resume_on_timeout: bool = False,
    max_resume_attempts: int = 3,
    enable_verifier: bool = False,
    enable_progress_streaming: bool = False,
    approval_sender_override: str = "",
) -> ApprovalHandler:
    return ApprovalHandler(
        connector=connector or FakeConnector(),
        egress=egress or FakeEgress(),
        store=store or FakeStore(),
        approval_ttl_minutes=60,
        enable_progress_streaming=enable_progress_streaming,
        progress_update_interval_seconds=5.0,
        execution_heartbeat_seconds=10.0,
        checkpoint_on_timeout=checkpoint_on_timeout,
        auto_resume_on_timeout=auto_resume_on_timeout,
        max_resume_attempts=max_resume_attempts,
        enable_verifier=enable_verifier,
        reminders_egress=None,
        reminders_archive_list_name="Archive",
        notes_egress=None,
        notes_archive_folder_name="Archive",
        calendar_egress=None,
        scheduler=None,
        log_notes_egress=None,
        notes_log_folder_name="Logs",
        approval_sender_override=approval_sender_override,
    )


def _future_expires_at(minutes: int = 60) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _past_expires_at(minutes: int = 5) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _setup_run_and_approval(
    store: FakeStore,
    *,
    run_id: str = "run_1",
    request_id: str = "req_1",
    sender: str = "+15551234567",
    expires_at: str | None = None,
) -> None:
    store.create_run(
        run_id=run_id,
        sender=sender,
        intent="task",
        state="awaiting_approval",
        cwd="/tmp/workspace",
        risk_level="execute",
    )
    store.create_approval(
        request_id=request_id,
        run_id=run_id,
        summary="Run a task",
        command_preview="mkdir demo",
        expires_at=expires_at or _future_expires_at(),
        sender=sender,
    )


# ---------------------------------------------------------------------------
# OrchestrationResult
# ---------------------------------------------------------------------------

def test_orchestration_result_defaults():
    r = OrchestrationResult(kind=CommandKind.TASK)
    assert r.run_id is None
    assert r.approval_request_id is None
    assert r.response is None


def test_orchestration_result_full():
    r = OrchestrationResult(
        kind=CommandKind.APPROVE,
        run_id="run_1",
        approval_request_id="req_1",
        response="done",
    )
    assert r.run_id == "run_1"
    assert r.approval_request_id == "req_1"
    assert r.response == "done"


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

def test_init_stores_all_fields():
    handler = _make_handler(
        checkpoint_on_timeout=True,
        auto_resume_on_timeout=True,
        max_resume_attempts=5,
        enable_verifier=True,
    )
    assert handler.checkpoint_on_timeout is True
    assert handler.auto_resume_on_timeout is True
    assert handler.max_resume_attempts == 5
    assert handler.enable_verifier is True
    assert handler.approval_ttl_minutes == 60


def test_init_max_resume_attempts_minimum():
    handler = _make_handler(max_resume_attempts=0)
    assert handler.max_resume_attempts == 1  # enforced minimum of 1


def test_init_execution_heartbeat_minimum():
    handler = ApprovalHandler(
        connector=FakeConnector(),
        egress=FakeEgress(),
        store=FakeStore(),
        approval_ttl_minutes=60,
        enable_progress_streaming=False,
        progress_update_interval_seconds=5.0,
        execution_heartbeat_seconds=1.0,  # below minimum of 5.0
        checkpoint_on_timeout=False,
        auto_resume_on_timeout=False,
        max_resume_attempts=3,
        enable_verifier=False,
        reminders_egress=None,
        reminders_archive_list_name="",
        notes_egress=None,
        notes_archive_folder_name="",
        calendar_egress=None,
        scheduler=None,
        log_notes_egress=None,
        notes_log_folder_name="",
    )
    assert handler.execution_heartbeat_seconds == 5.0


# ---------------------------------------------------------------------------
# resolve — unknown request_id
# ---------------------------------------------------------------------------

def test_resolve_unknown_request_id():
    store = FakeStore()
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_unknown")

    assert "Unknown request id" in result.response
    assert len(egress.messages) == 1


def test_resolve_empty_payload():
    egress = FakeEgress()
    handler = _make_handler(egress=egress)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "")

    assert "Usage" in result.response
    assert len(egress.messages) == 1


# ---------------------------------------------------------------------------
# resolve — deny
# ---------------------------------------------------------------------------

def test_resolve_deny_updates_state():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.resolve("+15551234567", CommandKind.DENY, "req_1")

    assert store.runs["run_1"]["state"] == "denied"
    assert store.approvals["req_1"]["status"] == "denied"
    assert "Denied" in result.response


def test_resolve_deny_wrong_sender_blocked():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.resolve("+19999999999", CommandKind.DENY, "req_1")

    assert "Only the original requester" in result.response
    assert store.runs["run_1"]["state"] == "awaiting_approval"  # unchanged


# ---------------------------------------------------------------------------
# resolve — approve expired
# ---------------------------------------------------------------------------

def test_resolve_approve_expired_request():
    store = FakeStore()
    _setup_run_and_approval(store, expires_at=_past_expires_at(), sender="+15551234567")
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1")

    assert "expired" in result.response
    assert store.approvals["req_1"]["status"] == "expired"
    assert store.runs["run_1"]["state"] == "failed"


# ---------------------------------------------------------------------------
# resolve — approve success (inline execution)
# ---------------------------------------------------------------------------

def test_resolve_approve_runs_execution():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    connector = FakeConnector()
    handler = _make_handler(store=store, egress=egress, connector=connector)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1")

    # Run should be completed
    assert store.runs["run_1"]["state"] == "completed"
    assert result.run_id == "run_1"
    # At least one message sent (started + result)
    assert len(egress.messages) >= 1


def test_resolve_approve_with_extra_instructions():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1 be careful with files")

    assert result.run_id == "run_1"


# ---------------------------------------------------------------------------
# resolve — approve with queued executor
# ---------------------------------------------------------------------------

def test_resolve_approve_queues_with_run_executor():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()

    run_executor = MagicMock()
    handler = _make_handler(store=store, egress=egress)
    handler.run_executor = run_executor

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1")

    run_executor.enqueue.assert_called_once()
    assert store.runs["run_1"]["state"] == "queued"
    assert "Queued" in result.response


# ---------------------------------------------------------------------------
# resolve — exception during execution marks run failed
# ---------------------------------------------------------------------------

def test_resolve_approve_unhandled_exception_marks_failed():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()

    bad_connector = FakeConnector()
    bad_connector.run_turn = MagicMock(side_effect=RuntimeError("connector crashed"))
    handler = _make_handler(store=store, egress=egress, connector=bad_connector)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1")

    assert store.runs["run_1"]["state"] == "failed"
    assert "internal error" in result.response.lower()


# ---------------------------------------------------------------------------
# execute_queued_run
# ---------------------------------------------------------------------------

def test_execute_queued_run_task():
    store = FakeStore()
    _setup_run_and_approval(store, run_id="run_2", request_id="req_2", sender="+15551234567")
    egress = FakeEgress()
    handler = _make_handler(store=store, egress=egress)

    result = handler.execute_queued_run(
        run_id="run_2",
        sender="+15551234567",
        request_id="req_2",
        attempt=1,
        extra_instructions="",
        plan_summary="mkdir demo",
        approval_sender="+15551234567",
    )

    assert result.run_id == "run_2"
    assert store.runs["run_2"]["state"] in {"completed", "failed"}


def test_execute_queued_run_missing_run():
    store = FakeStore()
    handler = _make_handler(store=store)

    result = handler.execute_queued_run(
        run_id="nonexistent",
        sender="+15551234567",
        request_id="req_x",
        attempt=1,
        extra_instructions="",
        plan_summary="",
        approval_sender="+15551234567",
    )

    assert "not found" in result.response


def test_execute_queued_run_project_kind():
    store = FakeStore()
    store.create_run(
        run_id="run_3",
        sender="+15551234567",
        intent="project",
        state="queued",
        cwd="/tmp",
        risk_level="execute",
    )
    store.create_approval(
        request_id="req_3",
        run_id="run_3",
        summary="project",
        command_preview="build",
        expires_at=_future_expires_at(),
        sender="+15551234567",
    )
    handler = _make_handler(store=store)

    result = handler.execute_queued_run(
        run_id="run_3",
        sender="+15551234567",
        request_id="req_3",
        attempt=1,
        extra_instructions="",
        plan_summary="build stuff",
        approval_sender="+15551234567",
    )

    assert result.kind == CommandKind.PROJECT


# ---------------------------------------------------------------------------
# _classify_execution_outcome
# ---------------------------------------------------------------------------

def test_classify_success():
    h = _make_handler()
    assert h._classify_execution_outcome("Files created successfully.") == ("success", "ok")


def test_classify_timeout():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("Error: Request timed out after 300s.")
    assert outcome == "timeout"


def test_classify_blocker():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("BLOCKER: Need your credentials.")
    assert outcome == "blocked"
    assert reason == "user input required"


def test_classify_requires_your_input():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("This requires your input before proceeding.")
    assert outcome == "blocked"


def test_classify_error():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("Error: Something went wrong.")
    assert outcome == "error"
    assert reason == "connector error"


def test_classify_placeholder_no_response():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("No response generated")
    assert outcome == "placeholder"


def test_classify_placeholder_follow_on():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("Follow-on request executed.")
    assert outcome == "placeholder"


def test_classify_empty_output():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("")
    assert outcome == "error"
    assert reason == "empty output"


def test_classify_empty_whitespace():
    h = _make_handler()
    outcome, reason = h._classify_execution_outcome("   ")
    assert outcome == "error"


# ---------------------------------------------------------------------------
# _should_checkpoint
# ---------------------------------------------------------------------------

def test_should_checkpoint_blocked():
    h = _make_handler(max_resume_attempts=3)
    assert h._should_checkpoint(outcome="blocked", attempt=1) is True


def test_should_checkpoint_placeholder():
    h = _make_handler(max_resume_attempts=3)
    assert h._should_checkpoint(outcome="placeholder", attempt=1) is True


def test_should_checkpoint_timeout_with_checkpoint_on():
    h = _make_handler(checkpoint_on_timeout=True, auto_resume_on_timeout=False, max_resume_attempts=3)
    assert h._should_checkpoint(outcome="timeout", attempt=1) is True


def test_should_checkpoint_timeout_auto_resume():
    h = _make_handler(checkpoint_on_timeout=True, auto_resume_on_timeout=True, max_resume_attempts=3)
    assert h._should_checkpoint(outcome="timeout", attempt=1) is False


def test_should_checkpoint_at_max_attempts():
    h = _make_handler(max_resume_attempts=3)
    assert h._should_checkpoint(outcome="blocked", attempt=3) is False


def test_should_not_checkpoint_success():
    h = _make_handler(max_resume_attempts=3)
    assert h._should_checkpoint(outcome="success", attempt=1) is False


def test_should_not_checkpoint_error():
    h = _make_handler(max_resume_attempts=3)
    assert h._should_checkpoint(outcome="error", attempt=1) is False


# ---------------------------------------------------------------------------
# _is_placeholder_output
# ---------------------------------------------------------------------------

def test_is_placeholder_no_response():
    assert ApprovalHandler._is_placeholder_output("No response generated") is True
    assert ApprovalHandler._is_placeholder_output("No response generated.") is True


def test_is_placeholder_follow_on():
    assert ApprovalHandler._is_placeholder_output("Follow-on request executed") is True
    assert ApprovalHandler._is_placeholder_output("Follow-on request executed.") is True


def test_is_placeholder_case_insensitive():
    assert ApprovalHandler._is_placeholder_output("NO RESPONSE GENERATED") is True


def test_is_not_placeholder_real_output():
    assert ApprovalHandler._is_placeholder_output("Created 3 files.") is False
    assert ApprovalHandler._is_placeholder_output("") is False


# ---------------------------------------------------------------------------
# _egress_context_from_source_context
# ---------------------------------------------------------------------------

def test_egress_context_mail_channel():
    source = {
        "channel": "mail",
        "mail_message_id": "msg_123",
        "mail_subject": "Hello",
        "mail_subject_raw": "Hello",
        "mail_subject_sanitized": "Hello",
    }
    ctx = ApprovalHandler._egress_context_from_source_context(source)
    assert ctx is not None
    assert ctx["channel"] == "mail"
    assert ctx["mail_message_id"] == "msg_123"


def test_egress_context_non_mail_channel():
    source = {"channel": "notes", "note_id": "note_1"}
    ctx = ApprovalHandler._egress_context_from_source_context(source)
    assert ctx is None


def test_egress_context_non_dict():
    ctx = ApprovalHandler._egress_context_from_source_context(None)  # type: ignore[arg-type]
    assert ctx is None


def test_egress_context_empty_dict():
    ctx = ApprovalHandler._egress_context_from_source_context({})
    assert ctx is None


# ---------------------------------------------------------------------------
# _parse_dt
# ---------------------------------------------------------------------------

def test_parse_dt_iso():
    dt = ApprovalHandler._parse_dt("2026-01-01T12:00:00+00:00")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_dt_z_suffix():
    dt = ApprovalHandler._parse_dt("2026-01-01T12:00:00Z")
    assert dt is not None


def test_parse_dt_naive_gets_utc():
    dt = ApprovalHandler._parse_dt("2026-01-01T12:00:00")
    assert dt is not None
    assert dt.tzinfo == UTC


def test_parse_dt_none():
    assert ApprovalHandler._parse_dt(None) is None


def test_parse_dt_empty():
    assert ApprovalHandler._parse_dt("") is None


def test_parse_dt_invalid():
    assert ApprovalHandler._parse_dt("not-a-date") is None


# ---------------------------------------------------------------------------
# _next_attempt
# ---------------------------------------------------------------------------

def test_next_attempt_no_events():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    h = _make_handler(store=store)
    assert h._next_attempt("run_1") == 1


def test_next_attempt_with_events():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    store.create_event("evt_1", "run_1", "executor", "execution_started", {})
    h = _make_handler(store=store)
    assert h._next_attempt("run_1") == 2


# ---------------------------------------------------------------------------
# _safe_send
# ---------------------------------------------------------------------------

def test_safe_send_success():
    egress = FakeEgress()
    h = _make_handler(egress=egress)
    result = h._safe_send("+15551234567", "hello")
    assert result is True
    assert egress.messages == [("+15551234567", "hello")]


def test_safe_send_with_context():
    egress = FakeEgress()
    h = _make_handler(egress=egress)
    h._safe_send("+15551234567", "hello", context={"channel": "mail"})
    assert len(egress.messages) == 1


# ---------------------------------------------------------------------------
# _create_event
# ---------------------------------------------------------------------------

def test_create_event_adds_to_store():
    store = FakeStore()
    store.create_run("run_1", "+1", "task", "executing", "/tmp", "execute")
    h = _make_handler(store=store)
    h._create_event(
        run_id="run_1",
        step="executor",
        event_type="execution_started",
        payload={"attempt": 1},
    )
    assert len(store.events) == 1
    assert store.events[0]["event_type"] == "execution_started"


def test_create_event_enriches_with_sender_and_workspace():
    store = FakeStore()
    store.create_run("run_1", "+15551234567", "task", "executing", "/workspace", "execute")
    h = _make_handler(store=store)
    h._create_event(run_id="run_1", step="executor", event_type="test", payload={})
    event = store.events[0]
    assert event["payload"].get("sender") == "+15551234567"
    assert event["payload"].get("workspace") == "/workspace"


# ---------------------------------------------------------------------------
# _checkpoint_run
# ---------------------------------------------------------------------------

def test_checkpoint_run_creates_approval():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    h = _make_handler(store=store, egress=egress)

    message, new_req_id = h._checkpoint_run(
        sender="+15551234567",
        run_id="run_1",
        attempt=1,
        reason="user input required",
        output="BLOCKER: Need password",
        approval_sender="+15551234567",
        previous_request_id="req_1",
    )

    # Should have created a new approval (old req_1 is still pending + new checkpoint approval)
    assert len(store.list_pending_approvals()) == 2
    assert new_req_id.startswith("req_")
    assert "paused" in message.lower()
    assert new_req_id in message
    # Run state updated to awaiting_approval
    assert store.runs["run_1"]["state"] == "awaiting_approval"


def test_checkpoint_run_sends_message():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()
    h = _make_handler(store=store, egress=egress)

    h._checkpoint_run(
        sender="+15551234567",
        run_id="run_1",
        attempt=1,
        reason="blocked",
        output="BLOCKER: need input",
        approval_sender="+15551234567",
        previous_request_id="req_1",
    )

    assert len(egress.messages) == 1
    assert "+15551234567" == egress.messages[0][0]


# ---------------------------------------------------------------------------
# _notify_source_channel_approval
# ---------------------------------------------------------------------------

def test_notify_source_channel_non_notes_is_noop():
    egress = FakeEgress()
    h = _make_handler(egress=egress)
    # Should not raise and should not write to notes (notes_egress is None)
    h._notify_source_channel_approval(
        source_context={"channel": "imessage"},
        request_id="req_1",
        run_id="run_1",
    )


def test_notify_source_channel_notes_writes_breadcrumb():
    notes_egress = MagicMock()
    notes_egress.append_result = MagicMock()
    h = _make_handler()
    h.notes_egress = notes_egress

    h._notify_source_channel_approval(
        source_context={"channel": "notes", "note_id": "note_123"},
        request_id="req_1",
        run_id="run_1",
    )

    notes_egress.append_result.assert_called_once()


# ---------------------------------------------------------------------------
# _handle_post_execution_cleanup
# ---------------------------------------------------------------------------

def test_post_execution_cleanup_notes_channel():
    notes_egress = MagicMock()
    notes_egress.move_to_archive = MagicMock()
    h = _make_handler()
    h.notes_egress = notes_egress

    source_context = {
        "channel": "notes",
        "note_id": "note_123",
        "folder_name": "Inbox",
    }
    h._handle_post_execution_cleanup(source_context, "Task complete.")
    notes_egress.move_to_archive.assert_called_once()


def test_post_execution_cleanup_calendar_channel():
    cal_egress = MagicMock()
    cal_egress.annotate_event = MagicMock()
    h = _make_handler()
    h.calendar_egress = cal_egress

    source_context = {"channel": "calendar", "event_id": "evt_abc"}
    h._handle_post_execution_cleanup(source_context, "Done")
    cal_egress.annotate_event.assert_called_once()


def test_post_execution_cleanup_exception_does_not_raise():
    notes_egress = MagicMock()
    notes_egress.move_to_archive = MagicMock(side_effect=RuntimeError("Notes unreachable"))
    h = _make_handler()
    h.notes_egress = notes_egress

    source_context = {"channel": "notes", "note_id": "note_x", "folder_name": "Inbox"}
    # Should not raise
    h._handle_post_execution_cleanup(source_context, "done")


def test_post_execution_cleanup_unknown_channel_is_noop():
    h = _make_handler()
    # Should not raise
    h._handle_post_execution_cleanup({"channel": "unknown"}, "done")


# ---------------------------------------------------------------------------
# enable_verifier path
# ---------------------------------------------------------------------------

def test_verifier_enabled_runs_verification():
    store = FakeStore()
    _setup_run_and_approval(store, sender="+15551234567")
    egress = FakeEgress()

    # Connector returns different things for executor and verifier
    connector = FakeConnector()
    handler = _make_handler(store=store, egress=egress, connector=connector, enable_verifier=True)

    result = handler.resolve("+15551234567", CommandKind.APPROVE, "req_1")

    # Verifier ran - check the turns include both executor and verifier prompts
    prompts = [t[1] for t in connector.turns]
    assert any("executor mode" in p for p in prompts)
    assert any("verifier mode" in p for p in prompts)
