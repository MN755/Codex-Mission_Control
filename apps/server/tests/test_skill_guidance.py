from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_core_mission_control_skill_requires_bridge_verification() -> None:
    repo_skill = _read(".codex/skills/mission-control/SKILL.md")
    plugin_skill = _read("plugins/mission-control/skills/mission-control/SKILL.md")

    for content in (repo_skill, plugin_skill):
        assert "Prove the Mission Control bridge surface before guessing" in content
        assert "verify MCP registration or resource visibility" in content
        assert "Do not say the Mission Control MCP surface is unavailable" in content
        assert "codex mcp list" in content


def test_existing_repo_fix_and_import_skills_distinguish_partial_mcp_exposure() -> None:
    repo_fix = _read("plugins/mission-control/skills/mission-control-existing-repo-fix/SKILL.md")
    import_codebase = _read("plugins/mission-control/skills/mission-control-import-codebase/SKILL.md")

    assert "bridge registered but named tools hidden in this session" in repo_fix
    assert "Mission Control registered but only partial MCP capabilities exposed" in import_codebase


def test_health_and_codex_cli_skills_require_precise_partial_bridge_wording() -> None:
    plugin_health = _read("plugins/mission-control/skills/mission-control-plugin-health/SKILL.md")
    codex_cli_mode = _read("plugins/mission-control/skills/mission-control-codex-cli-mode/SKILL.md")

    assert "plugin registered with only partial MCP exposure" in plugin_health
    assert "partial MCP exposure problem" in codex_cli_mode


def test_read_only_intake_skills_verify_bridge_before_declaring_fallback() -> None:
    repo_intake = _read(".codex/skills/mission-control-codebase-intake-burst/SKILL.md")
    plugin_intake = _read("plugins/mission-control/skills/mission-control-codebase-intake-burst/SKILL.md")
    explain_codebase = _read("plugins/mission-control/skills/mission-control-explain-codebase/SKILL.md")

    for content in (repo_intake, plugin_intake, explain_codebase):
        assert "confirm MCP registration or resource visibility" in content
        assert "codex mcp list" in content

    assert "partial MCP exposure" in explain_codebase
