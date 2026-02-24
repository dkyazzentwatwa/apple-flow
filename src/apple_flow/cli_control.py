from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import RelaySettings
from .gateway_setup import ensure_gateway_resources, resolve_binary
from .setup_wizard import (
    check_messages_db_access,
    generate_env,
    validate_email,
    validate_phone,
    validate_workspace_path,
)


SERVICE_LABEL = "local.apple-flow"
ADMIN_SERVICE_LABEL = "local.apple-flow-admin"
SERVICE_LABELS = (SERVICE_LABEL, ADMIN_SERVICE_LABEL)


def _response_ok(**payload: Any) -> dict[str, Any]:
    payload.setdefault("ok", True)
    return payload


def _response_error(code: str, errors: list[str] | None = None, **payload: Any) -> dict[str, Any]:
    payload.update({"ok": False, "code": code, "errors": errors or []})
    return payload


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _parse_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _write_env(path: Path, updates: dict[str, str]) -> list[str]:
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []

    updated_keys: list[str] = []
    index_by_key: dict[str, int] = {}
    key_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    for idx, line in enumerate(lines):
        match = key_pattern.match(line)
        if match:
            index_by_key[match.group(1)] = idx

    for key, value in updates.items():
        rendered = f"{key}={value}"
        if key in index_by_key:
            lines[index_by_key[key]] = rendered
        else:
            lines.append(rendered)
        updated_keys.append(key)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return updated_keys


def _connector_command_key(connector: str) -> str:
    if connector == "claude-cli":
        return "apple_flow_claude_cli_command"
    if connector == "codex-cli":
        return "apple_flow_codex_cli_command"
    if connector == "cline":
        return "apple_flow_cline_command"
    if connector == "codex-app-server":
        return "apple_flow_codex_app_server_cmd"
    return ""


def _connector_binary_from_command(command: str) -> str:
    if not command.strip():
        return ""
    return command.strip().split(" ", 1)[0].strip()


def _launchctl_list_output() -> tuple[int, str, str]:
    proc = subprocess.run(["launchctl", "list"], capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _launchctl_service_row(label: str) -> tuple[bool, int | None]:
    code, stdout, _stderr = _launchctl_list_output()
    if code != 0:
        return False, None

    for line in stdout.splitlines():
        if not line.strip().endswith(label):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        pid_token = parts[0]
        if pid_token == "-":
            return True, None
        try:
            return True, int(pid_token)
        except ValueError:
            return True, None
    return False, None


def _daemon_process_detected() -> bool:
    proc = subprocess.run(
        ["pgrep", "-f", "apple_flow daemon"], capture_output=True, text=True, check=False
    )
    return proc.returncode == 0


def _admin_process_detected() -> bool:
    proc = subprocess.run(
        ["pgrep", "-f", "apple_flow admin"], capture_output=True, text=True, check=False
    )
    return proc.returncode == 0


def _admin_health(host: str, port: int, token: str) -> bool:
    if not token.strip():
        return False

    url = f"http://{host}:{port}/health"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=2.0) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def _service_plist_path(label: str = SERVICE_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _log_path(stream_name: str) -> Path:
    filename = "apple-flow.err.log" if stream_name == "stderr" else "apple-flow.log"
    return Path("logs") / filename


def _tail_lines(path: Path, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max(1, limit) :]


def _python_context(project_dir: Path) -> tuple[str, str]:
    venv_python = project_dir / ".venv" / "bin" / "python"
    python_executable = venv_python if venv_python.exists() else Path(sys.executable)
    resolved_python = python_executable.resolve()

    version_out = subprocess.run(
        [str(python_executable), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        check=False,
    )
    if version_out.returncode == 0 and version_out.stdout.strip():
        py_ver = version_out.stdout.strip()
        site_packages = project_dir / ".venv" / "lib" / f"python{py_ver}" / "site-packages"
    else:
        site_packages = project_dir / "src"

    return str(resolved_python), str(site_packages)


def _render_service_plist(
    *,
    label: str,
    mode: str,
    python_bin: str,
    logs_dir: Path,
    project_dir: Path,
    site_packages: str,
    venv_dir: Path,
) -> str:
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
  <dict>
    <key>Label</key>
    <string>{label}</string>

    <key>ProgramArguments</key>
    <array>
      <string>{python_bin}</string>
      <string>-m</string>
      <string>apple_flow</string>
      <string>{mode}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>{logs_dir / f"apple-flow{'-admin' if mode == 'admin' else ''}.log"}</string>

    <key>StandardErrorPath</key>
    <string>{logs_dir / f"apple-flow{'-admin' if mode == 'admin' else ''}.err.log"}</string>

    <key>WorkingDirectory</key>
    <string>{project_dir}</string>

    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>{venv_dir / 'bin'}:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
      <key>PYTHONPATH</key>
      <string>{site_packages}:{project_dir / 'src'}</string>
      <key>VIRTUAL_ENV</key>
      <string>{venv_dir}</string>
    </dict>
  </dict>
</plist>
"""


def _install_service(project_dir: Path) -> dict[str, Any]:
    env_path = project_dir / ".env"
    if not env_path.exists():
        return _response_error(
            "missing_env",
            ["No .env file found. Run `apple-flow setup` first."],
        )

    logs_dir = project_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    plist_dir = _service_plist_path().parent
    plist_dir.mkdir(parents=True, exist_ok=True)

    python_bin, site_packages = _python_context(project_dir)
    venv_dir = project_dir / ".venv"

    service_specs = (
        (SERVICE_LABEL, "daemon"),
        (ADMIN_SERVICE_LABEL, "admin"),
    )
    plist_paths: dict[str, str] = {}

    for label, mode in service_specs:
        plist_path = _service_plist_path(label)
        plist = _render_service_plist(
            label=label,
            mode=mode,
            python_bin=python_bin,
            logs_dir=logs_dir,
            project_dir=project_dir,
            site_packages=site_packages,
            venv_dir=venv_dir,
        )
        plist_path.write_text(plist, encoding="utf-8")
        plist_paths[label] = str(plist_path)

        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, text=True, check=False)
        load = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True, check=False)
        if load.returncode != 0:
            return _response_error(
                "launchctl_load_failed",
                [f"{label}: {load.stderr.strip() or 'Failed to load launchd service.'}"],
                plist_path=str(plist_path),
                plist_paths=plist_paths,
                labels=list(SERVICE_LABELS),
            )

    return _response_ok(
        plist_path=plist_paths[SERVICE_LABEL],
        plist_paths=plist_paths,
        python_bin=python_bin,
        labels=list(SERVICE_LABELS),
    )


def _start_service() -> dict[str, Any]:
    errors: list[str] = []
    for label in SERVICE_LABELS:
        proc = subprocess.run(
            ["launchctl", "start", label],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"{label}: {proc.stderr.strip() or 'Failed to start service.'}")
    if errors:
        return _response_error("launchctl_start_failed", errors, labels=list(SERVICE_LABELS))
    return _response_ok(labels=list(SERVICE_LABELS))


def _stop_service() -> dict[str, Any]:
    errors: list[str] = []
    for label in SERVICE_LABELS:
        loaded, _pid = _launchctl_service_row(label)
        if not loaded:
            continue
        proc = subprocess.run(
            ["launchctl", "stop", label],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"{label}: {proc.stderr.strip() or 'Failed to stop service.'}")
    if errors:
        return _response_error("launchctl_stop_failed", errors, labels=list(SERVICE_LABELS))
    return _response_ok(labels=list(SERVICE_LABELS))


def _restart_service() -> dict[str, Any]:
    errors: list[str] = []
    for label in SERVICE_LABELS:
        target = f"gui/{os.getuid()}/{label}"
        proc = subprocess.run(
            ["launchctl", "kickstart", "-k", target],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            errors.append(f"{label}: {proc.stderr.strip() or 'Failed to restart service.'}")
    if errors:
        return _response_error("launchctl_restart_failed", errors, labels=list(SERVICE_LABELS))
    return _response_ok(labels=list(SERVICE_LABELS))


def _wizard_doctor(args: Any) -> dict[str, Any]:
    env_path = Path(getattr(args, "env_file", ".env"))
    env = _parse_env(env_path)
    env_path_display = str(env_path.resolve())

    python_ok = Path(sys.executable).exists()
    venv_ok = (Path.cwd() / ".venv" / "bin" / "python").exists()
    messages_db_exists = (Path.home() / "Library" / "Messages" / "chat.db").exists()
    readable, read_reason = check_messages_db_access()

    connector = env.get("apple_flow_connector", "codex-cli").strip() or "codex-cli"
    connector_key = _connector_command_key(connector)
    connector_command = env.get(connector_key, "").strip() if connector_key else ""
    if not connector_command:
        default_commands = {
            "claude-cli": "claude",
            "codex-cli": "codex",
            "cline": "cline",
            "codex-app-server": "codex app-server",
        }
        connector_command = default_commands.get(connector, "")

    connector_binary = _connector_binary_from_command(connector_command)
    resolved_binary = resolve_binary(connector_binary) if connector_binary else None
    connector_binary_found = bool(resolved_binary)

    token_present = bool(env.get("apple_flow_admin_api_token", "").strip())

    errors: list[str] = []
    if not env_path.exists():
        errors.append(f".env file not found at {env_path_display}")
    if not python_ok:
        errors.append("Python executable not found.")
    if not venv_ok:
        errors.append("Virtual environment not found at .venv/bin/python.")
    if not messages_db_exists:
        errors.append("Messages database not found at ~/Library/Messages/chat.db.")
    if not readable:
        errors.append(read_reason)
    if not connector_binary_found:
        errors.append(f"Connector binary not found for {connector}: {connector_binary or '(empty)'}")
    if not token_present:
        if "adminApiTokenPresent" in env:
            errors.append(
                "Found `adminApiTokenPresent` in .env, but the correct key is "
                "`apple_flow_admin_api_token`."
            )
        errors.append(f"apple_flow_admin_api_token is missing in .env ({env_path_display})")

    return _response_ok(
        python_ok=python_ok,
        venv_ok=venv_ok,
        messages_db_exists=messages_db_exists,
        messages_db_readable=readable,
        connector_binary_found=connector_binary_found,
        connector_binary_path=resolved_binary or "",
        admin_api_token_present=token_present,
        env_file_path=env_path_display,
        errors=errors,
    )


def _parse_gateways(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _wizard_generate_env(args: Any) -> dict[str, Any]:
    validation_errors: list[str] = []

    phone = validate_phone(args.phone or "")
    if not phone:
        validation_errors.append("phone must be E.164 format, e.g. +15551234567")

    connector = (args.connector or "").strip()
    if connector not in {"claude-cli", "codex-cli", "cline", "codex-app-server"}:
        validation_errors.append("connector must be one of: claude-cli, codex-cli, cline, codex-app-server")

    workspace = validate_workspace_path(args.workspace or "")
    if not workspace:
        validation_errors.append("workspace must be an existing directory")

    connector_command = (args.connector_command or "").strip()
    if not connector_command:
        validation_errors.append("connector-command is required")
    else:
        connector_binary = _connector_binary_from_command(connector_command)
        resolved = resolve_binary(connector_binary)
        if not resolved and not Path(connector_binary).is_absolute():
            validation_errors.append(f"connector binary not found: {connector_binary}")

    gateways = _parse_gateways(args.gateways or "")
    allowed_gateways = {"mail", "reminders", "notes", "calendar"}
    for gateway in gateways:
        if gateway not in allowed_gateways:
            validation_errors.append(f"unsupported gateway: {gateway}")

    mail_address = (args.mail_address or "").strip()
    if "mail" in gateways and not validate_email(mail_address):
        validation_errors.append("mail-address is required and must be valid when mail gateway is enabled")

    reminders_list_name = (args.reminders_list_name or "").strip() or "agent-task"
    reminders_archive_list_name = (args.reminders_archive_list_name or "").strip() or "agent-archive"
    notes_folder_name = (args.notes_folder_name or "").strip() or "agent-task"
    notes_archive_folder_name = (args.notes_archive_folder_name or "").strip() or "agent-archive"
    notes_log_folder_name = (args.notes_log_folder_name or "").strip() or "agent-logs"
    calendar_name = (
        (getattr(args, "calendar_name_override", "") or "").strip()
        or (getattr(args, "calendar_name", "") or "").strip()
        or "agent-schedule"
    )
    admin_api_token = (args.admin_api_token or "").strip()
    enable_agent_office = bool(getattr(args, "enable_agent_office", False))
    soul_file = (getattr(args, "soul_file", "") or "").strip() or "agent-office/SOUL.md"

    if validation_errors:
        return _response_error(
            "validation_failed",
            ["validation failed"],
            validation_errors=validation_errors,
            env_preview="",
        )

    env_preview = generate_env(
        phone=phone or "",
        connector=connector,
        connector_command=connector_command,
        workspace=workspace or "",
        gateways=gateways,
        mail_address=mail_address,
        reminders_list_name=reminders_list_name,
        reminders_archive_list_name=reminders_archive_list_name,
        notes_folder_name=notes_folder_name,
        notes_archive_folder_name=notes_archive_folder_name,
        notes_log_folder_name=notes_log_folder_name,
        calendar_name=calendar_name,
        enable_notes_logging=bool(getattr(args, "enable_notes_logging", False)),
        admin_api_token=admin_api_token,
        enable_agent_office=enable_agent_office,
        soul_file=soul_file,
    )

    return _response_ok(env_preview=env_preview, validation_errors=[])


def _wizard_ensure_gateways(args: Any) -> dict[str, Any]:
    calendar_name = (
        getattr(args, "calendar_name_override", None)
        or getattr(args, "calendar_name", None)
        or "agent-schedule"
    )
    statuses = ensure_gateway_resources(
        enable_reminders=bool(args.enable_reminders),
        enable_notes=bool(args.enable_notes),
        enable_notes_logging=bool(args.enable_notes_logging),
        enable_calendar=bool(args.enable_calendar),
        reminders_list_name=args.reminders_list_name,
        reminders_archive_list_name=args.reminders_archive_list_name,
        notes_folder_name=args.notes_folder_name,
        notes_archive_folder_name=args.notes_archive_folder_name,
        notes_log_folder_name=args.notes_log_folder_name,
        calendar_name=calendar_name,
    )

    results = [
        {
            "label": status.label,
            "name": status.name,
            "status": status.result.status,
            "detail": status.result.detail,
        }
        for status in statuses
    ]
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        return _response_error(
            "gateway_setup_failed",
            [f"{r['label']} failed: {r['detail'] or 'unknown error'}" for r in failed],
            results=results,
        )
    return _response_ok(results=results)


def _config_validate(args: Any) -> dict[str, Any]:
    env_path = Path(args.env_file)
    if not env_path.exists():
        return _response_error("env_not_found", [f"env file not found: {env_path}"])

    errors: list[str] = []
    warnings: list[str] = []
    try:
        settings = RelaySettings(_env_file=str(env_path))
    except Exception as exc:  # pragma: no cover - defensive catch
        return _response_error("config_invalid", [f"failed to load settings: {exc}"])

    if not settings.allowed_senders:
        errors.append("apple_flow_allowed_senders is empty")
    if not settings.allowed_workspaces:
        errors.append("apple_flow_allowed_workspaces is empty")
    if not settings.admin_api_token:
        errors.append("apple_flow_admin_api_token is missing")
    if not Path(settings.default_workspace).exists():
        warnings.append(f"default workspace does not exist: {settings.default_workspace}")

    if errors:
        return _response_error("config_invalid", errors, warnings=warnings)
    return _response_ok(errors=[], warnings=warnings)


def _config_write(args: Any) -> dict[str, Any]:
    env_path = Path(args.env_file)
    updates: dict[str, str] = {}
    for item in args.set_values or []:
        if "=" not in item:
            return _response_error(
                "invalid_set_argument",
                [f"invalid --set value: {item}. expected key=value"],
            )
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            return _response_error("invalid_set_argument", [f"invalid key in --set: {item}"])
        updates[key] = value

    if not updates:
        return _response_error("missing_updates", ["no --set values provided"])

    updated_keys = _write_env(env_path, updates)
    return _response_ok(updated_keys=updated_keys, errors=[])


def _config_read(args: Any) -> dict[str, Any]:
    env_path = Path(args.env_file)
    env = _parse_env(env_path)
    keys = args.keys or []
    if not keys:
        return _response_ok(values=env)
    values = {key: env.get(key, "") for key in keys}
    return _response_ok(values=values)


def _service_status(_args: Any) -> dict[str, Any]:
    loaded, pid = _launchctl_service_row(SERVICE_LABEL)
    admin_loaded, admin_pid = _launchctl_service_row(ADMIN_SERVICE_LABEL)
    plist_path = _service_plist_path(SERVICE_LABEL)
    admin_plist_path = _service_plist_path(ADMIN_SERVICE_LABEL)

    settings = RelaySettings()
    healthy = _admin_health(settings.admin_host, settings.admin_port, settings.admin_api_token)

    return _response_ok(
        launchd_loaded=loaded,
        launchd_pid=pid,
        admin_launchd_loaded=admin_loaded,
        admin_launchd_pid=admin_pid,
        daemon_process_detected=_daemon_process_detected(),
        admin_process_detected=_admin_process_detected(),
        plist_path=str(plist_path),
        admin_plist_path=str(admin_plist_path),
        healthy=healthy,
    )


def _service_install(_args: Any) -> dict[str, Any]:
    return _install_service(Path.cwd())


def _service_start(_args: Any) -> dict[str, Any]:
    return _start_service()


def _service_stop(_args: Any) -> dict[str, Any]:
    return _stop_service()


def _service_restart(_args: Any) -> dict[str, Any]:
    return _restart_service()


def _service_logs(args: Any) -> dict[str, Any]:
    stream_name = args.stream_name
    path = _log_path(stream_name)
    lines = _tail_lines(path, args.lines)
    return _response_ok(path=str(path), lines=lines)


def run_cli_control(mode: str, args: Any) -> int:
    command = (args.tool_args[0] if args.tool_args else "").strip().lower()
    if not command:
        _print_json(_response_error("missing_command", [f"missing subcommand for mode '{mode}'"]))
        return 1

    handlers: dict[tuple[str, str], Any] = {
        ("wizard", "doctor"): _wizard_doctor,
        ("wizard", "generate-env"): _wizard_generate_env,
        ("wizard", "ensure-gateways"): _wizard_ensure_gateways,
        ("config", "validate"): _config_validate,
        ("config", "write"): _config_write,
        ("config", "read"): _config_read,
        ("service", "status"): _service_status,
        ("service", "install"): _service_install,
        ("service", "start"): _service_start,
        ("service", "stop"): _service_stop,
        ("service", "restart"): _service_restart,
        ("service", "logs"): _service_logs,
    }

    handler = handlers.get((mode, command))
    if handler is None:
        _print_json(
            _response_error(
                "unsupported_command",
                [f"unsupported command: {mode} {command}"],
            )
        )
        return 1

    try:
        result = handler(args)
    except Exception as exc:  # pragma: no cover - defensive catch
        _print_json(_response_error("internal_error", [str(exc)]))
        return 1

    _print_json(result)
    return 0 if result.get("ok") else 1
