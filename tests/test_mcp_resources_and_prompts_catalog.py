from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
DOC_PATHS = [
    ROOT / "docs" / "MCP_RESOURCES_AND_PROMPTS.md",
    ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md",
]

REQUIRED_RESOURCES = {
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://orchestrations/{orchestration_id}/status",
}

REQUIRED_PROMPT_ALIASES = [
    {"attach-current-workspace", "attach_current_workspace"},
    {"start-manager-led-task", "start_manager_led_task", "use-mission-control-for-this-repo", "use_mission_control_for_repo"},
    {"continue-orchestration", "continue_orchestration"},
    {"answer-pending-approval", "answer_pending_approval", "show-pending-approvals", "show_pending_approvals"},
    {"review-handoff", "review-latest-handoff", "review_latest_handoff"},
    {"import-existing-repo", "import-existing-codebase", "import_existing_codebase"},
    {"ask-manager-for-plan", "ask_manager_for_plan"},
    {"pause-orchestration", "pause_orchestration"},
    {"resume-orchestration", "resume_orchestration"},
]

CANONICAL_PROMPTS_WITH_CATALOG_RESOURCES = {
    "switch_swarm_strategy",
    "review_latest_handoff",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_contains_required_resource_and_prompt_subsets() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    assert REQUIRED_RESOURCES.issubset(set(manifest["resources"]))
    manifest_prompts = set(manifest["prompts"])
    for aliases in REQUIRED_PROMPT_ALIASES:
        assert manifest_prompts.intersection(aliases), f"Missing required prompt coverage for aliases: {sorted(aliases)}"
    assert manifest["mcp"]["resources_catalog"] == "./mcp/resources.json"


def test_resources_catalog_has_safety_defaults_and_required_resources() -> None:
    catalog = _load_json(RESOURCES_CATALOG)
    assert catalog["safety_defaults"] == {
        "summary_only": True,
        "runs_commands": False,
        "shows_raw_logs": False,
        "redact_secrets": True,
    }

    resources = catalog["resources"]
    resource_names = {item["uri_template"] for item in resources}
    assert REQUIRED_RESOURCES.issubset(resource_names)
    for item in resources:
        assert item["summary"]
        assert item["default_fields"]
        assert item["redaction"]["omit_fields"]
        assert item["redaction"]["notes"]


def test_required_prompt_files_exist_and_are_nonempty() -> None:
    for aliases in REQUIRED_PROMPT_ALIASES:
        existing_paths = [PROMPTS_DIR / f"{prompt_name}.md" for prompt_name in aliases if (PROMPTS_DIR / f"{prompt_name}.md").exists()]
        assert existing_paths, f"Missing required prompt file coverage for aliases: {sorted(aliases)}"
        for prompt_path in existing_paths:
            content = prompt_path.read_text(encoding="utf-8").strip()
            assert content.startswith("# ")
            assert len(content) > 40


def test_selected_canonical_prompt_files_reference_catalog_resources() -> None:
    prompts = {item["name"]: item for item in _load_json(ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json")["prompts"]}

    for prompt_name in CANONICAL_PROMPTS_WITH_CATALOG_RESOURCES:
        prompt = prompts[prompt_name]
        prompt_text = (PROMPTS_DIR / f"{prompt_name}.md").read_text(encoding="utf-8")
        for resource in prompt["resource_sequence"]:
            assert resource in prompt_text, f"{prompt_name} is missing catalog resource {resource}"


def test_docs_explain_tools_resources_prompts_and_redaction() -> None:
    existing_docs = [path for path in DOC_PATHS if path.exists()]
    assert existing_docs, "No MCP resources/prompts documentation files found."
    content = "\n".join(path.read_text(encoding="utf-8") for path in existing_docs)
    assert "MCP Resources" in content
    assert "Prompts" in content
    assert "safe summaries" in content or "read-only resource rules" in content
