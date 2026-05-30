from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "codex-chat-workflows"


def _content(name: str) -> str:
    return (EXAMPLES / name).read_text(encoding="utf-8")


def test_debug_stuck_example_uses_current_debug_contract() -> None:
    content = _content("debug-stuck-orchestration.md")
    assert "Prompt: `debug-failed-orchestration`" in content
    assert "Tool: `mission_control_get_event_digest`" in content
    assert "Tool: `mission_control_request_recovery_plan`" in content
    assert "Resource: `mission-control://projects/{project_id}/diagnostics`" in content
    assert "Resource: `mission-control://projects/{project_id}/decision-ledger`" in content


def test_enable_safe_mode_example_uses_safe_mode_wrapper() -> None:
    content = _content("enable-safe-mode.md")
    assert "Prompt: `enable-safe-mode`" in content
    assert "Tool: `mission_control_enable_safe_mode`" in content
    assert "Tool: `mission_control_get_diagnostics`" in content
    assert "Resource: `mission-control://projects/{project_id}/diagnostics`" in content
    assert "Resource: `mission-control://projects/{project_id}/path-locks`" in content


def test_review_handoff_example_uses_handoff_summary_contract() -> None:
    content = _content("review-handoff.md")
    assert "Prompt: `review-latest-handoff`" in content
    assert "Tool: `mission_control_get_handoff_summary`" in content
    assert "Resource: `mission-control://projects/{project_id}/handoff`" in content
    assert "Resource: `mission-control://projects/{project_id}/validation-summary`" in content
