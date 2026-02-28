from apple_flow.config import RelaySettings
from apple_flow.config_schema import _SKIP_KEYS, build_config_schema


def test_schema_covers_all_relay_settings_fields():
    schema = build_config_schema()
    schema_keys = {field["key"] for field in schema["fields"]}
    expected_keys = {f"apple_flow_{name}" for name in RelaySettings.model_fields}
    expected_keys -= _SKIP_KEYS
    assert expected_keys.issubset(schema_keys)


def test_schema_has_sections_and_version():
    schema = build_config_schema()
    assert schema["schema_version"] == "1"
    assert schema["sections"]
    assert schema["fields"]
