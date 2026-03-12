#!/usr/bin/env python3
"""Small direct Notion API helper (no MCP required)."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"


def _token() -> str:
    token = os.getenv("NOTION_API_KEY", "").strip()
    if not token:
        raise SystemExit("Missing NOTION_API_KEY in environment.")
    return token


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url=f"{NOTION_BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
            message = parsed.get("message", body)
            code = parsed.get("code", "unknown_error")
        except json.JSONDecodeError:
            message = body
            code = "unknown_error"
        raise SystemExit(f"Notion API error ({exc.code}, {code}): {message}") from exc


def _short_id(raw_id: str) -> str:
    cleaned = raw_id.strip().replace("-", "")
    if len(cleaned) == 32:
        return (
            f"{cleaned[:8]}-{cleaned[8:12]}-{cleaned[12:16]}-"
            f"{cleaned[16:20]}-{cleaned[20:]}"
        )
    return raw_id


def _title_prop(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value}}]}


def _rich_text(value: str, link: str | None = None) -> list[dict[str, Any]]:
    text: dict[str, Any] = {"content": value}
    if link:
        text["link"] = {"url": link}
    return [{"type": "text", "text": text}]


def _rich_text_prop(value: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": value}}]}


def _select_prop(value: str) -> dict[str, Any]:
    return {"select": {"name": value}}


def _number_prop(value: float) -> dict[str, Any]:
    return {"number": value}


def _email_prop(value: str) -> dict[str, Any]:
    return {"email": value}


def _url_prop(value: str) -> dict[str, Any]:
    return {"url": value}


def _date_prop(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def _page_title(page: dict[str, Any]) -> str:
    title_parts = (((page.get("properties") or {}).get("title") or {}).get("title") or [])
    return "".join(part.get("plain_text", "") for part in title_parts).strip()


def _block_with_rich_text(block_type: str, rich_text: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": rich_text,
        },
    }


def _paragraph_block(text: str, link: str | None = None) -> dict[str, Any]:
    return _block_with_rich_text("paragraph", _rich_text(text, link=link))


def _heading_block(level: int, text: str) -> dict[str, Any]:
    return _block_with_rich_text(f"heading_{level}", _rich_text(text))


def _bulleted_item_block(text: str, link: str | None = None) -> dict[str, Any]:
    return _block_with_rich_text("bulleted_list_item", _rich_text(text, link=link))


def _numbered_item_block(text: str) -> dict[str, Any]:
    return _block_with_rich_text("numbered_list_item", _rich_text(text))


def _callout_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(text),
            "icon": {"type": "emoji", "emoji": "📌"},
            "color": "gray_background",
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_callout(page_tree_text: str) -> str:
    marker = "Suggested callout at the top of the root page:"
    if marker in page_tree_text:
        tail = page_tree_text.split(marker, 1)[1]
        match = re.search(r"`([^`]+)`", tail, flags=re.MULTILINE)
        if match:
            return match.group(1).strip()
    match = re.search(r"`([^`]+)`", page_tree_text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Local files and Apple Flow runtime state are canonical. This Notion space mirrors operations for readability, triage, and handoff."


def _markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    paragraph_lines: list[str] = []
    skipped_h1 = False

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        blocks.append(_paragraph_block(" ".join(paragraph_lines)))
        paragraph_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            if not skipped_h1:
                skipped_h1 = True
                continue
        if stripped.startswith("## "):
            flush_paragraph()
            blocks.append(_heading_block(2, stripped[3:].strip()))
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            blocks.append(_heading_block(3, stripped[4:].strip()))
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            blocks.append(_bulleted_item_block(stripped[2:].strip()))
            continue
        if re.match(r"^\d+\. ", stripped):
            flush_paragraph()
            blocks.append(_numbered_item_block(re.sub(r"^\d+\. ", "", stripped)))
            continue
        paragraph_lines.append(stripped)

    flush_paragraph()
    return blocks


def _build_page_payload(parent_page_id: str, title: str) -> dict[str, Any]:
    return {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": _title_prop(title)},
    }


def _build_database_payload(parent_page_id: str, schema: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for prop in schema.get("properties", []):
        prop_name = prop["name"]
        prop_type = prop["type"]
        if prop_type == "title":
            properties[prop_name] = {"title": {}}
        elif prop_type == "date":
            properties[prop_name] = {"date": {}}
        elif prop_type == "checkbox":
            properties[prop_name] = {"checkbox": {}}
        elif prop_type == "select":
            properties[prop_name] = {
                "select": {"options": [{"name": option} for option in prop.get("options", [])]}
            }
        elif prop_type == "url":
            properties[prop_name] = {"url": {}}
        elif prop_type == "email":
            properties[prop_name] = {"email": {}}
        elif prop_type == "number":
            properties[prop_name] = {"number": {"format": "number"}}
        else:
            properties[prop_name] = {"rich_text": {}}

    return {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": _rich_text(schema.get("title", "Untitled Database")),
        "properties": properties,
    }


def _list_child_titles(page_id: str) -> dict[str, set[str]]:
    response = _request("GET", f"/blocks/{page_id}/children?page_size=100")
    page_titles: set[str] = set()
    database_titles: set[str] = set()
    for item in response.get("results", []):
        item_type = item.get("type")
        if item_type == "child_page":
            title = ((item.get("child_page") or {}).get("title") or "").strip()
            if title:
                page_titles.add(title)
        elif item_type == "child_database":
            title = ((item.get("child_database") or {}).get("title") or "").strip()
            if title:
                database_titles.add(title)
    return {"pages": page_titles, "databases": database_titles}


def _append_blocks(block_id: str, blocks: list[dict[str, Any]]) -> None:
    if not blocks:
        return
    _request("PATCH", f"/blocks/{block_id}/children", {"children": blocks})


def _build_root_blocks(
    *,
    callout_text: str,
    created_pages: list[dict[str, str]],
    database: dict[str, str] | None,
    view_names: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        _callout_block(callout_text),
        _paragraph_block(
            "This Notion space mirrors Apple Flow operations for readability, onboarding, triage, and handoff."
        ),
        _heading_block(2, "Handbook Pages"),
    ]
    for page in created_pages:
        label = page["title"]
        if page.get("purpose"):
            label = f"{label}: {page['purpose']}"
        blocks.append(_bulleted_item_block(label, link=page.get("url")))
    if database:
        blocks.append(_heading_block(2, "Operational Database"))
        blocks.append(
            _paragraph_block(
                f"{database['title']} stores readable operational activity for runs, approvals, companion events, and follow-ups.",
                link=database.get("url"),
            )
        )
        if view_names:
            blocks.append(
                _paragraph_block(
                    "Create these manual Notion views after publish: " + ", ".join(view_names) + "."
                )
            )
    return blocks


def _coerce_property(key: str, value: str) -> dict[str, Any]:
    if key == "Name":
        return _title_prop(value)
    if key == "Score Points":
        try:
            return _number_prop(float(value))
        except ValueError:
            return _rich_text_prop(value)
    if key == "Emails Sent":
        try:
            return _number_prop(float(value))
        except ValueError:
            return _rich_text_prop(value)
    if key == "Status":
        return _select_prop(value)
    if key == "Email":
        return _email_prop(value)
    if key == "Website":
        return _url_prop(value)
    if key == "Last Contact":
        return _date_prop(value)
    return _rich_text_prop(value)


def publish_guidebook(root_page_id: str, guidebook_dir: str, dry_run: bool = False) -> dict[str, Any]:
    root_id = _short_id(root_page_id)
    guidebook_path = Path(guidebook_dir)
    manifest = _load_json(guidebook_path / "manifest.json")
    schema = _load_json(guidebook_path / manifest["database"]["schema_file"])
    page_tree_text = (guidebook_path / "page-tree.md").read_text(encoding="utf-8")

    root_page = _request("GET", f"/pages/{root_id}")
    existing_children = _list_child_titles(root_id)

    page_titles = [page["title"] for page in manifest.get("pages", [])]
    database_title = manifest["database"]["title"]
    duplicate_titles = [
        title for title in page_titles if title in existing_children["pages"]
    ]
    if database_title in existing_children["databases"]:
        duplicate_titles.append(database_title)
    if duplicate_titles:
        joined = ", ".join(sorted(duplicate_titles))
        raise SystemExit(f"Guidebook content already exists under root page: {joined}")

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "root_page_id": root_id,
        "root_title": _page_title(root_page),
        "page_titles": page_titles,
        "database_title": database_title,
    }
    if dry_run:
        return summary

    created_pages: list[dict[str, str]] = []
    for page_entry in manifest.get("pages", []):
        create_response = _request("POST", "/pages", _build_page_payload(root_id, page_entry["title"]))
        page_id = create_response["id"]
        markdown = (guidebook_path / page_entry["file"]).read_text(encoding="utf-8")
        _append_blocks(page_id, _markdown_to_blocks(markdown))
        created_pages.append(
            {
                "id": page_id,
                "title": page_entry["title"],
                "url": create_response.get("url", ""),
                "purpose": page_entry.get("purpose", ""),
            }
        )

    database_response = _request("POST", "/databases", _build_database_payload(root_id, schema))
    created_database = {
        "id": database_response["id"],
        "title": schema.get("title", database_title),
        "url": database_response.get("url", ""),
    }
    root_blocks = _build_root_blocks(
        callout_text=_extract_callout(page_tree_text),
        created_pages=created_pages,
        database=created_database,
        view_names=[view["name"] for view in schema.get("views", []) if view.get("name")],
    )
    _append_blocks(root_id, root_blocks)

    summary["created_pages"] = created_pages
    summary["created_database"] = created_database
    return summary


def cmd_fetch(object_id: str) -> None:
    obj_id = _short_id(object_id)
    page_resp: dict[str, Any] | None = None
    db_resp: dict[str, Any] | None = None

    try:
        page_resp = _request("GET", f"/pages/{obj_id}")
    except SystemExit:
        pass
    try:
        db_resp = _request("GET", f"/databases/{obj_id}")
    except SystemExit:
        pass

    if page_resp:
        print(json.dumps({"object_type": "page", "data": page_resp}, indent=2))
        return
    if db_resp:
        print(json.dumps({"object_type": "database", "data": db_resp}, indent=2))
        return

    raise SystemExit(
        "Object not accessible as page or database. Check workspace access and integration sharing."
    )


def cmd_list_dbs(query: str, limit: int) -> None:
    payload = {
        "query": query,
        "page_size": min(max(limit, 1), 100),
        "filter": {"property": "object", "value": "database"},
    }
    resp = _request("POST", "/search", payload)
    results = resp.get("results", [])
    print(f"Found {len(results)} database(s):")
    for item in results:
        title_parts = item.get("title", [])
        title = "".join(part.get("plain_text", "") for part in title_parts).strip() or "(untitled)"
        print(f"- {title} | id={item.get('id')}")


def cmd_query_db(database_id: str, page_size: int) -> None:
    db_id = _short_id(database_id)
    resp = _request("POST", f"/databases/{db_id}/query", {"page_size": min(max(page_size, 1), 100)})
    print(json.dumps(resp, indent=2))


def cmd_schema(database_id: str) -> None:
    db_id = _short_id(database_id)
    resp = _request("GET", f"/databases/{db_id}")
    print(json.dumps(resp, indent=2))


def cmd_create_lead(
    database_id: str,
    name: str,
    company: str,
    industry: str,
    website: str,
    email: str,
    source: str,
    status: str,
) -> None:
    db_id = _short_id(database_id)
    properties: dict[str, Any] = {"Name": _title_prop(name)}
    if company:
        properties["Company"] = _rich_text_prop(company)
    if industry:
        properties["Industry"] = _rich_text_prop(industry)
    if website:
        properties["Website"] = _url_prop(website)
    if email:
        properties["Email"] = _email_prop(email)
    if source:
        properties["Source"] = _rich_text_prop(source)
    if status:
        properties["Status"] = _select_prop(status)
    # Keep this aligned to the schema and default to zero sends.
    properties["Emails Sent"] = _number_prop(0)
    properties["Assigned Sequence"] = _rich_text_prop("")

    resp = _request("POST", "/pages", {"parent": {"database_id": db_id}, "properties": properties})
    print(json.dumps({"created_page_id": resp.get("id"), "url": resp.get("url")}, indent=2))


def cmd_update_page(page_id: str, sets: list[str]) -> None:
    pid = _short_id(page_id)
    props: dict[str, Any] = {}
    for item in sets:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        props[key] = _coerce_property(key, value)

    if not props:
        raise SystemExit("No valid --set values provided.")

    resp = _request("PATCH", f"/pages/{pid}", {"properties": props})
    print(json.dumps({"updated_page_id": resp.get("id")}, indent=2))


def cmd_append_research(
    page_id: str,
    tier: str,
    score: float,
    confidence: float,
    evidence: list[str],
    sources: list[str],
) -> None:
    pid = _short_id(page_id)
    page = _request("GET", f"/pages/{pid}")
    notes = (page.get("properties") or {}).get("Notes", {})
    existing = ""
    if isinstance(notes, dict) and notes.get("type") == "rich_text":
        existing = "".join(
            (part.get("plain_text") or "")
            for part in (notes.get("rich_text") or [])
            if isinstance(part, dict)
        ).strip()

    now = datetime.now(timezone.utc).isoformat()
    lines = [
        f"Lead Research Snapshot - {now}",
        f"Tier: {tier} | Score: {int(round(score))} | Confidence: {confidence:.2f}",
    ]
    for item in evidence[:6]:
        lines.append(f"- {item}")
    if sources:
        lines.append("Source URLs:")
        for url in sources[:6]:
            lines.append(f"- {url}")

    summary = "\n".join(lines)
    combined = summary if not existing else f"{existing}\n\n{summary}"
    if len(combined) > 1800:
        combined = combined[-1800:]

    resp = _request("PATCH", f"/pages/{pid}", {"properties": {"Notes": _rich_text_prop(combined)}})
    print(json.dumps({"updated_page_id": resp.get("id"), "notes_updated": True}, indent=2))


def cmd_publish_guidebook(root_page_id: str, guidebook_dir: str, dry_run: bool) -> None:
    summary = publish_guidebook(root_page_id, guidebook_dir, dry_run=dry_run)
    print(json.dumps(summary, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Direct Notion API helper (without MCP).")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch a page/database by ID.")
    fetch.add_argument("id", help="Notion page or database ID")

    list_dbs = sub.add_parser("list-dbs", help="List accessible databases.")
    list_dbs.add_argument("--query", default="", help="Optional search query")
    list_dbs.add_argument("--limit", type=int, default=25, help="Max databases to list (1-100)")

    query_db = sub.add_parser("query-db", help="Query rows from a database ID.")
    query_db.add_argument("id", help="Database ID")
    query_db.add_argument("--page-size", type=int, default=10, help="Rows to return (1-100)")

    schema = sub.add_parser("schema", help="Fetch database schema.")
    schema.add_argument("--database-id", required=True, help="Database ID")

    create_lead = sub.add_parser("create-lead", help="Create a lead row in a database.")
    create_lead.add_argument("--database-id", required=True, help="Database ID")
    create_lead.add_argument("--name", required=True, help="Lead name (Name title)")
    create_lead.add_argument("--company", default="", help="Company name")
    create_lead.add_argument("--industry", default="", help="Industry text")
    create_lead.add_argument("--website", default="", help="Website URL")
    create_lead.add_argument("--email", default="", help="Email address")
    create_lead.add_argument("--source", default="Web Research", help="Lead source label")
    create_lead.add_argument("--status", default="New", help="Status select option")

    update = sub.add_parser("update", help="Patch lead properties with --set Key=Value.")
    update.add_argument("--page-id", required=True, help="Page ID")
    update.add_argument("--set", action="append", default=[], help="Property assignment: Key=Value")

    append = sub.add_parser("append-research", help="Append a research snapshot to Notes.")
    append.add_argument("--page-id", required=True, help="Page ID")
    append.add_argument("--tier", required=True, help="Lead tier")
    append.add_argument("--score", type=float, required=True, help="Computed score")
    append.add_argument("--confidence", type=float, default=0.7, help="Confidence 0..1")
    append.add_argument("--evidence", action="append", default=[], help="Evidence bullet")
    append.add_argument("--source", action="append", default=[], help="Source URL")

    publish = sub.add_parser("publish-guidebook", help="Publish a local guidebook scaffold into Notion.")
    publish.add_argument("--root-page-id", required=True, help="Existing Notion page that will become the guidebook root")
    publish.add_argument(
        "--guidebook-dir",
        default="agent-office/docs/notion-guidebook",
        help="Path to the local guidebook scaffold directory",
    )
    publish.add_argument("--dry-run", action="store_true", help="Validate inputs and show planned publish actions")

    args = parser.parse_args()
    if args.command == "fetch":
        cmd_fetch(args.id)
    elif args.command == "list-dbs":
        cmd_list_dbs(args.query, args.limit)
    elif args.command == "query-db":
        cmd_query_db(args.id, args.page_size)
    elif args.command == "schema":
        cmd_schema(args.database_id)
    elif args.command == "create-lead":
        cmd_create_lead(
            args.database_id,
            args.name,
            args.company,
            args.industry,
            args.website,
            args.email,
            args.source,
            args.status,
        )
    elif args.command == "update":
        cmd_update_page(args.page_id, args.set)
    elif args.command == "append-research":
        cmd_append_research(args.page_id, args.tier, args.score, args.confidence, args.evidence, args.source)
    elif args.command == "publish-guidebook":
        cmd_publish_guidebook(args.root_page_id, args.guidebook_dir, args.dry_run)
    else:
        raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()
