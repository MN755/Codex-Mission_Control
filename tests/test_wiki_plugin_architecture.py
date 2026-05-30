from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE_WIKI = ROOT / "wiki-staging" / "MCP-Plugin-Architecture.md"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
SERVER_PATH = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "server.py"


def test_wiki_plugin_architecture_lists_all_current_tool_names() -> None:
    content = ARCHITECTURE_WIKI.read_text(encoding="utf-8")
    tool_names = re.findall(r'"name": "(mission_control_[A-Za-z0-9_]+)"', SERVER_PATH.read_text(encoding="utf-8"))

    for tool_name in tool_names:
        assert f"`{tool_name}`" in content


def test_wiki_plugin_architecture_lists_all_current_resource_uris() -> None:
    content = ARCHITECTURE_WIKI.read_text(encoding="utf-8")
    catalog = json.loads(RESOURCES_CATALOG.read_text(encoding="utf-8"))

    for item in catalog["resources"]:
        assert f"`{item['uri_template']}`" in content
