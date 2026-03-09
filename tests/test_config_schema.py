from apple_flow.config import RelaySettings
from apple_flow.config_schema import _SKIP_KEYS, build_config_schema


def test_schema_covers_all_relay_settings_fields():
    schema = build_config_schema()
    schema_keys = {field["key"] for field in schema["fields"]}
    expected_keys = {f"apple_flow_{name}" for name in RelaySettings.model_fields}
    expected_keys -= _SKIP_KEYS
    assert schema_keys == expected_keys


def test_schema_classifies_recent_config_families_into_expected_sections():
    schema = build_config_schema()
    by_key = {field["key"]: field for field in schema["fields"]}

    expected_sections = {
        "apple_flow_enable_memory_v2": "memory",
        "apple_flow_memory_v2_shadow_mode": "memory",
        "apple_flow_enable_companion": "companion",
        "apple_flow_companion_weekly_review_day": "companion",
        "apple_flow_enable_ambient_scanning": "scheduler",
        "apple_flow_enable_csv_audit_log": "scheduler",
        "apple_flow_enable_markdown_automation_log": "scheduler",
        "apple_flow_phone_tts_engine": "phone",
    }

    for key, section_id in expected_sections.items():
        assert by_key[key]["section_id"] == section_id


def test_schema_exposes_validation_hints_for_dashboard_editor():
    schema = build_config_schema()
    by_key = {field["key"]: field for field in schema["fields"]}

    assert by_key["apple_flow_companion_weekly_review_day"]["validation_hint"] == (
        "Allowed values: monday, tuesday, wednesday, thursday, friday, saturday, sunday"
    )
    assert by_key["apple_flow_allowed_senders"]["validation_hint"] == "Comma-separated values."
    assert by_key["apple_flow_poll_interval_seconds"]["validation_hint"] == "Numeric value; decimals allowed."
    assert by_key["apple_flow_admin_port"]["validation_hint"] == "Whole number."
    assert by_key["apple_flow_messages_db_path"]["validation_hint"] == "Absolute path required."


def test_schema_has_sections_and_version():
    schema = build_config_schema()
    assert schema["schema_version"] == "1"
    assert schema["sections"]
    assert schema["fields"]
