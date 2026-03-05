from apple_flow.healer_runner import _build_docker_test_script


def test_build_docker_test_script_bootstraps_pytest_and_package_install():
    script = _build_docker_test_script(["pytest", "-q", "tests/test_demo_math.py"])

    assert "python -m pip install --disable-pip-version-check -q pytest" in script
    assert "python -m pip install --disable-pip-version-check -q -e ." in script
    assert '"pytest" "-q" "tests/test_demo_math.py"' in script


def test_build_docker_test_script_skips_editable_install_when_no_python_project():
    script = _build_docker_test_script(["pytest", "-q"])

    assert "if [ -f pyproject.toml ] || [ -f setup.py ] || [ -f setup.cfg ]" in script
    assert script.endswith('"pytest" "-q"')
