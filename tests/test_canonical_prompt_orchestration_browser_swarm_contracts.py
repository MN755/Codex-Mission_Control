from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"

PROMPT_RESOURCE_EXPECTATIONS = {
    "continue_orchestration.md": [
        "mission-control://orchestrations/{orchestration_id}/status",
        "mission-control://projects/{project_id}/agents",
        "mission-control://projects/{project_id}/pending-decisions",
    ],
    "use_webwright_for_browser_task.md": [
        "mission-control://projects/{project_id}/webwright",
        "mission-control://projects/{project_id}/status",
    ],
    "explain_current_swarm.md": [
        "mission-control://projects/{project_id}/swarm-plan",
        "mission-control://projects/{project_id}/agents",
        "mission-control://projects/{project_id}/risk-register",
    ],
}


def test_orchestration_browser_and_swarm_prompt_markdown_mentions_cataloged_resources() -> None:
    for filename, resources in PROMPT_RESOURCE_EXPECTATIONS.items():
        content = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        for resource in resources:
            assert resource in content, f"{filename} is missing {resource}"
