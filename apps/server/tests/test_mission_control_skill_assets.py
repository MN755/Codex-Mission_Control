from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_root_mission_control_skill_references_only_exposed_tools() -> None:
    skill_path = ROOT / "plugins" / "mission-control" / "skills" / "mission-control" / "SKILL.md"
    server_path = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "server.py"

    skill_text = skill_path.read_text(encoding="utf-8")
    server_text = server_path.read_text(encoding="utf-8")

    referenced_tools = set(re.findall(r"`(mission_control_[a-z0-9_]+)`", skill_text))
    exposed_tools = set(re.findall(r"\"(mission_control_[a-z0-9_]+)\"\s*:", server_text))

    assert "mission_control_open_dashboard" not in referenced_tools
    assert referenced_tools <= exposed_tools
