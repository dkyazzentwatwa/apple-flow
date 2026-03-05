"""Tests for the system: command (stop / restart via iMessage)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import patch

from apple_flow.commanding import CommandKind, parse_command
from apple_flow.models import InboundMessage
from apple_flow.orchestrator import RelayOrchestrator


def _make_orchestrator(fake_connector, fake_egress, fake_store, shutdown_callback=None):
    return RelayOrchestrator(
        connector=fake_connector,
        egress=fake_egress,
        store=fake_store,
        allowed_workspaces=["/tmp"],
        default_workspace="/tmp",
        require_chat_prefix=False,
        shutdown_callback=shutdown_callback,
        healer_repo_path="/tmp",
    )


def _make_message(text: str, sender: str = "+15550000001") -> InboundMessage:
    return InboundMessage(
        id="msg_001",
        sender=sender,
        text=text,
        received_at=datetime.now(UTC).isoformat(),
        is_from_me=False,
        context={},
    )


# --- Parser tests ---

def test_system_stop_parsed_correctly():
    cmd = parse_command("system: stop")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "stop"


def test_system_restart_parsed_correctly():
    cmd = parse_command("system: restart")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "restart"


def test_system_stop_case_insensitive():
    cmd = parse_command("SYSTEM: STOP")
    assert cmd.kind is CommandKind.SYSTEM
    assert cmd.payload == "STOP"


# --- Orchestrator tests ---

def test_system_stop_calls_shutdown_callback(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    result = orchestrator.handle_message(_make_message("system: stop"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [True]
    assert len(fake_egress.messages) == 1
    assert "shutting down" in fake_egress.messages[0][1].lower()


def test_system_restart_triggers_launchd_kickstart(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = orchestrator.handle_message(_make_message("system: restart"))
        mock_run.assert_called_once_with(
            ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/local.apple-flow"],
            check=False,
            timeout=8,
        )

    assert result.kind is CommandKind.SYSTEM
    assert called == []
    assert len(fake_egress.messages) == 1
    assert "restarting" in fake_egress.messages[0][1].lower()
    marker = fake_store.get_state("system_restart_echo_suppress")
    assert marker is not None
    assert "Apple Flow restarting" in marker


def test_system_restart_falls_back_to_shutdown_when_kickstart_fails(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        result = orchestrator.handle_message(_make_message("system: restart"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [True]
    assert len(fake_egress.messages) == 1
    assert "restarting" in fake_egress.messages[0][1].lower()


def test_system_unknown_subcommand(fake_connector, fake_egress, fake_store):
    called = []
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=lambda: called.append(True),
    )
    result = orchestrator.handle_message(_make_message("system: dance"))

    assert result.kind is CommandKind.SYSTEM
    assert called == [], "Callback must NOT be called for unknown subcommand"
    assert len(fake_egress.messages) == 1
    assert "unknown system command" in fake_egress.messages[0][1].lower()
    assert "kill provider" in fake_egress.messages[0][1].lower()


def test_system_kill_provider_invokes_killswitch(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    with patch.object(
        orchestrator,
        "_kill_provider_processes",
        return_value="Killed 2 active Gemini provider process(es).",
    ) as mock_kill:
        result = orchestrator.handle_message(_make_message("system: kill provider"))

    assert result.kind is CommandKind.SYSTEM
    mock_kill.assert_called_once_with()
    assert len(fake_egress.messages) == 1
    assert "killed 2 active gemini provider process(es)." in fake_egress.messages[0][1].lower()


def test_system_healer_dashboard_basic(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    result = orchestrator.handle_message(_make_message("system: healer"))
    assert result.kind is CommandKind.SYSTEM
    assert "flow healer dashboard" in (result.response or "").lower()
    assert len(fake_egress.messages) == 1
    assert "state counts" in fake_egress.messages[0][1].lower()


def test_system_healer_dashboard_includes_pending_items(fake_connector, fake_egress, fake_store):
    fake_store.upsert_healer_issue(
        issue_id="501",
        repo="owner/repo",
        title="Fix test timeout",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=1,
    )
    fake_store.upsert_healer_issue(
        issue_id="502",
        repo="owner/repo",
        title="Repair parser edge case",
        body="",
        author="alice",
        labels=["healer:ready"],
        priority=2,
    )
    fake_store.set_healer_issue_state(issue_id="502", state="running")
    fake_store.healer_locks.append({"lock_key": "path:src/a.py", "issue_id": "502"})
    fake_store.create_healer_attempt(
        attempt_id="hatt_1",
        issue_id="501",
        attempt_no=1,
        state="running",
        prediction_source="path_level",
        predicted_lock_set=["repo:*"],
    )
    fake_store.finish_healer_attempt(
        attempt_id="hatt_1",
        state="failed",
        actual_diff_set=[],
        test_summary={},
        verifier_summary={},
    )

    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)
    result = orchestrator.handle_message(_make_message("system: healer"))

    assert result.kind is CommandKind.SYSTEM
    text = (result.response or "").lower()
    assert "top pending" in text
    assert "#501" in text or "#502" in text
    assert "active lock leases: 1" in text


def test_system_healer_pause_and_resume(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    paused = orchestrator.handle_message(_make_message("system: healer pause"))
    assert paused.kind is CommandKind.SYSTEM
    assert "paused" in (paused.response or "").lower()
    assert fake_store.get_state("healer_paused") == "true"

    resumed = orchestrator.handle_message(
        InboundMessage(
            id="msg_002",
            sender="+15550000001",
            text="system: healer resume",
            received_at=datetime.now(UTC).isoformat(),
            is_from_me=False,
            context={},
        )
    )
    assert resumed.kind is CommandKind.SYSTEM
    assert "resumed" in (resumed.response or "").lower()
    assert fake_store.get_state("healer_paused") == "false"


def test_system_healer_dashboard_shows_paused(fake_connector, fake_egress, fake_store):
    fake_store.set_state("healer_paused", "true")
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    result = orchestrator.handle_message(_make_message("system: healer"))
    assert result.kind is CommandKind.SYSTEM
    assert "paused: yes" in (result.response or "").lower()


def test_system_healer_dashboard_shows_learning_stats(fake_connector, fake_egress, fake_store):
    fake_store.create_healer_lesson(
        lesson_id="lesson_1",
        issue_id="501",
        attempt_id="hat_1",
        lesson_kind="guardrail",
        scope_key="path:src/apple_flow/store.py",
        fingerprint="fp_1",
        problem_summary="Fix flaky lock",
        lesson_text="Keep changes scoped.",
        test_hint="Run tests/test_store.py",
        guardrail={"failure_class": "lock_conflict"},
        confidence=65,
        outcome="failure",
    )
    fake_store.mark_healer_lessons_used(["lesson_1"])
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    result = orchestrator.handle_message(_make_message("system: healer"))

    assert result.kind is CommandKind.SYSTEM
    text = (result.response or "").lower()
    assert "learned lessons: 1" in text
    assert "top learned failure classes: lock_conflict=1" in text


def test_system_healer_scan_dry_run(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)
    scan_summary = {
        "run_id": "scan_20260305",
        "findings_total": 3,
        "findings_over_threshold": 2,
        "created_issues": [],
        "deduped_count": 1,
        "skipped_budget_count": 0,
        "failed_checks": ["pytest"],
        "severity_threshold": "medium",
    }
    with patch("apple_flow.orchestrator.FlowHealerScanner") as mock_scanner_cls:
        mock_scanner = mock_scanner_cls.return_value
        mock_scanner.run_scan.return_value = scan_summary

        result = orchestrator.handle_message(_make_message("system: healer scan dry-run"))

    assert result.kind is CommandKind.SYSTEM
    assert "flow healer scan" in (result.response or "").lower()
    assert "mode: dry-run" in (result.response or "").lower()
    assert "findings: 3 total" in (result.response or "").lower()
    mock_scanner.run_scan.assert_called_once_with(dry_run=True)


def test_system_healer_scan_live_reports_created_issues(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)
    scan_summary = {
        "run_id": "scan_20260305",
        "findings_total": 2,
        "findings_over_threshold": 2,
        "created_issues": [{"number": 101, "html_url": "https://github.com/o/r/issues/101"}],
        "deduped_count": 0,
        "skipped_budget_count": 0,
        "failed_checks": ["harness_eval_pack", "pytest"],
        "severity_threshold": "medium",
    }
    with patch("apple_flow.orchestrator.FlowHealerScanner") as mock_scanner_cls:
        mock_scanner = mock_scanner_cls.return_value
        mock_scanner.run_scan.return_value = scan_summary

        result = orchestrator.handle_message(_make_message("system: healer scan"))

    assert result.kind is CommandKind.SYSTEM
    text = (result.response or "").lower()
    assert "mode: live" in text
    assert "issues: 1 created" in text
    assert "#101" in text
    assert "failed checks: harness_eval_pack, pytest" in text
    mock_scanner.run_scan.assert_called_once_with(dry_run=False)


def test_mark_inflight_runs_cancelled_marks_only_running_states(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(fake_connector, fake_egress, fake_store)

    fake_store.create_run("run_plan", "+15550000001", "task", "planning", "/tmp", "execute")
    fake_store.create_run("run_queue", "+15550000001", "task", "queued", "/tmp", "execute")
    fake_store.create_run("run_running", "+15550000001", "task", "running", "/tmp", "execute")
    fake_store.create_run("run_exec", "+15550000001", "task", "executing", "/tmp", "execute")
    fake_store.create_run("run_verify", "+15550000001", "task", "verifying", "/tmp", "execute")
    fake_store.create_run("run_wait", "+15550000001", "task", "awaiting_approval", "/tmp", "execute")
    fake_store.create_run("run_done", "+15550000001", "task", "completed", "/tmp", "execute")

    updated = orchestrator._mark_inflight_runs_cancelled("test reason")
    assert updated == 5
    assert fake_store.get_run("run_plan")["state"] == "cancelled"
    assert fake_store.get_run("run_queue")["state"] == "cancelled"
    assert fake_store.get_run("run_running")["state"] == "cancelled"
    assert fake_store.get_run("run_exec")["state"] == "cancelled"
    assert fake_store.get_run("run_verify")["state"] == "cancelled"
    assert fake_store.get_run("run_wait")["state"] == "awaiting_approval"
    assert fake_store.get_run("run_done")["state"] == "completed"


def test_system_no_callback_is_safe(fake_connector, fake_egress, fake_store):
    orchestrator = _make_orchestrator(
        fake_connector, fake_egress, fake_store,
        shutdown_callback=None,
    )
    # Neither stop nor restart should raise when callback is None
    result_stop = orchestrator.handle_message(_make_message("system: stop", sender="+15550000001"))
    assert result_stop.kind is CommandKind.SYSTEM

    # Use a different message id to avoid dedup
    msg2 = InboundMessage(
        id="msg_002",
        sender="+15550000001",
        text="system: restart",
        received_at=datetime.now(UTC).isoformat(),
        is_from_me=False,
        context={},
    )
    result_restart = orchestrator.handle_message(msg2)
    assert result_restart.kind is CommandKind.SYSTEM
