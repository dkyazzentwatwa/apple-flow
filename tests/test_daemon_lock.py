import json
from pathlib import Path

import pytest

import apple_flow.__main__ as entrypoint


@pytest.fixture(autouse=True)
def _cleanup_lock():
    entrypoint._release_daemon_lock()
    yield
    entrypoint._release_daemon_lock()


def test_daemon_lock_path_uses_messages_db_path():
    messages_db = Path("/tmp/custom/chat.db")
    lock_path = entrypoint._daemon_lock_path(messages_db)
    assert lock_path == Path("/tmp/custom/chat.apple-flow.daemon.lock")


def test_acquire_writes_metadata_and_release_clears(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("apple_flow_messages_db_path", str(tmp_path / "chat.db"))
    monkeypatch.setenv("apple_flow_db_path", str(tmp_path / "relay.db"))

    _, lock_path = entrypoint._acquire_daemon_lock()

    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["messages_db_path"] == str(tmp_path / "chat.db")
    assert payload["db_path"] == str(tmp_path / "relay.db")
    assert payload["cwd"] == str(tmp_path)
    assert payload["pid"].isdigit()

    entrypoint._release_daemon_lock()
    assert entrypoint._LOCK_FILE is None


def test_acquire_surfaces_lock_holder_metadata(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("apple_flow_messages_db_path", str(tmp_path / "chat.db"))
    monkeypatch.setenv("apple_flow_db_path", str(tmp_path / "relay.db"))

    lock_path = entrypoint._daemon_lock_path(tmp_path / "chat.db")
    lock_path.write_text(
        json.dumps({"pid": "99999", "cwd": "/tmp/holder", "messages_db_path": str(tmp_path / "chat.db")}),
        encoding="utf-8",
    )

    def _always_block(*_args, **_kwargs):
        raise BlockingIOError("locked")

    monkeypatch.setattr(entrypoint.fcntl, "flock", _always_block)

    with pytest.raises(RuntimeError, match="Lock metadata"):
        entrypoint._acquire_daemon_lock()

    assert entrypoint._LOCK_FILE is None


def test_main_exits_when_lock_contended(monkeypatch, capsys):
    def _raise_locked():
        raise RuntimeError("locked")

    monkeypatch.setattr(entrypoint, "_acquire_daemon_lock", _raise_locked)
    monkeypatch.setattr(entrypoint.sys, "argv", ["apple-flow", "daemon"])

    with pytest.raises(SystemExit) as exc:
        entrypoint.main()

    assert exc.value.code == 1
    assert "locked" in capsys.readouterr().err
