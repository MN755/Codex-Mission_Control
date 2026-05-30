from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
REPO_LOCAL_PLUGIN_MANIFEST = ROOT / ".codex" / "plugins" / "mission-control" / "plugin.json"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
EXAMPLES_DIR = ROOT / "examples" / "codex-chat-workflows"
DOC_PATHS = [
    ROOT / "docs" / "MCP_RESOURCES_AND_PROMPTS.md",
    ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md",
]
PROMPTS_DOC = ROOT / "docs" / "MCP_PROMPTS.md"
PLUGIN_MODE_DOC = ROOT / "docs" / "CODEX_PLUGIN_MODE.md"
PLUGIN_BRIDGE_DOC = ROOT / "docs" / "MCP_PLUGIN_BRIDGE.md"
WORKFLOW_DOC = ROOT / "docs" / "CODEX_CHAT_WORKFLOWS.md"
WIKI_PLUGIN_ARCH_DOC = ROOT / "wiki-staging" / "MCP-Plugin-Architecture.md"
WIKI_RESOURCES_DOC = ROOT / "wiki-staging" / "MCP-Resources-Catalog.md"
WIKI_PROMPTS_DOC = ROOT / "wiki-staging" / "MCP-Prompts-Catalog.md"
WIKI_SKILLS_PROMPTS_DOC = ROOT / "wiki-staging" / "Skills-and-Prompts.md"
REPO_LOCAL_PLUGIN_README = ROOT / ".codex" / "plugins" / "mission-control" / "README.md"

REQUIRED_RESOURCES = {
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_contains_required_resource_and_prompt_subsets() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    assert REQUIRED_RESOURCES.issubset(set(manifest["resources"]))
    manifest_prompts = set(manifest["prompts"])
    for aliases in REQUIRED_PROMPT_ALIASES:
        assert manifest_prompts.intersection(aliases), f"Missing required prompt coverage for aliases: {sorted(aliases)}"
    assert manifest["mcp"]["resources_catalog"] == "./mcp/resources.json"


def test_repo_local_plugin_manifest_tracks_required_prompt_and_resource_surface() -> None:
    manifest = _load_json(REPO_LOCAL_PLUGIN_MANIFEST)
    prompt_names = set(manifest["prompts"])
    resources = set(manifest["resources"])

    assert "ask_manager_for_plan" in prompt_names
    assert "use_webwright_for_browser_task" in prompt_names

    for resource in [
        "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
        "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events",
        "mission-control://projects/{project_id}/workspace-tooling",
        "mission-control://projects/{project_id}/webwright",
        "mission-control://projects/{project_id}/operator-snapshot",
        "mission-control://projects/{project_id}/instincts",
        "mission-control://projects/{project_id}/verification-brief",
    ]:
        assert resource in resources

    assert "mission-control://orchestrations/{orchestration_id}/status" not in resources
    assert "mission-control://orchestrations/{orchestration_id}/events" not in resources


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


def test_docs_explain_tools_resources_prompts_and_redaction() -> None:
    existing_docs = [path for path in DOC_PATHS if path.exists()]
    assert existing_docs, "No MCP resources/prompts documentation files found."
    content = "\n".join(path.read_text(encoding="utf-8") for path in existing_docs)
    assert "MCP Resources" in content
    assert "Prompts" in content
    assert "safe summaries" in content or "read-only resource rules" in content


def test_repo_local_plugin_readme_links_only_existing_docs() -> None:
    content = REPO_LOCAL_PLUGIN_README.read_text(encoding="utf-8")
    for link in [
        "../../../docs/CODEX_PLUGIN_MODE.md",
        "../../../docs/MCP_RESOURCES_PROMPTS.md",
        "../../../wiki-staging/Install-From-Codex.md",
    ]:
        assert link in content
        assert (REPO_LOCAL_PLUGIN_README.parent / link).resolve().exists()


def test_docs_and_wiki_track_full_resource_catalog() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    docs_content = (ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md").read_text(encoding="utf-8")
    wiki_content = WIKI_RESOURCES_DOC.read_text(encoding="utf-8")

    for resource in manifest["resources"]:
        assert resource in docs_content, f"Missing resource in docs/MCP_RESOURCES_PROMPTS.md: {resource}"
        assert resource in wiki_content, f"Missing resource in wiki-staging/MCP-Resources-Catalog.md: {resource}"


def test_prompt_docs_include_current_canonical_prompts_and_aliases() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    prompt_catalog = _load_json(PROMPTS_CATALOG)
    prompts_doc = PROMPTS_DOC.read_text(encoding="utf-8")
    resources_prompts_doc = (ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md").read_text(encoding="utf-8")
    wiki_prompts_doc = WIKI_PROMPTS_DOC.read_text(encoding="utf-8").lower()
    wiki_skills_doc = WIKI_SKILLS_PROMPTS_DOC.read_text(encoding="utf-8").lower()

    for prompt_name in manifest["prompts"]:
        assert prompt_name in prompts_doc, f"Missing canonical prompt in docs/MCP_PROMPTS.md: {prompt_name}"

    for token in [
        "use-webwright-for-browser-task",
        "install-from-github",
        "autowire-providers",
        "ask-manager-for-plan",
    ]:
        assert token in resources_prompts_doc, f"Missing prompt alias in docs/MCP_RESOURCES_PROMPTS.md: {token}"

    for title in [item["title"].lower() for item in prompt_catalog["prompts"]]:
        assert title in wiki_prompts_doc, f"Missing prompt title in wiki-staging/MCP-Prompts-Catalog.md: {title}"

    assert "mission-control-install-from-github" in wiki_skills_doc
    assert "mission-control-autowire-providers" in wiki_skills_doc


def test_bridge_docs_include_current_tools_and_advanced_resources() -> None:
    plugin_mode = PLUGIN_MODE_DOC.read_text(encoding="utf-8")
    plugin_bridge = PLUGIN_BRIDGE_DOC.read_text(encoding="utf-8")
    wiki_bridge = WIKI_PLUGIN_ARCH_DOC.read_text(encoding="utf-8")

    for token in [
        "mission_control_get_workspace_tooling",
        "mission_control_get_diagnostics",
        "mission_control_get_nvidia_local_runtime_status",
        "mission_control_generate_swarm_plan",
        "mission_control_get_tool_catalog",
        "mission_control_request_recovery_options",
        "mission-control://projects/{project_id}/workspace-tooling",
        "mission-control://projects/{project_id}/nvidia-validation-plan",
        "mission-control://projects/{project_id}/decision-ledger",
        "mission-control://projects/{project_id}/operator-snapshot",
    ]:
        assert token in plugin_mode or token in plugin_bridge
        assert token in plugin_bridge, f"Missing token in docs/MCP_PLUGIN_BRIDGE.md: {token}"
        assert token in wiki_bridge, f"Missing token in wiki-staging/MCP-Plugin-Architecture.md: {token}"


def test_workflow_index_lists_all_shipped_examples() -> None:
    workflow_doc = WORKFLOW_DOC.read_text(encoding="utf-8")
    for example in EXAMPLES_DIR.glob("*.md"):
        assert example.name in workflow_doc, f"Missing workflow example link in docs/CODEX_CHAT_WORKFLOWS.md: {example.name}"


def test_examples_match_current_prompt_and_resource_contracts() -> None:
    examples: dict[str, list[str]] = {
        "use-mission-control-for-current-repo.md": [
            "mission_control_get_status",
            "mission-control://projects/{project_id}/pending-decisions",
        ],
        "check-status.md": [
            "mission_control_get_event_digest",
            "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
        ],
        "debug-stuck-orchestration.md": [
            "mission_control_get_event_digest",
            "mission_control_request_recovery_plan",
            "mission-control://projects/{project_id}/decision-ledger",
        ],
        "enable-safe-mode.md": [
            "mission_control_enable_safe_mode",
            "mission-control://projects/{project_id}/path-locks",
        ],
        "generate-agents-md.md": [
            "mission_control_generate_agents_md",
            "mission-control://projects/{project_id}/agent-contracts",
        ],
        "import-existing-codebase.md": [
            "mission_control_import_existing_codebase",
            "mission-control://projects/{project_id}/status",
        ],
        "review-handoff.md": [
            "mission_control_get_handoff_summary",
            "mission-control://projects/{project_id}/handoff",
        ],
        "approve-command.md": [
            "answer-pending-approval",
            "mission_control_get_pending_decisions",
        ],
        "answer-manager-question.md": [
            "answer-pending-approval",
            "mission_control_get_pending_decisions",
        ],
        "continue-later.md": [
            "continue-orchestration",
            "mission_control_get_event_digest",
            "resume-orchestration",
        ],
    }

    for filename, required_tokens in examples.items():
        content = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
        for token in required_tokens:
            assert token in content, f"Missing token in {filename}: {token}"
