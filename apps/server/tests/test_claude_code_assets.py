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
        "mission-control-install.md": "python scripts/mission-control-manage.py install",
        "mission-control-update.md": "python scripts/mission-control-manage.py update",
        "mission-control-uninstall.md": "python scripts/mission-control-manage.py uninstall",
    }
    for filename, tool_name in expected_commands.items():
        command_path = commands_root / filename
        assert command_path.exists(), f"Missing Claude command: {command_path}"
        text = command_path.read_text(encoding="utf-8")
        assert tool_name in text
        if filename in {"mission-control-install.md", "mission-control-update.md"}:
            assert "force-quit and reopen Claude Code and Codex" in text
            assert "Mission Control` as an available plugin" in text
            assert "approve the project MCP server from `.mcp.json`" in text
            assert "rerun `python scripts/mission-control-manage.py update`" in text
        if filename == "mission-control-uninstall.md":
            assert "stale Mission Control plugin or MCP state" in text


def test_packaged_claude_plugin_assets_exist_and_route_through_mission_control() -> None:
    plugin_root = ROOT / "plugins" / "mission-control"
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    bundle_manifest_path = plugin_root / "plugin.json"
    commands_root = plugin_root / "commands"
    agents_root = plugin_root / "agents"

    assert manifest_path.exists()
    assert bundle_manifest_path.exists()
    assert commands_root.exists()
    assert agents_root.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "mission-control"
    assert "Mission Control" in manifest["description"]

    expected_commands = {
        "mission-control.md",
        "mission-control-feature-dev.md",
        "mission-control-code-review.md",
        "mission-control-modernize.md",
        "mission-control-simplify.md",
        "mission-control-security-review.md",
        "mission-control-session-report.md",
        "mission-control-claude-md.md",
        "mission-control-mcp-dev.md",
        "mission-control-plugin-health.md",
        "mission-control-pr-review.md",
        "mission-control-commit-ready.md",
        "mission-control-frontend-design.md",
        "mission-control-understand.md",
        "mission-control-rag-design.md",
        "mission-control-evals.md",
        "mission-control-doc-workflow.md",
        "mission-control-skill-builder.md",
        "mission-control-webapp-testing.md",
    }
    expected_agents = {
        "code-explorer.md",
        "code-architect.md",
        "code-reviewer.md",
        "test-engineer.md",
        "security-auditor.md",
        "legacy-analyst.md",
        "code-simplifier.md",
        "mcp-integrator.md",
        "docs-maintainer.md",
        "release-captain.md",
        "knowledge-graph-builder.md",
        "retrieval-architect.md",
        "evals-analyst.md",
        "document-workflow-specialist.md",
        "skill-packager.md",
    }

    assert expected_commands.issubset({path.name for path in commands_root.glob("*.md")})
    assert expected_agents.issubset({path.name for path in agents_root.glob("*.md")})
    assert set(bundle_manifest["claude_code"]["primary_commands"]).issubset({path.stem for path in commands_root.glob("*.md")})

    for path in commands_root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "Mission Control" in text
        assert "disable-model-invocation" in text
        assert (
            "Mission Control is the Manager" in text
            or "through Mission Control" in text
            or "Ask Mission Control" in text
            or "Run the Mission Control" in text
            or "Use Mission Control" in text
        )

    for path in agents_root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "name:" in text
        assert "description:" in text
        assert "Mission Control" in text


def test_claude_code_mcp_wrapper_is_importable() -> None:
    module_path = ROOT / "scripts" / "serve-mission-control-mcp.py"
    spec = importlib.util.spec_from_file_location("serve_mission_control_mcp", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module._repo_root() == ROOT
