#!/usr/bin/env python3
"""Small direct Notion API helper (no MCP required)."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
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
    backoff_seconds = 1.0
    try:
        while True:
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    if retry_after:
                        try:
                            backoff_seconds = max(float(retry_after), backoff_seconds)
                        except ValueError:
                            pass
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 10.0)
                    continue
                try:
                    parsed = json.loads(body)
                    message = parsed.get("message", body)
                    code = parsed.get("code", "unknown_error")
                except json.JSONDecodeError:
                    message = body
                    code = "unknown_error"
                raise SystemExit(f"Notion API error ({exc.code}, {code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Notion API request failed: {exc.reason}") from exc


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


def _load_json_list(path: Path) -> list[dict[str, Any]]:
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
    for idx in range(0, len(blocks), 100):
        chunk = blocks[idx:idx + 100]
        _request("PATCH", f"/blocks/{block_id}/children", {"children": chunk})


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "workspace"


def _default_state_path(workspace_title: str) -> Path:
    return Path("/tmp") / "apple-flow-notion" / f"{_slugify(workspace_title)}.json"


def _default_row_key(record: dict[str, Any], fallback_index: int) -> str:
    if record.get("id"):
        return str(record["id"])
    for key in ("Name", "Document Name", "Session Name", "Resource Name", "Workflow Name", "Participant Name", "Item", "Issue / Question"):
        value = str(record.get(key, "")).strip()
        if value:
            return _slugify(value)
    return f"row-{fallback_index}"


def _load_state(path: Path, workspace_id: str) -> dict[str, Any]:
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("workspace_id", workspace_id)
    state.setdefault("hub_page", {})
    state.setdefault("hub_content_appended", False)
    state.setdefault("pages", {})
    state.setdefault("databases", {})
    state.setdefault("database_rows", {})
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


class _BatchThrottle:
    def __init__(self, batch_size: int, sleep_seconds: float) -> None:
        self.batch_size = max(batch_size, 1)
        self.sleep_seconds = max(sleep_seconds, 0.0)
        self.operations = 0

    def after_mutation(self) -> None:
        if self.sleep_seconds <= 0:
            return
        self.operations += 1
        if self.operations % self.batch_size == 0:
            time.sleep(self.sleep_seconds)


def _throttled_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    throttle: _BatchThrottle | None,
) -> dict[str, Any]:
    response = _request(method, path, payload)
    if throttle is not None and method in {"POST", "PATCH"}:
        throttle.after_mutation()
    return response


def _append_blocks_throttled(
    block_id: str,
    blocks: list[dict[str, Any]],
    throttle: _BatchThrottle | None,
) -> None:
    if not blocks:
        return
    for idx in range(0, len(blocks), 100):
        chunk = blocks[idx:idx + 100]
        _throttled_request(
            "PATCH",
            f"/blocks/{block_id}/children",
            {"children": chunk},
            throttle,
        )


def _manual_view_blocks(manual_views: dict[str, list[str]]) -> list[dict[str, Any]]:
    if not manual_views:
        return []
    blocks = [_heading_block(2, "Manual Saved Views")]
    blocks.append(
        _paragraph_block(
            "Notion saved views still need to be created in the UI after this publish completes."
        )
    )
    for database_title, view_names in manual_views.items():
        blocks.append(_heading_block(3, database_title))
        for view_name in view_names:
            blocks.append(_bulleted_item_block(view_name))
    return blocks


def _build_properties_from_schema(schema: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for prop in schema.get("properties", []):
        prop_name = prop["name"]
        prop_type = prop["type"]
        raw_value = values.get(prop_name)
        if raw_value in (None, ""):
            continue
        if prop_type == "title":
            properties[prop_name] = _title_prop(str(raw_value))
        elif prop_type == "date":
            properties[prop_name] = _date_prop(str(raw_value))
        elif prop_type == "checkbox":
            properties[prop_name] = {"checkbox": bool(raw_value)}
        elif prop_type == "select":
            properties[prop_name] = _select_prop(str(raw_value))
        elif prop_type == "url":
            properties[prop_name] = _url_prop(str(raw_value))
        elif prop_type == "email":
            properties[prop_name] = _email_prop(str(raw_value))
        elif prop_type == "number":
            properties[prop_name] = _number_prop(float(raw_value))
        else:
            properties[prop_name] = _rich_text_prop(str(raw_value))
    return properties


def _build_database_row_payload(database_id: str, schema: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    return {
        "parent": {"database_id": database_id},
        "properties": _build_properties_from_schema(schema, values),
    }


def _load_workspace_manifest(workspace_dir: Path) -> dict[str, Any]:
    manifest = _load_json(workspace_dir / "manifest.json")
    pages: list[dict[str, Any]] = []
    for page in manifest.get("pages", []):
        page_copy = dict(page)
        page_copy["content"] = (workspace_dir / page["file"]).read_text(encoding="utf-8")
        pages.append(page_copy)

    databases: list[dict[str, Any]] = []
    for database in manifest.get("databases", []):
        db_copy = dict(database)
        db_copy["schema"] = _load_json(workspace_dir / database["schema_file"])
        seed_file = database.get("seed_file")
        db_copy["seed_rows"] = _load_json_list(workspace_dir / seed_file) if seed_file else []
        databases.append(db_copy)

    home_file = manifest.get("home_file")
    home_markdown = (workspace_dir / home_file).read_text(encoding="utf-8") if home_file else ""

    return {
        "workspace_title": manifest["workspace_title"],
        "workspace_intro": manifest.get("workspace_intro", ""),
        "workspace_id": manifest.get("workspace_id", _slugify(manifest["workspace_title"])),
        "home_markdown": home_markdown,
        "pages": pages,
        "databases": databases,
        "manual_views": manifest.get("manual_views", {}),
    }


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


def publish_workspace(
    root_page_id: str,
    workspace_dir: str,
    dry_run: bool = False,
    *,
    state_path: str | None = None,
    batch_size: int = 5,
    sleep_seconds: float = 0.75,
) -> dict[str, Any]:
    root_id = _short_id(root_page_id)
    workspace_path = Path(workspace_dir)
    spec = _load_workspace_manifest(workspace_path)
    state_file = Path(state_path) if state_path else _default_state_path(spec["workspace_title"])
    state = _load_state(state_file, spec["workspace_id"])

    root_page = _request("GET", f"/pages/{root_id}")
    existing_children = _list_child_titles(root_id)
    workspace_title = spec["workspace_title"]
    existing_hub_in_state = ((state.get("hub_page") or {}).get("title") or "").strip() == workspace_title
    if workspace_title in existing_children["pages"] and not existing_hub_in_state:
        raise SystemExit(f"Workspace content already exists under root page: {workspace_title}")

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "hub_parent_id": root_id,
        "hub_parent_title": _page_title(root_page),
        "workspace_title": workspace_title,
        "page_titles": [page["title"] for page in spec["pages"]],
        "database_titles": [database["title"] for database in spec["databases"]],
        "manual_views": spec["manual_views"],
    }
    if dry_run:
        return summary

    throttle = _BatchThrottle(batch_size=batch_size, sleep_seconds=sleep_seconds)

    hub_page = state.get("hub_page") or {}
    if not hub_page:
        hub_response = _throttled_request(
            "POST",
            "/pages",
            _build_page_payload(root_id, workspace_title),
            throttle,
        )
        hub_page = {
            "id": hub_response["id"],
            "title": workspace_title,
            "url": hub_response.get("url", ""),
        }
        state["hub_page"] = hub_page
        _save_state(state_file, state)

    if not state.get("hub_content_appended"):
        hub_blocks = _markdown_to_blocks(spec["home_markdown"])
        hub_blocks.extend(_manual_view_blocks(spec["manual_views"]))
        if hub_blocks:
            _append_blocks_throttled(hub_page["id"], hub_blocks, throttle)
        state["hub_content_appended"] = True
        _save_state(state_file, state)

    created_pages: list[dict[str, str]] = []
    for page in spec["pages"]:
        existing_page = state["pages"].get(page["id"])
        if existing_page:
            created_pages.append(existing_page)
            continue
        page_response = _throttled_request(
            "POST",
            "/pages",
            _build_page_payload(hub_page["id"], page["title"]),
            throttle,
        )
        page_info = {
            "id": page_response["id"],
            "title": page["title"],
            "url": page_response.get("url", ""),
        }
        blocks = _markdown_to_blocks(page["content"])
        if blocks:
            _append_blocks_throttled(page_info["id"], blocks, throttle)
        state["pages"][page["id"]] = page_info
        _save_state(state_file, state)
        created_pages.append(page_info)

    created_databases: list[dict[str, str]] = []
    for database in spec["databases"]:
        existing_database = state["databases"].get(database["id"])
        if existing_database:
            created_databases.append(existing_database)
            db_info = existing_database
        else:
            database_response = _throttled_request(
                "POST",
                "/databases",
                _build_database_payload(hub_page["id"], database["schema"]),
                throttle,
            )
            db_info = {
                "id": database_response["id"],
                "title": database["title"],
                "url": database_response.get("url", ""),
            }
            state["databases"][database["id"]] = db_info
            _save_state(state_file, state)
            created_databases.append(db_info)

        row_state = state["database_rows"].setdefault(database["id"], {})
        for idx, record in enumerate(database.get("seed_rows", []), start=1):
            row_key = _default_row_key(record, idx)
            if row_key in row_state:
                continue
            row_response = _throttled_request(
                "POST",
                "/pages",
                _build_database_row_payload(db_info["id"], database["schema"], record),
                throttle,
            )
            row_state[row_key] = {
                "id": row_response["id"],
                "url": row_response.get("url", ""),
            }
            _save_state(state_file, state)

    summary["created_hub_page"] = hub_page
    summary["created_pages"] = created_pages
    summary["created_databases"] = created_databases
    summary["state_path"] = str(state_file)
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


def cmd_publish_workspace(
    root_page_id: str,
    workspace_dir: str,
    dry_run: bool,
    state_path: str | None,
    batch_size: int,
    sleep_seconds: float,
) -> None:
    summary = publish_workspace(
        root_page_id,
        workspace_dir,
        dry_run=dry_run,
        state_path=state_path,
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
    )
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

    workspace = sub.add_parser("publish-workspace", help="Publish a multi-page, multi-database Notion workspace scaffold.")
    workspace.add_argument("--root-page-id", required=True, help="Existing Notion page that will become the workspace parent")
    workspace.add_argument("--workspace-dir", required=True, help="Path to the local workspace scaffold directory")
    workspace.add_argument("--dry-run", action="store_true", help="Validate inputs and show planned publish actions")
    workspace.add_argument("--state-path", default="", help="Optional local JSON checkpoint path for resumable publishing")
    workspace.add_argument("--batch-size", type=int, default=5, help="Mutating request count before pausing briefly")
    workspace.add_argument("--sleep-seconds", type=float, default=0.75, help="Pause duration between batches")

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
    elif args.command == "publish-workspace":
        cmd_publish_workspace(
            args.root_page_id,
            args.workspace_dir,
            args.dry_run,
            args.state_path.strip() or None,
            args.batch_size,
            args.sleep_seconds,
        )
    else:
        raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()
