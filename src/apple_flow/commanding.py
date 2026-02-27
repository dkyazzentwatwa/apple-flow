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
    HELP = "help"
    CLEAR_CONTEXT = "clear_context"
    APPROVE = "approve"
    DENY = "deny"
    DENY_ALL = "deny_all"
    STATUS = "status"
    HEALTH = "health"
    HISTORY = "history"
    USAGE = "usage"
    SYSTEM = "system"
    LOGS = "logs"


@dataclass(slots=True)
class ParsedCommand:
    kind: CommandKind
    payload: str
    workspace: str = ""  # @alias extracted from payload


# Pattern: @alias at the start of the payload, e.g. "@web-app fix CSS"
_WORKSPACE_ALIAS_RE = re.compile(r"^@([\w.-]+)\s*")

_MUTATING_VERB_RE = re.compile(
    r"\b(create|write|generate|scaffold|bootstrap|init(?:ialise|ialize)?|"
    r"build|compile|deploy|release|publish|ship|"
    r"delete|remove|drop|wipe|purge|"
    r"edit|update|modify|patch|refactor|rename|move|"
    r"install|uninstall|upgrade|downgrade|"
    r"run|execute|exec|apply|migrate|seed|"
    r"commit|push|merge|rebase|reset|checkout)\b",
    re.IGNORECASE,
)

_OBJECT_RE = re.compile(
    r"\b(file|files|directory|dir|folder|"
    r"script|code|function|class|module|package|"
    r"database|db|schema|migration|"
    r"service|server|api|endpoint|"
    r"test|tests|spec|specs|"
    r"project|app|application|repo|repository)\b",
    re.IGNORECASE,
)

_LABELS_CLAUSE_RE = re.compile(r"\blabels?\s*[:=]\s*([^\n.;]+)", re.IGNORECASE)
_CLASSIFY_INTO_RE = re.compile(r"\bclassif(?:y|ication)?\b[^\n]*?\binto\b\s+([^\n.;]+)", re.IGNORECASE)
_INTO_LABELS_RE = re.compile(r"\binto\s+labels?\s*[:=]?\s*([^\n.;]+)", re.IGNORECASE)
_NATURAL_TEAM_LOAD_RE = re.compile(
    r"(?:^|\b)(?:load up|load|switch to)\s+(?:the\s+)?[\"']?(?P<slug>[a-z0-9][a-z0-9-]*)[\"']?",
    re.IGNORECASE,
)


def is_likely_mutating(text: str) -> bool:
    """Return True when text contains a mutating verb AND a concrete object noun.

    Requires both signals to reduce false positives — e.g. "write me a haiku"
    has a verb but no object noun, so it returns False.
    """
    return bool(_MUTATING_VERB_RE.search(text) and _OBJECT_RE.search(text))


def extract_prompt_labels(text: str) -> list[str]:
    """Extract a user-provided label list from free-form prompt text.

    Supported examples:
    - "labels: Focus, Noise, Action"
    - "classify into Focus / Noise / Action"
    - "move into labels Focus, Noise, Action"
    """
    if not text:
        return []

    match = (
        _LABELS_CLAUSE_RE.search(text)
        or _CLASSIFY_INTO_RE.search(text)
        or _INTO_LABELS_RE.search(text)
    )
    if not match:
        return []

    raw = match.group(1).strip()
    # Trim trailing clauses that usually start a new instruction.
    raw = re.split(r"\b(?:based on|from|using|where|when)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0]

    chunks = re.split(r"\s*(?:,|/|\||\band\b)\s*", raw, flags=re.IGNORECASE)
    labels: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        label = chunk.strip().strip("\"'`")
        label = re.sub(r"^(?:the|a|an)\s+", "", label, flags=re.IGNORECASE)
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            continue
        normalized = label.lower()
        if normalized in {"you decide", "decide", "which", "whichever"}:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        labels.append(label)
    return labels


_PREFIX_TO_KIND = {
    "idea": CommandKind.IDEA,
    "plan": CommandKind.PLAN,
    "task": CommandKind.TASK,
    "project": CommandKind.PROJECT,
    "help": CommandKind.HELP,
    "health": CommandKind.HEALTH,
    "history": CommandKind.HISTORY,
    "usage": CommandKind.USAGE,
    "system": CommandKind.SYSTEM,
    "logs": CommandKind.LOGS,
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

    if lowered.startswith("status "):
        return ParsedCommand(kind=CommandKind.STATUS, payload=text.split(" ", 1)[1].strip())

    if lowered == "help":
        return ParsedCommand(kind=CommandKind.HELP, payload="")

    if lowered.startswith("help "):
        return ParsedCommand(kind=CommandKind.HELP, payload=text.split(" ", 1)[1].strip())

    if lowered in {"clear context", "new chat", "reset context"}:
        return ParsedCommand(kind=CommandKind.CLEAR_CONTEXT, payload="")

    if lowered == "health":
        return ParsedCommand(kind=CommandKind.HEALTH, payload="")

    if lowered == "usage":
        return ParsedCommand(kind=CommandKind.USAGE, payload="")

    if lowered == "logs":
        return ParsedCommand(kind=CommandKind.LOGS, payload="")

    if lowered.startswith("approve "):
        return ParsedCommand(kind=CommandKind.APPROVE, payload=text.split(" ", 1)[1].strip())

    if lowered in {"deny all", "clear approvals", "cancel all"}:
        return ParsedCommand(kind=CommandKind.DENY_ALL, payload="")

    if lowered.startswith("deny "):
        return ParsedCommand(kind=CommandKind.DENY, payload=text.split(" ", 1)[1].strip())

    natural_team = _parse_natural_team_command(text, lowered)
    if natural_team is not None:
        return natural_team

    for prefix, kind in _PREFIX_TO_KIND.items():
        marker = f"{prefix}:"
        if lowered.startswith(marker):
            payload = text[len(marker):].strip()
            workspace, clean_payload = _extract_workspace_alias(payload)
            return ParsedCommand(kind=kind, payload=clean_payload, workspace=workspace)

    # Plain chat — still check for @alias
    workspace, clean_payload = _extract_workspace_alias(text)
    return ParsedCommand(kind=CommandKind.CHAT, payload=clean_payload, workspace=workspace)


def _parse_natural_team_command(text: str, lowered: str) -> ParsedCommand | None:
    compact = lowered.strip(" \t\n\r.,!?")

    list_signals = (
        "list available agent teams",
        "list available teams",
        "list agent teams",
        "list teams",
        "show teams",
        "show agent teams",
        "what teams are available",
        "what agent teams are available",
        "available teams",
        "available agent teams",
    )
    if compact in list_signals:
        return ParsedCommand(kind=CommandKind.SYSTEM, payload="teams list")

    current_signals = (
        "what team is active",
        "what team is loaded",
        "what team is current",
        "current team",
        "active team",
        "loaded team",
    )
    if compact in current_signals:
        return ParsedCommand(kind=CommandKind.SYSTEM, payload="team current")

    unload_signals = (
        "unload team",
        "clear team",
        "reset team",
        "disable team",
    )
    if compact in unload_signals:
        return ParsedCommand(kind=CommandKind.SYSTEM, payload="team unload")

    match = _NATURAL_TEAM_LOAD_RE.search(text)
    if not match:
        return None

    slug = (match.group("slug") or "").strip().lower()
    if not slug:
        return None

    remainder = text[match.end() :].strip()
    if remainder.lower().startswith("team "):
        remainder = remainder[5:].strip()
    if remainder.lower().startswith("and "):
        remainder = remainder[4:].strip()

    payload = f"team load {slug}"
    if remainder:
        payload = f"{payload} and {remainder}"
    return ParsedCommand(kind=CommandKind.SYSTEM, payload=payload)
