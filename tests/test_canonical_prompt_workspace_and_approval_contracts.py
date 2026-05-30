from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"

PROMPT_RESOURCE_EXPECTATIONS = {
    "attach_current_workspace.md": [
        "mission-control://projects/{project_id}/status",
    ],
    "use_mission_control_for_repo.md": [
        "mission-control://orchestrations/{orchestration_id}/status",
        "mission-control://projects/{project_id}/pending-decisions",
    ],
    "show_pending_approvals.md": [
        "mission-control://projects/{project_id}/pending-decisions",
    ],
}


def test_workspace_and_approval_prompt_markdown_mentions_cataloged_resources() -> None:
    for filename, resources in PROMPT_RESOURCE_EXPECTATIONS.items():
        content = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        for resource in resources:
            assert resource in content, f"{filename} is missing {resource}"
