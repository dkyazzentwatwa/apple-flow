"""General-purpose Apple app tools for AI use via the apple-flow CLI.

Each function is a standalone callable backed by AppleScript (or SQLite for
iMessage).  Designed to be invoked by an AI assistant via::

    apple-flow tools <command> [args]

All functions return JSON-serializable values and never raise — failures are
logged and empty/falsy values are returned.
"""

from __future__ import annotations

import html
import json
import logging
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("apple_flow.apple_tools")
PAGES_APP_IDS = ("com.apple.Pages", "com.apple.iWork.Pages")
PAGES_APP_TARGETS = (
    'application id "com.apple.Pages"',
    'application id "com.apple.iWork.Pages"',
    'application "/Applications/Pages Creator Studio.app"',
    'application "Pages Creator Studio"',
    'application "Pages"',
)
PAGES_OPEN_TARGETS = (
    "/Applications/Pages Creator Studio.app",
    "Pages Creator Studio",
    "Pages",
)
PAGES_PAGEBREAK_TOKEN = "__APPLE_FLOW_PAGE_BREAK__"
PAGES_THEME_PRESETS = {"auto", "neutral", "minimal", "corporate", "legal", "proposal"}
PAGES_EXPORT_PRESETS = {"none", "pdf", "docx"}
PAGES_DEFAULT_PAGE_BREAK_MARKER = "<!-- pagebreak -->"
NUMBERS_APP_IDS = ("com.apple.Numbers", "com.apple.iWork.Numbers")
NUMBERS_APP_TARGETS = (
    'application id "com.apple.Numbers"',
    'application id "com.apple.iWork.Numbers"',
    'application "/Applications/Numbers Creator Studio.app"',
    'application "Numbers Creator Studio"',
    'application "Numbers"',
)

# ---------------------------------------------------------------------------
# TOOLS_CONTEXT — injected into AI prompts so the AI knows these tools exist
# ---------------------------------------------------------------------------

TOOLS_CONTEXT = """\
You have access to Apple apps via the apple-flow CLI. Run: apple-flow tools <command>
Output is JSON. Use --text for human-readable output.

NOTES:  notes_search "q" [--folder X] [--limit N]  |  notes_list [--folder X]  |  notes_list_folders
        notes_get_content "Title" [--folder X]  |  notes_create "Title" "Body" [--folder X]
        notes_append "Title" "Text" [--folder X]
PAGES:  pages_create "/abs/path/file.pages" "Title" "Body" [--overwrite true|false]
        pages_append "/abs/path/file.pages" "Text"
        pages_from_markdown "<input.md|->" ["/abs/path/output.pages"] [--theme auto|neutral|minimal|corporate|legal|proposal] [--style auto|neutral] [--title-page auto|off] [--toc auto|off] [--citations auto|off] [--images auto|off] [--image-max-width N] [--page-break-marker TEXT] [--qa true|false] [--export none|pdf|docx|pdf,docx] [--overwrite true|false]
        pages_update_sections "<base.md|->" "<updates.md>" "<output.pages>" [--sections "A,B"] [same render flags]
        pages_template "<research|contract|proposal>" ["/abs/path/template.md"]
NUMBERS: numbers_create "/abs/path/file.numbers" '["H1","H2"]' [--sheet X] [--table X] [--overwrite true|false]
         numbers_create_workbook "/abs/path/file.numbers" '{"sheets":[{"sheet_name":"Transactions","table_name":"Tx","headers":["Date","Item","Amount"],"rows":[["2026-03-04","Coffee",15]]}]}' [--overwrite true|false]
         numbers_add_sheet "/abs/path/file.numbers" '{"sheet_name":"Summary","table_name":"Summary","headers":["Metric","Value"],"rows":[["Total",45]]}'
         numbers_append_rows "/abs/path/file.numbers" '[["a",1],["b",2]]' [--sheet X] [--table X] [--position after-headers|after-data|at-end]
         numbers_style_apply "/abs/path/file.numbers" '{"scope":"range","start_row":2,"end_row":10,"start_column":1,"end_column":5}' '{"background_color":[255,245,230],"font_size":12,"alignment":"center"}' [--sheet X] [--table X]
MAIL:   mail_list_unread [--limit N]  |  mail_search "q" [--days N]  |  mail_get_content "id"
        mail_send "to@x.com" "Subject" "Body"  |  mail_list_mailboxes [--account X] [--include-system true|false]
        mail_move_to_label --message-id <id> [--message-id <id> ...] --label <name> [--account X] [--mailbox X]
REMINDERS: reminders_list_lists  |  reminders_list [--list X] [--filter incomplete|complete|all]
           reminders_search "q" [--list X]  |  reminders_create "name" [--list X] [--due YYYY-MM-DD]
           reminders_complete "id" --list "List"
CALENDAR:  calendar_list_calendars  |  calendar_list_events [--cal X] [--days N]
           calendar_search "q" [--cal X]  |  calendar_create "Title" "YYYY-MM-DD HH:MM" [--cal X]
MESSAGES:  messages_list_recent_chats [--limit N]  |  messages_search "q" [--limit N]
           messages_send_voice "<text>" "<number>" [--voice X] [--speech-rate N] [--tts-engine auto|say|piper]
"""

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _probe_applescript_target(target: str, timeout: float = 5.0) -> bool:
    """Best-effort probe for whether a document-based app is scriptable."""
    script = f"tell {target} to count of documents"
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _resolve_applescript_target_candidates(
    candidates: tuple[str, ...],
    *,
    fallback: str,
    app_label: str,
) -> str:
    for candidate in candidates:
        if _probe_applescript_target(candidate):
            return candidate
    logger.warning(
        "Unable to verify AppleScript target for %s from candidates; falling back to %s",
        app_label,
        fallback,
    )
    return fallback


def _resolve_applescript_app(
    bundle_ids: tuple[str, ...],
    fallback_name: str,
    *,
    allow_name_fallback: bool = True,
) -> str:
    candidates = [f'application id "{bundle_id}"' for bundle_id in bundle_ids]
    for candidate in candidates:
        if _probe_applescript_target(candidate):
            return candidate
    if allow_name_fallback:
        name_candidate = f'application "{fallback_name}"'
        if _probe_applescript_target(name_candidate):
            return name_candidate
    logger.warning(
        "Unable to verify AppleScript target for %s via bundle id(s); falling back to %s",
        fallback_name,
        candidates[0],
    )
    return candidates[0]


def _pages_app_target() -> str:
    return _resolve_applescript_target_candidates(
        PAGES_APP_TARGETS,
        fallback=PAGES_APP_TARGETS[0],
        app_label="Pages",
    )


def _warm_pages_app() -> bool:
    """Best-effort launcher so Pages AppleScript calls do not fail on cold start."""
    for target in PAGES_OPEN_TARGETS:
        try:
            result = subprocess.run(
                ["open", "-a", target],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            if result.returncode == 0:
                # Give LaunchServices a short window before AppleScript queries.
                time.sleep(1.0)
                return True
        except Exception:
            continue
    logger.warning("Unable to warm Pages app via known launch targets")
    return False


def _numbers_app_target() -> str:
    # Support classic iWork bundle IDs and Creator Studio installs where
    # bundle-id resolution can be flaky but path/name scripting still works.
    return _resolve_applescript_target_candidates(
        NUMBERS_APP_TARGETS,
        fallback=NUMBERS_APP_TARGETS[0],
        app_label="Numbers",
    )


def _run_script(script: str, timeout: float = 30.0) -> str | None:
    """Run an osascript -e command. Returns stdout string or None on any failure."""
    transient_markers = (
        "Connection Invalid error for service com.apple.hiservices-xpcservice",
        "Error received in message reply handler: Connection invalid",
        "Expected class name but found identifier. (-2741)",
    )
    max_attempts = 8
    for attempt in range(1, max_attempts + 1):
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip("\r\n")

            stderr = (result.stderr or "").strip()
            is_transient = any(marker in stderr for marker in transient_markers)
            if is_transient and attempt < max_attempts:
                time.sleep(0.5 * attempt)
                continue

            logger.warning("AppleScript failed (rc=%s): %s", result.returncode, stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("AppleScript timed out after %.1fs", timeout)
            return None
        except FileNotFoundError:
            logger.warning("osascript not found — apple_tools requires macOS")
            return None
        except Exception as exc:
            logger.warning("Unexpected error running AppleScript: %s", exc)
            return None
    return None


def _parse_json_output(raw: str | None) -> list[dict]:
    """Clean control characters and parse a JSON array from AppleScript output."""
    if not raw or raw == "[]":
        return []
    cleaned = "".join(char if (32 <= ord(char) < 127) else " " for char in raw)
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse JSON output: %s", exc)
        return []


def _parse_delimited_output(raw: str | None, field_names: list[str]) -> list[dict]:
    """Parse tab-delimited AppleScript output into a list of dicts.

    Each line is one record; fields are separated by a single tab.
    Lines with the wrong number of fields are silently skipped.
    """
    if not raw:
        return []
    records: list[dict] = []
    expected = len(field_names)
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != expected:
            continue
        records.append(dict(zip(field_names, parts)))
    return records


def _format_output(
    data: list[dict],
    as_text: bool = False,
    format_fn=None,
) -> list | str:
    """Return a JSON-serializable list or a human-readable newline-joined string."""
    if not as_text:
        return data
    if not data:
        return ""
    if format_fn:
        return "\n".join(format_fn(item) for item in data)
    # Default: join first-field values
    first_key = list(data[0].keys())[0] if data else "id"
    return "\n".join(str(item.get(first_key, item)) for item in data)


def _normalize_text_key(value: str) -> str:
    """Normalize a value for case-insensitive matching."""
    return " ".join((value or "").strip().lower().split())


# ---------------------------------------------------------------------------
# Apple Notes
# ---------------------------------------------------------------------------

def notes_list_folders() -> list[str]:
    """Return a list of all Notes folder names."""
    script = '''
    tell application "Notes"
        set folderNames to {}
        repeat with f in every folder
            set end of folderNames to name of f as text
        end repeat
        set AppleScript's text item delimiters to "|||"
        return folderNames as text
    end tell
    '''
    raw = _run_script(script)
    if not raw:
        return []
    return [name.strip() for name in raw.split("|||") if name.strip()]


def _notes_fetch_raw(folder: str = "", limit: int = 50) -> list[dict]:
    """Internal: fetch notes metadata via AppleScript."""
    if folder:
        esc_folder = folder.replace('"', '\\"')
        fetch_block = f'''
            try
                set targetContainer to folder "{esc_folder}"
            on error
                return ""
            end try
            set allNotes to every note of targetContainer
        '''
    else:
        fetch_block = "set allNotes to every note"

    script = f'''
    on sanitise(txt)
        set AppleScript's text item delimiters to character id 9
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 10
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 13
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to ""
        return txt
    end sanitise

    tell application "Notes"
        set maxCount to {int(limit)}
        set outputLines to {{}}
        {fetch_block}

        repeat with n in allNotes
            if (count of outputLines) >= maxCount then exit repeat

            set nId to my sanitise(id of n as text)
            set nName to my sanitise(name of n as text)
            try
                set nBody to plaintext of n as text
                if length of nBody > 400 then set nBody to text 1 thru 400 of nBody
                set nBody to my sanitise(nBody)
            on error
                set nBody to ""
            end try
            try
                set nModDate to my sanitise(modification date of n as text)
            on error
                set nModDate to ""
            end try

            set end of outputLines to nId & character id 9 & nName & character id 9 & nBody & character id 9 & nModDate
        end repeat

        set AppleScript's text item delimiters to character id 10
        return (outputLines as text)
    end tell
    '''
    return _parse_delimited_output(_run_script(script, timeout=60.0), ["id", "name", "preview", "modification_date"])


def notes_list(folder: str = "", limit: int = 20, as_text: bool = False) -> list | str:
    """List notes with id, name, preview, and modification_date.

    Args:
        folder: Notes folder name (empty = all notes)
        limit: Maximum number of notes to return
        as_text: Return human-readable string instead of list

    Returns:
        List of dicts or newline-joined string of note names
    """
    data = _notes_fetch_raw(folder=folder, limit=limit)
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('name', '')}  [{x.get('modification_date', '')}]",
    )


def notes_search(
    query: str,
    folder: str = "",
    limit: int = 20,
    as_text: bool = False,
) -> list | str:
    """Search notes by title or preview content (case-insensitive, Python-side filter).

    Fetches up to 200 notes and filters in Python to avoid per-note shell invocations.
    """
    all_notes = _notes_fetch_raw(folder=folder, limit=200)
    q = query.lower()
    matches = [
        n for n in all_notes
        if q in (n.get("name") or "").lower() or q in (n.get("preview") or "").lower()
    ][:limit]
    return _format_output(
        matches,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('name', '')}  [{x.get('modification_date', '')}]",
    )


def notes_get_content(note_name_or_id: str, folder: str = "") -> str:
    """Return the full plaintext body of a note, or '' if not found."""
    esc_name = note_name_or_id.replace('"', '\\"')
    if folder:
        esc_folder = folder.replace('"', '\\"')
        find_block = f'''
            try
                set targetContainer to folder "{esc_folder}"
            on error
                return ""
            end try
            set matchedNote to missing value
            repeat with n in (every note of targetContainer)
                if (name of n as text) is "{esc_name}" or (id of n as text) is "{esc_name}" then
                    set matchedNote to n
                    exit repeat
                end if
            end repeat
        '''
    else:
        find_block = f'''
            set matchedNote to missing value
            repeat with n in (every note)
                if (name of n as text) is "{esc_name}" or (id of n as text) is "{esc_name}" then
                    set matchedNote to n
                    exit repeat
                end if
            end repeat
        '''

    script = f'''
    tell application "Notes"
        {find_block}
        if matchedNote is missing value then return ""
        try
            return plaintext of matchedNote as text
        on error
            return ""
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    return result or ""


def notes_create(title: str, body: str, folder: str = "") -> str | None:
    """Create a new note. Returns the new note's ID string or None on failure."""
    def _esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    et = _esc(title)
    eb = _esc(body)

    if folder:
        ef = _esc(folder)
        placement = f'''
            if not (exists folder "{ef}") then
                set targetFolder to make new folder with properties {{name:"{ef}"}}
            else
                set targetFolder to folder "{ef}"
            end if
            set newNote to make new note at targetFolder with properties {{name:"{et}", body:"{eb}"}}
        '''
    else:
        placement = f'set newNote to make new note with properties {{name:"{et}", body:"{eb}"}}'

    script = f'''
    tell application "Notes"
        try
            {placement}
            return id of newNote as text
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if not result or result.startswith("error:"):
        logger.warning("notes_create failed: %s", result)
        return None
    return result


def notes_append(note_name_or_id: str, text: str, folder: str = "") -> bool:
    """Append text to an existing note. Returns True on success."""
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    esc_name = _esc(note_name_or_id)
    esc_text = _esc(text)

    if folder:
        esc_folder = _esc(folder)
        find_block = f'''
            try
                set targetContainer to folder "{esc_folder}"
            on error
                return "error: folder not found"
            end try
            set matchedNote to missing value
            repeat with n in (every note of targetContainer)
                if (name of n as text) is "{esc_name}" or (id of n as text) is "{esc_name}" then
                    set matchedNote to n
                    exit repeat
                end if
            end repeat
        '''
    else:
        find_block = f'''
            set matchedNote to missing value
            repeat with n in (every note)
                if (name of n as text) is "{esc_name}" or (id of n as text) is "{esc_name}" then
                    set matchedNote to n
                    exit repeat
                end if
            end repeat
        '''

    script = f'''
    tell application "Notes"
        {find_block}
        if matchedNote is missing value then return "error: note not found"
        try
            set existingBody to plaintext of matchedNote
            set body of matchedNote to existingBody & "\\n\\n" & "{esc_text}"
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if result == "ok":
        return True
    logger.warning("notes_append failed: %s", result)
    return False


# ---------------------------------------------------------------------------
# Apple Pages
# ---------------------------------------------------------------------------

def pages_create(
    file_path: str,
    title: str,
    body: str,
    overwrite: bool = False,
) -> str | None:
    """Create a Pages document at an absolute path. Returns path on success."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        logger.warning("pages_create requires an absolute path: %s", file_path)
        return None
    if path.suffix.lower() != ".pages":
        logger.warning("pages_create requires a .pages path: %s", file_path)
        return None
    if path.exists() and not overwrite:
        logger.warning("pages_create target exists and overwrite=false: %s", file_path)
        return None

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    esc_path = _esc(str(path))
    esc_text = _esc(f"{title}\n\n{body}" if body else title)
    _warm_pages_app()
    pages_app = _pages_app_target()

    script = f'''
    tell {pages_app}
        try
            activate
            set newDoc to make new document
            set body text of newDoc to "{esc_text}"
            save newDoc in POSIX file "{esc_path}"
            close newDoc saving yes
            return "{esc_path}"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=45.0)
    if not result or result.startswith("error:"):
        logger.warning("pages_create failed: %s", result)
        return None
    return result


def pages_append(
    file_path: str,
    text: str,
    include_timestamp_header: bool = True,
) -> bool:
    """Append text to an existing Pages document."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        logger.warning("pages_append requires an absolute path: %s", file_path)
        return False
    if path.suffix.lower() != ".pages":
        logger.warning("pages_append requires a .pages path: %s", file_path)
        return False
    if not path.exists():
        logger.warning("pages_append target does not exist: %s", file_path)
        return False

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    payload = text
    if include_timestamp_header:
        payload = f"--- Apple Flow Entry {timestamp} ---\n{payload}"
    esc_path = _esc(str(path))
    esc_payload = _esc(payload)
    _warm_pages_app()
    pages_app = _pages_app_target()

    script = f'''
    tell {pages_app}
        try
            activate
            open POSIX file "{esc_path}"
            delay 1
            set targetDoc to front document
            set body text of targetDoc to (body text of targetDoc as text) & "\\n\\n" & "{esc_payload}"
            save targetDoc
            close targetDoc saving yes
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=45.0)
    if result == "ok":
        return True
    logger.warning("pages_append failed: %s", result)
    return False


def _normalize_heading_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _strip_markdown_markup(text: str) -> str:
    plain = re.sub(r"`([^`]+)`", r"\1", text)
    plain = re.sub(r"\*\*(.+?)\*\*", r"\1", plain)
    plain = re.sub(r"__(.+?)__", r"\1", plain)
    plain = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", plain)
    plain = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"\1", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    return re.sub(r"\s+", " ", plain).strip()


def _slugify_heading(text: str, seen: dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"
    count = seen.get(base, 0) + 1
    seen[base] = count
    return base if count == 1 else f"{base}-{count}"


def _extract_frontmatter(markdown_text: str) -> tuple[dict[str, str], str]:
    lines = markdown_text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, markdown_text

    closing_idx = None
    for idx in range(1, min(len(lines), 80)):
        if lines[idx].strip() == "---":
            closing_idx = idx
            break
    if closing_idx is None:
        return {}, markdown_text

    metadata: dict[str, str] = {}
    for line in lines[1:closing_idx]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key and normalized_value:
            metadata[normalized_key] = normalized_value

    if not metadata:
        return {}, markdown_text

    body = "\n".join(lines[closing_idx + 1 :])
    return metadata, body


def _extract_markdown_links(markdown_text: str) -> list[dict[str, str]]:
    pattern = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
    seen: set[tuple[str, str]] = set()
    links: list[dict[str, str]] = []

    for label, raw_target in pattern.findall(markdown_text):
        target = raw_target.strip().split(" ", 1)[0].strip("<>")
        clean_label = _strip_markdown_markup(label)
        if not target:
            continue
        key = (clean_label.lower(), target.lower())
        if key in seen:
            continue
        seen.add(key)
        links.append({"label": clean_label or target, "url": target})
    return links


def _apply_inline_markdown_markup(escaped_text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped_text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<em>\1</em>", text)
    return text


def _resolve_markdown_image_source(raw_source: str, source_dir: Path | None) -> tuple[str | None, str | None]:
    source = raw_source.strip()
    if not source:
        return None, "encountered an empty markdown image source"

    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", source):
        return source, None

    candidate = Path(source).expanduser()
    if not candidate.is_absolute():
        base = source_dir or Path.cwd()
        candidate = (base / candidate).resolve()

    if not candidate.exists():
        return None, f"image path does not exist and was skipped: {candidate}"
    if not candidate.is_file():
        return None, f"image path is not a file and was skipped: {candidate}"
    return candidate.as_uri(), None


def _absolutize_markdown_image_links(markdown_text: str, source_dir: Path | None) -> str:
    """Rewrite relative markdown image links to absolute paths for stable merging."""
    if source_dir is None:
        return markdown_text

    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def _replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        raw_source = match.group(2).strip()
        token = raw_source
        remainder = ""

        # Preserve optional title text: ![alt](path "title")
        if " " in raw_source:
            maybe_path, maybe_rest = raw_source.split(" ", 1)
            if maybe_rest.strip().startswith(("'", '"')):
                token = maybe_path
                remainder = " " + maybe_rest

        clean_token = token.strip().strip("<>")
        if not clean_token:
            return match.group(0)
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", clean_token):
            return match.group(0)

        candidate = Path(clean_token).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (source_dir / candidate).resolve()

        resolved_text = resolved.as_posix()
        if token.startswith("<") and token.endswith(">"):
            resolved_text = f"<{resolved_text}>"
        return f"![{alt}]({resolved_text}{remainder})"

    return pattern.sub(_replace, markdown_text)


def _inline_markdown_to_html(
    text: str,
    *,
    include_images: bool = False,
    source_dir: Path | None = None,
    image_max_width: int = 640,
    warnings: list[str] | None = None,
    image_stats: dict[str, int] | None = None,
) -> str:
    image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    out: list[str] = []
    cursor = 0

    for match in image_pattern.finditer(text):
        before = text[cursor : match.start()]
        if before:
            out.append(_apply_inline_markdown_markup(html.escape(before)))

        alt = match.group(1).strip()
        raw_source = match.group(2).strip()
        if image_stats is not None:
            image_stats["references"] = image_stats.get("references", 0) + 1

        if include_images:
            resolved_source, warning = _resolve_markdown_image_source(raw_source, source_dir)
            if resolved_source:
                safe_alt = html.escape(alt or "image")
                safe_src = html.escape(resolved_source, quote=True)
                width = max(120, image_max_width)
                out.append(
                    '<img src="'
                    + safe_src
                    + '" alt="'
                    + safe_alt
                    + '" style="max-width:'
                    + str(width)
                    + 'px;width:100%;height:auto;" />'
                )
                if image_stats is not None:
                    image_stats["embedded"] = image_stats.get("embedded", 0) + 1
            else:
                if warning and warnings is not None:
                    warnings.append(warning)
                fallback = alt or raw_source
                out.append(f"<em>[Image unavailable: {html.escape(fallback)}]</em>")
                if image_stats is not None:
                    image_stats["missing"] = image_stats.get("missing", 0) + 1
        else:
            fallback = alt or raw_source
            out.append(f"<em>[Image: {html.escape(fallback)}]</em>")
            if image_stats is not None:
                image_stats["disabled"] = image_stats.get("disabled", 0) + 1

        cursor = match.end()

    tail = text[cursor:]
    if tail:
        out.append(_apply_inline_markdown_markup(html.escape(tail)))
    return "".join(out)


def _split_markdown_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_markdown_table_row(line)
    if not cells:
        return False
    return all(bool(re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))) for cell in cells)


def _is_ordered_item(line: str) -> bool:
    return bool(re.match(r"^\d+[.)]\s+.+$", line.strip()))


def _is_unordered_item(line: str) -> bool:
    return bool(re.match(r"^[-*+]\s+.+$", line.strip()))


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^#{1,6}\s+.+$", line.strip()))


def _is_special_block_start(lines: list[str], idx: int, *, page_break_marker: str) -> bool:
    line = lines[idx]
    stripped = line.strip()
    if not stripped:
        return True
    if page_break_marker and stripped == page_break_marker.strip():
        return True
    if stripped.startswith("```"):
        return True
    if stripped in {"---", "***", "___"}:
        return True
    if _is_heading(line):
        return True
    if _is_unordered_item(line) or _is_ordered_item(line):
        return True
    if "|" in line and idx + 1 < len(lines) and _is_markdown_table_separator(lines[idx + 1]):
        return True
    return False


def _pages_theme_css(theme: str) -> str:
    base_css = """
    body { font-family: 'Avenir Next', 'Helvetica Neue', sans-serif; line-height: 1.5; font-size: 12pt; }
    h1 { margin: 0 0 14pt 0; font-size: 28pt; letter-spacing: -0.02em; }
    h2 { margin: 16pt 0 8pt 0; font-size: 18pt; }
    h3 { margin: 12pt 0 6pt 0; font-size: 14pt; }
    p { margin: 0 0 9pt 0; }
    ul, ol { margin: 0 0 10pt 20pt; }
    li { margin: 0 0 4pt 0; }
    pre { border: 1px solid #e5e7eb; padding: 10pt; border-radius: 8pt; font-family: Menlo, Consolas, monospace; font-size: 10.5pt; }
    code { font-family: Menlo, Consolas, monospace; padding: 1pt 3pt; border-radius: 3pt; }
    table { border-collapse: collapse; width: 100%; margin: 12pt 0; }
    th, td { border: 1px solid #d1d5db; padding: 7pt 9pt; text-align: left; vertical-align: top; }
    th { font-weight: 700; }
    hr { border: none; border-top: 1px solid #d1d5db; margin: 14pt 0; }
    a { text-decoration: underline; }
    .title-page { text-align: center; margin: 20vh 0 12vh 0; }
    .title-page h1 { font-size: 34pt; margin-bottom: 12pt; }
    .title-page .subtitle { font-size: 14pt; margin-bottom: 12pt; }
    .title-page .meta { font-size: 10.5pt; margin: 4pt 0; }
    .toc { margin: 8pt 0 16pt 0; padding: 10pt 12pt; border-radius: 8pt; }
    .toc h2 { margin-top: 0; }
    .toc ol { margin-bottom: 0; }
    .toc li { margin-bottom: 3pt; }
    .sources { margin-top: 16pt; }
    .source-url { font-size: 9.5pt; }
    img { display: block; margin: 8pt 0; }
    """
    theme_css = {
        "neutral": """
        body { color: #202124; }
        h1, h2, h3 { color: #202124; }
        pre, code { background: #f5f5f5; }
        th { background: #f4f4f4; }
        .toc { background: #f7f7f7; border: 1px solid #dedede; }
        a { color: #1f4b99; }
        """,
        "minimal": """
        body { color: #111827; font-family: 'Charter', 'Times New Roman', serif; line-height: 1.6; }
        h1, h2, h3 { color: #111827; font-family: 'Avenir Next', 'Helvetica Neue', sans-serif; }
        pre, code { background: #f8f8f8; border-color: #ececec; }
        th { background: #fafafa; }
        .toc { background: #fbfbfb; border: 1px solid #ececec; }
        a { color: #1d4ed8; }
        """,
        "corporate": """
        body { color: #1f2937; }
        h1, h2, h3 { color: #111827; }
        pre, code { background: #f3f4f6; }
        th { background: #eef2ff; color: #111827; }
        .toc { background: #eef2ff; border: 1px solid #c7d2fe; }
        a { color: #1d4ed8; }
        """,
        "legal": """
        body { color: #1b1b1b; font-family: 'Times New Roman', Georgia, serif; line-height: 1.55; }
        h1, h2, h3 { color: #111111; font-family: 'Times New Roman', Georgia, serif; letter-spacing: 0; }
        pre, code { background: #f8f8f8; border-color: #e5e5e5; }
        th { background: #f4f4f4; color: #111111; }
        .toc { background: #f8f8f8; border: 1px solid #dddddd; }
        a { color: #0f2f6b; }
        """,
        "proposal": """
        body { color: #1f2937; }
        h1 { color: #0f172a; font-size: 32pt; }
        h2 { color: #1e3a8a; }
        pre, code { background: #f8fafc; border-color: #e2e8f0; }
        th { background: #dbeafe; color: #0f172a; }
        .toc { background: #eff6ff; border: 1px solid #bfdbfe; }
        a { color: #1d4ed8; }
        """,
        "auto": """
        body { color: #1f2937; }
        h1, h2, h3 { color: #111827; }
        pre, code { background: #f3f4f6; }
        th { background: #eef2ff; color: #111827; }
        .toc { background: #f3f4f6; border: 1px solid #d1d5db; }
        a { color: #1d4ed8; }
        """,
    }
    return base_css + theme_css.get(theme, theme_css["auto"])


def _normalize_style(style: str, warnings: list[str]) -> str:
    normalized = style.strip().lower() if style else "auto"
    if normalized not in {"auto", "neutral"}:
        warnings.append(f"unsupported style '{style}' requested; defaulted to 'auto'")
        return "auto"
    return normalized


def _normalize_theme(theme: str, style: str, warnings: list[str]) -> str:
    requested = theme.strip().lower() if theme else "auto"
    legacy_theme = "neutral" if style == "neutral" else "auto"

    if requested == "auto":
        return legacy_theme
    if requested not in PAGES_THEME_PRESETS:
        warnings.append(f"unsupported theme '{theme}' requested; defaulted to '{legacy_theme}'")
        return legacy_theme
    if style == "neutral" and requested != "neutral":
        warnings.append("style='neutral' was overridden by explicit --theme")
    return requested


def _normalize_toggle(
    value: str,
    *,
    option_name: str,
    auto_default: bool,
    warnings: list[str],
) -> bool:
    normalized = (value or "auto").strip().lower()
    truthy = {"true", "yes", "y", "1", "on"}
    falsy = {"false", "no", "n", "0", "off"}
    if normalized == "auto":
        return auto_default
    if normalized in truthy:
        return True
    if normalized in falsy:
        return False
    warnings.append(f"unsupported value '{value}' for {option_name}; using auto")
    return auto_default


def _normalize_export_targets(export: str, warnings: list[str]) -> list[str]:
    value = (export or "none").strip().lower()
    if not value or value == "none":
        return []

    targets: list[str] = []
    for token in value.split(","):
        item = token.strip().lower()
        if not item:
            continue
        if item not in PAGES_EXPORT_PRESETS:
            warnings.append(f"unsupported export target '{item}' ignored")
            continue
        if item != "none" and item not in targets:
            targets.append(item)
    return targets


def _build_title_page_html(metadata: dict[str, str], fallback_title: str) -> str:
    title = metadata.get("title") or fallback_title or "Untitled Document"
    subtitle = metadata.get("subtitle", "")
    author = metadata.get("author", "")
    date = metadata.get("date", "")
    client = metadata.get("client", "")

    parts = [
        '<section class="title-page">',
        f"<h1>{html.escape(title)}</h1>",
    ]
    if subtitle:
        parts.append(f'<p class="subtitle">{html.escape(subtitle)}</p>')
    if author:
        parts.append(f'<p class="meta"><strong>Author:</strong> {html.escape(author)}</p>')
    if client:
        parts.append(f'<p class="meta"><strong>Client:</strong> {html.escape(client)}</p>')
    if date:
        parts.append(f'<p class="meta"><strong>Date:</strong> {html.escape(date)}</p>')
    parts.append("</section>")
    parts.append(f"<p>{PAGES_PAGEBREAK_TOKEN}</p>")
    return "".join(parts)


def _build_toc_html(headings: list[dict[str, Any]]) -> str:
    if not headings:
        return ""
    lines = ['<section class="toc"><h2>Table of Contents</h2><ol>']
    for heading in headings:
        heading_id = html.escape(str(heading["id"]), quote=True)
        text = html.escape(str(heading["text"]))
        lines.append(f'<li><a href="#{heading_id}">{text}</a></li>')
    lines.append("</ol></section>")
    return "".join(lines)


def _insert_native_pages_toc(
    pages_path: Path,
    *,
    include_title_page: bool,
    warnings: list[str],
) -> bool:
    """Insert a real native Pages TOC so in-document links work."""

    def _esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    esc_path = _esc(str(pages_path))
    move_cursor_script = ""
    if include_title_page:
        # Best-effort move toward the document body so the TOC lands after the
        # title page instead of on top of it.
        move_cursor_script = """
        tell application "System Events"
            tell process "Pages"
                key code 125 using {command down}
            end tell
        end tell
        delay 0.3
        """

    script = f'''
    tell application "Pages"
        activate
        open POSIX file "{esc_path}"
    end tell
    delay 1.5
    {move_cursor_script}
    tell application "System Events"
        tell process "Pages"
            click menu item "Document" of menu 1 of menu item "Table of Contents" of menu 1 of menu bar item "Insert" of menu bar 1
        end tell
    end tell
    delay 1.0
    tell application "Pages"
        save front document
        close front document saving yes
    end tell
    return "ok"
    '''
    result = _run_script(script, timeout=60.0)
    if result == "ok":
        return True
    warnings.append(f"native Pages TOC insertion failed: {result or 'unknown error'}")
    return False


def _build_sources_html(citation_links: list[dict[str, str]]) -> str:
    if not citation_links:
        return ""
    lines = ['<section class="sources"><h2>Sources</h2><ol>']
    for item in citation_links:
        label = html.escape(item.get("label", "") or item.get("url", ""))
        url = html.escape(item.get("url", ""), quote=True)
        lines.append(f'<li><a href="{url}">{label}</a><div class="source-url">{url}</div></li>')
    lines.append("</ol></section>")
    return "".join(lines)


def _markdown_to_html_document(
    markdown_text: str,
    *,
    theme: str,
    include_title_page: bool,
    include_toc: bool,
    include_citations: bool,
    citation_links: list[dict[str, str]],
    include_images: bool,
    image_max_width: int,
    page_break_marker: str,
    source_dir: Path | None,
    metadata: dict[str, str],
    warnings: list[str],
) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
    lines = markdown_text.splitlines()
    i = 0
    body_parts: list[str] = []
    heading_entries: list[dict[str, Any]] = []
    heading_slug_counts: dict[str, int] = {}
    image_stats: dict[str, int] = {"references": 0, "embedded": 0, "missing": 0, "disabled": 0}
    page_break_marker = (page_break_marker or "").strip()

    stats = {
        "headings": 0,
        "paragraphs": 0,
        "unordered_lists": 0,
        "ordered_lists": 0,
        "table_count": 0,
        "code_blocks": 0,
        "images": 0,
        "page_breaks": 0,
    }

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if page_break_marker and stripped == page_break_marker:
            body_parts.append(f"<p>{PAGES_PAGEBREAK_TOKEN}</p>")
            stats["page_breaks"] += 1
            i += 1
            continue

        if stripped.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip().startswith("```"):
                i += 1
            body_parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
            stats["code_blocks"] += 1
            continue

        if stripped in {"---", "***", "___"}:
            body_parts.append("<hr>")
            i += 1
            continue

        if _is_heading(line):
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            assert heading_match is not None
            depth = min(len(heading_match.group(1)), 3)
            raw_heading = heading_match.group(2)
            plain_heading = _strip_markdown_markup(raw_heading) or raw_heading.strip()
            heading_id = _slugify_heading(plain_heading, heading_slug_counts)
            content = _inline_markdown_to_html(
                raw_heading,
                include_images=include_images,
                source_dir=source_dir,
                image_max_width=image_max_width,
                warnings=warnings,
                image_stats=image_stats,
            )
            body_parts.append(f'<h{depth} id="{heading_id}">{content}</h{depth}>')
            heading_entries.append({"id": heading_id, "text": plain_heading, "depth": depth})
            stats["headings"] += 1
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and _is_markdown_table_separator(lines[i + 1]):
            header = _split_markdown_table_row(lines[i])
            i += 2
            body_rows: list[list[str]] = []
            while i < len(lines):
                candidate = lines[i]
                candidate_stripped = candidate.strip()
                if not candidate_stripped or "|" not in candidate:
                    break
                if _is_markdown_table_separator(candidate):
                    i += 1
                    continue
                body_rows.append(_split_markdown_table_row(candidate))
                i += 1

            col_count = max(len(header), max((len(row) for row in body_rows), default=0))
            if col_count == 0:
                continue

            padded_header = header + [""] * (col_count - len(header))
            body_parts.append("<table><thead><tr>")
            for cell in padded_header:
                body_parts.append(
                    "<th>"
                    + _inline_markdown_to_html(
                        cell,
                        include_images=include_images,
                        source_dir=source_dir,
                        image_max_width=image_max_width,
                        warnings=warnings,
                        image_stats=image_stats,
                    )
                    + "</th>"
                )
            body_parts.append("</tr></thead><tbody>")
            for row in body_rows:
                padded_row = row + [""] * (col_count - len(row))
                body_parts.append("<tr>")
                for cell in padded_row:
                    body_parts.append(
                        "<td>"
                        + _inline_markdown_to_html(
                            cell,
                            include_images=include_images,
                            source_dir=source_dir,
                            image_max_width=image_max_width,
                            warnings=warnings,
                            image_stats=image_stats,
                        )
                        + "</td>"
                    )
                body_parts.append("</tr>")
            body_parts.append("</tbody></table>")
            stats["table_count"] += 1
            continue

        if _is_unordered_item(line):
            items: list[str] = []
            while i < len(lines) and _is_unordered_item(lines[i]):
                item = re.sub(r"^[-*+]\s+", "", lines[i].strip(), count=1)
                items.append(
                    _inline_markdown_to_html(
                        item,
                        include_images=include_images,
                        source_dir=source_dir,
                        image_max_width=image_max_width,
                        warnings=warnings,
                        image_stats=image_stats,
                    )
                )
                i += 1
            body_parts.append("<ul>")
            for item in items:
                body_parts.append(f"<li>{item}</li>")
            body_parts.append("</ul>")
            stats["unordered_lists"] += 1
            continue

        if _is_ordered_item(line):
            items = []
            while i < len(lines) and _is_ordered_item(lines[i]):
                item = re.sub(r"^\d+[.)]\s+", "", lines[i].strip(), count=1)
                items.append(
                    _inline_markdown_to_html(
                        item,
                        include_images=include_images,
                        source_dir=source_dir,
                        image_max_width=image_max_width,
                        warnings=warnings,
                        image_stats=image_stats,
                    )
                )
                i += 1
            body_parts.append("<ol>")
            for item in items:
                body_parts.append(f"<li>{item}</li>")
            body_parts.append("</ol>")
            stats["ordered_lists"] += 1
            continue

        paragraph_lines = [stripped]
        i += 1
        while i < len(lines) and not _is_special_block_start(lines, i, page_break_marker=page_break_marker):
            next_line = lines[i].strip()
            if next_line:
                paragraph_lines.append(next_line)
            i += 1
        paragraph = " ".join(paragraph_lines).strip()
        if paragraph:
            body_parts.append(
                "<p>"
                + _inline_markdown_to_html(
                    paragraph,
                    include_images=include_images,
                    source_dir=source_dir,
                    image_max_width=image_max_width,
                    warnings=warnings,
                    image_stats=image_stats,
                )
                + "</p>"
            )
            stats["paragraphs"] += 1

    stats["images"] = image_stats.get("embedded", 0)
    if image_stats.get("missing", 0):
        stats["images_missing"] = image_stats["missing"]  # type: ignore[index]
    if image_stats.get("disabled", 0):
        stats["images_disabled"] = image_stats["disabled"]  # type: ignore[index]

    preface_parts: list[str] = []
    fallback_title = heading_entries[0]["text"] if heading_entries else ""
    if include_title_page:
        preface_parts.append(_build_title_page_html(metadata, fallback_title))
    # We no longer embed an HTML TOC here because those links do not survive
    # the HTML -> RTF -> Pages conversion path as working internal links.
    # A native Pages TOC is inserted after document creation instead.

    appendix_parts: list[str] = []
    if include_citations and citation_links:
        appendix_parts.append(_build_sources_html(citation_links))

    css = _pages_theme_css(theme)
    doc = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<style>{css}</style>"
        "</head><body>"
        + "".join(preface_parts)
        + "".join(body_parts)
        + "".join(appendix_parts)
        + "</body></html>"
    )
    return doc, stats, heading_entries


def _inject_rtf_page_breaks(rtf_file: Path) -> int:
    try:
        payload = rtf_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0
    replacements = payload.count(PAGES_PAGEBREAK_TOKEN)
    if replacements <= 0:
        return 0
    updated = payload.replace(PAGES_PAGEBREAK_TOKEN, r"\page ")
    try:
        rtf_file.write_text(updated, encoding="utf-8")
    except OSError:
        return 0
    return replacements


def _pages_export_document(
    pages_path: Path,
    targets: list[str],
    pages_app: str,
    warnings: list[str],
) -> dict[str, str]:
    if not targets:
        return {}

    def _esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    exports: dict[str, str] = {}
    esc_input = _esc(str(pages_path))
    for target in targets:
        suffix = ".pdf" if target == "pdf" else ".docx"
        export_kind = "PDF" if target == "pdf" else "Microsoft Word"
        export_path = pages_path.with_suffix(suffix)
        esc_output = _esc(str(export_path))
        script = f'''
        tell {pages_app}
            try
                activate
                set targetDoc to open POSIX file "{esc_input}"
                delay 1
                export targetDoc to POSIX file "{esc_output}" as {export_kind}
                close targetDoc saving no
                return "ok"
            on error errMsg
                try
                    if (count of documents) > 0 then close front document saving no
                end try
                return "error: " & errMsg
            end try
        end tell
        '''
        result = _run_script(script, timeout=90.0)
        if result == "ok":
            exports[target] = str(export_path)
        else:
            warnings.append(f"failed to export {target}: {result or 'unknown error'}")
    return exports


def _render_pages_markdown(
    markdown_text: str,
    *,
    source_label: str,
    source_path: Path | None,
    output_path: str,
    style: str,
    theme: str,
    title_page: str,
    toc: str,
    citations: str,
    images: str,
    image_max_width: int,
    page_break_marker: str,
    qa: bool,
    export: str,
    overwrite: bool,
) -> dict[str, Any]:
    if not markdown_text.strip():
        return {"ok": False, "error": "markdown input is empty"}

    if output_path:
        output = Path(output_path).expanduser()
        if not output.is_absolute():
            output = (Path.cwd() / output).resolve()
    elif source_path is not None:
        output = source_path.with_suffix(".pages")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = (Path.cwd() / f"pages-report-{stamp}.pages").resolve()

    if output.suffix.lower() != ".pages":
        return {"ok": False, "error": "output must use .pages extension"}
    if output.exists() and not overwrite:
        return {"ok": False, "error": f"output exists and overwrite=false: {output}"}

    warnings: list[str] = []
    normalized_style = _normalize_style(style, warnings)
    normalized_theme = _normalize_theme(theme, normalized_style, warnings)
    marker = (page_break_marker or PAGES_DEFAULT_PAGE_BREAK_MARKER).strip()
    if not marker:
        marker = PAGES_DEFAULT_PAGE_BREAK_MARKER
        warnings.append("empty page break marker requested; using default marker")
    width = image_max_width
    if width < 120:
        warnings.append("image_max_width too small; clamped to 120")
        width = 120

    metadata, markdown_body = _extract_frontmatter(markdown_text)
    citation_links = _extract_markdown_links(markdown_body)
    has_images = bool(re.search(r"!\[[^\]]*\]\(([^)]+)\)", markdown_body))
    heading_count = len(re.findall(r"^#{1,6}\s+.+$", markdown_body, flags=re.MULTILINE))

    include_title_page = _normalize_toggle(
        title_page,
        option_name="title_page",
        auto_default=bool(metadata.get("title") or metadata.get("subtitle")),
        warnings=warnings,
    )
    include_toc = _normalize_toggle(
        toc,
        option_name="toc",
        auto_default=heading_count >= 6,
        warnings=warnings,
    )
    include_citations = _normalize_toggle(
        citations,
        option_name="citations",
        auto_default=bool(citation_links),
        warnings=warnings,
    )
    include_images = _normalize_toggle(
        images,
        option_name="images",
        auto_default=has_images,
        warnings=warnings,
    )
    export_targets = _normalize_export_targets(export, warnings)

    source_dir = source_path.parent if source_path else Path.cwd()
    html_doc, stats, headings = _markdown_to_html_document(
        markdown_body,
        theme=normalized_theme,
        include_title_page=include_title_page,
        include_toc=include_toc,
        include_citations=include_citations,
        citation_links=citation_links,
        include_images=include_images,
        image_max_width=width,
        page_break_marker=marker,
        source_dir=source_dir,
        metadata=metadata,
        warnings=warnings,
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    def _esc(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    exports: dict[str, str] = {}
    native_toc_inserted = False
    try:
        with tempfile.TemporaryDirectory(prefix="appleflow-pages-") as tmp_dir:
            stem = source_path.stem if source_path is not None else "stdin-report"
            html_file = Path(tmp_dir) / f"{stem}.html"
            rtf_file = Path(tmp_dir) / f"{stem}.rtf"
            html_file.write_text(html_doc, encoding="utf-8")

            textutil_result = subprocess.run(
                [
                    "textutil",
                    "-convert",
                    "rtf",
                    "-format",
                    "html",
                    str(html_file),
                    "-output",
                    str(rtf_file),
                ],
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            if textutil_result.returncode != 0:
                detail = (textutil_result.stderr or "").strip() or "textutil conversion failed"
                return {"ok": False, "error": detail}

            if rtf_file.exists() and stats.get("page_breaks", 0) > 0:
                applied = _inject_rtf_page_breaks(rtf_file)
                if applied <= 0:
                    warnings.append("page break markers were requested but could not be injected into RTF")
                else:
                    stats["page_breaks_applied"] = applied

            _warm_pages_app()
            pages_app = _pages_app_target()
            esc_rtf = _esc(str(rtf_file))
            esc_output = _esc(str(output))
            script = f'''
            tell {pages_app}
                try
                    activate
                    open POSIX file "{esc_rtf}"
                    delay 1
                    set targetDoc to front document
                    save targetDoc in POSIX file "{esc_output}"
                    close targetDoc saving yes
                    return "ok"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            result = _run_script(script, timeout=90.0)
            if result != "ok":
                return {"ok": False, "error": result or "Pages conversion failed"}

            if include_toc and headings:
                native_toc_inserted = _insert_native_pages_toc(
                    output,
                    include_title_page=include_title_page,
                    warnings=warnings,
                )

            exports = _pages_export_document(output, export_targets, pages_app, warnings)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "conversion timed out"}
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"required tool missing: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"conversion error: {exc}"}

    if not output.exists():
        return {"ok": False, "error": "conversion completed but output file was not created"}

    response: dict[str, Any] = {
        "ok": True,
        "input_path": source_label,
        "output_path": str(output),
        "style": normalized_style,
        "theme": normalized_theme,
        "warnings": warnings,
        "stats": stats,
        "options": {
            "title_page": include_title_page,
            "toc": include_toc,
            "toc_native_inserted": native_toc_inserted,
            "citations": include_citations,
            "images": include_images,
            "page_break_marker": marker,
            "export_targets": export_targets,
        },
        "metadata": metadata,
    }

    if exports:
        response["exports"] = exports

    if qa:
        word_count = len(re.findall(r"\b[\w'-]+\b", _strip_markdown_markup(markdown_body)))
        estimated_pages = max(1, (word_count + 399) // 400)
        response["qa_report"] = {
            "word_count": word_count,
            "estimated_pages": estimated_pages,
            "heading_count": stats.get("headings", 0),
            "citation_count": len(citation_links),
            "warnings_count": len(warnings),
            "toc_enabled": include_toc,
            "title_page_enabled": include_title_page,
            "has_images": stats.get("images", 0) > 0,
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    response["sections"] = [heading["text"] for heading in headings]
    return response


def pages_from_markdown(
    input_path: str,
    output_path: str = "",
    style: str = "auto",
    overwrite: bool = False,
    *,
    theme: str = "auto",
    title_page: str = "auto",
    toc: str = "auto",
    citations: str = "auto",
    images: str = "auto",
    image_max_width: int = 640,
    page_break_marker: str = PAGES_DEFAULT_PAGE_BREAK_MARKER,
    qa: bool = False,
    export: str = "none",
) -> dict[str, Any]:
    """Convert markdown to a styled Pages document with deterministic rendering."""
    from_stdin = input_path.strip() == "-"
    source_path: Path | None = None
    source_label = ""

    if from_stdin:
        markdown_text = sys.stdin.read()
        if not markdown_text.strip():
            return {"ok": False, "error": "stdin markdown input is empty"}
        source_label = "<stdin>"
    else:
        source_path = Path(input_path).expanduser()
        if not source_path.is_absolute():
            source_path = (Path.cwd() / source_path).resolve()
        if not source_path.exists():
            return {"ok": False, "error": f"input file not found: {source_path}"}
        if not source_path.is_file():
            return {"ok": False, "error": f"input path is not a file: {source_path}"}
        source_label = str(source_path)
        try:
            markdown_text = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": "input file must be UTF-8 text"}
        except OSError as exc:
            return {"ok": False, "error": f"failed to read input file: {exc}"}

    return _render_pages_markdown(
        markdown_text,
        source_label=source_label,
        source_path=source_path,
        output_path=output_path,
        style=style,
        theme=theme,
        title_page=title_page,
        toc=toc,
        citations=citations,
        images=images,
        image_max_width=image_max_width,
        page_break_marker=page_break_marker,
        qa=qa,
        export=export,
        overwrite=overwrite,
    )


def _split_markdown_sections(markdown_text: str) -> tuple[str, list[dict[str, str]]]:
    lines = markdown_text.splitlines(keepends=True)
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    heading_indices = [idx for idx, line in enumerate(lines) if heading_re.match(line.strip("\r\n"))]

    if not heading_indices:
        preamble = "".join(lines)
        return preamble, []

    preamble = "".join(lines[: heading_indices[0]])
    sections: list[dict[str, str]] = []
    for i, start_idx in enumerate(heading_indices):
        end_idx = heading_indices[i + 1] if i + 1 < len(heading_indices) else len(lines)
        block = "".join(lines[start_idx:end_idx]).rstrip() + "\n"
        heading_match = heading_re.match(lines[start_idx].strip("\r\n"))
        assert heading_match is not None
        title = _strip_markdown_markup(heading_match.group(2))
        sections.append(
            {
                "key": _normalize_heading_key(title),
                "title": title,
                "block": block,
            }
        )
    return preamble, sections


def _merge_markdown_sections(
    base_markdown: str,
    updates_markdown: str,
    requested_sections: list[str] | None,
) -> tuple[str, dict[str, Any]]:
    base_preamble, base_sections = _split_markdown_sections(base_markdown)
    _, update_sections = _split_markdown_sections(updates_markdown)
    merge_warnings: list[str] = []

    update_lookup: dict[str, dict[str, str]] = {}
    update_order: list[str] = []
    for section in update_sections:
        key = section["key"]
        if key in update_lookup:
            merge_warnings.append(f"duplicate section in updates ignored: {section['title']}")
            continue
        update_lookup[key] = section
        update_order.append(key)

    if requested_sections:
        requested_lookup = {_normalize_heading_key(name): name for name in requested_sections if name.strip()}
        selected_keys = [key for key in update_order if key in requested_lookup]
        for key, original in requested_lookup.items():
            if key not in update_lookup:
                merge_warnings.append(f"requested section not found in updates: {original}")
    else:
        selected_keys = list(update_order)

    selected_key_set = set(selected_keys)
    applied_keys: list[str] = []
    merged_blocks: list[str] = []

    for section in base_sections:
        key = section["key"]
        if key in selected_key_set and key in update_lookup:
            merged_blocks.append(update_lookup[key]["block"].rstrip())
            applied_keys.append(key)
        else:
            merged_blocks.append(section["block"].rstrip())

    appended_keys = [key for key in selected_keys if key not in applied_keys]
    for key in appended_keys:
        merged_blocks.append(update_lookup[key]["block"].rstrip())

    if not base_sections and selected_keys:
        merged_blocks = [update_lookup[key]["block"].rstrip() for key in selected_keys]

    merged_parts: list[str] = []
    if base_preamble.strip():
        merged_parts.append(base_preamble.rstrip())
    merged_parts.extend(block for block in merged_blocks if block.strip())
    merged_markdown = "\n\n".join(merged_parts).strip()
    if merged_markdown:
        merged_markdown += "\n"

    key_to_title = {section["key"]: section["title"] for section in update_sections}
    return merged_markdown, {
        "requested_sections": requested_sections or [],
        "applied_sections": [key_to_title.get(key, key) for key in applied_keys],
        "appended_sections": [key_to_title.get(key, key) for key in appended_keys],
        "warnings": merge_warnings,
    }


def pages_update_sections(
    base_input_path: str,
    updates_path: str,
    output_path: str,
    *,
    sections: list[str] | str | None = None,
    style: str = "auto",
    theme: str = "auto",
    title_page: str = "auto",
    toc: str = "auto",
    citations: str = "auto",
    images: str = "auto",
    image_max_width: int = 640,
    page_break_marker: str = PAGES_DEFAULT_PAGE_BREAK_MARKER,
    qa: bool = False,
    export: str = "none",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Merge selected markdown sections and render the result to a Pages document."""
    if not output_path:
        return {"ok": False, "error": "output path is required"}

    base_source: Path | None = None
    base_from_stdin = base_input_path.strip() == "-"
    if base_from_stdin:
        base_markdown = sys.stdin.read()
        if not base_markdown.strip():
            return {"ok": False, "error": "stdin markdown input is empty"}
        base_label = "<stdin>"
    else:
        base_source = Path(base_input_path).expanduser()
        if not base_source.is_absolute():
            base_source = (Path.cwd() / base_source).resolve()
        if not base_source.exists():
            return {"ok": False, "error": f"base file not found: {base_source}"}
        if not base_source.is_file():
            return {"ok": False, "error": f"base input path is not a file: {base_source}"}
        try:
            base_markdown = base_source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": "base input file must be UTF-8 text"}
        except OSError as exc:
            return {"ok": False, "error": f"failed to read base input file: {exc}"}
        base_label = str(base_source)

    updates_source = Path(updates_path).expanduser()
    if not updates_source.is_absolute():
        updates_source = (Path.cwd() / updates_source).resolve()
    if not updates_source.exists():
        return {"ok": False, "error": f"updates file not found: {updates_source}"}
    if not updates_source.is_file():
        return {"ok": False, "error": f"updates path is not a file: {updates_source}"}
    try:
        updates_markdown = updates_source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "updates file must be UTF-8 text"}
    except OSError as exc:
        return {"ok": False, "error": f"failed to read updates file: {exc}"}

    base_markdown = _absolutize_markdown_image_links(
        base_markdown,
        base_source.parent if base_source else None,
    )
    updates_markdown = _absolutize_markdown_image_links(updates_markdown, updates_source.parent)

    requested_sections: list[str] | None
    if isinstance(sections, str):
        requested_sections = [part.strip() for part in sections.split(",") if part.strip()] or None
    elif sections:
        requested_sections = [str(part).strip() for part in sections if str(part).strip()] or None
    else:
        requested_sections = None

    merged_markdown, merge_info = _merge_markdown_sections(
        base_markdown,
        updates_markdown,
        requested_sections=requested_sections,
    )
    if not merged_markdown.strip():
        return {"ok": False, "error": "merged markdown is empty after applying updates"}

    result = _render_pages_markdown(
        merged_markdown,
        source_label=f"{base_label} + {updates_source}",
        source_path=base_source or updates_source,
        output_path=output_path,
        style=style,
        theme=theme,
        title_page=title_page,
        toc=toc,
        citations=citations,
        images=images,
        image_max_width=image_max_width,
        page_break_marker=page_break_marker,
        qa=qa,
        export=export,
        overwrite=overwrite,
    )
    if result.get("ok"):
        result["merge"] = merge_info
        if merge_info["warnings"]:
            result.setdefault("warnings", []).extend(merge_info["warnings"])
    return result


def pages_template(
    template_type: str,
    output_path: str = "",
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a markdown starter template for Pages document generation."""
    normalized = template_type.strip().lower()
    templates = {
        "research": """---
title: Research Report
subtitle: Topic Overview
author: Your Name
date: 2026-03-04
---

# Executive Summary

Summarize the key findings in 3-5 bullets.

## Background

Describe the context and why this topic matters.

## Findings

1. Finding one
2. Finding two
3. Finding three

<!-- pagebreak -->

## Comparison Table

| Option | Strengths | Risks |
| --- | --- | --- |
| A | ... | ... |
| B | ... | ... |

## Recommendations

- Recommendation 1
- Recommendation 2

## Sources

- [Example Source](https://example.com)
""",
        "contract": """---
title: Service Agreement
subtitle: Draft
author: Your Company
date: 2026-03-04
client: Client Name
---

# Parties

This agreement is between [Provider] and [Client].

## Scope of Work

Describe deliverables, milestones, and acceptance criteria.

## Term and Termination

Define start date, term length, and termination rights.

## Fees and Payment

State pricing, invoice schedule, and late terms.

<!-- pagebreak -->

## Confidentiality

Define protected information and obligations.

## Intellectual Property

Define ownership of work product and licenses.

## Liability and Dispute Resolution

Define caps, exclusions, governing law, and venue.
""",
        "proposal": """---
title: Project Proposal
subtitle: Client Engagement
author: Your Name
date: 2026-03-04
client: Client Name
---

# Objective

State the business goal this proposal solves.

## Current Situation

Summarize the current workflow and constraints.

## Proposed Solution

Describe the recommended solution in clear phases.

## Timeline

| Phase | Duration | Output |
| --- | --- | --- |
| Discovery | 1 week | Scope + plan |
| Build | 3 weeks | Working deliverable |
| Launch | 1 week | Training + handoff |

<!-- pagebreak -->

## Budget

- Line item 1
- Line item 2

## Next Steps

1. Approve scope
2. Confirm timeline
3. Kickoff meeting
""",
    }

    if normalized not in templates:
        supported = ", ".join(sorted(templates.keys()))
        return {"ok": False, "error": f"unsupported template type '{template_type}'. supported: {supported}"}

    if output_path:
        destination = Path(output_path).expanduser()
        if not destination.is_absolute():
            destination = (Path.cwd() / destination).resolve()
    else:
        destination = (Path.cwd() / f"{normalized}-template.md").resolve()

    if destination.suffix.lower() != ".md":
        return {"ok": False, "error": "template output must use .md extension"}
    if destination.exists() and not overwrite:
        return {"ok": False, "error": f"template output exists and overwrite=false: {destination}"}

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(templates[normalized], encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"failed to write template: {exc}"}

    return {
        "ok": True,
        "template_type": normalized,
        "output_path": str(destination),
    }


# ---------------------------------------------------------------------------
# Apple Numbers
# ---------------------------------------------------------------------------

def numbers_create(
    file_path: str,
    headers: list[str],
    sheet_name: str = "",
    table_name: str = "",
    overwrite: bool = False,
) -> str | None:
    """Create a Numbers document and initialize header row."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        logger.warning("numbers_create requires an absolute path: %s", file_path)
        return None
    if path.suffix.lower() != ".numbers":
        logger.warning("numbers_create requires a .numbers path: %s", file_path)
        return None
    if path.exists() and not overwrite:
        logger.warning("numbers_create target exists and overwrite=false: %s", file_path)
        return None
    if not headers:
        logger.warning("numbers_create requires at least one header")
        return None

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    esc_path = _esc(str(path))
    esc_sheet = _esc(sheet_name)
    esc_table = _esc(table_name)

    header_lines: list[str] = []
    for idx, header in enumerate(headers, start=1):
        header_lines.append(f'set value of cell {idx} of row 1 to "{_esc(str(header))}"')
    headers_block = "\n            ".join(header_lines)

    sheet_name_setter = (
        f'set name of first sheet of newDoc to "{esc_sheet}"'
        if sheet_name
        else ""
    )
    table_name_setter = (
        f'set name of first table of first sheet of newDoc to "{esc_table}"'
        if table_name
        else ""
    )
    numbers_app = _numbers_app_target()

    script = f'''
    tell {numbers_app}
        try
            activate
            set newDoc to make new document
            save newDoc in POSIX file "{esc_path}"
            {sheet_name_setter}
            {table_name_setter}
            set targetTable to first table of first sheet of newDoc
            tell targetTable
                set totalCols to count of columns
                set requiredCols to {len(headers)}
                repeat while totalCols < requiredCols
                    make new column at end of columns
                    set totalCols to totalCols + 1
                end repeat
                {headers_block}
            end tell
            save newDoc
            close newDoc saving yes
            return "{esc_path}"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=60.0)
    if not result or result.startswith("error:"):
        logger.warning("numbers_create failed: %s", result)
        return None
    return result


def _normalize_numbers_rows_payload(rows: Any) -> list[list[Any]] | None:
    if rows is None:
        return []
    if not isinstance(rows, list):
        return None
    normalized_rows: list[list[Any]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            normalized_rows.append(list(row))
        else:
            normalized_rows.append([row])
    return normalized_rows


def _validate_numbers_sheet_spec(sheet_spec: Any) -> tuple[dict[str, Any], str | None]:
    if not isinstance(sheet_spec, dict):
        return {}, "sheet spec must be a JSON object"

    sheet_name = str(sheet_spec.get("sheet_name", "")).strip()
    if not sheet_name:
        return {}, "sheet_name is required"

    headers_raw = sheet_spec.get("headers")
    if not isinstance(headers_raw, list) or not headers_raw:
        return {}, "headers must be a non-empty JSON array"
    headers = [str(header) for header in headers_raw if str(header).strip()]
    if len(headers) != len(headers_raw):
        return {}, "headers must not contain empty values"

    table_name = str(sheet_spec.get("table_name", "")).strip()
    rows = _normalize_numbers_rows_payload(sheet_spec.get("rows"))
    if rows is None:
        return {}, "rows must be a JSON array when provided"

    return {
        "sheet_name": sheet_name,
        "table_name": table_name,
        "headers": headers,
        "rows": rows,
    }, None


def numbers_add_sheet(file_path: str, sheet_spec: dict[str, Any]) -> dict[str, Any]:
    """Add one initialized sheet to an existing Numbers workbook."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        return {"ok": False, "error": "absolute path required"}
    if path.suffix.lower() != ".numbers":
        return {"ok": False, "error": ".numbers path required"}
    if not path.exists():
        return {"ok": False, "error": "target document does not exist"}

    normalized_spec, spec_error = _validate_numbers_sheet_spec(sheet_spec)
    if spec_error:
        return {"ok": False, "error": spec_error}

    sheet_name = normalized_spec["sheet_name"]
    table_name = normalized_spec["table_name"]
    headers = normalized_spec["headers"]
    rows = normalized_spec["rows"]
    required_cols = max(1, max(len(headers), max((len(row) for row in rows), default=0)))

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    esc_path = _esc(str(path))
    esc_sheet = _esc(sheet_name)
    esc_table = _esc(table_name)

    header_lines: list[str] = []
    for idx, header in enumerate(headers, start=1):
        header_lines.append(f'set value of cell {idx} of row 1 to "{_esc(str(header))}"')
    headers_block = "\n                    ".join(header_lines)

    row_lines: list[str] = []
    for row in rows:
        row_lines.extend(
            [
                "if insertionRow <= totalRows then",
                "set targetRow to row insertionRow",
                "else",
                "set targetRow to make new row at end of rows",
                "set totalRows to totalRows + 1",
                "end if",
            ]
        )
        for idx, value in enumerate(row, start=1):
            if value is None:
                row_lines.append(f"set value of cell {idx} of targetRow to \"\"")
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                row_lines.append(f"set value of cell {idx} of targetRow to {value}")
            else:
                row_lines.append(f'set value of cell {idx} of targetRow to "{_esc(str(value))}"')
        row_lines.append("set insertionRow to insertionRow + 1")
    rows_block = "\n                    ".join(row_lines) if row_lines else ""

    table_name_setter = f'set name of targetTable to "{esc_table}"' if table_name else ""
    rows_section = rows_block if rows_block else "-- no initial rows"
    numbers_app = _numbers_app_target()

    script = f'''
    tell {numbers_app}
        try
            activate
            set targetDoc to open POSIX file "{esc_path}"
            tell targetDoc
                set existingSheet to missing value
                try
                    set existingSheet to first sheet whose name is "{esc_sheet}"
                end try
                if existingSheet is not missing value then
                    close targetDoc saving no
                    return "error: sheet already exists"
                end if

                set newSheet to make new sheet at end of sheets
                set name of newSheet to "{esc_sheet}"
                tell newSheet
                    set targetTable to first table
                    {table_name_setter}
                    tell targetTable
                        set totalCols to count of columns
                        set requiredCols to {required_cols}
                        repeat while totalCols < requiredCols
                            make new column at end of columns
                            set totalCols to totalCols + 1
                        end repeat
                        set totalRows to count of rows
                        set insertionRow to 2
                        {headers_block}
                        {rows_section}
                    end tell
                end tell
            end tell
            save targetDoc
            close targetDoc saving yes
            return "ok|{len(rows)}"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=90.0)
    if not result:
        return {"ok": False, "error": "no response from Numbers"}
    if result.startswith("error:"):
        return {"ok": False, "error": result}

    rows_inserted = len(rows)
    parts = result.split("|")
    if len(parts) >= 2:
        try:
            rows_inserted = int(parts[1])
        except ValueError:
            pass
    return {
        "ok": True,
        "sheet_name": sheet_name,
        "table_name": table_name or "Table 1",
        "rows_inserted": rows_inserted,
    }


def numbers_create_workbook(
    file_path: str,
    workbook_spec: dict[str, Any],
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a multi-sheet workbook from a workbook spec."""
    if not isinstance(workbook_spec, dict):
        return {"ok": False, "error": "workbook_json must be a JSON object"}
    sheets_raw = workbook_spec.get("sheets")
    if not isinstance(sheets_raw, list) or not sheets_raw:
        return {"ok": False, "error": "workbook_json.sheets must be a non-empty JSON array"}

    normalized_sheets: list[dict[str, Any]] = []
    seen_sheet_names: set[str] = set()
    for sheet_spec in sheets_raw:
        normalized_spec, spec_error = _validate_numbers_sheet_spec(sheet_spec)
        if spec_error:
            return {"ok": False, "error": spec_error}
        sheet_key = normalized_spec["sheet_name"].strip().lower()
        if sheet_key in seen_sheet_names:
            return {"ok": False, "error": f'duplicate sheet_name: "{normalized_spec["sheet_name"]}"'}
        seen_sheet_names.add(sheet_key)
        normalized_sheets.append(normalized_spec)

    first_sheet = normalized_sheets[0]
    created = numbers_create(
        file_path,
        headers=first_sheet["headers"],
        sheet_name=first_sheet["sheet_name"],
        table_name=first_sheet["table_name"],
        overwrite=overwrite,
    )
    if not created:
        return {"ok": False, "error": "failed to create workbook"}

    rows_inserted_total = 0
    first_rows = first_sheet["rows"]
    if first_rows:
        first_insert = numbers_append_rows(
            file_path,
            rows=first_rows,
            sheet_name=first_sheet["sheet_name"],
            table_name=first_sheet["table_name"],
            insert_position="after-data",
        )
        if not first_insert.get("ok"):
            return {"ok": False, "error": str(first_insert.get("error", "failed to insert initial rows"))}
        rows_inserted_total += int(first_insert.get("inserted_rows", len(first_rows)))

    for sheet_spec in normalized_sheets[1:]:
        add_result = numbers_add_sheet(file_path, sheet_spec)
        if not add_result.get("ok"):
            return {
                "ok": False,
                "error": str(add_result.get("error", "failed to add sheet")),
                "sheets_created": len(normalized_sheets[: normalized_sheets.index(sheet_spec)]),
            }
        rows_inserted_total += int(add_result.get("rows_inserted", len(sheet_spec["rows"])))

    return {
        "ok": True,
        "path": str(Path(file_path).expanduser()),
        "sheets_created": len(normalized_sheets),
        "rows_inserted_total": rows_inserted_total,
    }


def numbers_append_rows(
    file_path: str,
    rows: list[list[Any]],
    sheet_name: str = "",
    table_name: str = "",
    insert_position: str = "after-data",
) -> dict[str, Any]:
    """Append one or more rows to a Numbers table."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        return {"ok": False, "error": "absolute path required"}
    if path.suffix.lower() != ".numbers":
        return {"ok": False, "error": ".numbers path required"}
    if not path.exists():
        return {"ok": False, "error": "target document does not exist"}
    if insert_position not in {"after-headers", "after-data", "at-end"}:
        return {"ok": False, "error": "invalid insert position"}
    if not rows:
        return {"ok": False, "error": "rows must not be empty"}

    normalized_rows: list[list[Any]] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            normalized_rows.append(list(row))
        else:
            normalized_rows.append([row])
    required_cols = max(1, max((len(row) for row in normalized_rows), default=1))

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    esc_path = _esc(str(path))
    esc_sheet = _esc(sheet_name)
    esc_table = _esc(table_name)
    esc_position = _esc(insert_position)

    if insert_position == "after-headers":
        target_row_block = '''if insertionRow <= totalRows then
                    set anchorRow to row insertionRow
                    set targetRow to make new row at before anchorRow
                else
                    set targetRow to make new row at end of rows
                end if
                set totalRows to totalRows + 1'''
    elif insert_position == "at-end":
        target_row_block = '''set targetRow to make new row at end of rows
                set totalRows to totalRows + 1'''
    else:
        target_row_block = '''if insertionRow > totalRows then
                    set targetRow to make new row at end of rows
                    set totalRows to totalRows + 1
                else
                    set targetRow to row insertionRow
                end if'''

    row_lines: list[str] = []
    for row in normalized_rows:
        row_lines.append(target_row_block)
        for idx, value in enumerate(row, start=1):
            if value is None:
                row_lines.append(f"set value of cell {idx} of targetRow to \"\"")
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                row_lines.append(f"set value of cell {idx} of targetRow to {value}")
            else:
                row_lines.append(f'set value of cell {idx} of targetRow to "{_esc(str(value))}"')
        row_lines.append("set insertionRow to insertionRow + 1")
    rows_block = "\n                ".join(row_lines)

    sheet_lookup = (
        f'set targetSheet to (first sheet of targetDoc whose name is "{esc_sheet}")'
        if sheet_name
        else "set targetSheet to first sheet of targetDoc"
    )
    table_lookup = (
        f'set targetTable to (first table of targetSheet whose name is "{esc_table}")'
        if table_name
        else "set targetTable to first table of targetSheet"
    )
    numbers_app = _numbers_app_target()

    script = f'''
    tell {numbers_app}
        try
            activate
            set targetDoc to open POSIX file "{esc_path}"
            {sheet_lookup}
            {table_lookup}

            tell targetTable
                set totalRows to count of rows
                set totalCols to count of columns
                set requiredCols to {required_cols}
                repeat while totalCols < requiredCols
                    make new column at end of columns
                    set totalCols to totalCols + 1
                end repeat
                set scanCols to totalCols
                if scanCols < 1 then set scanCols to 1
                set headerRows to 1
                try
                    set headerRows to header row count
                end try
                if headerRows < 1 then set headerRows to 1
                set dataStartRow to headerRows + 1

                if "{esc_position}" is "after-headers" then
                    set insertionRow to dataStartRow
                else if "{esc_position}" is "at-end" then
                    set insertionRow to totalRows + 1
                else
                    set lastDataRow to headerRows
                    if totalRows >= dataStartRow then
                        repeat with r from dataStartRow to totalRows
                            set rowHasData to false
                            repeat with c from 1 to scanCols
                                set cellVal to missing value
                                try
                                    set cellVal to value of cell c of row r
                                on error
                                    set cellVal to missing value
                                end try
                                if cellVal is not missing value then
                                    try
                                        if (cellVal as text) is not "" then
                                            set rowHasData to true
                                            exit repeat
                                        end if
                                    on error
                                        set rowHasData to true
                                        exit repeat
                                    end try
                                end if
                            end repeat
                            if rowHasData then set lastDataRow to r
                        end repeat
                    end if
                    set insertionRow to lastDataRow + 1
                end if

                set startRow to insertionRow
                {rows_block}
            end tell

            save targetDoc
            close targetDoc saving yes
            return "ok|" & startRow & "|" & (insertionRow - 1)
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=60.0)
    if not result:
        return {"ok": False, "error": "no response from Numbers"}
    if result.startswith("error:"):
        return {"ok": False, "error": result}

    parts = result.split("|")
    start_row = -1
    insert_after_row = -1
    if len(parts) >= 3:
        try:
            start_row = int(parts[1])
            insert_after_row = int(parts[2])
        except ValueError:
            pass
    return {
        "ok": True,
        "insert_position": insert_position,
        "attempted_rows": len(normalized_rows),
        "inserted_rows": len(normalized_rows),
        "start_row": start_row,
        "insert_after_row": insert_after_row,
    }


def _normalize_numbers_color_triplet(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    channels: list[float] = []
    for channel in value:
        if isinstance(channel, bool):
            return None
        try:
            numeric = float(channel)
        except (TypeError, ValueError):
            return None
        if numeric < 0:
            return None
        channels.append(numeric)
    if all(channel <= 255 for channel in channels):
        return tuple(int(round(channel * 257)) for channel in channels)
    if all(channel <= 65535 for channel in channels):
        return tuple(int(round(channel)) for channel in channels)
    return None


def _validate_numbers_style_target(target: Any) -> tuple[dict[str, int | str], str | None]:
    if not isinstance(target, dict):
        return {}, "target_json must be a JSON object"
    scope = str(target.get("scope", "")).strip().lower()
    if scope not in {"table", "row", "column", "cell", "range"}:
        return {}, "target_json.scope must be one of: table|row|column|cell|range"

    def _positive_int(key: str) -> tuple[int | None, str | None]:
        value = target.get(key)
        if isinstance(value, bool):
            return None, f"target_json.{key} must be a positive integer"
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            return None, f"target_json.{key} must be a positive integer"
        if int_value < 1:
            return None, f"target_json.{key} must be >= 1"
        return int_value, None

    normalized: dict[str, int | str] = {"scope": scope}
    if scope == "table":
        return normalized, None
    if scope == "row":
        index, err = _positive_int("index")
        if err:
            return {}, err
        normalized["index"] = int(index)
        return normalized, None
    if scope == "column":
        index, err = _positive_int("index")
        if err:
            return {}, err
        normalized["index"] = int(index)
        return normalized, None
    if scope == "cell":
        row, err = _positive_int("row")
        if err:
            return {}, err
        col, err = _positive_int("column")
        if err:
            return {}, err
        normalized["row"] = int(row)
        normalized["column"] = int(col)
        return normalized, None

    start_row, err = _positive_int("start_row")
    if err:
        return {}, err
    end_row, err = _positive_int("end_row")
    if err:
        return {}, err
    start_col, err = _positive_int("start_column")
    if err:
        return {}, err
    end_col, err = _positive_int("end_column")
    if err:
        return {}, err
    if int(start_row) > int(end_row):
        return {}, "target_json start_row must be <= end_row"
    if int(start_col) > int(end_col):
        return {}, "target_json start_column must be <= end_column"
    normalized["start_row"] = int(start_row)
    normalized["end_row"] = int(end_row)
    normalized["start_column"] = int(start_col)
    normalized["end_column"] = int(end_col)
    return normalized, None


def _validate_numbers_style(style: Any, target_scope: str) -> tuple[dict[str, Any], str | None]:
    if not isinstance(style, dict):
        return {}, "style_json must be a JSON object"
    if not style:
        return {}, "style_json must not be empty"

    allowed_keys = {
        "background_color",
        "text_color",
        "font_name",
        "font_size",
        "alignment",
        "number_format",
        "text_wrap",
        "row_height",
        "column_width",
    }
    unknown = sorted(set(style.keys()) - allowed_keys)
    if unknown:
        return {}, f"unsupported style key(s): {', '.join(unknown)}"

    normalized: dict[str, Any] = {}
    for color_key in ("background_color", "text_color"):
        if color_key in style:
            color = _normalize_numbers_color_triplet(style[color_key])
            if color is None:
                return {}, f"style_json.{color_key} must be [r,g,b] with values in 0-255 or 0-65535"
            normalized[color_key] = color

    if "font_name" in style:
        font_name = str(style["font_name"]).strip()
        if not font_name:
            return {}, "style_json.font_name must be a non-empty string"
        normalized["font_name"] = font_name

    for numeric_key in ("font_size", "row_height", "column_width"):
        if numeric_key not in style:
            continue
        value = style[numeric_key]
        if isinstance(value, bool):
            return {}, f"style_json.{numeric_key} must be a positive number"
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return {}, f"style_json.{numeric_key} must be a positive number"
        if numeric <= 0:
            return {}, f"style_json.{numeric_key} must be > 0"
        normalized[numeric_key] = numeric

    if "alignment" in style:
        alignment = str(style["alignment"]).strip().lower()
        if alignment not in {"left", "center", "right", "justified", "natural"}:
            return {}, "style_json.alignment must be one of: left|center|right|justified|natural"
        normalized["alignment"] = alignment

    if "number_format" in style:
        number_format = str(style["number_format"]).strip().lower()
        if number_format not in {"automatic", "currency", "percentage", "scientific", "fraction", "text"}:
            return {}, "style_json.number_format must be one of: automatic|currency|percentage|scientific|fraction|text"
        normalized["number_format"] = number_format

    if "text_wrap" in style:
        text_wrap = style["text_wrap"]
        if not isinstance(text_wrap, bool):
            return {}, "style_json.text_wrap must be true or false"
        normalized["text_wrap"] = text_wrap

    if target_scope == "row" and "column_width" in normalized:
        return {}, "column_width is not supported for row target scope"
    if target_scope == "column" and "row_height" in normalized:
        return {}, "row_height is not supported for column target scope"

    return normalized, None


def numbers_style_apply(
    file_path: str,
    target: dict[str, Any],
    style: dict[str, Any],
    sheet_name: str = "",
    table_name: str = "",
) -> dict[str, Any]:
    """Apply formatting/style to a Numbers target scope."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        return {"ok": False, "error": "absolute path required"}
    if path.suffix.lower() != ".numbers":
        return {"ok": False, "error": ".numbers path required"}
    if not path.exists():
        return {"ok": False, "error": "target document does not exist"}

    normalized_target, target_error = _validate_numbers_style_target(target)
    if target_error:
        return {"ok": False, "error": target_error}

    target_scope = str(normalized_target["scope"])
    normalized_style, style_error = _validate_numbers_style(style, target_scope=target_scope)
    if style_error:
        return {"ok": False, "error": style_error}

    cell_style_keys = {
        "background_color",
        "text_color",
        "font_name",
        "font_size",
        "alignment",
        "number_format",
        "text_wrap",
    }
    has_cell_styles = any(key in normalized_style for key in cell_style_keys)

    def _esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    def _num_literal(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    cell_style_lines: list[str] = []
    if "background_color" in normalized_style:
        r, g, b = normalized_style["background_color"]
        cell_style_lines.append(f"set background color of cellRef to {{{r}, {g}, {b}}}")
    if "text_color" in normalized_style:
        r, g, b = normalized_style["text_color"]
        cell_style_lines.append(f"set text color of cellRef to {{{r}, {g}, {b}}}")
    if "font_name" in normalized_style:
        cell_style_lines.append(f'set font name of cellRef to "{_esc(normalized_style["font_name"])}"')
    if "font_size" in normalized_style:
        cell_style_lines.append(f"set font size of cellRef to {_num_literal(normalized_style['font_size'])}")
    if "alignment" in normalized_style:
        cell_style_lines.append(f"set alignment of cellRef to {normalized_style['alignment']}")
    if "number_format" in normalized_style:
        cell_style_lines.append(f"set format of cellRef to {normalized_style['number_format']}")
    if "text_wrap" in normalized_style:
        cell_style_lines.append(
            f"set text wrap of cellRef to {'true' if normalized_style['text_wrap'] else 'false'}"
        )
    cell_styles_block = "\n                        ".join(cell_style_lines)

    has_row_height = "row_height" in normalized_style
    has_column_width = "column_width" in normalized_style
    row_height_line = _num_literal(float(normalized_style["row_height"])) if has_row_height else ""
    column_width_line = _num_literal(float(normalized_style["column_width"])) if has_column_width else ""

    if target_scope == "table":
        table_row_height_block = ""
        if has_row_height:
            table_row_height_block = f'''
                repeat with r from 1 to totalRows
                    set height of row r to {row_height_line}
                end repeat
                set rowsResized to totalRows
            '''
        table_column_width_block = ""
        if has_column_width:
            table_column_width_block = f'''
                repeat with c from 1 to totalCols
                    set width of column c to {column_width_line}
                end repeat
                set columnsResized to totalCols
            '''
        scope_block = f'''
                if {str(has_cell_styles).lower()} then
                    repeat with r from 1 to totalRows
                        repeat with c from 1 to totalCols
                            set cellRef to cell c of row r
                            {cell_styles_block}
                        end repeat
                    end repeat
                    set cellsTouched to totalRows * totalCols
                end if
                {table_row_height_block}
                {table_column_width_block}
        '''
    elif target_scope == "row":
        row_index = int(normalized_target["index"])
        row_height_block = ""
        if has_row_height:
            row_height_block = f'''
                set height of row {row_index} to {row_height_line}
                set rowsResized to 1
            '''
        scope_block = f'''
                if {row_index} > totalRows then return "error: target row out of bounds"
                if {str(has_cell_styles).lower()} then
                    repeat with c from 1 to totalCols
                        set cellRef to cell c of row {row_index}
                        {cell_styles_block}
                    end repeat
                    set cellsTouched to totalCols
                end if
                {row_height_block}
        '''
    elif target_scope == "column":
        column_index = int(normalized_target["index"])
        column_width_block = ""
        if has_column_width:
            column_width_block = f'''
                set width of column {column_index} to {column_width_line}
                set columnsResized to 1
            '''
        scope_block = f'''
                if {column_index} > totalCols then return "error: target column out of bounds"
                if {str(has_cell_styles).lower()} then
                    repeat with r from 1 to totalRows
                        set cellRef to cell {column_index} of row r
                        {cell_styles_block}
                    end repeat
                    set cellsTouched to totalRows
                end if
                {column_width_block}
        '''
    elif target_scope == "cell":
        row_index = int(normalized_target["row"])
        column_index = int(normalized_target["column"])
        cell_row_height_block = ""
        if has_row_height:
            cell_row_height_block = f'''
                set height of row {row_index} to {row_height_line}
                set rowsResized to 1
            '''
        cell_column_width_block = ""
        if has_column_width:
            cell_column_width_block = f'''
                set width of column {column_index} to {column_width_line}
                set columnsResized to 1
            '''
        scope_block = f'''
                if {row_index} > totalRows then return "error: target row out of bounds"
                if {column_index} > totalCols then return "error: target column out of bounds"
                if {str(has_cell_styles).lower()} then
                    set cellRef to cell {column_index} of row {row_index}
                    {cell_styles_block}
                    set cellsTouched to 1
                end if
                {cell_row_height_block}
                {cell_column_width_block}
        '''
    else:
        start_row = int(normalized_target["start_row"])
        end_row = int(normalized_target["end_row"])
        start_column = int(normalized_target["start_column"])
        end_column = int(normalized_target["end_column"])
        range_row_height_block = ""
        if has_row_height:
            range_row_height_block = f'''
                repeat with r from {start_row} to {end_row}
                    set height of row r to {row_height_line}
                end repeat
                set rowsResized to rangeRowCount
            '''
        range_column_width_block = ""
        if has_column_width:
            range_column_width_block = f'''
                repeat with c from {start_column} to {end_column}
                    set width of column c to {column_width_line}
                end repeat
                set columnsResized to rangeColCount
            '''
        scope_block = f'''
                if {end_row} > totalRows then return "error: range row out of bounds"
                if {end_column} > totalCols then return "error: range column out of bounds"
                set rangeRowCount to ({end_row} - {start_row}) + 1
                set rangeColCount to ({end_column} - {start_column}) + 1
                if {str(has_cell_styles).lower()} then
                    repeat with r from {start_row} to {end_row}
                        repeat with c from {start_column} to {end_column}
                            set cellRef to cell c of row r
                            {cell_styles_block}
                        end repeat
                    end repeat
                    set cellsTouched to rangeRowCount * rangeColCount
                end if
                {range_row_height_block}
                {range_column_width_block}
        '''

    esc_path = _esc(str(path))
    esc_sheet = _esc(sheet_name)
    esc_table = _esc(table_name)
    sheet_lookup = (
        f'set targetSheet to (first sheet of targetDoc whose name is "{esc_sheet}")'
        if sheet_name
        else "set targetSheet to first sheet of targetDoc"
    )
    table_lookup = (
        f'set targetTable to (first table of targetSheet whose name is "{esc_table}")'
        if table_name
        else "set targetTable to first table of targetSheet"
    )
    numbers_app = _numbers_app_target()

    script = f'''
    tell {numbers_app}
        try
            activate
            set targetDoc to open POSIX file "{esc_path}"
            {sheet_lookup}
            {table_lookup}

            tell targetTable
                set totalRows to count of rows
                set totalCols to count of columns
                set cellsTouched to 0
                set rowsResized to 0
                set columnsResized to 0
                {scope_block}
            end tell

            save targetDoc
            close targetDoc saving yes
            return "ok|" & cellsTouched & "|" & rowsResized & "|" & columnsResized
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=90.0)
    if not result:
        return {"ok": False, "error": "no response from Numbers"}
    if result.startswith("error:"):
        return {"ok": False, "error": result}

    cells_touched = 0
    rows_resized = 0
    columns_resized = 0
    parts = result.split("|")
    if len(parts) >= 4:
        try:
            cells_touched = int(parts[1])
            rows_resized = int(parts[2])
            columns_resized = int(parts[3])
        except ValueError:
            pass

    return {
        "ok": True,
        "target_scope": target_scope,
        "applied_keys": list(normalized_style.keys()),
        "cells_touched": cells_touched,
        "rows_resized": rows_resized,
        "columns_resized": columns_resized,
    }


# ---------------------------------------------------------------------------
# TTS + Audio Messages
# ---------------------------------------------------------------------------

def _normalize_phone_number(raw: str) -> str | None:
    """Best-effort E.164-ish normalization for dial targets."""
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("tel:"):
        value = value[4:]
    if value.startswith("facetime-audio://"):
        value = value[len("facetime-audio://") :]
    if value.startswith("facetime://"):
        value = value[len("facetime://") :]

    value = value.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if value.startswith("+"):
        if not value[1:].isdigit():
            return None
        return value
    if not value.isdigit():
        return None
    return value


def _resolve_binary(command: str) -> str | None:
    candidate = (command or "").strip()
    if not candidate:
        return None
    if "/" in candidate:
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return str(path)
        return None
    return shutil.which(candidate)


def _run_command(
    command: list[str],
    *,
    timeout: float,
    input_text: str | None = None,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timed out", "stdout": "", "stderr": "timed out", "returncode": -1}
    except Exception as exc:  # pragma: no cover - runtime safety
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }

    return {
        "ok": result.returncode == 0,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
        "returncode": result.returncode,
    }


def _build_temp_audio_path(suffix: str) -> str:
    with tempfile.NamedTemporaryFile(prefix="apple-flow-tts-", suffix=suffix, delete=False) as tmp:
        path = tmp.name
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
    return path


def _synthesize_tts_to_audio_file(
    text: str,
    *,
    voice: str,
    rate: float,
    tts_engine: str,
    piper_command: str,
    piper_model_path: str,
) -> dict[str, Any]:
    payload = (text or "").strip()
    if not payload:
        return {"ok": False, "error": "text is required"}

    engine = (tts_engine or "auto").strip().lower()
    if engine not in {"auto", "say", "piper"}:
        return {"ok": False, "error": "tts_engine must be one of: auto, say, piper"}

    errors: list[str] = []
    timeout = max(20.0, min(180.0, 12.0 + (len(payload) / 7.0)))

    if engine in {"auto", "piper"}:
        piper_binary = _resolve_binary(piper_command)
        if not piper_binary:
            errors.append("piper binary not found")
        else:
            model_value = (piper_model_path or "").strip()
            if not model_value:
                errors.append("piper model path is required for piper TTS")
            else:
                model_path = Path(model_value).expanduser()
                if not model_path.exists():
                    errors.append(f"piper model not found: {model_path}")
                else:
                    audio_path = _build_temp_audio_path(".wav")
                    piper_result = _run_command(
                        [piper_binary, "--model", str(model_path), "--output_file", audio_path],
                        timeout=timeout,
                        input_text=payload,
                    )
                    if piper_result["ok"] and Path(audio_path).exists() and Path(audio_path).stat().st_size > 0:
                        return {"ok": True, "engine": "piper", "path": audio_path}
                    errors.append(
                        f"piper failed: {piper_result.get('stderr') or piper_result.get('error') or 'unknown error'}"
                    )
                    try:
                        Path(audio_path).unlink(missing_ok=True)
                    except Exception:
                        pass
        if engine == "piper":
            return {"ok": False, "error": " ; ".join(errors) if errors else "piper synthesis failed"}

    say_binary = _resolve_binary("say")
    if not say_binary:
        errors.append("say command not found")
        return {"ok": False, "error": " ; ".join(errors) if errors else "speech synthesis failed"}

    audio_path = _build_temp_audio_path(".aiff")
    say_command = [say_binary, "-o", audio_path, "-r", str(int(rate))]
    if voice:
        say_command.extend(["-v", voice])
    say_command.append(payload)
    say_result = _run_command(say_command, timeout=timeout)
    if say_result["ok"] and Path(audio_path).exists() and Path(audio_path).stat().st_size > 0:
        return {"ok": True, "engine": "say", "path": audio_path}

    errors.append(f"say failed: {say_result.get('stderr') or say_result.get('error') or 'unknown error'}")
    try:
        Path(audio_path).unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": False, "error": " ; ".join(errors) if errors else "speech synthesis failed"}


def messages_send_voice(
    text: str,
    recipient: str,
    voice: str = "",
    rate: float = 180.0,
    tts_engine: str = "auto",
    piper_command: str = "piper",
    piper_model_path: str = "",
) -> dict[str, Any]:
    """Send a synthesized voice message as an iMessage attachment."""
    payload = (text or "").strip()
    if not payload:
        return {"ok": False, "error": "text is required"}

    normalized = _normalize_phone_number(recipient)
    if not normalized:
        return {"ok": False, "error": "invalid recipient phone number", "stage": "validation"}

    logger.info("Creating voice message for %s (%d chars)", normalized, len(payload))

    synth = _synthesize_tts_to_audio_file(
        payload,
        voice=voice,
        rate=rate,
        tts_engine=tts_engine,
        piper_command=piper_command,
        piper_model_path=piper_model_path,
    )

    if not synth.get("ok"):
        return {
            "ok": False,
            "error": synth.get("error", "TTS synthesis failed"),
            "stage": "synthesis",
        }

    audio_path = synth.get("path", "")
    if not audio_path:
        return {"ok": False, "error": "no audio path returned", "stage": "synthesis"}

    logger.info("Sending iMessage voice attachment: %s", audio_path)
    try:
        send_result = _send_imessage_attachment(normalized, audio_path)
    finally:
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            logger.debug("Could not clean up temp audio file: %s", audio_path)

    if not send_result.get("ok"):
        return {
            "ok": False,
            "error": send_result.get("error", "failed to send iMessage"),
            "stage": "send",
        }

    return {
        "ok": True,
        "recipient": normalized,
        "text_length": len(payload),
        "tts_engine": synth.get("engine"),
    }


def _send_imessage_attachment(recipient: str, file_path: str) -> dict[str, Any]:
    """Send an iMessage with a file attachment to a recipient."""
    normalized = _normalize_phone_number(recipient)
    if not normalized:
        return {"ok": False, "error": "invalid phone number"}

    path = Path(file_path).expanduser()
    if not path.exists():
        return {"ok": False, "error": "file not found"}

    if not path.is_file():
        return {"ok": False, "error": "not a file"}

    esc_number = normalized
    esc_path = str(path).replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{esc_number}" of targetService
        set audioFile to POSIX file "{esc_path}"
        send audioFile to targetBuddy
    end tell
    '''

    try:
        result = _run_command(["osascript", "-e", script], timeout=60.0)
        if result["ok"]:
            return {"ok": True}
        return {"ok": False, "error": result.get("stderr") or result.get("error") or "AppleScript failed"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Apple Mail
# ---------------------------------------------------------------------------

def _mail_fetch_raw(
    account: str = "",
    mailbox: str = "INBOX",
    limit: int = 50,
    max_age_days: int = 30,
    unread_only: bool = False,
) -> list[dict]:
    """Internal: fetch mail messages via AppleScript."""
    if account:
        esc_account = account.replace('"', '\\"')
        esc_mailbox = mailbox.replace('"', '\\"')
        mailbox_ref = f'mailbox "{esc_mailbox}" of account "{esc_account}"'
    else:
        mailbox_ref = "inbox"

    read_clause = "whose read status is false" if unread_only else ""

    script = f'''
    on sanitise(txt)
        set AppleScript's text item delimiters to character id 9
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 10
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 13
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to ""
        return txt
    end sanitise

    tell application "Mail"
        set maxCount to {int(limit)}
        set maxAgeDays to {int(max_age_days)}
        set cutoffDate to (current date) - (maxAgeDays * days)
        set outputLines to {{}}

        set allMessages to (every message of {mailbox_ref} {read_clause})

        repeat with msg in allMessages
            if (count of outputLines) >= maxCount then exit repeat
            set msgDate to date received of msg
            if msgDate < cutoffDate then
            else
                set msgId to my sanitise(id of msg as text)
                set msgSender to my sanitise(sender of msg as text)
                set msgSubject to my sanitise(subject of msg as text)
                try
                    set msgBody to content of msg as text
                    if length of msgBody > 500 then set msgBody to text 1 thru 500 of msgBody
                    set msgBody to my sanitise(msgBody)
                on error
                    set msgBody to ""
                end try
                try
                    set msgDateStr to my sanitise(date received of msg as text)
                on error
                    set msgDateStr to ""
                end try
                set msgRead to read status of msg
                set msgReadStr to "false"
                if msgRead then set msgReadStr to "true"

                set end of outputLines to msgId & character id 9 & msgSender & character id 9 & msgSubject & character id 9 & msgBody & character id 9 & msgDateStr & character id 9 & msgReadStr
            end if
        end repeat

        set AppleScript's text item delimiters to character id 10
        return (outputLines as text)
    end tell
    '''
    return _parse_delimited_output(_run_script(script, timeout=60.0), ["id", "sender", "subject", "body_preview", "date", "read"])


def mail_list_unread(
    account: str = "",
    mailbox: str = "INBOX",
    limit: int = 20,
    as_text: bool = False,
) -> list | str:
    """List unread emails with id, sender, subject, body_preview, date, read.

    Args:
        account: Mail.app account name (empty = default inbox)
        mailbox: Mailbox name (default: INBOX)
        limit: Maximum messages to return
        as_text: Return human-readable string

    Returns:
        List of message dicts or formatted string
    """
    data = _mail_fetch_raw(account=account, mailbox=mailbox, limit=limit, unread_only=True)
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('sender', '')}  |  {x.get('subject', '')}  [{x.get('date', '')}]",
    )


def mail_search(
    query: str,
    account: str = "",
    mailbox: str = "INBOX",
    limit: int = 20,
    max_age_days: int = 30,
    as_text: bool = False,
) -> list | str:
    """Search emails by sender, subject, or body preview (Python-side filter).

    Fetches a bounded recent window then filters in Python.
    """
    fetch_limit = min(200, max(limit * 5, limit))
    all_msgs = _mail_fetch_raw(account=account, mailbox=mailbox, limit=fetch_limit, max_age_days=max_age_days)
    q = query.lower()
    matches = [
        m for m in all_msgs
        if q in (m.get("sender") or "").lower()
        or q in (m.get("subject") or "").lower()
        or q in (m.get("body_preview") or "").lower()
    ][:limit]
    return _format_output(
        matches,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('sender', '')}  |  {x.get('subject', '')}  [{x.get('date', '')}]",
    )


def mail_get_content(message_id: str, account: str = "", mailbox: str = "INBOX") -> str:
    """Return the full body of a specific email by ID, or '' if not found."""
    esc_id = message_id.replace('"', '\\"')
    id_match = f"id is {int(message_id)}" if message_id.isdigit() else f'id as text is "{esc_id}"'
    if account:
        esc_account = account.replace('"', '\\"')
        esc_mailbox = mailbox.replace('"', '\\"')
        mailbox_ref = f'mailbox "{esc_mailbox}" of account "{esc_account}"'
    else:
        mailbox_ref = "inbox"

    script = f'''
    tell application "Mail"
        try
            set matchedMsg to first message of {mailbox_ref} whose {id_match}
            return content of matchedMsg as text
        on error
            return ""
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    return result or ""


def mail_send(to_address: str, subject: str, body: str, account: str = "") -> bool:
    """Send an email via Apple Mail. Returns True on success."""
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    esc_to = _esc(to_address)
    esc_subject = _esc(subject)
    esc_body = _esc(body)

    if account:
        esc_account = _esc(account)
        account_clause = f'set sender of newMsg to "{esc_account}"'
    else:
        account_clause = ""

    script = f'''
    tell application "Mail"
        try
            set newMsg to make new outgoing message with properties {{subject:"{esc_subject}", content:"{esc_body}", visible:false}}
            {account_clause}
            tell newMsg
                make new to recipient with properties {{address:"{esc_to}"}}
            end tell
            send newMsg
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if result == "ok":
        return True
    logger.warning("mail_send failed: %s", result)
    return False


def _mail_is_system_mailbox(name: str) -> bool:
    """Return True when mailbox name appears to be a system mailbox."""
    normalized = _normalize_text_key(name)
    canonical = {
        "inbox",
        "sent",
        "sent messages",
        "sent mail",
        "drafts",
        "trash",
        "deleted messages",
        "junk",
        "junk e-mail",
        "spam",
        "archive",
        "all mail",
        "important",
        "starred",
        "outbox",
    }
    return normalized in canonical


def mail_list_mailboxes(
    account: str = "",
    include_system: bool = False,
    as_text: bool = False,
) -> list | str:
    """List mailboxes for an account or default Mail context."""

    if account:
        esc_account = account.replace('"', '\\"')
        fetch_block = f'''
            try
                set targetAccounts to {{account "{esc_account}"}}
            on error
                return ""
            end try
        '''
    else:
        fetch_block = "set targetAccounts to every account"

    script = f'''
    on sanitise(txt)
        set AppleScript's text item delimiters to character id 9
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 10
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 13
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to ""
        return txt
    end sanitise

    using terms from application "Mail"
        on appendMailboxRows(mailboxesToWalk, accountName, parentPath, outputLines)
            repeat with mb in mailboxesToWalk
                set mbName to my sanitise(name of mb as text)
                set mbPath to mbName
                if parentPath is not "" then set mbPath to parentPath & "/" & mbName
                try
                    set mbId to my sanitise(id of mb as text)
                on error
                    set mbId to ""
                end try
                set end of outputLines to mbName & character id 9 & accountName & character id 9 & mbPath & character id 9 & mbId

                try
                    set childMailboxes to every mailbox of mb
                    if (count of childMailboxes) > 0 then
                        set outputLines to my appendMailboxRows(childMailboxes, accountName, mbPath, outputLines)
                    end if
                on error
                    -- Ignore folders that cannot be enumerated.
                end try
            end repeat
            return outputLines
        end appendMailboxRows
    end using terms from

    tell application "Mail"
        set outputLines to {{}}
        {fetch_block}
        repeat with acc in targetAccounts
            try
                set accName to my sanitise(name of acc as text)
            on error
                set accName to ""
            end try
            try
                set rootMailboxes to every mailbox of acc
                if (count of rootMailboxes) > 0 then
                    set outputLines to my appendMailboxRows(rootMailboxes, accName, "", outputLines)
                end if
            on error
                -- Ignore accounts that cannot be read.
            end try
        end repeat
        set AppleScript's text item delimiters to character id 10
        return outputLines as text
    end tell
    '''

    raw = _run_script(script, timeout=60.0)
    parsed: list[dict[str, str]] = []
    for line in (raw or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        mailbox_name = (parts[0] or "").strip()
        account_name = (parts[1] or "").strip()
        mailbox_path = (parts[2] or "").strip() if len(parts) >= 3 else mailbox_name
        mailbox_id = (parts[3] or "").strip() if len(parts) >= 4 else ""
        parsed.append(
            {
                "mailbox": mailbox_name,
                "account": account_name,
                "path": mailbox_path or mailbox_name,
                "mailbox_id": mailbox_id,
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in parsed:
        mailbox = (row.get("mailbox") or "").strip()
        account_name = (row.get("account") or "").strip()
        mailbox_path = (row.get("path") or mailbox).strip()
        mailbox_id = (row.get("mailbox_id") or "").strip()
        if not mailbox:
            continue
        key = (
            _normalize_text_key(account_name),
            _normalize_text_key(mailbox_path),
            mailbox_id,
        )
        if key in seen:
            continue
        seen.add(key)
        is_system = _mail_is_system_mailbox(mailbox)
        if not include_system and is_system:
            continue
        deduped.append(
            {
                "mailbox": mailbox,
                "account": account_name,
                "path": mailbox_path,
                "mailbox_id": mailbox_id,
                "is_system_mailbox": is_system,
            }
        )

    deduped.sort(key=lambda item: (_normalize_text_key(item.get("account", "")), _normalize_text_key(item.get("path", item["mailbox"]))))
    return _format_output(
        deduped,
        as_text=as_text,
        format_fn=lambda x: (
            f"{x.get('path', x.get('mailbox', ''))}"
            if not x.get("account")
            else f"{x.get('path', x.get('mailbox', ''))}  [{x.get('account', '')}]"
        ),
    )


def _resolve_mail_label(
    label: str,
    mailboxes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str], str | None]:
    """Resolve a label string to a mailbox row."""
    candidates = [item for item in mailboxes if str(item.get("mailbox", "")).strip()]
    if not candidates:
        return None, [], "no mailboxes discovered"

    def _display_name(row: dict[str, Any]) -> str:
        path = str(row.get("path") or row.get("mailbox") or "").strip()
        return path

    normalized_candidates: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        mailbox_name = str(row.get("mailbox") or "").strip()
        path_name = str(row.get("path") or mailbox_name).strip()
        for token in {
            _normalize_text_key(mailbox_name),
            _normalize_text_key(path_name),
            _normalize_text_key(_display_name(row)),
        }:
            if not token:
                continue
            normalized_candidates.setdefault(token, []).append(row)

    query = _normalize_text_key(label)
    if query in normalized_candidates:
        exact_matches = normalized_candidates[query]
        if len(exact_matches) == 1:
            return exact_matches[0], [], None
        suggestions = sorted({_display_name(row) for row in exact_matches}, key=_normalize_text_key)[:5]
        return None, suggestions, f"label '{label}' is ambiguous"

    alias = {
        "action": "Action",
        "focus": "Focus",
        "noise": "Noise",
        "delete": "Delete",
    }.get(query)
    if alias:
        alias_norm = _normalize_text_key(alias)
        alias_matches = normalized_candidates.get(alias_norm, [])
        if len(alias_matches) == 1:
            return alias_matches[0], [], None
        if len(alias_matches) > 1:
            suggestions = sorted({_display_name(row) for row in alias_matches}, key=_normalize_text_key)[:5]
            return None, suggestions, f"label '{label}' is ambiguous"

    partial_matches = []
    for row in candidates:
        mailbox_name = str(row.get("mailbox") or "").strip()
        path_name = str(row.get("path") or mailbox_name).strip()
        haystacks = {
            _normalize_text_key(mailbox_name),
            _normalize_text_key(path_name),
            _normalize_text_key(_display_name(row)),
        }
        if query and any(query in target or target.startswith(query) for target in haystacks):
            partial_matches.append(row)

    # Keep deterministic, case-insensitive ordering for suggestions.
    partial_matches = sorted(
        partial_matches,
        key=lambda row: (
            _normalize_text_key(str(row.get("account") or "")),
            _normalize_text_key(str(row.get("path") or row.get("mailbox") or "")),
        ),
    )
    if len(partial_matches) == 1:
        return partial_matches[0], [], None

    suggestions = (
        [_display_name(row) for row in partial_matches[:5]]
        if partial_matches
        else sorted({_display_name(row) for row in candidates}, key=_normalize_text_key)[:5]
    )
    if not partial_matches:
        return None, suggestions, f"no mailbox matches label '{label}'"
    return None, suggestions, f"label '{label}' is ambiguous"


def mail_move_to_label(
    message_ids: list[str],
    label: str,
    account: str = "",
    source_mailbox: str = "INBOX",
) -> dict[str, Any]:
    """Move messages to a destination mailbox resolved from a label."""
    cleaned_ids = [str(mid).strip() for mid in (message_ids or []) if str(mid).strip()]
    attempted = len(cleaned_ids)
    if attempted == 0:
        return {
            "attempted": 0,
            "moved": 0,
            "failed": 0,
            "destination_mailbox": None,
            "results": [],
            "error": "no message IDs provided",
        }

    mailbox_rows = mail_list_mailboxes(account=account, include_system=True, as_text=False)
    if not isinstance(mailbox_rows, list):
        mailbox_rows = []
    destination, suggestions, resolution_error = _resolve_mail_label(label, mailbox_rows)
    if not destination:
        return {
            "attempted": attempted,
            "moved": 0,
            "failed": attempted,
            "destination_mailbox": None,
            "results": [
                {
                    "message_id": mid,
                    "status": "failed",
                    "error": resolution_error or "destination label could not be resolved",
                }
                for mid in cleaned_ids
            ],
            "suggestions": suggestions,
        }

    esc_source = source_mailbox.replace('"', '\\"')
    destination_name = str(destination.get("mailbox") or "").strip()
    destination_path = str(destination.get("path") or destination_name).strip()
    destination_id = str(destination.get("mailbox_id") or "").strip()
    destination_account = str(destination.get("account") or "").strip()

    esc_dest_name = destination_name.replace('"', '\\"')
    esc_dest_path = destination_path.replace('"', '\\"')
    esc_dest_id = destination_id.replace('"', '\\"')
    esc_dest_account = destination_account.replace('"', '\\"')
    if account:
        esc_account = account.replace('"', '\\"')
        source_ref = f'mailbox "{esc_source}" of account "{esc_account}"'
    elif _normalize_text_key(source_mailbox) == "inbox":
        source_ref = "inbox"
    else:
        source_ref = f'mailbox "{esc_source}"'

    moved = 0
    inbox_removed = 0
    results: list[dict[str, str]] = []
    for message_id in cleaned_ids:
        esc_id = message_id.replace('"', '\\"')
        match_clause = f"id is {int(message_id)}" if message_id.isdigit() else f'id as text is "{esc_id}"'
        script = f'''
        using terms from application "Mail"
            on findMailboxById(targetId, mailboxList)
                repeat with mb in mailboxList
                    try
                        if (id of mb as text) is targetId then return mb
                    on error
                        -- Ignore unreadable mailbox IDs.
                    end try
                    try
                        set childMailboxes to every mailbox of mb
                        if (count of childMailboxes) > 0 then
                            set nestedFound to my findMailboxById(targetId, childMailboxes)
                            if nestedFound is not missing value then return nestedFound
                        end if
                    on error
                        -- Ignore unreadable child mailboxes.
                    end try
                end repeat
                return missing value
            end findMailboxById

            on findMailboxByPath(targetPath, mailboxList, parentPath)
                repeat with mb in mailboxList
                    try
                        set mbName to name of mb as text
                    on error
                        set mbName to ""
                    end try
                    set nextPath to mbName
                    if parentPath is not "" then set nextPath to parentPath & "/" & mbName
                    if nextPath is targetPath then return mb
                    try
                        set childMailboxes to every mailbox of mb
                        if (count of childMailboxes) > 0 then
                            set nestedFound to my findMailboxByPath(targetPath, childMailboxes, nextPath)
                            if nestedFound is not missing value then return nestedFound
                        end if
                    on error
                        -- Ignore unreadable child mailboxes.
                    end try
                end repeat
                return missing value
            end findMailboxByPath
        end using terms from

        tell application "Mail"
            try
                set sourceBox to {source_ref}
                if "{esc_dest_account}" is not "" then
                    set targetAccounts to {{account "{esc_dest_account}"}}
                else
                    set targetAccounts to every account
                end if
                set destinationBox to missing value
                if "{esc_dest_id}" is not "" then
                    repeat with acc in targetAccounts
                        try
                            set destinationBox to my findMailboxById("{esc_dest_id}", every mailbox of acc)
                        on error
                            set destinationBox to missing value
                        end try
                        if destinationBox is not missing value then exit repeat
                    end repeat
                end if
                if destinationBox is missing value and "{esc_dest_path}" is not "" then
                    repeat with acc in targetAccounts
                        try
                            set destinationBox to my findMailboxByPath("{esc_dest_path}", every mailbox of acc, "")
                        on error
                            set destinationBox to missing value
                        end try
                        if destinationBox is not missing value then exit repeat
                    end repeat
                end if
                if destinationBox is missing value then
                    repeat with acc in targetAccounts
                        try
                            set destinationBox to first mailbox of acc whose name is "{esc_dest_name}"
                        on error
                            set destinationBox to missing value
                        end try
                        if destinationBox is not missing value then exit repeat
                    end repeat
                end if
                if destinationBox is missing value then error "destination mailbox not found"
                try
                    set matchedMsg to first message of sourceBox whose {match_clause}
                on error
                    error "message not found in source mailbox"
                end try

                move matchedMsg to destinationBox

                try
                    set sourceRemaining to count of (every message of sourceBox whose {match_clause})
                on error
                    set sourceRemaining to 0
                end try
                try
                    set destinationCount to count of (every message of destinationBox whose {match_clause})
                on error
                    set destinationCount to 0
                end try

                if destinationCount > 0 and sourceRemaining is 0 then
                    return "ok_exclusive"
                else if destinationCount > 0 then
                    return "ok_labeled"
                end if
                return "error: destination mailbox did not receive message"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        result = _run_script(script, timeout=30.0)
        if result in {"ok", "ok_exclusive"}:
            moved += 1
            inbox_removed += 1
            results.append({"message_id": message_id, "status": "moved"})
        elif result == "ok_labeled":
            moved += 1
            results.append(
                {
                    "message_id": message_id,
                    "status": "moved_inbox_retained",
                    "warning": "message moved to destination but still visible in source mailbox",
                }
            )
        else:
            results.append(
                {
                    "message_id": message_id,
                    "status": "failed",
                    "error": result or "unknown error",
                }
            )

    return {
        "attempted": attempted,
        "moved": moved,
        "failed": attempted - moved,
        "inbox_removed": inbox_removed,
        "destination_mailbox": destination_name,
        "destination_path": destination_path,
        "destination_account": destination_account,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Apple Reminders
# ---------------------------------------------------------------------------

def reminders_list_lists() -> list[str]:
    """Return a list of all Reminders list names."""
    script = '''
    tell application "Reminders"
        set listNames to {}
        repeat with lst in every list
            set end of listNames to name of lst as text
        end repeat
        set AppleScript's text item delimiters to "|||"
        return listNames as text
    end tell
    '''
    raw = _run_script(script)
    if not raw:
        return []
    return [name.strip() for name in raw.split("|||") if name.strip()]


def _reminders_fetch_raw(list_name: str = "", filter_completed: str = "incomplete", limit: int = 100) -> list[dict]:
    """Internal: fetch reminders via AppleScript."""
    if filter_completed == "incomplete":
        completion_clause = "whose completed is false"
    elif filter_completed == "complete":
        completion_clause = "whose completed is true"
    else:
        completion_clause = ""

    if list_name:
        esc_list = list_name.replace('"', '\\"')
        fetch_block = f'''
            try
                set targetList to list "{esc_list}"
            on error
                return ""
            end try
            set allReminders to (every reminder of targetList {completion_clause})
        '''
    else:
        # Iterate all lists
        fetch_block = f'''
            set allReminders to {{}}
            repeat with lst in every list
                set allReminders to allReminders & (every reminder of lst {completion_clause})
            end repeat
        '''

    script = f'''
    on sanitise(txt)
        set AppleScript's text item delimiters to character id 9
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 10
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 13
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to ""
        return txt
    end sanitise

    tell application "Reminders"
        set maxCount to {int(limit)}
        set outputLines to {{}}
        {fetch_block}

        repeat with rem in allReminders
            if (count of outputLines) >= maxCount then exit repeat

            set remId to my sanitise(id of rem as text)
            set remName to my sanitise(name of rem as text)
            try
                set remBody to body of rem as text
                if length of remBody > 400 then set remBody to text 1 thru 400 of remBody
                set remBody to my sanitise(remBody)
            on error
                set remBody to ""
            end try
            try
                set remDue to my sanitise(due date of rem as text)
            on error
                set remDue to ""
            end try
            set remCompleted to completed of rem
            set remCompletedStr to "false"
            if remCompleted then set remCompletedStr to "true"
            try
                set remList to my sanitise(name of container of rem as text)
            on error
                set remList to ""
            end try

            set end of outputLines to remId & character id 9 & remName & character id 9 & remBody & character id 9 & remDue & character id 9 & remCompletedStr & character id 9 & remList
        end repeat

        set AppleScript's text item delimiters to character id 10
        return (outputLines as text)
    end tell
    '''
    return _parse_delimited_output(_run_script(script, timeout=60.0), ["id", "name", "body", "due_date", "completed", "list"])


def reminders_list(
    list_name: str = "",
    filter: str = "incomplete",
    limit: int = 50,
    as_text: bool = False,
) -> list | str:
    """List reminders with id, name, body, due_date, completed, list.

    Args:
        list_name: Reminders list name (empty = all lists)
        filter: 'incomplete' | 'complete' | 'all'
        limit: Maximum reminders to return
        as_text: Return human-readable string

    Returns:
        List of reminder dicts or formatted string
    """
    data = _reminders_fetch_raw(list_name=list_name, filter_completed=filter, limit=limit)
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: "{name}{due}".format(
            name=x.get("name", ""),
            due=f"  [due: {x['due_date']}]" if x.get("due_date") else "",
        ),
    )


def reminders_search(
    query: str,
    list_name: str = "",
    limit: int = 20,
    as_text: bool = False,
) -> list | str:
    """Search reminders by name or body (Python-side filter).

    Fetches up to 200 reminders then filters in Python.
    """
    all_reminders = _reminders_fetch_raw(list_name=list_name, filter_completed="all", limit=200)
    q = query.lower()
    matches = [
        r for r in all_reminders
        if q in (r.get("name") or "").lower() or q in (r.get("body") or "").lower()
    ][:limit]
    return _format_output(
        matches,
        as_text=as_text,
        format_fn=lambda x: "{name}{due}".format(
            name=x.get("name", ""),
            due=f"  [due: {x['due_date']}]" if x.get("due_date") else "",
        ),
    )


def reminders_create(
    name: str,
    list_name: str = "Reminders",
    notes: str = "",
    due_date: str = "",
) -> str | None:
    """Create a new reminder. Returns its ID string or None on failure.

    Args:
        name: Reminder title
        list_name: Target list name (default: "Reminders")
        notes: Optional notes/body text
        due_date: Optional due date string (e.g. "2026-03-01 09:00")

    Returns:
        Reminder ID string or None
    """
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    esc_name = _esc(name)
    esc_list = _esc(list_name)
    esc_notes = _esc(notes)

    props_parts = [f'name:"{esc_name}"']
    if notes:
        props_parts.append(f'body:"{esc_notes}"')

    props = "{" + ", ".join(props_parts) + "}"

    if due_date:
        esc_due = _esc(due_date)
        due_clause = f'set due date of newRem to date "{esc_due}"'
    else:
        due_clause = ""

    script = f'''
    tell application "Reminders"
        try
            set targetList to list "{esc_list}"
        on error
            return "error: list not found"
        end try
        try
            set newRem to make new reminder at targetList with properties {props}
            {due_clause}
            return id of newRem as text
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if not result or result.startswith("error:"):
        logger.warning("reminders_create failed: %s", result)
        return None
    return result


def reminders_complete(reminder_id: str, list_name: str) -> bool:
    """Mark a reminder as completed. Returns True on success."""
    esc_id = reminder_id.replace('"', '\\"')
    esc_list = list_name.replace('"', '\\"')

    script = f'''
    tell application "Reminders"
        try
            set targetList to list "{esc_list}"
            set matchedRem to first reminder of targetList whose id as text is "{esc_id}"
            set completed of matchedRem to true
            return "ok"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if result == "ok":
        return True
    logger.warning("reminders_complete failed: %s", result)
    return False


# ---------------------------------------------------------------------------
# Apple Calendar
# ---------------------------------------------------------------------------

def calendar_list_calendars() -> list[str]:
    """Return a list of all Calendar names."""
    script = '''
    tell application "Calendar"
        set calNames to {}
        repeat with cal in every calendar
            set end of calNames to name of cal as text
        end repeat
        set AppleScript's text item delimiters to "|||"
        return calNames as text
    end tell
    '''
    raw = _run_script(script)
    if not raw:
        return []
    return [name.strip() for name in raw.split("|||") if name.strip()]


def _calendar_fetch_raw(calendar: str = "", days_ahead: int = 7, limit: int = 50) -> list[dict]:
    """Internal: fetch calendar events in a date range via AppleScript."""
    if calendar:
        esc_cal = calendar.replace('"', '\\"')
        fetch_block = f'''
            try
                set targetCal to calendar "{esc_cal}"
            on error
                return ""
            end try
            set allEvents to (every event of targetCal whose start date >= nowDate and start date <= futureDate)
        '''
    else:
        fetch_block = '''
            set allEvents to {}
            repeat with cal in every calendar
                set allEvents to allEvents & (every event of cal whose start date >= nowDate and start date <= futureDate)
            end repeat
        '''

    script = f'''
    on sanitise(txt)
        set AppleScript's text item delimiters to character id 9
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 10
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to character id 13
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to ""
        return txt
    end sanitise

    tell application "Calendar"
        set maxCount to {int(limit)}
        set outputLines to {{}}
        set nowDate to current date
        set futureDate to nowDate + ({int(days_ahead)} * days)
        {fetch_block}

        repeat with evt in allEvents
            if (count of outputLines) >= maxCount then exit repeat

            set evtId to my sanitise(uid of evt as text)
            set evtSummary to my sanitise(summary of evt as text)
            try
                set evtDescription to description of evt as text
                if length of evtDescription > 400 then set evtDescription to text 1 thru 400 of evtDescription
                set evtDescription to my sanitise(evtDescription)
            on error
                set evtDescription to ""
            end try
            try
                set evtStart to my sanitise(start date of evt as text)
            on error
                set evtStart to ""
            end try
            try
                set evtEnd to my sanitise(end date of evt as text)
            on error
                set evtEnd to ""
            end try
            try
                set evtCal to my sanitise(name of calendar of evt as text)
            on error
                set evtCal to ""
            end try

            set end of outputLines to evtId & character id 9 & evtSummary & character id 9 & evtDescription & character id 9 & evtStart & character id 9 & evtEnd & character id 9 & evtCal
        end repeat

        set AppleScript's text item delimiters to character id 10
        return (outputLines as text)
    end tell
    '''
    return _parse_delimited_output(_run_script(script, timeout=60.0), ["id", "summary", "description", "start_date", "end_date", "calendar"])


def calendar_list_events(
    calendar: str = "",
    days_ahead: int = 7,
    limit: int = 20,
    as_text: bool = False,
) -> list | str:
    """List upcoming calendar events with id, summary, description, start_date, end_date, calendar.

    Args:
        calendar: Calendar name (empty = all calendars)
        days_ahead: How many days ahead to look (default: 7)
        limit: Maximum events to return
        as_text: Return human-readable string

    Returns:
        List of event dicts or formatted string
    """
    data = _calendar_fetch_raw(calendar=calendar, days_ahead=days_ahead, limit=limit)
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('start_date', '')}  {x.get('summary', '')}",
    )


def calendar_search(
    query: str,
    calendar: str = "",
    limit: int = 20,
    as_text: bool = False,
) -> list | str:
    """Search upcoming calendar events by summary or description (Python-side filter).

    Fetches events for 90 days ahead and filters in Python.
    """
    all_events = _calendar_fetch_raw(calendar=calendar, days_ahead=90, limit=200)
    q = query.lower()
    matches = [
        e for e in all_events
        if q in (e.get("summary") or "").lower() or q in (e.get("description") or "").lower()
    ][:limit]
    return _format_output(
        matches,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('start_date', '')}  {x.get('summary', '')}",
    )


def calendar_create(
    title: str,
    start_date: str,
    end_date: str = "",
    notes: str = "",
    calendar: str = "",
) -> str | None:
    """Create a calendar event. Returns the event UID or None on failure.

    Args:
        title: Event title/summary
        start_date: Start date/time string (e.g. "2026-03-01 09:00")
        end_date: End date/time string (optional; defaults to 1 hour after start)
        notes: Optional description/notes
        calendar: Calendar name (empty = default calendar)

    Returns:
        Event UID string or None
    """
    from datetime import datetime, timedelta

    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def _parse_dt(s: str) -> datetime:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {s!r}")

    def _dt_to_as(dt: datetime) -> str:
        """Build an AppleScript snippet that produces a date object."""
        month_names = ["January","February","March","April","May","June",
                       "July","August","September","October","November","December"]
        mo = month_names[dt.month - 1]
        h12 = dt.hour % 12 or 12
        ampm = "AM" if dt.hour < 12 else "PM"
        return f'date "{mo} {dt.day}, {dt.year} {h12}:{dt.minute:02d}:{dt.second:02d} {ampm}"'

    esc_title = _esc(title)

    try:
        start_dt = _parse_dt(start_date)
    except ValueError as exc:
        logger.warning("calendar_create: bad start_date: %s", exc)
        return None

    if end_date:
        try:
            end_dt = _parse_dt(end_date)
        except ValueError as exc:
            logger.warning("calendar_create: bad end_date: %s", exc)
            return None
    else:
        end_dt = start_dt + timedelta(hours=1)

    as_start = _dt_to_as(start_dt)
    as_end = _dt_to_as(end_dt)

    if calendar:
        esc_cal = _esc(calendar)
        cal_clause = f'set targetCal to calendar "{esc_cal}"'
    else:
        cal_clause = "set targetCal to default calendar"

    notes_clause = ""
    if notes:
        esc_notes = _esc(notes)
        notes_clause = f'set description of newEvent to "{esc_notes}"'

    script = f'''
    tell application "Calendar"
        try
            {cal_clause}
        on error
            return "error: calendar not found"
        end try
        try
            set newEvent to make new event at targetCal with properties {{summary:"{esc_title}", start date:{as_start}, end date:{as_end}}}
            {notes_clause}
            return uid of newEvent as text
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_script(script, timeout=30.0)
    if not result or result.startswith("error:"):
        logger.warning("calendar_create failed: %s", result)
        return None
    return result


# ---------------------------------------------------------------------------
# iMessage (read-only SQLite)
# ---------------------------------------------------------------------------

_DEFAULT_MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"


def _messages_connect(db_path: Path | None = None) -> sqlite3.Connection | None:
    """Open Messages chat.db in read-only mode. Returns None on failure."""
    path = db_path or _DEFAULT_MESSAGES_DB
    try:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn
    except Exception as exc:
        logger.warning("Failed to open Messages DB at %s: %s", path, exc)
        return None


def messages_list_recent_chats(
    limit: int = 10,
    as_text: bool = False,
    db_path: Path | None = None,
) -> list | str:
    """List recently active chats with handle (phone/email) and service.

    Args:
        limit: Maximum number of chats to return
        as_text: Return human-readable string
        db_path: Override path to chat.db (default: ~/Library/Messages/chat.db)

    Returns:
        List of dicts with 'handle' and 'service', or formatted string
    """
    conn = _messages_connect(db_path)
    if conn is None:
        return [] if not as_text else ""
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT h.id AS handle, h.service
            FROM handle h
            JOIN chat_handle_join chj ON h.ROWID = chj.handle_id
            JOIN chat c ON chj.chat_id = c.ROWID
            ORDER BY c.last_read_message_timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        data = [{"handle": row["handle"], "service": row["service"]} for row in rows]
    except Exception as exc:
        logger.warning("messages_list_recent_chats query failed: %s", exc)
        data = []
    finally:
        conn.close()
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('handle', '')}  ({x.get('service', '')})",
    )


def messages_search(
    query: str,
    limit: int = 20,
    as_text: bool = False,
    db_path: Path | None = None,
) -> list | str:
    """Search message text in chat.db.

    Args:
        query: Search string (case-insensitive LIKE match)
        limit: Maximum results to return
        as_text: Return human-readable string
        db_path: Override path to chat.db

    Returns:
        List of dicts with 'handle', 'text', and 'date', or formatted string
    """
    conn = _messages_connect(db_path)
    if conn is None:
        return [] if not as_text else ""
    try:
        rows = conn.execute(
            """
            SELECT m.text, COALESCE(h.id, 'unknown') AS handle, m.date
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text LIKE ? ESCAPE '\'
            ORDER BY m.ROWID DESC
            LIMIT ?
            """,
            (f"%{query.replace(chr(92), chr(92)*2).replace('%', chr(92)+'%').replace('_', chr(92)+'_')}%", limit),
        ).fetchall()
        data = [
            {"handle": row["handle"], "text": row["text"] or "", "date": str(row["date"])}
            for row in rows
        ]
    except Exception as exc:
        logger.warning("messages_search query failed: %s", exc)
        data = []
    finally:
        conn.close()
    return _format_output(
        data,
        as_text=as_text,
        format_fn=lambda x: f"{x.get('handle', '')}:  {(x.get('text') or '')[:120]}",
    )
