"""General-purpose Apple app tools for AI use via the apple-flow CLI.

Each function is a standalone callable backed by AppleScript (or SQLite for
iMessage).  Designed to be invoked by an AI assistant via::

    apple-flow tools <command> [args]

All functions return JSON-serializable values and never raise — failures are
logged and empty/falsy values are returned.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path

logger = logging.getLogger("apple_flow.apple_tools")

# ---------------------------------------------------------------------------
# TOOLS_CONTEXT — injected into AI prompts so the AI knows these tools exist
# ---------------------------------------------------------------------------

TOOLS_CONTEXT = """\
You have access to Apple apps via the apple-flow CLI. Run: apple-flow tools <command>
Output is JSON. Use --text for human-readable output.

NOTES:  notes_search "q" [--folder X] [--limit N]  |  notes_list [--folder X]  |  notes_list_folders
        notes_get_content "Title" [--folder X]  |  notes_create "Title" "Body" [--folder X]
        notes_append "Title" "Text" [--folder X]
MAIL:   mail_list_unread [--limit N]  |  mail_search "q" [--days N]  |  mail_get_content "id"
        mail_send "to@x.com" "Subject" "Body"
REMINDERS: reminders_list_lists  |  reminders_list [--list X] [--filter incomplete|complete|all]
           reminders_search "q" [--list X]  |  reminders_create "name" [--list X] [--due YYYY-MM-DD]
           reminders_complete "id" --list "List"
CALENDAR:  calendar_list_calendars  |  calendar_list_events [--cal X] [--days N]
           calendar_search "q" [--cal X]  |  calendar_create "Title" "YYYY-MM-DD HH:MM" [--cal X]
MESSAGES:  messages_list_recent_chats [--limit N]  |  messages_search "q" [--limit N]\
"""

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ESCAPE_JSON_HANDLER = r"""
on escapeJSON(txt)
    set output to ""
    repeat with ch in (characters of txt)
        set charCode to (ASCII number of ch)
        if ch is "\"" then
            set output to output & "\\\""
        else if ch is "\\" then
            set output to output & "\\\\"
        else if ch is (ASCII character 10) then
            set output to output & "\\n"
        else if ch is (ASCII character 13) then
            set output to output & "\\n"
        else if ch is (ASCII character 9) then
            set output to output & "\\t"
        else if charCode < 32 and charCode is not 10 and charCode is not 13 and charCode is not 9 then
            set output to output & " "
        else
            set output to output & ch
        end if
    end repeat
    return output
end escapeJSON
"""


def _run_script(script: str, timeout: float = 30.0) -> str | None:
    """Run an osascript -e command. Returns stdout string or None on any failure."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("AppleScript failed (rc=%s): %s", result.returncode, result.stderr.strip())
            return None
        return result.stdout.strip("\r\n")
    except subprocess.TimeoutExpired:
        logger.warning("AppleScript timed out after %.1fs", timeout)
        return None
    except FileNotFoundError:
        logger.warning("osascript not found — apple_tools requires macOS")
        return None
    except Exception as exc:
        logger.warning("Unexpected error running AppleScript: %s", exc)
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
        set AppleScript's text item delimiters to (ASCII character 9)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 10)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 13)
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

            set end of outputLines to nId & (ASCII character 9) & nName & (ASCII character 9) & nBody & (ASCII character 9) & nModDate
        end repeat

        set AppleScript's text item delimiters to (ASCII character 10)
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
        set AppleScript's text item delimiters to (ASCII character 9)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 10)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 13)
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

                set end of outputLines to msgId & (ASCII character 9) & msgSender & (ASCII character 9) & msgSubject & (ASCII character 9) & msgBody & (ASCII character 9) & msgDateStr & (ASCII character 9) & msgReadStr
            end if
        end repeat

        set AppleScript's text item delimiters to (ASCII character 10)
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

    Fetches up to 200 messages then filters in Python.
    """
    all_msgs = _mail_fetch_raw(account=account, mailbox=mailbox, limit=200, max_age_days=max_age_days)
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
    if account:
        esc_account = account.replace('"', '\\"')
        esc_mailbox = mailbox.replace('"', '\\"')
        mailbox_ref = f'mailbox "{esc_mailbox}" of account "{esc_account}"'
    else:
        mailbox_ref = "inbox"

    script = f'''
    tell application "Mail"
        try
            set matchedMsg to first message of {mailbox_ref} whose id as text is "{esc_id}"
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
        set AppleScript's text item delimiters to (ASCII character 9)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 10)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 13)
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

            set end of outputLines to remId & (ASCII character 9) & remName & (ASCII character 9) & remBody & (ASCII character 9) & remDue & (ASCII character 9) & remCompletedStr & (ASCII character 9) & remList
        end repeat

        set AppleScript's text item delimiters to (ASCII character 10)
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
        set AppleScript's text item delimiters to (ASCII character 9)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 10)
        set parts to text items of txt
        set AppleScript's text item delimiters to " "
        set txt to parts as text
        set AppleScript's text item delimiters to (ASCII character 13)
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

            set end of outputLines to evtId & (ASCII character 9) & evtSummary & (ASCII character 9) & evtDescription & (ASCII character 9) & evtStart & (ASCII character 9) & evtEnd & (ASCII character 9) & evtCal
        end repeat

        set AppleScript's text item delimiters to (ASCII character 10)
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
            WHERE m.text LIKE ?
            ORDER BY m.ROWID DESC
            LIMIT ?
            """,
            (f"%{query}%", limit),
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
