from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_setup_autostart_uses_script_safe_setup_mode_when_env_missing():
    content = _read("scripts/setup_autostart.sh")
    assert "setup --script-safe --non-interactive-safe" in content


def test_start_beginner_does_not_run_full_pytest_suite_by_default():
    content = _read("scripts/start_beginner.sh")
    assert "pytest -q" not in content


def test_setup_scripts_include_connector_resolution_failure_guidance():
    content = _read("scripts/setup_autostart.sh")
    assert "Could not resolve connector binary" in content


def test_launchd_path_includes_local_bin_fallback():
    setup_content = _read("scripts/setup_autostart.sh")
    install_content = _read("scripts/install_autostart.sh")
    assert "$HOME/.local/bin" in setup_content
    assert "$HOME/.local/bin" in install_content


def test_autostart_scripts_manage_daemon_and_admin_services():
    setup_content = _read("scripts/setup_autostart.sh")
    install_content = _read("scripts/install_autostart.sh")
    uninstall_content = _read("scripts/uninstall_autostart.sh")
    assert "local.apple-flow-admin" in setup_content
    assert "local.apple-flow-admin" in install_content
    assert "local.apple-flow-admin" in uninstall_content
