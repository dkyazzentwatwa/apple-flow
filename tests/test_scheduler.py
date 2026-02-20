"""Tests for the follow-up scheduler (SQLite-backed trigger table)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apple_flow.scheduler import FollowUpScheduler  # noqa: E402
from apple_flow.store import SQLiteStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "test.db")
    s.bootstrap()
    return s


@pytest.fixture
def scheduler(store):
    return FollowUpScheduler(store, default_follow_up_hours=2.0, max_nudges=3)


class TestSchedule:
    def test_creates_action(self, scheduler):
        action_id = scheduler.schedule(
            run_id="run_1",
            sender="+15551234567",
            action_type="follow_up",
            payload={"summary": "Check deploy status"},
        )
        assert action_id.startswith("sched_")

    def test_action_appears_in_pending(self, scheduler):
        scheduler.schedule(run_id="run_1", sender="+15551234567")
        pending = scheduler.list_pending()
        assert len(pending) == 1
        assert pending[0]["sender"] == "+15551234567"
        assert pending[0]["action_type"] == "follow_up"

    def test_payload_stored(self, scheduler):
        scheduler.schedule(
            run_id="run_1",
            sender="+15551234567",
            payload={"summary": "Test payload", "extra": 42},
        )
        pending = scheduler.list_pending()
        assert pending[0]["payload"]["summary"] == "Test payload"
        assert pending[0]["payload"]["run_id"] == "run_1"


class TestCheckDue:
    def test_future_action_not_due(self, scheduler):
        scheduler.schedule(run_id="run_1", sender="+1", hours_from_now=24.0)
        due = scheduler.check_due()
        assert len(due) == 0

    def test_past_action_is_due(self, store):
        sched = FollowUpScheduler(store, default_follow_up_hours=0.0)
        sched.schedule(run_id="run_1", sender="+1", hours_from_now=0.0)
        time.sleep(0.01)
        due = sched.check_due()
        assert len(due) == 1
        assert due[0]["action_type"] == "follow_up"

    def test_multiple_due_actions(self, store):
        sched = FollowUpScheduler(store)
        sched.schedule(run_id="run_1", sender="+1", hours_from_now=0.0)
        sched.schedule(run_id="run_2", sender="+2", hours_from_now=0.0)
        time.sleep(0.01)
        due = sched.check_due()
        assert len(due) == 2


class TestMarkFired:
    def test_mark_fired(self, store):
        sched = FollowUpScheduler(store)
        action_id = sched.schedule(run_id="run_1", sender="+1", hours_from_now=0.0)
        time.sleep(0.01)
        due = sched.check_due()
        assert len(due) == 1
        sched.mark_fired(action_id)
        due_after = sched.check_due()
        assert len(due_after) == 0

    def test_fired_not_in_pending(self, store):
        sched = FollowUpScheduler(store)
        action_id = sched.schedule(run_id="run_1", sender="+1")
        sched.mark_fired(action_id)
        assert len(sched.list_pending()) == 0


class TestCancel:
    def test_cancel(self, store):
        sched = FollowUpScheduler(store)
        action_id = sched.schedule(run_id="run_1", sender="+1")
        sched.cancel(action_id)
        assert len(sched.list_pending()) == 0


class TestListPending:
    def test_filters_by_sender(self, scheduler):
        scheduler.schedule(run_id="run_1", sender="+1")
        scheduler.schedule(run_id="run_2", sender="+2")
        pending_1 = scheduler.list_pending(sender="+1")
        assert len(pending_1) == 1
        assert pending_1[0]["sender"] == "+1"

    def test_all_senders(self, scheduler):
        scheduler.schedule(run_id="run_1", sender="+1")
        scheduler.schedule(run_id="run_2", sender="+2")
        all_pending = scheduler.list_pending()
        assert len(all_pending) == 2
