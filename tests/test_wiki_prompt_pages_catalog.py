from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
PROMPTS_WIKI = ROOT / "wiki-staging" / "MCP-Prompts-Catalog.md"
SKILLS_WIKI = ROOT / "wiki-staging" / "Skills-and-Prompts.md"


def _prompt_names() -> list[str]:
    catalog = json.loads(PROMPTS_CATALOG.read_text(encoding="utf-8"))
    return [item["name"] for item in catalog["prompts"]]


def test_wiki_prompt_catalog_lists_all_current_prompt_names() -> None:
    content = PROMPTS_WIKI.read_text(encoding="utf-8")
    for prompt_name in _prompt_names():
        assert f"`{prompt_name}`" in content


def test_skills_and_prompts_page_covers_current_prompt_names_and_shipped_helpers() -> None:
    content = SKILLS_WIKI.read_text(encoding="utf-8")
    for prompt_name in _prompt_names():
        assert f"`{prompt_name}`" in content

    assert "`mission-control-install-from-github`" in content
    assert "`mission-control-autowire-providers`" in content
    assert "If those specific skills are not present yet" not in content
