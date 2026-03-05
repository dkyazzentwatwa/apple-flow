from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_preflight_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "flow-healer-ops"
        / "scripts"
        / "healer_preflight.py"
    )
    spec = importlib.util.spec_from_file_location("healer_preflight", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_github_token_prefers_environment(monkeypatch, tmp_path):
    module = _load_preflight_module()
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    (tmp_path / ".env").write_text("GITHUB_TOKEN=file-token\n", encoding="utf-8")

    assert module._resolve_github_token(tmp_path) == "env-token"


def test_resolve_github_token_falls_back_to_repo_env(monkeypatch, tmp_path):
    module = _load_preflight_module()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GITHUB_TOKEN=file-token\n", encoding="utf-8")

    assert module._resolve_github_token(tmp_path) == "file-token"
