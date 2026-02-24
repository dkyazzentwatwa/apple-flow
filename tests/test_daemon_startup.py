from pathlib import Path
from types import SimpleNamespace

from apple_flow.daemon import RelayDaemon, gateway_resource_statuses_for_settings, migrate_legacy_db_if_needed
from apple_flow.gateway_setup import EnsureResult, GatewayResourceStatus


def _settings(**overrides):
    values = {
        "enable_reminders_polling": False,
        "enable_notes_polling": False,
        "enable_notes_logging": False,
        "enable_calendar_polling": False,
        "reminders_list_name": "agent-task",
        "reminders_archive_list_name": "agent-archive",
        "notes_folder_name": "agent-task",
        "notes_archive_folder_name": "agent-archive",
        "notes_log_folder_name": "agent-logs",
        "calendar_name": "agent-schedule",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_gateway_resource_statuses_respect_enabled_gateways(monkeypatch):
    captured = {}

    def fake_ensure_gateway_resources(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("apple_flow.daemon.ensure_gateway_resources", fake_ensure_gateway_resources)

    gateway_resource_statuses_for_settings(
        _settings(enable_reminders_polling=True, enable_notes_logging=True, enable_calendar_polling=True)
    )

    assert captured["enable_reminders"] is True
    assert captured["enable_notes"] is False
    assert captured["enable_notes_logging"] is True
    assert captured["enable_calendar"] is True


def test_relaydaemon_logs_gateway_resource_statuses(caplog, monkeypatch):
    daemon = RelayDaemon.__new__(RelayDaemon)
    daemon.settings = _settings()

    monkeypatch.setattr(
        "apple_flow.daemon.gateway_resource_statuses_for_settings",
        lambda _settings: [
            GatewayResourceStatus("Reminders task list", "agent-task", EnsureResult(status="created")),
            GatewayResourceStatus(
                "Calendar",
                "agent-schedule",
                EnsureResult(status="failed", detail="Calendar permission denied"),
            ),
        ],
    )

    caplog.set_level("INFO")
    daemon._ensure_gateway_resources()

    assert "Gateway resource ensure: Reminders task list 'agent-task': created" in caplog.text
    assert "Gateway resource ensure failed: Calendar 'agent-schedule': failed (Calendar permission denied)" in caplog.text


def test_migrate_legacy_db_when_safe(tmp_path):
    legacy_db = tmp_path / "legacy" / "relay.db"
    target_db = tmp_path / "apple-flow" / "relay.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_text("legacy-db", encoding="utf-8")

    settings = SimpleNamespace(model_fields_set=set(), db_path=target_db)

    migrated = migrate_legacy_db_if_needed(
        settings,
        legacy_db_path=legacy_db,
        default_db_path=target_db,
    )

    assert migrated is True
    assert target_db.read_text(encoding="utf-8") == "legacy-db"
    assert not legacy_db.exists()


def test_migrate_legacy_db_skips_when_db_path_is_explicit(tmp_path):
    legacy_db = tmp_path / "legacy" / "relay.db"
    target_db = tmp_path / "apple-flow" / "relay.db"
    legacy_db.parent.mkdir(parents=True)
    legacy_db.write_text("legacy-db", encoding="utf-8")

    settings = SimpleNamespace(model_fields_set={"db_path"}, db_path=target_db)

    migrated = migrate_legacy_db_if_needed(
        settings,
        legacy_db_path=legacy_db,
        default_db_path=target_db,
    )

    assert migrated is False
    assert legacy_db.exists()
    assert not target_db.exists()
