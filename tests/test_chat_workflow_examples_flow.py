from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "codex-chat-workflows"


def _content(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def test_use_mission_control_current_repo_example_matches_published_sequence() -> None:
    content = _content("use-mission-control-for-current-repo.md")
    assert "Prompt: `use-mission-control-for-this-repo`" in content
    assert "Tool: `mission_control_get_status`" in content
    assert "Resource: `mission-control://orchestrations/{orchestration_id}/status`" in content
    assert "Tool: `mission_control_get_pending_decisions`" in content
    assert "Resource: `mission-control://projects/{project_id}/pending-decisions`" in content


def test_check_status_example_uses_continue_orchestration_tool_flow() -> None:
    content = _content("check-status.md")
    assert "Prompt: `continue-orchestration`" in content
    assert "Tool: `mission_control_get_status`" in content
    assert "Tool: `mission_control_get_pending_decisions`" in content
    assert "Tool: `mission_control_get_event_digest`" in content
    assert "Resource: `mission-control://projects/{project_id}/agents`" in content
    assert "Resource: `mission-control://projects/{project_id}/pending-decisions`" in content


def test_import_existing_codebase_example_uses_wrapper_flow() -> None:
    content = _content("import-existing-codebase.md")
    assert "Prompt: `import-existing-codebase`" in content
    assert "Tool: `mission_control_import_existing_codebase`" in content
    assert "Resource: `mission-control://projects/{project_id}/codebase-map`" in content
    assert "Resource: `mission-control://projects/{project_id}/status`" in content
    assert "Tool: `mission_control_set_import_interview_choice`" in content
    assert "Tool: `mission_control_start_task`" in content
