from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
MCP_PROMPTS_DOC = ROOT / "docs" / "MCP_PROMPTS.md"
MCP_RESOURCES_PROMPTS_DOC = ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md"


def _load_prompts() -> list[dict[str, object]]:
    return json.loads(PROMPTS_CATALOG.read_text(encoding="utf-8"))["prompts"]


def test_mcp_prompts_doc_lists_every_canonical_prompt() -> None:
    doc = MCP_PROMPTS_DOC.read_text(encoding="utf-8")
    for prompt in _load_prompts():
        name = prompt["name"]
        assert f"`{name}`" in doc, f"{name} is missing from {MCP_PROMPTS_DOC}"


def test_mcp_resources_prompts_doc_lists_every_hyphenated_alias() -> None:
    doc = MCP_RESOURCES_PROMPTS_DOC.read_text(encoding="utf-8")
    aliases = sorted(
        alias
        for prompt in _load_prompts()
        for alias in prompt.get("aliases", [])
    )
    for alias in aliases:
        assert f"`{alias}`" in doc, f"{alias} is missing from {MCP_RESOURCES_PROMPTS_DOC}"
