from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_PLUGIN_MODE_DOC = ROOT / "docs" / "CODEX_PLUGIN_MODE.md"
MCP_PLUGIN_BRIDGE_DOC = ROOT / "docs" / "MCP_PLUGIN_BRIDGE.md"


def test_codex_plugin_mode_uses_subset_headings_and_links_to_authoritative_catalogs() -> None:
    content = CODEX_PLUGIN_MODE_DOC.read_text(encoding="utf-8")

    assert "## Current MCP tools" not in content
    assert "## Current MCP resources" not in content
    assert "For the full current MCP tool catalog, see [MCP Tools](MCP_TOOLS.md)." in content
    assert "For the full current MCP resource catalog, see [MCP Resources](MCP_RESOURCES.md)." in content
    assert "mission_control_open_dashboard" not in content
    assert "user's answer back" in content


def test_mcp_plugin_bridge_uses_subset_headings_and_links_to_authoritative_catalogs() -> None:
    content = MCP_PLUGIN_BRIDGE_DOC.read_text(encoding="utf-8")

    assert "## Expected tools" not in content
    assert "## Expected resources" not in content
    assert "The full current tool catalog lives in [MCP Tools](MCP_TOOLS.md)." in content
    assert "The full current resource catalog lives in [MCP Resources](MCP_RESOURCES.md), and the workflow catalog lives in [MCP Prompts](MCP_PROMPTS.md)." in content
