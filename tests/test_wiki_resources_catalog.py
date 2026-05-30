from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
RESOURCES_WIKI = ROOT / "wiki-staging" / "MCP-Resources-Catalog.md"


def test_wiki_resources_catalog_lists_all_current_resource_uris() -> None:
    content = RESOURCES_WIKI.read_text(encoding="utf-8")
    catalog = json.loads(RESOURCES_CATALOG.read_text(encoding="utf-8"))

    for item in catalog["resources"]:
        assert f"`{item['uri_template']}`" in content
