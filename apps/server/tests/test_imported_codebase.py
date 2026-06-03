from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from imported_codebase import import_service
from schemas import CodebaseMapRead, CodebaseUnderstandingRead, RepoIntelligenceSummaryRead


pytestmark = pytest.mark.no_db_reset


def test_scan_payload_uses_repo_relative_metadata_paths(tmp_path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text("# Repo\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (root / "deploy" / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=value\n", encoding="utf-8")

    payload = import_service._build_scan_payload(root, depth="standard")

    assert "README.md" in payload["docs_json"]
    assert "docs/guide.md" in payload["docs_json"]
    assert ".github/workflows/ci.yml" in payload["ci_config_json"]
    assert "deploy/Dockerfile" in payload["deployment_config_json"]
    assert any(flag.endswith(".env") for flag in payload["risk_flags_json"])
    assert all(str(root).replace("\\", "/") not in item for item in payload["docs_json"])


def test_repo_intelligence_read_exposes_inventory_counts_and_presence_flags() -> None:
    payload = RepoIntelligenceSummaryRead.model_validate(
        SimpleNamespace(
            project_id=7,
            languages_json=["Python", "TypeScript"],
            frameworks_json=["FastAPI", "React"],
            package_managers_json=["pip", "npm"],
            entry_points_json=["main.py", "src/main.tsx"],
            build_commands_json=["python -m build", "npm run build"],
            test_commands_json=["python -m pytest"],
            important_folders_json=["src", "tests", "docs"],
            risky_files_json=[".env"],
            docs_found_json=["README.md", "docs/guide.md"],
            ci_config_json=[".github/workflows/ci.yml"],
            deployment_config_json=["Dockerfile"],
            last_indexed_at="2026-06-03T00:00:00Z",
        )
    )

    assert payload.language_count == 2
    assert payload.framework_count == 2
    assert payload.package_manager_count == 2
    assert payload.entry_point_count == 2
    assert payload.build_command_count == 2
    assert payload.test_command_count == 1
    assert payload.important_folder_count == 3
    assert payload.risky_file_count == 1
    assert payload.doc_count == 2
    assert payload.ci_config_count == 1
    assert payload.deployment_config_count == 1
    assert payload.has_docs is True
    assert payload.has_ci_config is True
    assert payload.has_deployment_config is True
    assert payload.has_risky_files is True


def test_codebase_map_read_exposes_counts_git_rollups_and_scan_flags() -> None:
    payload = CodebaseMapRead.model_validate(
        SimpleNamespace(
            project_id=11,
            source_path="C:/repo",
            languages_json=["Python", "TypeScript"],
            frameworks_json=["FastAPI", "React"],
            package_managers_json=["pip", "npm"],
            build_tools_json=["setuptools", "vite"],
            test_frameworks_json=["pytest", "vitest"],
            entry_points_json=["main.py", "src/main.tsx"],
            build_commands_json=["python -m build", "npm run build"],
            test_commands_json=["python -m pytest", "npm run test"],
            important_folders_json=["src", "tests", "docs"],
            docs_json=["README.md", "docs/guide.md"],
            agent_instructions_json=[{"path": "AGENTS.md"}, {"path": "docs/AGENTS.md"}],
            config_files_json=["pyproject.toml", "package.json"],
            ci_config_json=[".github/workflows/ci.yml"],
            deployment_config_json=["Dockerfile"],
            git_status_json={
                "is_git_repo": True,
                "dirty_working_tree": "unknown_without_command",
                "command_required_for_dirty_check": True,
            },
            risk_flags_json=["Large binary detected", "Found .env file"],
            scan_depth="targeted",
            codebase_size="large",
            recommended_scan_strategy="progressive_targeted",
            indexed_areas_json=["src", "tests"],
            unindexed_areas_json=["vendor"],
            created_at="2026-06-03T00:00:00Z",
            updated_at="2026-06-03T00:00:00Z",
        )
    )

    assert payload.language_count == 2
    assert payload.framework_count == 2
    assert payload.package_manager_count == 2
    assert payload.build_tool_count == 2
    assert payload.test_framework_count == 2
    assert payload.entry_point_count == 2
    assert payload.build_command_count == 2
    assert payload.test_command_count == 2
    assert payload.important_folder_count == 3
    assert payload.doc_count == 2
    assert payload.agent_instruction_count == 2
    assert payload.config_file_count == 2
    assert payload.ci_config_count == 1
    assert payload.deployment_config_count == 1
    assert payload.risk_flag_count == 2
    assert payload.indexed_area_count == 2
    assert payload.unindexed_area_count == 1
    assert payload.has_docs is True
    assert payload.has_agent_instructions is True
    assert payload.has_risk_flags is True
    assert payload.is_git_repo is True
    assert payload.dirty_working_tree_status == "unknown_without_command"
    assert payload.dirty_working_tree_known is False
    assert payload.command_required_for_dirty_check is True
    assert payload.is_fully_indexed is False
    assert payload.is_targeted_scan is True


def test_codebase_understanding_read_exposes_counts_and_confidence_rollups() -> None:
    payload = CodebaseUnderstandingRead.model_validate(
        SimpleNamespace(
            project_id=19,
            summary="This appears to be FastAPI and React.",
            architecture_summary="Key areas: src, api, docs.",
            detected_stack_json=["FastAPI", "React", "TypeScript"],
            likely_run_instructions_json=["uvicorn main:app", "npm run dev"],
            likely_test_instructions_json=["python -m pytest"],
            risk_summary="No reliable test command was detected.",
            missing_context_json=["No reliable build command was detected.", "Documentation is thin or missing."],
            suggested_next_steps_json=["Review the Codebase Understanding report.", "Use targeted scan first."],
            recommended_interview_mode="manager_decides",
            confidence_by_area_json={
                "architecture": 0.62,
                "run_commands": 0.41,
                "test_commands": 0.35,
                "framework_detection": 0.95,
            },
            generation_mode="deterministic_scanner",
            created_at="2026-06-03T00:00:00Z",
            updated_at="2026-06-03T00:00:00Z",
        )
    )

    assert payload.detected_stack_count == 3
    assert payload.likely_run_instruction_count == 2
    assert payload.likely_test_instruction_count == 1
    assert payload.missing_context_count == 2
    assert payload.suggested_next_step_count == 2
    assert payload.confidence_area_count == 4
    assert payload.average_confidence == 0.583
    assert payload.lowest_confidence_areas == ["test_commands", "run_commands", "architecture"]
    assert payload.highest_confidence_areas == ["framework_detection", "architecture", "run_commands"]
    assert payload.has_missing_context is True
    assert payload.has_suggested_next_steps is True
