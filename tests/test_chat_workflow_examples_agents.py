from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "codex-chat-workflows"


def test_generate_agents_example_uses_current_prompt_contract() -> None:
    content = (EXAMPLES / "generate-agents-md.md").read_text(encoding="utf-8")
    assert "Prompt: `generate-agents-md-proposal`" in content
    assert "Tool: `mission_control_get_codebase_map`" in content
    assert "Tool: `mission_control_get_agents_md_status`" in content
    assert "Resource: `mission-control://projects/{project_id}/codebase-map`" in content
    assert "Resource: `mission-control://projects/{project_id}/agent-contracts`" in content
    assert "Tool: `mission_control_generate_agents_md`" in content
