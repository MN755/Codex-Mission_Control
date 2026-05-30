from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md"
RESOURCE_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"


def test_mcp_resources_prompts_doc_lists_all_catalog_resources() -> None:
    catalog = json.loads(RESOURCE_CATALOG.read_text(encoding="utf-8"))
    documented_resources = set(re.findall(r"`(mission-control://[^`]+)`", DOC_PATH.read_text(encoding="utf-8")))
    catalog_resources = {item["uri_template"] for item in catalog["resources"]}

    assert catalog_resources.issubset(documented_resources)
