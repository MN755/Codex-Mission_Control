from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
MCP_RESOURCES_PROMPTS_DOC = ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md"


def test_mcp_resources_prompts_doc_lists_every_resource_uri() -> None:
    doc = MCP_RESOURCES_PROMPTS_DOC.read_text(encoding="utf-8")
    resources = json.loads(RESOURCES_CATALOG.read_text(encoding="utf-8"))["resources"]
    for resource in resources:
        uri_template = resource["uri_template"]
        assert f"`{uri_template}`" in doc, f"{uri_template} is missing from {MCP_RESOURCES_PROMPTS_DOC}"
