from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md"
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"


def test_mcp_resources_prompts_doc_lists_all_catalog_prompt_names_or_aliases() -> None:
    catalog = json.loads(PROMPTS_CATALOG.read_text(encoding="utf-8"))
    documented_prompts = set(re.findall(r"`([a-z0-9_-]+)`", DOC_PATH.read_text(encoding="utf-8")))

    for prompt in catalog["prompts"]:
        names = {prompt["name"], *prompt.get("aliases", [])}
        assert documented_prompts.intersection(names), f"Missing prompt documentation for: {sorted(names)}"
