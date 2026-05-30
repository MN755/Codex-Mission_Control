from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "plugins" / "mission-control" / "skills"
INDEX_PATH = ROOT / "plugins" / "mission-control" / "SKILL_INDEX.md"
DOC_PATH = ROOT / "docs" / "MISSION_CONTROL_SKILL_LIBRARY.md"
PLUGIN_MANIFEST = ROOT / "plugins" / "mission-control" / "plugin.json"
COMMANDS_ROOT = ROOT / "plugins" / "mission-control" / "commands"
SKILL_STALE_MARKERS = [
    "mission_control_open_dashboard",
    "mission-control://projects/current/",
    "mission-control://projects/{project_id}/events",
]

BRIDGE_STATEMENT = "The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager."
REQUIRED_SECTIONS = [
    "## Purpose",
    "## Use when",
    "## Workflow",
    "## Mission Control calls",
    "## User-facing output",
    "## Approval behavior",
    "## Never do",
    "## Failure and fallback",
    "## Example invocation",
]
REQUIRED_SKILLS = [
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
    "mission-control-plan",
    "mission-control-interview",
    "mission-control-skip-interview",
    "mission-control-quick-clarify",
    "mission-control-existing-repo-fix",
    "mission-control-run-validation",
    "mission-control-cuda-kernel-generation",
    "mission-control-cuda-tile-refactor",
    "mission-control-nsight-profiling",
    "mission-control-benchmark-comparison",
    "mission-control-compiler-autotuning-guidance",
    "mission-control-review-tests",
    "mission-control-generate-runbook",
    "mission-control-explain-codebase",
    "mission-control-refactor-safely",
    "mission-control-security-review",
    "mission-control-docs-heavy",
    "mission-control-github-ready-docs",
    "mission-control-release-prep",
    "mission-control-scope-creep-check",
    "mission-control-risk-register",
    "mission-control-decision-ledger",
    "mission-control-context-pack",
    "mission-control-agent-contracts",
    "mission-control-path-locks",
    "mission-control-snapshot",
    "mission-control-restore-plan",
    "mission-control-conflict-resolution",
    "mission-control-agent-stuck",
    "mission-control-recovery-plan",
    "mission-control-model-policy",
    "mission-control-tool-policy",
    "mission-control-local-first",
    "mission-control-ollama-mode",
    "mission-control-codex-cli-mode",
    "mission-control-claude-cli-mode",
    "mission-control-api-provider-mode",
    "mission-control-plugin-health",
    "mission-control-install-from-github",
    "mission-control-autowire-providers",
    "mission-control-headless-health",
    "mission-control-event-digest",
    "mission-control-evidence-check",
    "mission-control-change-request",
    "mission-control-continue-handoff",
    "mission-control-pause",
    "mission-control-resume-agents",
    "mission-control-stop",
    "mission-control-skill-ecosystem-builder",
    "mission-control-mcp-builder",
    "mission-control-webapp-testing",
    "mission-control-document-workflow",
    "mission-control-brand-comms",
    "mission-control-creative-web-artifacts",
    "mission-control-codebase-knowledge-graph",
    "mission-control-understand-chat",
    "mission-control-diff-impact",
    "mission-control-domain-map",
    "mission-control-onboarding-tour",
    "mission-control-knowledge-base-map",
    "mission-control-runnable-chain-design",
    "mission-control-rag-retrieval-design",
    "mission-control-tool-registry",
    "mission-control-evals-observability",
    "mission-control-memory-state-policy",
    "mission-control-agent-graph-workflows",
]


def validate() -> list[str]:
    errors: list[str] = []
    index_content = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    doc_content = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.exists() else ""
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")) if PLUGIN_MANIFEST.exists() else {}

    if not INDEX_PATH.exists():
        errors.append(f"Missing index: {INDEX_PATH}")
    if not DOC_PATH.exists():
        errors.append(f"Missing docs file: {DOC_PATH}")
    else:
        for phrase in [
            "Mission Control is the headless or background orchestrator.",
            "## How the library is grouped",
            "## How Codex should use these skills",
            "## Approval relay",
            "## Headless mode",
        ]:
            if phrase not in doc_content:
                errors.append(f"Docs missing phrase: {phrase}")

    manifest_skills = manifest.get("skills", [])
    missing_manifest_skills = [skill for skill in REQUIRED_SKILLS if skill not in manifest_skills]
    if missing_manifest_skills:
        errors.append(
            "plugin.json is missing required Mission Control skills: "
            + ", ".join(missing_manifest_skills)
        )
    for command_name in ((manifest.get("claude_code") or {}).get("primary_commands") or []):
        command_path = COMMANDS_ROOT / f"{command_name}.md"
        if not command_path.exists():
            errors.append(f"Missing Claude command file: {command_path}")
    for resource in manifest.get("resources", []):
        if resource.startswith("mission-control://orchestrations/"):
            errors.append(f"plugin.json still advertises an unscoped orchestration resource: {resource}")

    for skill_name in REQUIRED_SKILLS:
        skill_path = SKILLS_ROOT / skill_name / "SKILL.md"
        if not skill_path.exists():
            errors.append(f"Missing skill file: {skill_path}")
            continue
        content = skill_path.read_text(encoding="utf-8")
        if f"name: {skill_name}" not in content:
            errors.append(f"Frontmatter name mismatch in {skill_path}")
        if BRIDGE_STATEMENT not in content:
            errors.append(f"Bridge statement missing in {skill_path}")
        for section in REQUIRED_SECTIONS:
            if section not in content:
                errors.append(f"Missing section '{section}' in {skill_path}")
        for marker in SKILL_STALE_MARKERS:
            if marker in content:
                errors.append(f"Stale Mission Control reference {marker!r} found in {skill_path}")
        if f"`{skill_name}`" not in index_content:
            errors.append(f"Skill index missing {skill_name}")
    for marker in SKILL_STALE_MARKERS:
        if marker in index_content:
            errors.append(f"Stale Mission Control reference {marker!r} found in {INDEX_PATH}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        print(f"{len(errors)} validation error(s) found.")
        return 1
    print(f"Validated {len(REQUIRED_SKILLS)} Mission Control skills successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
