from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"

PROMPT_RESOURCE_EXPECTATIONS = {
    "import_existing_codebase.md": [
        "mission-control://projects/{project_id}/codebase-map",
        "mission-control://projects/{project_id}/status",
    ],
    "enable_safe_mode.md": [
        "mission-control://projects/{project_id}/diagnostics",
        "mission-control://projects/{project_id}/path-locks",
    ],
    "generate_agents_md_proposal.md": [
        "mission-control://projects/{project_id}/codebase-map",
        "mission-control://projects/{project_id}/agent-contracts",
    ],
}


def test_import_safe_mode_and_agents_prompt_markdown_mentions_cataloged_resources() -> None:
    for filename, resources in PROMPT_RESOURCE_EXPECTATIONS.items():
        content = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        for resource in resources:
            assert resource in content, f"{filename} is missing {resource}"
