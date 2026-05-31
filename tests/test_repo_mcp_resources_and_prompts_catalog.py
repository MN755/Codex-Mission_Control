from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
REPO_LOCAL_PLUGIN_MANIFEST = ROOT / ".codex" / "plugins" / "mission-control" / "plugin.json"
CANONICAL_CODEX_PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json"
REPO_LOCAL_CODEX_PLUGIN_MANIFEST = ROOT / ".codex" / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
REPO_LOCAL_PROMPTS_DIR = ROOT / ".codex" / "plugins" / "mission-control" / "prompts"
REPO_LOCAL_MCP_DIR = ROOT / ".codex" / "plugins" / "mission-control" / "mcp"
CANONICAL_SKILLS_DIR = ROOT / "plugins" / "mission-control" / "skills"
REPO_LOCAL_SKILLS_DIR = ROOT / ".codex" / "plugins" / "mission-control" / "skills"
CANONICAL_README = ROOT / "plugins" / "mission-control" / "README.md"
REPO_LOCAL_README = ROOT / ".codex" / "plugins" / "mission-control" / "README.md"
CANONICAL_ASSETS_DIR = ROOT / "plugins" / "mission-control" / "assets"
REPO_LOCAL_ASSETS_DIR = ROOT / ".codex" / "plugins" / "mission-control" / "assets"
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
WIKI_INSTALL_DOC = ROOT / "wiki-staging" / "Install-From-Codex.md"
WIKI_HEADLESS_INSTALL_DOC = ROOT / "wiki-staging" / "Headless-Install-and-Autowire.md"
HEADLESS_INSTALL_DOC = ROOT / "docs" / "HEADLESS_INSTALL.md"
INSTALL_SCRIPT = ROOT / "scripts" / "install-mission-control-plugin.ps1"

REQUIRED_RESOURCES = {
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
    "mission-control://projects/{project_id}/capability-report/{section_key}",
}

REQUIRED_PROMPT_ALIASES = [
    {"attach-current-workspace", "attach_current_workspace"},
    {"start-manager-led-task", "start_manager_led_task", "use-mission-control-for-this-repo", "use_mission_control_for_repo"},
    {"continue-orchestration", "continue_orchestration"},
    {"answer-pending-approval", "answer_pending_approval", "show-pending-approvals", "show_pending_approvals"},
    {"review-handoff", "review-latest-handoff", "review_latest_handoff"},
    {"import-existing-repo", "import-existing-codebase", "import_existing_codebase"},
    {"ask-manager-for-plan", "ask_manager_for_plan"},
    {"review-project-capabilities", "review_project_capabilities"},
    {"review-project-capability-section", "review_project_capability_section"},
    {"pause-orchestration", "pause_orchestration"},
    {"resume-orchestration", "resume_orchestration"},
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _prompt_entries() -> list[dict]:
    return list(_load_json(PROMPTS_CATALOG)["prompts"])


def _supported_install_flags() -> set[str]:
    param_block = INSTALL_SCRIPT.read_text(encoding="utf-8").split("Set-StrictMode", 1)[0]
    return {f"-{name}" for name in re.findall(r"\[(?:string|switch|int)\]\$(\w+)", param_block)}


def _expected_prompt_stems() -> set[str]:
    stems: set[str] = set()
    for prompt in _prompt_entries():
        stems.add(str(prompt["name"]))
        stems.update(str(alias) for alias in list(prompt.get("aliases") or []))
    return stems


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


def test_prompt_directories_match_catalog_exactly() -> None:
    expected_stems = _expected_prompt_stems()
    actual_stems = {path.stem for path in PROMPTS_DIR.glob("*.md")}
    repo_local_stems = {path.stem for path in REPO_LOCAL_PROMPTS_DIR.glob("*.md")}
    assert actual_stems == expected_stems
    assert repo_local_stems == expected_stems


def test_prompt_alias_markdown_matches_canonical_contracts() -> None:
    for prompt in _prompt_entries():
        canonical = (PROMPTS_DIR / f"{prompt['name']}.md").read_text(encoding="utf-8")
        for alias in list(prompt.get("aliases") or []):
            alias_text = (PROMPTS_DIR / f"{alias}.md").read_text(encoding="utf-8")
            assert f"Canonical prompt: `{prompt['name']}`" in alias_text
            assert f"Invocation name: `{alias}`" in alias_text
            assert canonical.split("## Tool Sequence", 1)[1] == alias_text.split("## Tool Sequence", 1)[1]


def test_docs_explain_tools_resources_prompts_and_redaction() -> None:
    existing_docs = [path for path in DOC_PATHS if path.exists()]
    assert existing_docs, "No MCP resources/prompts documentation files found."
    content = "\n".join(path.read_text(encoding="utf-8") for path in existing_docs)
    assert "MCP Resources" in content
    assert "Prompts" in content
    assert "safe summaries" in content or "read-only resource rules" in content


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


def test_install_docs_track_shipped_headless_entrypoints() -> None:
    supported_flags = _supported_install_flags()
    docs = {
        "docs/HEADLESS_INSTALL.md": HEADLESS_INSTALL_DOC.read_text(encoding="utf-8"),
        "wiki-staging/Install-From-Codex.md": WIKI_INSTALL_DOC.read_text(encoding="utf-8"),
        "wiki-staging/Headless-Install-and-Autowire.md": WIKI_HEADLESS_INSTALL_DOC.read_text(encoding="utf-8"),
    }
    for label, text in docs.items():
        lowered = text.lower()
        assert "planned / partial" not in lowered
        assert "partial / experimental" not in lowered
        assert ".\\scripts\\install-mission-control-plugin.ps1 -HeadlessOnly" not in text
        assert ".\\scripts\\install-mission-control-plugin.ps1 -Repair" not in text
        assert ".\\scripts\\install-mission-control-plugin.ps1 -HealthCheckOnly" not in text
    for flag in supported_flags:
        assert flag in docs["docs/HEADLESS_INSTALL.md"], f"Missing supported installer flag in docs/HEADLESS_INSTALL.md: {flag}"
        assert flag in docs["wiki-staging/Headless-Install-and-Autowire.md"], f"Missing supported installer flag in wiki-staging/Headless-Install-and-Autowire.md: {flag}"


def test_repo_local_plugin_manifest_tracks_canonical_prompts_and_resources() -> None:
    canonical_manifest = _load_json(PLUGIN_MANIFEST)
    repo_local_manifest = _load_json(REPO_LOCAL_PLUGIN_MANIFEST)
    assert repo_local_manifest["prompts"] == canonical_manifest["prompts"]
    assert repo_local_manifest["resources"] == canonical_manifest["resources"]
    assert repo_local_manifest["mcp"]["prompts_catalog"] == "./mcp/prompts.json"
    assert repo_local_manifest["mcp"]["resources_catalog"] == "./mcp/resources.json"
    assert (REPO_LOCAL_MCP_DIR / "prompts.json").exists()
    assert (REPO_LOCAL_MCP_DIR / "resources.json").exists()


def test_repo_local_plugin_bundle_tracks_canonical_skills_docs_and_assets() -> None:
    canonical_manifest = _load_json(PLUGIN_MANIFEST)
    repo_local_manifest = _load_json(REPO_LOCAL_PLUGIN_MANIFEST)
    canonical_skills = {path.name for path in CANONICAL_SKILLS_DIR.iterdir() if path.is_dir()}
    repo_local_skills = {path.name for path in REPO_LOCAL_SKILLS_DIR.iterdir() if path.is_dir()}
    canonical_assets = {
        path.relative_to(CANONICAL_ASSETS_DIR)
        for path in CANONICAL_ASSETS_DIR.rglob("*")
        if path.is_file()
    }
    repo_local_assets = {
        path.relative_to(REPO_LOCAL_ASSETS_DIR)
        for path in REPO_LOCAL_ASSETS_DIR.rglob("*")
        if path.is_file()
    }

    assert repo_local_manifest["skills"] == canonical_manifest["skills"]
    assert repo_local_skills == canonical_skills
    assert REPO_LOCAL_README.read_text(encoding="utf-8") == CANONICAL_README.read_text(encoding="utf-8")
    assert _load_json(REPO_LOCAL_CODEX_PLUGIN_MANIFEST) == _load_json(CANONICAL_CODEX_PLUGIN_MANIFEST)
    assert repo_local_assets == canonical_assets


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
        "build-your-own-x-catalog.md": [
            "ask-manager-for-plan",
            "mission_control_generate_swarm_plan",
            "mission-control://projects/{project_id}/workspace-tooling",
        ],
        "build-web-stack.md": [
            "mission_control_get_webwright_status",
            "mission-control://projects/{project_id}/webwright",
            "mission-control://projects/{project_id}/verification-brief",
        ],
        "build-game-or-renderer.md": [
            "mission_control_get_nvidia_local_runtime_status",
            "mission_control_get_nvidia_validation_plan",
            "mission-control://projects/{project_id}/nvidia-validation-plan",
        ],
        "build-programming-language-or-shell.md": [
            "ask-manager-for-plan",
            "mission-control://projects/{project_id}/agent-contracts",
            "mission-control://projects/{project_id}/verification-brief",
        ],
        "build-low-level-systems.md": [
            "mission_control_request_snapshot",
            "mission-control://projects/{project_id}/decision-ledger",
            "mission-control://projects/{project_id}/verification-brief",
        ],
    }

    for filename, required_tokens in examples.items():
        content = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
        for token in required_tokens:
            assert token in content, f"Missing token in {filename}: {token}"
