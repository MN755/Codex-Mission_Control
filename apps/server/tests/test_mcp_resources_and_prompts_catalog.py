from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
MIRROR_PLUGIN_MANIFEST = ROOT / ".codex" / "plugins" / "mission-control" / "plugin.json"
BUNDLED_PLUGIN_MANIFEST = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled" / "plugin.json"
RESOURCES_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "resources.json"
MIRROR_RESOURCES_CATALOG = ROOT / ".codex" / "plugins" / "mission-control" / "mcp" / "resources.json"
BUNDLED_RESOURCES_CATALOG = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled" / "resources.json"
BUNDLED_MCP_RESOURCES_CATALOG = ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled" / "mcp" / "resources.json"
PROMPTS_CATALOG = ROOT / "plugins" / "mission-control" / "mcp" / "prompts.json"
PROMPTS_DIR = ROOT / "plugins" / "mission-control" / "prompts"
RUNTIME_DOC = ROOT / "docs" / "MCP_RUNTIME.md"
TOOLS_DOC = ROOT / "docs" / "MCP_TOOLS.md"
RESOURCES_DOC = ROOT / "docs" / "MCP_RESOURCES.md"
PROMPTS_DOC = ROOT / "docs" / "MCP_PROMPTS.md"
PENDING_DOC = ROOT / "docs" / "PENDING_DECISIONS.md"
AGENT_CONTRACT_SKILLS = [
    ROOT / ".codex" / "skills" / "mission-control-agent-contracts" / "SKILL.md",
    ROOT / "plugins" / "mission-control" / "skills" / "mission-control-agent-contracts" / "SKILL.md",
    ROOT / ".codex" / "plugins" / "mission-control" / "skills" / "mission-control-agent-contracts" / "SKILL.md",
    ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled" / "skills" / "mission-control-agent-contracts" / "SKILL.md",
]
DECISION_LEDGER_SKILLS = [
    ROOT / ".codex" / "skills" / "mission-control-decision-ledger" / "SKILL.md",
    ROOT / "plugins" / "mission-control" / "skills" / "mission-control-decision-ledger" / "SKILL.md",
    ROOT / ".codex" / "plugins" / "mission-control" / "skills" / "mission-control-decision-ledger" / "SKILL.md",
    ROOT / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "_bundled" / "skills" / "mission-control-decision-ledger" / "SKILL.md",
]


EXPECTED_RESOURCES = [
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/pending-decisions",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status-summary",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/event-digest",
    "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary",
    "mission-control://projects/{project_id}/orchestrations/active",
    "mission-control://projects/{project_id}/status",
    "mission-control://projects/{project_id}/agents",
    "mission-control://projects/{project_id}/pending-decisions",
    "mission-control://projects/{project_id}/questions/pending",
    "mission-control://projects/{project_id}/approvals/pending",
    "mission-control://projects/{project_id}/event-digest",
    "mission-control://projects/{project_id}/handoff-summary",
    "mission-control://projects/{project_id}/handoff",
    "mission-control://projects/{project_id}/handoff/evidence",
    "mission-control://projects/{project_id}/handoff/evidence/preview",
    "mission-control://projects/{project_id}/codebase-map",
    "mission-control://projects/{project_id}/codebase-understanding",
    "mission-control://projects/{project_id}/import-safety",
    "mission-control://integrations/catalog",
    "mission-control://integrations/connections",
    "mission-control://integrations/health",
    "mission-control://agent-archetypes",
    "mission-control://agents/reputation",
    "mission-control://capabilities/benchmarks",
    "mission-control://capabilities/matrix",
    "mission-control://context-packs/{context_pack_id}",
    "mission-control://playbooks",
    "mission-control://playbooks/{playbook_key}",
    "mission-control://security/policy",
    "mission-control://security/audit-log",
    "mission-control://daemon/status",
    "mission-control://runners/status",
    "mission-control://plugin/health",
    "mission-control://headless/config",
    "mission-control://system/status",
    "mission-control://system/auth-state",
    "mission-control://system/auth-jobs/{job_id}",
    "mission-control://system/codex-status",
    "mission-control://startup/status",
    "mission-control://dashboard/summary",
    "mission-control://widgets/catalog",
    "mission-control://widgets/catalog/{scope}",
    "mission-control://widgets/instances",
    "mission-control://widgets/instances/{instance_id}/data",
    "mission-control://tools",
    "mission-control://skills",
    "mission-control://handoffs",
    "mission-control://health",
    "mission-control://diagnostics/reports",
    "mission-control://diagnostics/identity",
    "mission-control://headless/health",
    "mission-control://headless/diagnostic-summary",
    "mission-control://projects",
    "mission-control://profile",
    "mission-control://profile/summary",
    "mission-control://preferences",
    "mission-control://preferences/summary",
    "mission-control://subagent-policy",
    "mission-control://subagent-policy/summary",
    "mission-control://projects/{project_id}/integrations",
    "mission-control://projects/{project_id}/integrations/{family}",
    "mission-control://projects/{project_id}/settings",
    "mission-control://projects/{project_id}/details",
    "mission-control://projects/{project_id}/understanding",
    "mission-control://projects/{project_id}/interview",
    "mission-control://projects/{project_id}/plan",
    "mission-control://projects/{project_id}/runbook",
    "mission-control://projects/{project_id}/runbook/summary",
    "mission-control://projects/{project_id}/safe-mode",
    "mission-control://projects/{project_id}/recovery-plans",
    "mission-control://projects/{project_id}/recovery-plans/preview",
    "mission-control://projects/{project_id}/snapshots",
    "mission-control://projects/{project_id}/snapshots/{snapshot_id}/restore-plan",
    "mission-control://projects/{project_id}/playbook",
    "mission-control://projects/{project_id}/playbook/recommendations",
    "mission-control://projects/{project_id}/context-packs",
    "mission-control://projects/{project_id}/agents/reputation",
    "mission-control://projects/{project_id}/preferences",
    "mission-control://projects/{project_id}/preferences/summary",
    "mission-control://projects/{project_id}/preferences/effective",
    "mission-control://projects/{project_id}/subagent-batches",
    "mission-control://projects/{project_id}/subagent-batches/{batch_id}",
    "mission-control://projects/{project_id}/widgets/summary",
    "mission-control://projects/{project_id}/widgets/instances",
    "mission-control://projects/{project_id}/workspace",
    "mission-control://projects/{project_id}/workspace-tooling",
    "mission-control://projects/{project_id}/security/policy",
    "mission-control://projects/{project_id}/security/audit-log",
    "mission-control://projects/{project_id}/decisions/{decision_id}/bridge-message",
    "mission-control://projects/{project_id}/action",
    "mission-control://projects/{project_id}/actions",
    "mission-control://projects/{project_id}/manager/messages",
    "mission-control://projects/{project_id}/manager/queue",
    "mission-control://projects/{project_id}/tasks",
    "mission-control://projects/{project_id}/reservations",
    "mission-control://projects/{project_id}/events",
    "mission-control://projects/{project_id}/status-summary",
    "mission-control://projects/{project_id}/execution-policy/summary",
    "mission-control://projects/{project_id}/coordination/summary",
    "mission-control://projects/{project_id}/tensorflow/features",
    "mission-control://projects/{project_id}/tensorflow/features/{feature_id}",
    "mission-control://projects/{project_id}/pytorch/features",
    "mission-control://projects/{project_id}/pytorch/features/{feature_id}",
    "mission-control://projects/{project_id}/spatial/features",
    "mission-control://projects/{project_id}/spatial/features/{feature_id}",
    "mission-control://projects/{project_id}/diagnostics",
    "mission-control://projects/{project_id}/webwright",
    "mission-control://projects/{project_id}/nvidia-dynamo",
    "mission-control://projects/{project_id}/nvidia-nim",
    "mission-control://projects/{project_id}/nvidia-aiq",
    "mission-control://projects/{project_id}/nvidia-gpu-diagnostics",
    "mission-control://projects/{project_id}/nvidia-local-runtime",
    "mission-control://projects/{project_id}/nvidia-validation-plan",
    "mission-control://projects/{project_id}/swarm/preferences",
    "mission-control://projects/{project_id}/swarm-plan",
    "mission-control://projects/{project_id}/swarm/events",
    "mission-control://projects/{project_id}/swarm/simulations",
    "mission-control://projects/{project_id}/swarm/simulations/latest",
    "mission-control://risks/common",
    "mission-control://risks/summary",
    "mission-control://projects/{project_id}/scope-creep",
    "mission-control://projects/{project_id}/risk-register",
    "mission-control://projects/{project_id}/risks/summary",
    "mission-control://projects/{project_id}/agent-contracts",
    "mission-control://projects/{project_id}/validation-summary",
    "mission-control://projects/{project_id}/validation-coverage",
    "mission-control://projects/{project_id}/validation-coverage/summary",
    "mission-control://projects/{project_id}/decision-ledger",
    "mission-control://projects/{project_id}/path-locks",
    "mission-control://projects/{project_id}/agents-md/status",
    "mission-control://projects/{project_id}/operator-snapshot",
    "mission-control://projects/{project_id}/instincts",
    "mission-control://projects/{project_id}/verification-brief",
    "mission-control://projects/{project_id}/capability-report",
    "mission-control://projects/{project_id}/capability-report/{section_key}",
]

EXPECTED_PROMPTS = [
    "attach_current_workspace",
    "use_mission_control_for_repo",
    "import_existing_codebase",
    "start_manager_led_task",
    "continue_orchestration",
    "show_pending_approvals",
    "answer_pending_approval",
    "review_latest_handoff",
    "debug_failed_orchestration",
    "use_webwright_for_browser_task",
    "pause_orchestration",
    "resume_orchestration",
    "explain_current_swarm",
    "switch_swarm_strategy",
    "enable_safe_mode",
    "generate_agents_md_proposal",
    "install_from_github",
    "autowire_providers",
    "review_project_capabilities",
    "ask_manager_for_plan",
    "review_project_capability_section",
    "review_integration_catalog",
    "import_host_integrations",
    "review_project_integrations",
    "review_project_integration_family",
    "review_tensorflow_feature_catalog",
    "review_tensorflow_feature_bundle",
    "review_pytorch_feature_catalog",
    "review_pytorch_feature_bundle",
    "review_spatial_feature_catalog",
    "review_spatial_feature_bundle",
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


def test_repo_local_mirror_plugin_catalog_matches_canonical_resources() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    mirror_manifest = _load_json(MIRROR_PLUGIN_MANIFEST)
    resources = _load_json(RESOURCES_CATALOG)
    mirror_resources = _load_json(MIRROR_RESOURCES_CATALOG)

    assert mirror_manifest["resources"] == manifest["resources"] == EXPECTED_RESOURCES
    assert [item["uri_template"] for item in mirror_resources["resources"]] == EXPECTED_RESOURCES
    assert mirror_resources["safety_defaults"] == resources["safety_defaults"]


def test_bundled_plugin_catalog_matches_canonical_resources() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    resources = _load_json(RESOURCES_CATALOG)
    bundled_manifest = _load_json(BUNDLED_PLUGIN_MANIFEST)
    bundled_resources = _load_json(BUNDLED_RESOURCES_CATALOG)
    bundled_mcp_resources = _load_json(BUNDLED_MCP_RESOURCES_CATALOG)

    assert bundled_manifest["resources"] == manifest["resources"] == EXPECTED_RESOURCES
    assert [item["uri_template"] for item in bundled_resources["resources"]] == EXPECTED_RESOURCES
    assert [item["uri_template"] for item in bundled_mcp_resources["resources"]] == EXPECTED_RESOURCES
    assert bundled_resources["safety_defaults"] == resources["safety_defaults"]
    assert bundled_mcp_resources["safety_defaults"] == resources["safety_defaults"]


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
    runtime_content = RUNTIME_DOC.read_text(encoding="utf-8")
    tools_content = TOOLS_DOC.read_text(encoding="utf-8")
    resources_content = RESOURCES_DOC.read_text(encoding="utf-8")
    prompts_content = PROMPTS_DOC.read_text(encoding="utf-8")
    pending_content = PENDING_DOC.read_text(encoding="utf-8")

    assert "Codex chat is the bridge" in runtime_content
    assert "localhost" in runtime_content.lower()
    assert "mission_control_attach_workspace" in tools_content
    assert "mission-control://projects/{project_id}/decision-ledger" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status-summary" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/event-digest" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff-summary" in resources_content
    assert "mission-control://projects/{project_id}/questions/pending" in resources_content
    assert "mission-control://projects/{project_id}/approvals/pending" in resources_content
    assert "mission-control://system/auth-jobs/{job_id}" in resources_content
    assert "mission-control://projects/{project_id}/event-digest" in resources_content
    assert "mission-control://projects/{project_id}/handoff-summary" in resources_content
    assert "mission-control://projects/{project_id}/handoff/evidence" in resources_content
    assert "mission-control://projects/{project_id}/handoff/evidence/preview" in resources_content
    assert "mission-control://projects/{project_id}/operator-snapshot" in resources_content
    assert "mission-control://projects/{project_id}/capability-report" in resources_content
    assert "mission-control://projects/{project_id}/capability-report/{section_key}" in resources_content
    assert "mission-control://projects/{project_id}/runbook" in resources_content
    assert "mission-control://projects/{project_id}/runbook/summary" in resources_content
    assert "mission-control://projects/{project_id}/safe-mode" in resources_content
    assert "mission-control://projects/{project_id}/recovery-plans" in resources_content
    assert "mission-control://projects/{project_id}/recovery-plans/preview" in resources_content
    assert "mission-control://projects/{project_id}/snapshots" in resources_content
    assert "mission-control://projects/{project_id}/snapshots/{snapshot_id}/restore-plan" in resources_content
    assert "mission-control://playbooks" in resources_content
    assert "mission-control://playbooks/{playbook_key}" in resources_content
    assert "mission-control://agent-archetypes" in resources_content
    assert "mission-control://agents/reputation" in resources_content
    assert "mission-control://capabilities/benchmarks" in resources_content
    assert "mission-control://capabilities/matrix" in resources_content
    assert "mission-control://context-packs/{context_pack_id}" in resources_content
    assert "mission-control://security/policy" in resources_content
    assert "mission-control://daemon/status" in resources_content
    assert "mission-control://runners/status" in resources_content
    assert "mission-control://plugin/health" in resources_content
    assert "mission-control://headless/config" in resources_content
    assert "mission-control://headless/diagnostic-summary" in resources_content
    assert "mission-control://system/status" in resources_content
    assert "mission-control://system/auth-state" in resources_content
    assert "mission-control://system/codex-status" in resources_content
    assert "mission-control://startup/status" in resources_content
    assert "mission-control://dashboard/summary" in resources_content
    assert "mission-control://widgets/catalog" in resources_content
    assert "mission-control://widgets/catalog/{scope}" in resources_content
    assert "mission-control://widgets/instances" in resources_content
    assert "mission-control://widgets/instances/{instance_id}/data" in resources_content
    assert "mission-control://tools" in resources_content
    assert "mission-control://skills" in resources_content
    assert "mission-control://handoffs" in resources_content
    assert "mission-control://health" in resources_content
    assert "mission-control://diagnostics/reports" in resources_content
    assert "mission-control://diagnostics/identity" in resources_content
    assert "mission-control://headless/health" in resources_content
    assert "mission-control://projects" in resources_content
    assert "mission-control://profile" in resources_content
    assert "mission-control://profile/summary" in resources_content
    assert "mission-control://preferences" in resources_content
    assert "mission-control://preferences/summary" in resources_content
    assert "mission-control://subagent-policy" in resources_content
    assert "mission-control://subagent-policy/summary" in resources_content
    assert "mission-control://projects/{project_id}/settings" in resources_content
    assert "mission-control://projects/{project_id}/details" in resources_content
    assert "mission-control://projects/{project_id}/understanding" in resources_content
    assert "mission-control://projects/{project_id}/interview" in resources_content
    assert "mission-control://projects/{project_id}/plan" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/handoff" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/{orchestration_id}/pending-decisions" in resources_content
    assert "mission-control://projects/{project_id}/orchestrations/active" in resources_content
    assert "mission-control://projects/{project_id}/playbook" in resources_content
    assert "mission-control://projects/{project_id}/playbook/recommendations" in resources_content
    assert "mission-control://projects/{project_id}/context-packs" in resources_content
    assert "mission-control://projects/{project_id}/agents/reputation" in resources_content
    assert "mission-control://projects/{project_id}/preferences" in resources_content
    assert "mission-control://projects/{project_id}/preferences/summary" in resources_content
    assert "mission-control://projects/{project_id}/preferences/effective" in resources_content
    assert "mission-control://projects/{project_id}/workspace" in resources_content
    assert "mission-control://projects/{project_id}/codebase-understanding" in resources_content
    assert "mission-control://projects/{project_id}/import-safety" in resources_content
    assert "mission-control://projects/{project_id}/widgets/summary" in resources_content
    assert "mission-control://projects/{project_id}/widgets/instances" in resources_content
    assert "mission-control://projects/{project_id}/webwright" in resources_content
    assert "mission-control://projects/{project_id}/nvidia-nim" in resources_content
    assert "mission-control://projects/{project_id}/nvidia-aiq" in resources_content
    assert "mission-control://projects/{project_id}/nvidia-validation-plan" in resources_content
    assert "mission-control://projects/{project_id}/swarm/preferences" in resources_content
    assert "mission-control://projects/{project_id}/workspace-tooling" in resources_content
    assert "mission-control://projects/{project_id}/security/policy" in resources_content
    assert "mission-control://projects/{project_id}/security/audit-log" in resources_content
    assert "mission-control://projects/{project_id}/decisions/{decision_id}/bridge-message" in resources_content
    assert "mission-control://projects/{project_id}/action" in resources_content
    assert "mission-control://projects/{project_id}/actions" in resources_content
    assert "mission-control://projects/{project_id}/manager/messages" in resources_content
    assert "mission-control://projects/{project_id}/manager/queue" in resources_content
    assert "mission-control://projects/{project_id}/tasks" in resources_content
    assert "mission-control://projects/{project_id}/reservations" in resources_content
    assert "mission-control://projects/{project_id}/events" in resources_content
    assert "mission-control://projects/{project_id}/status-summary" in resources_content
    assert "mission-control://projects/{project_id}/subagent-batches" in resources_content
    assert "mission-control://projects/{project_id}/subagent-batches/{batch_id}" in resources_content
    assert "mission-control://projects/{project_id}/execution-policy/summary" in resources_content
    assert "mission-control://projects/{project_id}/coordination/summary" in resources_content
    assert "mission-control://projects/{project_id}/swarm/events" in resources_content
    assert "mission-control://projects/{project_id}/swarm/simulations" in resources_content
    assert "mission-control://projects/{project_id}/swarm/simulations/latest" in resources_content
    assert "mission-control://risks/common" in resources_content
    assert "mission-control://risks/summary" in resources_content
    assert "mission-control://security/audit-log" in resources_content
    assert "mission-control://projects/{project_id}/scope-creep" in resources_content
    assert "mission-control://projects/{project_id}/risks/summary" in resources_content
    assert "mission-control://projects/{project_id}/validation-coverage" in resources_content
    assert "mission-control://projects/{project_id}/validation-coverage/summary" in resources_content
    assert "mission-control://projects/{project_id}/agents-md/status" in resources_content
    assert "mission-control://projects/{project_id}/tensorflow/features" in resources_content
    assert "mission-control://projects/{project_id}/tensorflow/features/{feature_id}" in resources_content
    assert "mission-control://projects/{project_id}/pytorch/features" in resources_content
    assert "mission-control://projects/{project_id}/pytorch/features/{feature_id}" in resources_content
    assert "mission-control://projects/{project_id}/spatial/features" in resources_content
    assert "mission-control://projects/{project_id}/spatial/features/{feature_id}" in resources_content
    assert "attach_current_workspace" in prompts_content
    assert "use_webwright_for_browser_task" in prompts_content
    assert "review_project_capability_section" in prompts_content
    assert "review_tensorflow_feature_catalog" in prompts_content
    assert "review_tensorflow_feature_bundle" in prompts_content
    assert "review_pytorch_feature_catalog" in prompts_content
    assert "review_pytorch_feature_bundle" in prompts_content
    assert "review_spatial_feature_catalog" in prompts_content
    assert "review_spatial_feature_bundle" in prompts_content
    assert "Invalid answers are rejected" in pending_content


def test_skill_docs_do_not_claim_live_resources_are_missing() -> None:
    for path in AGENT_CONTRACT_SKILLS:
        content = path.read_text(encoding="utf-8")
        assert "mission-control://projects/{project_id}/agent-contracts" in content
        assert "not yet a first-class resource" not in content

    for path in DECISION_LEDGER_SKILLS:
        content = path.read_text(encoding="utf-8")
        assert "mission-control://projects/{project_id}/decision-ledger" in content
        assert "not yet exposed" not in content
