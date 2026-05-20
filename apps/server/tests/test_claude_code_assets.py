from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_claude_code_project_assets_exist_and_are_bridge_oriented() -> None:
    claude_memory = ROOT / "CLAUDE.md"
    project_mcp = ROOT / ".mcp.json"
    commands_root = ROOT / ".claude" / "commands"

    assert claude_memory.exists()
    assert project_mcp.exists()
    assert commands_root.exists()

    memory_text = claude_memory.read_text(encoding="utf-8")
    assert "bridge between the user and Mission Control" in memory_text
    assert "not inside the Claude chat" in memory_text

    config = json.loads(project_mcp.read_text(encoding="utf-8"))
    server = config["mcpServers"]["mission-control"]
    assert server["command"] == "${MISSION_CONTROL_PYTHON:-python}"
    assert server["args"] == ["scripts/serve-mission-control-mcp.py"]

    expected_commands = {
        "mission-control.md": "mission_control_start_task",
        "mission-control-status.md": "mission_control_get_status",
        "mission-control-approve.md": "mission_control_answer_decision",
        "mission-control-handoff.md": "mission_control_get_handoff_summary",
        "mission-control-resume.md": "mission_control_resume",
        "mission-control-safe-mode.md": "mission_control_enable_safe_mode",
    }
    for filename, tool_name in expected_commands.items():
        command_path = commands_root / filename
        assert command_path.exists(), f"Missing Claude command: {command_path}"
        text = command_path.read_text(encoding="utf-8")
        assert tool_name in text


def test_claude_code_mcp_wrapper_is_importable() -> None:
    module_path = ROOT / "scripts" / "serve-mission-control-mcp.py"
    spec = importlib.util.spec_from_file_location("serve_mission_control_mcp", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module._repo_root() == ROOT
