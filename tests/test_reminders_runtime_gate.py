from __future__ import annotations

import json

from apple_flow import reminders_runtime_gate as gate


def test_is_reminders_polling_paused_false_when_gate_missing(tmp_path, monkeypatch):
    gate_path = tmp_path / "gate.json"
    monkeypatch.setattr(gate, "_GATE_FILE_PATH", gate_path)

    assert gate.is_reminders_polling_paused() is False


def test_reminders_live_gate_sets_and_clears_pause_state(tmp_path, monkeypatch):
    gate_path = tmp_path / "gate.json"
    monkeypatch.setattr(gate, "_GATE_FILE_PATH", gate_path)

    with gate.reminders_live_gate(reason="test-gate"):
        assert gate.is_reminders_polling_paused() is True
        payload = json.loads(gate_path.read_text(encoding="utf-8"))
        assert payload["reason"] == "test-gate"
        assert float(payload["expires_at_epoch"]) > float(payload["created_at_epoch"])

    assert gate.is_reminders_polling_paused() is False


def test_reminders_live_gate_is_reentrant_within_same_thread(tmp_path, monkeypatch):
    gate_path = tmp_path / "gate.json"
    monkeypatch.setattr(gate, "_GATE_FILE_PATH", gate_path)

    with gate.reminders_live_gate(reason="outer"):
        assert gate.is_reminders_polling_paused() is True
        with gate.reminders_live_gate(reason="inner"):
            assert gate.is_reminders_polling_paused() is True
        assert gate.is_reminders_polling_paused() is True

    assert gate.is_reminders_polling_paused() is False


def test_is_reminders_polling_paused_false_when_gate_expired(tmp_path, monkeypatch):
    gate_path = tmp_path / "gate.json"
    monkeypatch.setattr(gate, "_GATE_FILE_PATH", gate_path)
    gate_path.write_text(
        json.dumps({"reason": "expired", "created_at_epoch": 10, "expires_at_epoch": 20}),
        encoding="utf-8",
    )

    assert gate.is_reminders_polling_paused(now_epoch=25) is False
