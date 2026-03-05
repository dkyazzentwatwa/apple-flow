#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _load_env_token(repo: Path) -> str:
    candidates = [
        Path.cwd() / ".env",
        repo / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or not stripped.startswith("GITHUB_TOKEN="):
                    continue
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _resolve_github_token(repo: Path) -> str:
    return (os.getenv("GITHUB_TOKEN", "") or _load_env_token(repo)).strip()


def _run(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return False, str(exc)
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode == 0, output


def _check(label: str, ok: bool, detail: str) -> str:
    status = "OK" if ok else "FAIL"
    return f"[{status}] {label}: {detail}"


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    lines: list[str] = []
    failures = 0

    is_repo = (repo / ".git").exists()
    lines.append(_check("git repo", is_repo, str(repo)))
    if not is_repo:
        print("\n".join(lines))
        return 1

    ok, origin = _run(["git", "remote", "get-url", "origin"], repo)
    lines.append(_check("origin remote", ok, origin or "missing"))
    failures += 0 if ok else 1

    ok, branch = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], repo)
    if not ok:
        ok, branch = _run(["git", "branch", "--show-current"], repo)
    lines.append(_check("default branch hint", ok, branch or "unknown"))
    failures += 0 if ok else 1

    docker = shutil.which("docker")
    lines.append(_check("docker cli", docker is not None, docker or "not found"))
    failures += 0 if docker else 1

    token = _resolve_github_token(repo)
    token_present = bool(token)
    token_detail = "present" if token_present else "not in environment or repo .env"
    lines.append(_check("GITHUB_TOKEN", token_present, token_detail))
    if not token_present:
        failures += 1

    python_markers = [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "tests",
    ]
    hits = [name for name in python_markers if (repo / name).exists()]
    lines.append(_check("python test signals", bool(hits), ", ".join(hits) if hits else "none detected"))
    if not hits:
        failures += 1

    print("\n".join(lines))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
