"""Notes logging utilities — markdown→HTML conversion and Apple Notes log writer."""

from __future__ import annotations

import html as _html_mod
import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("apple_flow.notes_logging")


def _inline_md(text: str) -> str:
    """Convert inline markdown spans to HTML (bold, italic, code, links)."""
    text = _html_mod.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _md_to_html(text: str) -> str:
    """Convert a markdown string to HTML suitable for Apple Notes body."""
    lines = text.split("\n")
    parts: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    for line in lines:
        s = line.strip()
        if s in ("---", "***", "___"):
            close_ul()
            parts.append("<hr>")
        elif s.startswith("### "):
            close_ul()
            parts.append(f"<h3>{_inline_md(s[4:])}</h3>")
        elif s.startswith("## "):
            close_ul()
            parts.append(f"<h2>{_inline_md(s[3:])}</h2>")
        elif s.startswith("# "):
            close_ul()
            parts.append(f"<h1>{_inline_md(s[2:])}</h1>")
        elif s.startswith("- ") or s.startswith("* "):
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_inline_md(s[2:])}</li>")
        elif not s:
            close_ul()
            parts.append("<br>")
        else:
            close_ul()
            parts.append(f"<p>{_inline_md(s)}</p>")

    close_ul()
    return "".join(parts)


def log_to_notes(
    egress: Any,
    folder_name: str,
    kind: str,
    sender: str,
    request: str,
    response: str,
) -> None:
    """Create a rich-HTML log note for a completed AI turn (fire-and-forget)."""
    if egress is None:
        return
    try:
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        payload_preview = request[:50].replace("\n", " ")
        title = f"[{kind}] {payload_preview} — {now_str}"

        request_html = _md_to_html(request)
        response_html = _md_to_html(response)

        body = (
            f"<h1>Agent Log</h1>"
            f"<p><b>Command:</b> {_html_mod.escape(kind)}"
            f" &nbsp;|&nbsp; <b>Sender:</b> {_html_mod.escape(sender)}<br>"
            f"<b>Time:</b> {now_str}</p>"
            f"<hr>"
            f"<h2>Request</h2>"
            f"{request_html}"
            f"<hr>"
            f"<h2>Response</h2>"
            f"{response_html}"
        )

        egress.create_log_note(
            folder_name=folder_name,
            title=title,
            body=body,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to log to Notes: %s", exc)
