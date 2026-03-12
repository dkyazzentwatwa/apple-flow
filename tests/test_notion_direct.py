from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    script_path = ROOT / "scripts" / "notion_direct.py"
    spec = importlib.util.spec_from_file_location("notion_direct", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_markdown_to_blocks_skips_h1_and_maps_sections():
    notion_direct = _load_module()

    blocks = notion_direct._markdown_to_blocks(
        "# Start Here\n\n"
        "Intro paragraph.\n\n"
        "## Fastest Path\n\n"
        "- Install one connector\n"
        "- Configure .env\n\n"
        "1. Validate config\n"
        "2. Send smoke test\n"
    )

    assert [block["type"] for block in blocks] == [
        "paragraph",
        "heading_2",
        "bulleted_list_item",
        "bulleted_list_item",
        "numbered_list_item",
        "numbered_list_item",
    ]
    assert "Start Here" not in json.dumps(blocks)


def test_extract_callout_uses_suggested_callout_section():
    notion_direct = _load_module()

    callout = notion_direct._extract_callout(
        "# Notion Page Tree\n\n"
        "Root page: `Codex Flow User Guide`\n\n"
        "Suggested callout at the top of the root page:\n\n"
        "`Local files and Apple Flow runtime state are canonical.`\n"
    )

    assert callout == "Local files and Apple Flow runtime state are canonical."


def test_build_database_payload_uses_schema_properties_and_parent():
    notion_direct = _load_module()

    schema = {
        "title": "Automation Process Log",
        "properties": [
            {"name": "Title", "type": "title"},
            {"name": "Timestamp", "type": "date"},
            {"name": "Process Type", "type": "select", "options": ["Run", "Approval"]},
            {"name": "Follow-up Needed", "type": "checkbox"},
        ],
    }

    payload = notion_direct._build_database_payload("page-123", schema)

    assert payload["parent"] == {"type": "page_id", "page_id": "page-123"}
    assert payload["title"][0]["text"]["content"] == "Automation Process Log"
    assert payload["properties"]["Title"] == {"title": {}}
    assert payload["properties"]["Timestamp"] == {"date": {}}
    assert payload["properties"]["Process Type"]["select"]["options"] == [
        {"name": "Run"},
        {"name": "Approval"},
    ]
    assert payload["properties"]["Follow-up Needed"] == {"checkbox": {}}


def test_publish_guidebook_dry_run_reports_pages_and_database(tmp_path, monkeypatch):
    notion_direct = _load_module()
    guidebook_dir = tmp_path / "notion-guidebook"
    pages_dir = guidebook_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "start-here.md").write_text("# Start Here\n\nIntro paragraph.\n", encoding="utf-8")
    (guidebook_dir / "manifest.json").write_text(
        json.dumps(
            {
                "guidebook_title": "Codex Flow User Guide",
                "pages": [
                    {
                        "title": "Start Here",
                        "file": "pages/start-here.md",
                        "purpose": "Orient operators.",
                    }
                ],
                "database": {"title": "Automation Process Log", "schema_file": "automation-process-log-schema.json"},
            }
        ),
        encoding="utf-8",
    )
    (guidebook_dir / "page-tree.md").write_text(
        "# Notion Page Tree\n\nSuggested callout at the top of the root page:\n\n"
        "`Local files are canonical.`\n",
        encoding="utf-8",
    )
    (guidebook_dir / "automation-process-log-schema.json").write_text(
        json.dumps({"title": "Automation Process Log", "properties": [{"name": "Title", "type": "title"}]}),
        encoding="utf-8",
    )

    calls: list[tuple[str, str, object | None]] = []

    def fake_request(method: str, path: str, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {"rich_text": []},
                    }
                ]
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    summary = notion_direct.publish_guidebook("root-page", str(guidebook_dir), dry_run=True)

    assert summary["dry_run"] is True
    assert summary["root_page_id"] == "root-page"
    assert summary["page_titles"] == ["Start Here"]
    assert summary["database_title"] == "Automation Process Log"
    assert any(path == "/blocks/root-page/children?page_size=100" for _, path, _ in calls)


def test_publish_guidebook_rejects_existing_child_title_collision(tmp_path, monkeypatch):
    notion_direct = _load_module()
    guidebook_dir = tmp_path / "notion-guidebook"
    pages_dir = guidebook_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "setup.md").write_text("# Setup\n\nConfig steps.\n", encoding="utf-8")
    (guidebook_dir / "manifest.json").write_text(
        json.dumps(
            {
                "guidebook_title": "Codex Flow User Guide",
                "pages": [{"title": "Setup", "file": "pages/setup.md", "purpose": "Setup flow."}],
                "database": {"title": "Automation Process Log", "schema_file": "automation-process-log-schema.json"},
            }
        ),
        encoding="utf-8",
    )
    (guidebook_dir / "page-tree.md").write_text("# Notion Page Tree\n", encoding="utf-8")
    (guidebook_dir / "automation-process-log-schema.json").write_text(
        json.dumps({"title": "Automation Process Log", "properties": [{"name": "Title", "type": "title"}]}),
        encoding="utf-8",
    )

    def fake_request(method: str, path: str, payload=None):
        if method == "GET" and path == "/pages/root-page":
            return {"id": "root-page", "url": "https://example.com/root"}
        if method == "GET" and path == "/blocks/root-page/children?page_size=100":
            return {
                "results": [
                    {
                        "type": "child_page",
                        "child_page": {"title": "Setup"},
                    }
                ]
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    monkeypatch.setattr(notion_direct, "_request", fake_request)

    with pytest.raises(SystemExit, match="already exists"):
        notion_direct.publish_guidebook("root-page", str(guidebook_dir), dry_run=True)
