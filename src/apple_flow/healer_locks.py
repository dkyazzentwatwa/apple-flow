from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class LockPrediction:
    keys: list[str]
    source: str


_PATH_PATTERN = re.compile(r"(?P<path>(?:src|tests|docs|scripts)/[A-Za-z0-9._/\-]+)")


def predict_lock_set(*, issue_text: str, max_paths: int = 24) -> LockPrediction:
    """Deterministic lock prediction from issue text and error snippets."""
    matches = [m.group("path") for m in _PATH_PATTERN.finditer(issue_text or "")]
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in matches:
        candidate = _normalize_path(raw)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= max_paths:
            break

    if not normalized:
        return LockPrediction(keys=["repo:*"], source="coarse_repo_lock")

    if len(normalized) > 10:
        coarse = sorted({_to_directory_lock(p) for p in normalized})
        return LockPrediction(keys=coarse, source="directory_escalation")

    return LockPrediction(keys=[f"path:{p}" for p in sorted(normalized)], source="path_level")


def canonicalize_lock_keys(keys: list[str]) -> list[str]:
    return sorted({(key or "").strip().lower() for key in keys if (key or "").strip()})


def lock_granularity(lock_key: str) -> str:
    if lock_key.startswith("path:"):
        return "path"
    if lock_key.startswith("dir:"):
        return "dir"
    if lock_key.startswith("module:"):
        return "module"
    return "repo"


def diff_paths_to_lock_keys(paths: list[str], *, coarse_threshold: int = 12) -> list[str]:
    normalized = sorted({_normalize_path(path) for path in paths if _normalize_path(path)})
    if not normalized:
        return ["repo:*"]
    if len(normalized) > coarse_threshold:
        return sorted({_to_directory_lock(path) for path in normalized})
    return [f"path:{path}" for path in normalized]


def _normalize_path(path: str) -> str:
    cleaned = (path or "").strip().replace("\\", "/")
    cleaned = cleaned.lstrip("./")
    cleaned = os.path.normpath(cleaned).replace("\\", "/")
    if cleaned.startswith("../"):
        return ""
    if cleaned in {".", ""}:
        return ""
    return cleaned


def _to_directory_lock(path: str) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return f"module:{parts[0]}"
    if len(parts) == 2:
        return f"dir:{parts[0]}"
    return f"dir:{'/'.join(parts[:2])}"
