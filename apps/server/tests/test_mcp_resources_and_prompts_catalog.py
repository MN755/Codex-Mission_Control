from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
DOC_PATH = ROOT / "docs" / "MCP_RESOURCES_PROMPTS.md"


EXPECTED_RESOURCES = [
    "mission-control://orchestrations/{orchestration_id}/status",
    "mission-control://orchestrations/{orchestration_id}/events",
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
]

EXPECTED_PROMPTS = [
    "attach-current-workspace",
    "use-mission-control-for-this-repo",
    "import-existing-codebase",
    "start-manager-led-task",
    "continue-orchestration",
    "show-pending-approvals",
    "answer-pending-approval",
    "review-latest-handoff",
    "debug-failed-orchestration",
    "pause-orchestration",
    "resume-orchestration",
    "explain-current-swarm",
    "switch-swarm-strategy",
    "enable-safe-mode",
    "generate-agents-md-proposal",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_manifest_lists_expected_mcp_resources_and_prompts() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    assert manifest["resources"] == EXPECTED_RESOURCES
    assert all(prompt in manifest["prompts"] for prompt in EXPECTED_PROMPTS)
    assert manifest["mcp"]["resources_catalog"] == "./mcp/resources.json"
    assert manifest["mcp"]["prompts_catalog"] == "./mcp/prompts.json"


def test_resources_catalog_has_safety_defaults_and_redaction_notes() -> None:
    catalog = _load_json(RESOURCES_CATALOG)
    assert catalog["safety_defaults"] == {
        "summary_only": True,
        "runs_commands": False,
        "shows_raw_logs": False,
        "redact_secrets": True,
    }
    resources = catalog["resources"]
    assert [item["uri_template"] for item in resources] == EXPECTED_RESOURCES
    for item in resources:
        assert item["summary"]
        assert item["default_fields"]
        assert item["redaction"]["omit_fields"]
        assert item["redaction"]["notes"]
        assert item["support_status"]


def test_prompt_catalog_and_prompt_files_exist() -> None:
    catalog = _load_json(PROMPTS_CATALOG)
    actual_prompt_names = [item["name"] for item in catalog["prompts"]]
    assert all(prompt in actual_prompt_names for prompt in EXPECTED_PROMPTS)
    for item in catalog["prompts"]:
        assert item["description"]
        assert item["required_arguments"]
        assert item["tool_sequence"]
        assert item["expected_chat_output"]
        assert item["safety_notes"]
        prompt_path = PROMPTS_DIR / f"{item['name']}.md"
        assert prompt_path.exists(), f"Missing prompt file: {prompt_path}"
        assert prompt_path.read_text(encoding="utf-8").startswith("# ")


def test_docs_explain_resources_prompts_and_headless_boundary() -> None:
    content = DOC_PATH.read_text(encoding="utf-8")
    assert "## Resource Rules" in content
    assert "## Prompt Catalog" in content
    assert "dashboard is optional" in content.lower()
