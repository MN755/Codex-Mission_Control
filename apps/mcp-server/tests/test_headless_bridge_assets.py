from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
PLUGIN_SKILLS = ROOT / "plugins" / "mission-control" / "skills"
LOCAL_SKILLS = ROOT / ".codex" / "skills"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
TEMPLATES_DIR = ROOT / "plugins" / "mission-control" / "templates"
EXAMPLES_DIR = ROOT / "examples" / "codex-chat-workflows"

EXPECTED_SKILLS = [
    "mission-control-orchestrate",
    "mission-control-import-codebase",
    "mission-control-status",
    "mission-control-approve",
    "mission-control-handoff",
    "mission-control-debug",
    "mission-control-swarm",
    "mission-control-safe-mode",
    "mission-control-resume",
    "mission-control-agents-md",
]

EXPECTED_TEMPLATES = [
    "status_summary.md",
    "pending_decision.md",
    "approval_request.md",
    "manager_question.md",
    "handoff_summary.md",
    "debug_summary.md",
    "swarm_explanation.md",
    "codebase_map_summary.md",
    "safe_mode_enabled.md",
    "agents_md_proposal.md",
    "event_digest.md",
]

EXPECTED_EXAMPLES = [
    "use-mission-control-for-current-repo.md",
    "import-existing-codebase.md",
    "approve-command.md",
    "answer-manager-question.md",
    "check-status.md",
    "review-handoff.md",
    "debug-stuck-orchestration.md",
    "enable-safe-mode.md",
    "generate-agents-md.md",
    "continue-later.md",
]

EXPECTED_DOCS = [
    ROOT / "docs" / "CODEX_CHAT_MODE.md",
    ROOT / "docs" / "MISSION_CONTROL_SKILLS.md",
    ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md",
    ROOT / "docs" / "CODEX_CHAT_WORKFLOWS.md",
    ROOT / "docs" / "MCP_RUNTIME.md",
    ROOT / "docs" / "MCP_TOOLS.md",
    ROOT / "docs" / "MCP_RESOURCES.md",
    ROOT / "docs" / "MCP_PROMPTS.md",
    ROOT / "docs" / "PENDING_DECISIONS.md",
]

PROMPT_SEQUENCE_ALIASES = {
    "debug_failed_orchestration": "debug-failed-orchestration.md",
    "enable_safe_mode": "enable-safe-mode.md",
}


def test_plugin_manifest_lists_expected_headless_skills() -> None:
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert all(skill in manifest["skills"] for skill in EXPECTED_SKILLS)


def test_bridge_skills_exist_in_plugin_and_local_layouts() -> None:
    bridge_statement = "The Codex chat agent is not the Mission Control Manager."
    for skill in EXPECTED_SKILLS:
        for root in (PLUGIN_SKILLS, LOCAL_SKILLS):
            skill_file = root / skill / "SKILL.md"
            assert skill_file.exists(), f"Missing skill file: {skill_file}"
            content = skill_file.read_text(encoding="utf-8")
            assert bridge_statement in content
            assert "bridge" in content.lower()
            assert "## Step-By-Step Workflow" in content or "## Workflow" in content
            assert "## Fallback Behavior If The Daemon Is Unavailable" in content or "## Failure and fallback" in content


def test_prompt_template_files_exist() -> None:
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    for prompt_name in manifest["prompts"]:
        prompt_file = PROMPTS_DIR / f"{prompt_name}.md"
        assert prompt_file.exists(), f"Missing prompt file: {prompt_file}"


def test_chat_templates_examples_and_docs_exist() -> None:
    for template_name in EXPECTED_TEMPLATES:
        assert (TEMPLATES_DIR / template_name).exists(), f"Missing template: {template_name}"
    for example_name in EXPECTED_EXAMPLES:
        assert (EXAMPLES_DIR / example_name).exists(), f"Missing example: {example_name}"
    for doc_path in EXPECTED_DOCS:
        assert doc_path.exists(), f"Missing doc: {doc_path}"


def test_alias_prompt_markdown_mentions_catalog_sequences() -> None:
    prompt_catalog = json.loads((ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json").read_text(encoding="utf-8"))
    catalog_by_name = {entry["name"]: entry for entry in prompt_catalog["prompts"]}

    for prompt_name, alias_filename in PROMPT_SEQUENCE_ALIASES.items():
        prompt_entry = catalog_by_name[prompt_name]
        prompt_markdown = (PROMPTS_DIR / alias_filename).read_text(encoding="utf-8")

        for tool_name in prompt_entry["tool_sequence"]:
            assert tool_name in prompt_markdown, f"{alias_filename} is missing tool {tool_name}"
        for resource_name in prompt_entry["resource_sequence"]:
            assert resource_name in prompt_markdown, f"{alias_filename} is missing resource {resource_name}"
