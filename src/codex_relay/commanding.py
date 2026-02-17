from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CommandKind(str, Enum):
    CHAT = "chat"
    IDEA = "idea"
    PLAN = "plan"
    TASK = "task"
    PROJECT = "project"
    CLEAR_CONTEXT = "clear_context"
    APPROVE = "approve"
    DENY = "deny"
    STATUS = "status"
    HEALTH = "health"
    HISTORY = "history"


@dataclass(slots=True)
class ParsedCommand:
    kind: CommandKind
    payload: str
    workspace: str = ""  # @alias extracted from payload


# Pattern: @alias at the start of the payload, e.g. "@web-app fix CSS"
_WORKSPACE_ALIAS_RE = re.compile(r"^@([\w.-]+)\s*")

_PREFIX_TO_KIND = {
    "idea": CommandKind.IDEA,
    "plan": CommandKind.PLAN,
    "task": CommandKind.TASK,
    "project": CommandKind.PROJECT,
    "health": CommandKind.HEALTH,
    "history": CommandKind.HISTORY,
}


def _extract_workspace_alias(payload: str) -> tuple[str, str]:
    """Extract @alias from the beginning of the payload.

    Returns (alias, remaining_payload). If no alias, returns ("", payload).
    """
    match = _WORKSPACE_ALIAS_RE.match(payload)
    if match:
        alias = match.group(1)
        remaining = payload[match.end():].strip()
        return alias, remaining
    return "", payload


def parse_command(raw_text: str) -> ParsedCommand:
    text = raw_text.strip()
    lowered = text.lower()

    if lowered == "status":
        return ParsedCommand(kind=CommandKind.STATUS, payload="")

    if lowered in {"clear context", "new chat", "reset context"}:
        return ParsedCommand(kind=CommandKind.CLEAR_CONTEXT, payload="")

    if lowered == "health":
        return ParsedCommand(kind=CommandKind.HEALTH, payload="")

    if lowered.startswith("approve "):
        return ParsedCommand(kind=CommandKind.APPROVE, payload=text.split(" ", 1)[1].strip())

    if lowered.startswith("deny "):
        return ParsedCommand(kind=CommandKind.DENY, payload=text.split(" ", 1)[1].strip())

    for prefix, kind in _PREFIX_TO_KIND.items():
        marker = f"{prefix}:"
        if lowered.startswith(marker):
            payload = text[len(marker):].strip()
            workspace, clean_payload = _extract_workspace_alias(payload)
            return ParsedCommand(kind=kind, payload=clean_payload, workspace=workspace)

    # Plain chat — still check for @alias
    workspace, clean_payload = _extract_workspace_alias(text)
    return ParsedCommand(kind=CommandKind.CHAT, payload=clean_payload, workspace=workspace)
