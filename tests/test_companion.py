"""Tests for the companion loop — observations, synthesis, rate limiting, quiet hours, digest."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, time, date, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from conftest import FakeConnector, FakeEgress, FakeStore
from apple_flow.companion import CompanionLoop


def _make_config(**overrides):
    """Create a fake config with companion defaults."""
    defaults = dict(
        companion_poll_interval_seconds=300.0,
        companion_max_proactive_per_hour=4,
        companion_quiet_hours_start="22:00",
        companion_quiet_hours_end="07:00",
        companion_stale_approval_minutes=30,
        companion_calendar_lookahead_minutes=60,
        companion_enable_daily_digest=False,
        companion_digest_time="08:00",
        enable_companion=True,
        companion_weekly_review_day="sunday",
        companion_weekly_review_time="20:00",
        enable_memory=False,
        enable_follow_ups=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_companion(
    connector=None, egress=None, store=None, office_path=None, config=None, **kw
):
    return CompanionLoop(
        connector=connector or FakeConnector(),
        egress=egress or FakeEgress(),
        store=store or FakeStore(),
        owner="+15551234567",
        soul_prompt="You are Flow.",
        office_path=office_path,
        config=config or _make_config(),
        **kw,
    )


# ------------------------------------------------------------------
# Quiet hours
# ------------------------------------------------------------------


class TestQuietHours:
    def test_overnight_inside_late(self):
        """23:00 should be quiet when range is 22:00-07:00."""
        comp = _make_companion()
        fake_now = datetime(2026, 2, 18, 23, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_quiet_hours() is True

    def test_overnight_inside_early(self):
        """05:00 should be quiet when range is 22:00-07:00."""
        comp = _make_companion()
        fake_now = datetime(2026, 2, 18, 5, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_quiet_hours() is True

    def test_overnight_outside(self):
        """12:00 should NOT be quiet when range is 22:00-07:00."""
        comp = _make_companion()
        fake_now = datetime(2026, 2, 18, 12, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_quiet_hours() is False

    def test_same_day_range_inside(self):
        """14:00 should be quiet when range is 13:00-17:00."""
        comp = _make_companion(config=_make_config(
            companion_quiet_hours_start="13:00",
            companion_quiet_hours_end="17:00",
        ))
        fake_now = datetime(2026, 2, 18, 14, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_quiet_hours() is True

    def test_same_day_range_outside(self):
        """10:00 should NOT be quiet when range is 13:00-17:00."""
        comp = _make_companion(config=_make_config(
            companion_quiet_hours_start="13:00",
            companion_quiet_hours_end="17:00",
        ))
        fake_now = datetime(2026, 2, 18, 10, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_quiet_hours() is False

    def test_invalid_format_returns_false(self):
        """Invalid time format should not crash, returns False."""
        comp = _make_companion(config=_make_config(
            companion_quiet_hours_start="not-a-time",
            companion_quiet_hours_end="also-bad",
        ))
        assert comp._is_quiet_hours() is False


# ------------------------------------------------------------------
# Rate limiting
# ------------------------------------------------------------------


class TestRateLimiting:
    def test_not_rate_limited_initially(self):
        comp = _make_companion()
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 18, 12, 0, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_rate_limited() is False

    def test_rate_limited_after_max(self):
        store = FakeStore()
        comp = _make_companion(store=store, config=_make_config(companion_max_proactive_per_hour=2))
        fixed_now = datetime(2026, 2, 18, 12, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            comp._is_rate_limited()  # init hour
            comp._record_proactive_send()
            comp._record_proactive_send()
            assert comp._is_rate_limited() is True

    def test_rate_limit_resets_new_hour(self):
        store = FakeStore()
        comp = _make_companion(store=store, config=_make_config(companion_max_proactive_per_hour=1))
        hour1 = datetime(2026, 2, 18, 12, 0, 0)
        hour2 = datetime(2026, 2, 18, 13, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = hour1
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            comp._is_rate_limited()  # init hour
            comp._record_proactive_send()
            assert comp._is_rate_limited() is True
            mock_dt.now.return_value = hour2
            assert comp._is_rate_limited() is False


# ------------------------------------------------------------------
# Mute/unmute
# ------------------------------------------------------------------


class TestMuteUnmute:
    def test_not_muted_by_default(self):
        comp = _make_companion()
        assert comp._is_muted() is False

    def test_muted_when_set(self):
        store = FakeStore()
        store.set_state("companion_muted", "true")
        comp = _make_companion(store=store)
        assert comp._is_muted() is True

    def test_unmuted_when_false(self):
        store = FakeStore()
        store.set_state("companion_muted", "false")
        comp = _make_companion(store=store)
        assert comp._is_muted() is False

    def test_muted_any_other_value_is_not_muted(self):
        store = FakeStore()
        store.set_state("companion_muted", "yes")
        comp = _make_companion(store=store)
        assert comp._is_muted() is False


# ------------------------------------------------------------------
# Observations
# ------------------------------------------------------------------


class TestObservations:
    def test_gather_stale_approvals(self):
        store = FakeStore()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        store.approvals["req_stale"] = {
            "request_id": "req_stale",
            "run_id": "run_1",
            "sender": "+1",
            "summary": "test",
            "command_preview": "do something important",
            "expires_at": "2099-01-01T00:00:00",
            "status": "pending",
            "created_at": old_time,
        }
        comp = _make_companion(store=store)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert any("Stale approval" in o for o in obs)

    def test_gather_no_stale_when_recent(self):
        store = FakeStore()
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        store.approvals["req_new"] = {
            "request_id": "req_new",
            "run_id": "run_1",
            "sender": "+1",
            "summary": "test",
            "command_preview": "something",
            "expires_at": "2099-01-01T00:00:00",
            "status": "pending",
            "created_at": recent_time,
        }
        comp = _make_companion(store=store)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert not any("Stale approval" in o for o in obs)

    def test_gather_calendar_events(self):
        comp = _make_companion()
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[
            {"start_date": "2026-02-18 09:00", "summary": "Standup"}
        ]), patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert any("Standup" in o for o in obs)

    def test_gather_reminders(self):
        comp = _make_companion()
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[
                 {"name": "Buy milk", "due_date": "2026-02-18"}
             ]):
            obs = comp._gather_observations()
        assert any("Buy milk" in o for o in obs)

    def test_gather_office_inbox(self, tmp_path):
        inbox_dir = tmp_path / "00_inbox"
        inbox_dir.mkdir()
        (inbox_dir / "inbox.md").write_text("- [ ] Item one\n- [ ] Item two\n- [x] Done\n")
        comp = _make_companion(office_path=tmp_path)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert any("2 untriaged" in o for o in obs)

    def test_gather_empty_when_nothing_notable(self):
        comp = _make_companion()
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert isinstance(obs, list)

    def test_gather_completed_tasks(self):
        store = FakeStore()
        store.runs["r1"] = {"state": "completed"}
        store.runs["r2"] = {"state": "completed"}
        comp = _make_companion(store=store)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            obs = comp._gather_observations()
        assert any("2 completed" in o for o in obs)


# ------------------------------------------------------------------
# Cross-channel correlation
# ------------------------------------------------------------------


class TestCrossChannelCorrelation:
    def test_related_items_annotated(self):
        comp = _make_companion()
        observations = [
            "Upcoming event: deploy staging meeting",
            "Reminder: deploy hotfix to production",
            "Something unrelated about cats",
        ]
        result = comp._cross_channel_correlate(observations)
        assert any("related" in o.lower() for o in result)

    def test_no_correlation_single_item(self):
        comp = _make_companion()
        observations = ["Just one item"]
        result = comp._cross_channel_correlate(observations)
        assert result == observations

    def test_no_correlation_no_overlap(self):
        comp = _make_companion()
        observations = ["Calendar: abc xyz", "Reminder: def ghi"]
        result = comp._cross_channel_correlate(observations)
        assert not any("related" in o.lower() for o in result)

    def test_empty_observations(self):
        comp = _make_companion()
        result = comp._cross_channel_correlate([])
        assert result == []

    def test_common_words_excluded(self):
        """Common words like 'with', 'from', 'this' should not trigger correlation."""
        comp = _make_companion()
        observations = [
            "From the office with love",
            "From your desk with care",
        ]
        result = comp._cross_channel_correlate(observations)
        assert not any("related" in o.lower() for o in result)


# ------------------------------------------------------------------
# Synthesis
# ------------------------------------------------------------------


class TestSynthesis:
    def test_empty_response_means_no_message(self):
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "EMPTY"
        comp = _make_companion(connector=connector)
        result = comp._synthesize_message(["minor observation"])
        assert result == ""

    def test_empty_lowercase_means_no_message(self):
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "  empty  "
        comp = _make_companion(connector=connector)
        result = comp._synthesize_message(["minor observation"])
        assert result == ""

    def test_normal_response_returned(self):
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "Heads up — you have a meeting in 30 min."
        comp = _make_companion(connector=connector)
        result = comp._synthesize_message(["Upcoming event: standup in 30 min"])
        assert "meeting" in result.lower() or "30 min" in result

    def test_synthesis_error_returns_empty(self):
        connector = FakeConnector()
        def _fail(tid, prompt):
            raise RuntimeError("fail")
        connector.run_turn = _fail
        comp = _make_companion(connector=connector)
        result = comp._synthesize_message(["some obs"])
        assert result == ""

    def test_synthesis_uses_companion_thread(self):
        connector = FakeConnector()
        comp = _make_companion(connector=connector)
        comp._synthesize_message(["test"])
        assert any("__companion__" in s for s in connector.created)


# ------------------------------------------------------------------
# Check and notify integration
# ------------------------------------------------------------------


class TestCheckAndNotify:
    def test_muted_skips_everything(self):
        store = FakeStore()
        store.set_state("companion_muted", "true")
        egress = FakeEgress()
        comp = _make_companion(store=store, egress=egress)
        comp._check_and_notify()
        assert len(egress.messages) == 0

    def test_quiet_hours_skip(self):
        egress = FakeEgress()
        comp = _make_companion(egress=egress)
        with patch.object(comp, "_is_quiet_hours", return_value=True):
            comp._check_and_notify()
        assert len(egress.messages) == 0

    def test_rate_limited_skip(self):
        egress = FakeEgress()
        comp = _make_companion(egress=egress)
        with patch.object(comp, "_is_rate_limited", return_value=True):
            comp._check_and_notify()
        assert len(egress.messages) == 0

    def test_sends_when_observations_exist(self):
        egress = FakeEgress()
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "You have stuff to do!"
        store = FakeStore()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        store.approvals["req_1"] = {
            "request_id": "req_1",
            "run_id": "run_1",
            "sender": "+1",
            "summary": "test",
            "command_preview": "do something",
            "expires_at": "2099-01-01T00:00:00",
            "status": "pending",
            "created_at": old_time,
        }
        comp = _make_companion(connector=connector, egress=egress, store=store)
        with patch.object(comp, "_is_quiet_hours", return_value=False), \
             patch.object(comp, "_is_rate_limited", return_value=False), \
             patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            comp._check_and_notify()
        assert len(egress.messages) >= 1
        assert egress.messages[0][0] == "+15551234567"

    def test_no_send_when_synthesis_empty(self):
        egress = FakeEgress()
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "EMPTY"
        store = FakeStore()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        store.approvals["req_1"] = {
            "request_id": "req_1",
            "run_id": "run_1",
            "sender": "+1",
            "summary": "test",
            "command_preview": "something",
            "expires_at": "2099-01-01T00:00:00",
            "status": "pending",
            "created_at": old_time,
        }
        comp = _make_companion(connector=connector, egress=egress, store=store)
        with patch.object(comp, "_is_quiet_hours", return_value=False), \
             patch.object(comp, "_is_rate_limited", return_value=False), \
             patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            comp._check_and_notify()
        assert len(egress.messages) == 0

    def test_records_proactive_send(self):
        egress = FakeEgress()
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "Heads up!"
        store = FakeStore()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        store.approvals["req_1"] = {
            "request_id": "req_1",
            "run_id": "run_1",
            "sender": "+1",
            "summary": "test",
            "command_preview": "something",
            "expires_at": "2099-01-01T00:00:00",
            "status": "pending",
            "created_at": old_time,
        }
        comp = _make_companion(connector=connector, egress=egress, store=store)
        with patch.object(comp, "_is_quiet_hours", return_value=False), \
             patch.object(comp, "_is_rate_limited", return_value=False), \
             patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            comp._check_and_notify()
        count = store.get_state("companion_proactive_hour_count")
        assert count is not None and int(count) >= 1

    def test_follow_up_scheduler_fires(self):
        egress = FakeEgress()
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "Follow-up: checking in."
        scheduler = MagicMock()
        scheduler.check_due.return_value = [
            {"action_id": "a1", "action_type": "check_in", "payload": {"summary": "deploy check"}}
        ]
        comp = _make_companion(connector=connector, egress=egress, scheduler=scheduler)
        with patch.object(comp, "_is_quiet_hours", return_value=False), \
             patch.object(comp, "_is_rate_limited", return_value=False), \
             patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            comp._check_and_notify()
        scheduler.mark_fired.assert_called_once_with("a1")
        assert len(egress.messages) >= 1


# ------------------------------------------------------------------
# Daily digest
# ------------------------------------------------------------------


class TestDailyDigest:
    def test_digest_not_sent_twice(self):
        store = FakeStore()
        store.set_state("companion_last_digest_date", date.today().isoformat())
        comp = _make_companion(store=store)
        assert comp._digest_sent_today() is True

    def test_digest_not_sent_yesterday(self):
        store = FakeStore()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        store.set_state("companion_last_digest_date", yesterday)
        comp = _make_companion(store=store)
        assert comp._digest_sent_today() is False

    def test_digest_time_matches(self):
        comp = _make_companion(config=_make_config(companion_digest_time="08:00"))
        fake_now = datetime(2026, 2, 18, 8, 0, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_digest_time() is True

    def test_digest_time_no_match(self):
        comp = _make_companion(config=_make_config(companion_digest_time="08:00"))
        fake_now = datetime(2026, 2, 18, 12, 30, 0)
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_digest_time() is False

    def test_digest_time_invalid_format(self):
        comp = _make_companion(config=_make_config(companion_digest_time="bad"))
        assert comp._is_digest_time() is False

    def test_build_digest_with_calendar(self):
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "Good morning! Here's your briefing."
        comp = _make_companion(connector=connector)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[
            {"start_date": "2026-02-18 09:00", "summary": "Standup"}
        ]), patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            result = comp._build_daily_digest()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_digest_empty_when_nothing(self):
        connector = FakeConnector()
        comp = _make_companion(connector=connector)
        with patch("apple_flow.apple_tools.calendar_list_events", return_value=[]), \
             patch("apple_flow.apple_tools.reminders_list", return_value=[]):
            result = comp._build_daily_digest()
        assert isinstance(result, str)


# ------------------------------------------------------------------
# Weekly review
# ------------------------------------------------------------------


class TestWeeklyReview:
    def test_weekly_review_not_sent_twice(self):
        store = FakeStore()
        store.set_state("companion_last_weekly_review", datetime.now().strftime("%Y-W%W"))
        comp = _make_companion(store=store)
        assert comp._weekly_review_sent_this_week() is True

    def test_weekly_review_sent_last_week(self):
        store = FakeStore()
        last_week = (datetime.now() - timedelta(weeks=1)).strftime("%Y-W%W")
        store.set_state("companion_last_weekly_review", last_week)
        comp = _make_companion(store=store)
        assert comp._weekly_review_sent_this_week() is False

    def test_weekly_review_time_wrong_day(self):
        comp = _make_companion(config=_make_config(
            companion_weekly_review_day="monday",
            companion_weekly_review_time="20:00",
        ))
        fake_now = datetime(2026, 2, 18, 20, 0, 0)  # Wednesday
        with patch("apple_flow.companion.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert comp._is_weekly_review_time() is False

    def test_build_weekly_review_returns_string(self):
        connector = FakeConnector()
        connector.run_turn = lambda tid, prompt: "Great week! Here's your summary."
        store = FakeStore()
        store.runs["r1"] = {"state": "completed"}
        comp = _make_companion(connector=connector, store=store)
        result = comp._build_weekly_review()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_weekly_review_empty_when_nothing(self):
        connector = FakeConnector()
        comp = _make_companion(connector=connector)
        result = comp._build_weekly_review()
        assert isinstance(result, str)


# ------------------------------------------------------------------
# Office logging
# ------------------------------------------------------------------


class TestOfficeLogging:
    def test_log_appends_to_automation_log(self, tmp_path):
        log_dir = tmp_path / "90_logs"
        log_dir.mkdir()
        log_file = log_dir / "automation-log.md"
        log_file.write_text("# Automation Log\n\n## Runs\n")
        comp = _make_companion(office_path=tmp_path)
        comp._log_to_office("observation", ["test obs"], "test message")
        content = log_file.read_text()
        assert "companion" in content
        assert "observation" in content

    def test_log_no_crash_when_no_office(self):
        comp = _make_companion(office_path=None)
        comp._log_to_office("test", [], "msg")  # Should not crash

    def test_log_no_crash_when_log_missing(self, tmp_path):
        comp = _make_companion(office_path=tmp_path)
        comp._log_to_office("test", [], "msg")

    def test_log_multiple_entries(self, tmp_path):
        log_dir = tmp_path / "90_logs"
        log_dir.mkdir()
        log_file = log_dir / "automation-log.md"
        log_file.write_text("# Log\n")
        comp = _make_companion(office_path=tmp_path)
        comp._log_to_office("first", ["a"], "msg1")
        comp._log_to_office("second", ["b", "c"], "msg2")
        content = log_file.read_text()
        assert "first" in content
        assert "second" in content
        assert "2 obs" in content


# ------------------------------------------------------------------
# Daily note writing
# ------------------------------------------------------------------


class TestDailyNote:
    def test_write_daily_note_with_template(self, tmp_path):
        daily_dir = tmp_path / "10_daily"
        daily_dir.mkdir()
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "daily-note.md").write_text("# Daily Note — {{date}}\n")
        comp = _make_companion(office_path=tmp_path)
        comp._write_daily_note("Morning briefing content")
        note_path = daily_dir / f"{date.today().isoformat()}.md"
        assert note_path.exists()
        content = note_path.read_text()
        assert "Morning briefing content" in content
        assert date.today().isoformat() in content

    def test_write_daily_note_without_template(self, tmp_path):
        daily_dir = tmp_path / "10_daily"
        daily_dir.mkdir()
        comp = _make_companion(office_path=tmp_path)
        comp._write_daily_note("Briefing without template")
        note_path = daily_dir / f"{date.today().isoformat()}.md"
        assert note_path.exists()
        content = note_path.read_text()
        assert "Briefing without template" in content
        assert "Daily Note" in content

    def test_write_daily_note_no_office(self):
        comp = _make_companion(office_path=None)
        comp._write_daily_note("content")  # Should not crash

    def test_write_daily_note_no_daily_dir(self, tmp_path):
        comp = _make_companion(office_path=tmp_path)
        comp._write_daily_note("content")  # Should not crash


# ------------------------------------------------------------------
# run_forever async (basic structure test)
# ------------------------------------------------------------------


class TestRunForever:
    async def test_run_forever_shuts_down_immediately(self):
        """run_forever should exit promptly when is_shutdown returns True."""
        comp = _make_companion()
        call_count = 0

        def is_shutdown():
            nonlocal call_count
            call_count += 1
            return True

        await asyncio.wait_for(comp.run_forever(is_shutdown), timeout=5.0)
        assert call_count >= 1
