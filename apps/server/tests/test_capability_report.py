from __future__ import annotations

from pathlib import Path

from context_packs import context_pack_service
from db import SessionLocal
from manager import service
from models import (
    Agent,
    AgentExecutionTrace,
    AgentPerformanceRecord,
    CapabilityBenchmark,
    EvidenceBasedHandoff,
    HandoffEvidence,
    PathLock,
    Project,
    ReviewGate,
    Task,
    ValidationCoverageArea,
    ValidationRecipe,
)

from conftest import sample_workspace


def _seed_capability_project() -> int:
    workspace = Path(sample_workspace("capability-report"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "kernels").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n[tool.ruff]\nline-length=100\n", encoding="utf-8")
    (workspace / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (workspace / "package.json").write_text('{"devDependencies": {"@playwright/test": "^1.55.0"}}\n', encoding="utf-8")
    (workspace / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
    (workspace / "CMakeLists.txt").write_text("project(Demo LANGUAGES CXX CUDA)\nfind_package(CUDAToolkit REQUIRED)\n", encoding="utf-8")
    (workspace / "src" / "worker.py").write_text(
        "class Worker:\n    pass\n\n\ndef ship_feature():\n    return 'done'\n",
        encoding="utf-8",
    )
    (workspace / "src" / "client.ts").write_text("export function requestData() { return 'ok'; }\n", encoding="utf-8")
    (workspace / "src" / "app.ts").write_text("import { requestData } from './client';\nexport const boot = () => requestData();\n", encoding="utf-8")
    (workspace / "tests" / "test_worker.py").write_text("def test_worker():\n    assert True\n", encoding="utf-8")
    (workspace / "kernels" / "vector_add.cu").write_text("__global__ void vector_add() {}\n", encoding="utf-8")

    db = SessionLocal()
    try:
        project = Project(
            name="Capability Report Demo",
            idea="Exercise the capability report with a realistic seeded workspace.",
            workspace_path=workspace.as_posix(),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.flush()

        worker = Agent(
            project_id=project.id,
            name="Implementation Worker",
            role="Implementation",
            kind="worker",
            status="working",
            current_action="Finishing validation and browser evidence capture.",
            workspace_path=project.workspace_path,
        )
        db.add(worker)
        db.flush()

        task = Task(
            project_id=project.id,
            assigned_agent_id=worker.id,
            title="Ship the capability report",
            goal="Expose useful project execution surfaces.",
            scope="Keep the implementation headless and evidence-backed.",
            agent_role="Implementation",
            milestone="vNext",
            allowed_paths_json=["src/worker.py", "src/app.ts", "src/client.ts", "kernels/vector_add.cu"],
            forbidden_paths_json=["apps/dashboard"],
            validation_steps_json=["python -m pytest apps/server/tests/test_capability_report.py -q"],
            success_criteria_json=["Capability report returns all 15 sections"],
            estimated_complexity="medium",
            dependencies_json=[],
            status="working",
            priority=5,
        )
        db.add(task)
        db.flush()

        db.add(
            PathLock(
                project_id=project.id,
                path_pattern="src/worker.py",
                owner_agent_id=worker.id,
                owner_task_id=task.id,
                reason="Current implementation path.",
                status="active",
            )
        )
        db.add(
            PathLock(
                project_id=project.id,
                path_pattern="kernels/vector_add.cu",
                owner_agent_id=worker.id,
                owner_task_id=task.id,
                reason="CUDA validation lane.",
                status="active",
            )
        )
        db.add(
            ValidationRecipe(
                project_id=project.id,
                name="Primary validation recipe",
                status="active",
                steps_json=[{"title": "Run capability report tests", "command": "python -m pytest apps/server/tests/test_capability_report.py -q"}],
            )
        )
        db.add(
            ValidationCoverageArea(
                project_id=project.id,
                area="capability_report",
                coverage_status="partial",
                evidence_summary="Core coverage exists but browser evidence still needs capture.",
            )
        )
        db.add(
            ReviewGate(
                project_id=project.id,
                gate_type="validation",
                title="Capability report gate",
                status="pending",
                required=True,
                related_task_id=task.id,
                related_agent_id=worker.id,
                required_checks_json=["python -m pytest apps/server/tests/test_capability_report.py -q"],
                evidence_ids_json=[],
                result_summary="Waiting on the latest run.",
            )
        )
        db.add(
            HandoffEvidence(
                project_id=project.id,
                evidence_type="test",
                claim="Capability report endpoint works.",
                summary="Targeted capability report test is defined and queued.",
                source_path="apps/server/tests/test_capability_report.py",
                command="python -m pytest apps/server/tests/test_capability_report.py -q",
                status="pending",
                metadata_json={"lane": "capability_report"},
            )
        )
        db.add(
            EvidenceBasedHandoff(
                project_id=project.id,
                title="Capability report handoff",
                summary="Capability report exists but still needs a fresh green run.",
                what_was_built="Capability report surface.",
                how_to_run="Call the project capability report endpoint.",
                how_to_use="Read execution profiles first, then release/security/runner posture.",
                tests_run_json=[],
                known_limitations_json=["Fresh validation evidence is still pending."],
                suggested_next_steps_json=["Run the capability report test lane."],
                evidence_ids_json=[],
                confidence_level="medium",
                dry_run=False,
            )
        )
        db.add(
            AgentExecutionTrace(
                project_id=project.id,
                agent_id=worker.id,
                task_id=task.id,
                prompt_summary="Implement capability report surfaces.",
                response_summary="Added API surface and report assembly logic.",
                report_json={"status": "in_progress"},
                files_changed_json=["src/worker.py", "kernels/vector_add.cu"],
                approvals_requested_json=[],
                commands_attempted_json=["python -m pytest apps/server/tests/test_capability_report.py -q"],
                manager_decision_after="Run validation next.",
                redaction_status="clean",
            )
        )
        db.add(
            AgentPerformanceRecord(
                project_id=project.id,
                agent_archetype="coder",
                agent_name="Implementation Worker",
                provider="codex",
                model="gpt-5",
                runner_mode="auto",
                task_category="feature",
                task_id=task.id,
                outcome="success",
                duration_seconds=420,
                review_passed=True,
                tests_passed=True,
            )
        )
        db.add(
            CapabilityBenchmark(
                provider="codex",
                model="gpt-5",
                runner_mode="auto",
                category="coding",
                score=92,
                sample_size=4,
                notes="Strong on headless backend work.",
            )
        )
        db.commit()

        db.refresh(task)
        context_pack_service.build_context_pack(db, project, agent_id=worker.id, task_id=task.id, title="Pack A", goal="Initial build lane")
        task.allowed_paths_json = ["src/worker.py", "src/app.ts", "src/client.ts", "kernels/vector_add.cu"]
        db.commit()
        context_pack_service.build_context_pack(db, project, agent_id=worker.id, task_id=task.id, title="Pack B", goal="CUDA-aware verification lane")
        db.commit()
        return project.id
    finally:
        db.close()


def test_capability_report_endpoint_returns_all_fifteen_sections(client, bridge_headers, monkeypatch) -> None:
    project_id = _seed_capability_project()

    monkeypatch.setattr(
        "manager.detect_workspace_tooling",
        lambda workspace_path, project_name=None: {
            "workspace_path": str(workspace_path),
            "available": True,
            "summary": "Python, browser, intake, and security helper lanes are detectable.",
            "repo_profile": {
                "python_repo": True,
                "node_repo": True,
                "rust_repo": False,
                "go_repo": False,
                "lockfiles": ["uv.lock"],
            },
            "tools": [
                {"id": "uv", "label": "uv", "category": "bootstrap", "installed": False, "configured": True, "status": "needs_setup", "notes": [], "recommended_commands": ["uv sync"], "config_files": ["uv.lock"], "config_sections": [], "binary_path": None},
                {"id": "ruff", "label": "Ruff", "category": "validation", "installed": True, "configured": True, "status": "ready", "notes": [], "recommended_commands": ["ruff check ."], "config_files": ["pyproject.toml"], "config_sections": ["[tool.ruff]"], "binary_path": "C:/tools/ruff.exe"},
                {"id": "pre-commit", "label": "pre-commit", "category": "validation", "installed": False, "configured": True, "status": "needs_setup", "notes": [], "recommended_commands": ["pre-commit run --all-files"], "config_files": [".pre-commit-config.yaml"], "config_sections": [], "binary_path": None},
                {"id": "rg", "label": "ripgrep", "category": "intake", "installed": True, "configured": False, "status": "available", "notes": [], "recommended_commands": ["rg --files"], "config_files": [], "config_sections": [], "binary_path": "C:/tools/rg.exe"},
                {"id": "tree-sitter", "label": "tree-sitter", "category": "intake", "installed": True, "configured": False, "status": "available", "notes": [], "recommended_commands": ["tree-sitter parse src/worker.py"], "config_files": [], "config_sections": [], "binary_path": "C:/tools/tree-sitter.exe"},
                {"id": "playwright", "label": "Playwright", "category": "validation", "installed": True, "configured": True, "status": "ready", "notes": [], "recommended_commands": ["playwright test"], "config_files": ["playwright.config.ts"], "config_sections": [], "binary_path": "C:/tools/playwright.cmd"},
                {"id": "gitleaks", "label": "Gitleaks", "category": "security", "installed": True, "configured": False, "status": "available", "notes": [], "recommended_commands": ["gitleaks dir . --redact"], "config_files": [], "config_sections": [], "binary_path": "C:/tools/gitleaks.exe"},
                {"id": "pip-audit", "label": "pip-audit", "category": "security", "installed": True, "configured": True, "status": "ready", "notes": [], "recommended_commands": ["pip-audit"], "config_files": ["uv.lock"], "config_sections": [], "binary_path": "C:/tools/pip-audit.exe"},
            ],
            "packs": [],
            "recommended_next_steps": ["Install uv.", "Install pre-commit."],
            "repo_mode_summaries": ["TensorFlow mode `tensorflow_product` with frameworks: TensorFlow, SavedModel / Serving"],
            "important_paths": ["train.py", "configs/train.yaml"],
            "execution_entrypoints": ["python train.py", "python export.py"],
            "runtime_blockers": ["Python is not available on PATH for the repo-owned TensorFlow commands this workspace expects to run."],
            "validation_evidence_targets": ["Capture TensorBoard evidence instead of motivational speeches."],
            "intake_commands": ["rg --files", "tree-sitter parse src/worker.py"],
            "notebook_paths": ["notebooks/experiment.ipynb"],
            "notebook_commands": ["jupyter nbconvert --to script notebooks/experiment.ipynb"],
            "validation_commands": ["ruff check .", "playwright test", "python -m pytest apps/server/tests/test_capability_report.py -q"],
            "security_commands": ["gitleaks dir . --redact", "pip-audit"],
            "artifact_paths": ["artifacts/exported_model/saved_model.pb"],
            "artifact_inspection_commands": ["saved_model_cli show --dir artifacts/exported_model --all"],
            "config_review_paths": ["configs/train.yaml"],
            "config_review_commands": ['python -c "from pathlib import Path; p = Path(\\"configs/train.yaml\\"); print(p.read_text(encoding=\'utf-8\', errors=\'ignore\'))"'],
        },
    )
    monkeypatch.setattr(
        service,
        "build_webwright_status",
        lambda project: {
            "project_id": project.id,
            "project_name": project.name,
            "workspace_path": project.workspace_path,
            "available": True,
            "install_status": "ready",
            "summary": "Webwright is ready.",
        },
    )
    monkeypatch.setattr(
        "manager.list_diagnostic_reports",
        lambda: [
            {
                "project_id": project_id,
                "path": "C:/diagnostics/demo.md",
                "workspace_path": sample_workspace("capability-report"),
                "safe_debug_commands": ["python -m pytest apps/server/tests/test_capability_report.py -q"],
            }
        ],
    )
    monkeypatch.setattr(
        "system_status.detect_provider_statuses",
        lambda **kwargs: [
            {
                "provider": "codex",
                "runtime_ready": True,
                "runtime_status": "ready",
                "runtime_summary": "Local Codex runner is available.",
                "runtime_blockers": [],
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_build_python_semantic_index",
        lambda root: {
            "module_index": {"src.worker": "src/worker.py", "tests.test_worker": "tests/test_worker.py"},
            "symbols_by_file": {"src/worker.py": ["def run_worker", "class Worker"]},
            "imports_by_file": {"tests/test_worker.py": ["src/worker.py"]},
            "dependents_by_file": {"src/worker.py": ["tests/test_worker.py"]},
        },
    )
    monkeypatch.setattr(service, "_tree_sitter_binary", lambda tooling: "C:/tools/tree-sitter.exe")
    monkeypatch.setattr(service, "_extract_tree_sitter_tags", lambda binary, path: ["function launch_kernel"] if path.suffix.lower() == ".cu" else [])

    response = client.get(f"/api/projects/{project_id}/capability-report", headers=bridge_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["section_count"] == 15
    keys = {item["key"] for item in payload["sections"]}
    assert keys == {
        "issue_to_execution_profiles",
        "repo_capability_auto_detection",
        "semantic_code_impact_mapping",
        "validation_evidence_ledger",
        "security_review_profile",
        "workspace_tool_installer_bootstrap",
        "failure_replay_pack",
        "agent_performance_analytics",
        "approval_policy_engine",
        "release_readiness_mode",
        "context_pack_diffing",
        "swarm_role_templates",
        "runner_cost_latency_awareness",
        "browser_evidence_pipeline",
        "repo_drift_and_contract_audit",
    }
    sections = {item["key"]: item for item in payload["sections"]}
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["semantic_backend"] == "cross-language-workspace-graph"
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["dependent_files"]["src/worker.py"] == ["tests/test_worker.py"]
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["dependent_files"]["src/client.ts"] == ["src/app.ts"]
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["imports_by_file"]["src/app.ts"] == ["src/client.ts"]
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["parser_backends_by_file"]["src/client.ts"] == "js-ts-import-graph"
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["parser_backends_by_file"]["kernels/vector_add.cu"] == "tree-sitter-tags"
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["symbols_by_file"]["kernels/vector_add.cu"] == ["function launch_kernel"]
    assert "javascript-typescript" in sections["semantic_code_impact_mapping"]["metadata_json"]["graph_languages"]
    assert "package-json" in sections["semantic_code_impact_mapping"]["metadata_json"]["build_systems"]
    assert "cmake" in sections["semantic_code_impact_mapping"]["metadata_json"]["build_systems"]
    assert "src" in sections["semantic_code_impact_mapping"]["metadata_json"]["source_roots"]
    assert "kernels" in sections["semantic_code_impact_mapping"]["metadata_json"]["source_roots"]
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["edge_count"] >= 2
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["call_edge_count"] >= 1
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["edge_confidence_counts"]["high"] >= 1
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["runtime_edge_count"] >= 0
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["codegen_edge_count"] >= 0
    assert sections["semantic_code_impact_mapping"]["metadata_json"]["cache_hit"] is False
    assert any(
        edge["source"] == "src/app.ts"
        and edge["target"] == "src/client.ts"
        and edge["backend"] == "js-ts-import-graph"
        and edge["confidence"] in {"medium", "high"}
        for edge in sections["semantic_code_impact_mapping"]["metadata_json"]["dependency_edges"]
    )
    assert "CUDA mode" in " ".join(sections["repo_capability_auto_detection"]["details"])
    assert sections["workspace_tool_installer_bootstrap"]["status"] == "needs_setup"
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["repo_mode_summaries"] == [
        "TensorFlow mode `tensorflow_product` with frameworks: TensorFlow, SavedModel / Serving"
    ]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["important_paths"] == ["train.py", "configs/train.yaml"]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["execution_entrypoints"] == ["python train.py", "python export.py"]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["runtime_blockers"] == [
        "Python is not available on PATH for the repo-owned TensorFlow commands this workspace expects to run."
    ]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["validation_evidence_targets"] == [
        "Capture TensorBoard evidence instead of motivational speeches."
    ]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["notebook_paths"] == ["notebooks/experiment.ipynb"]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["artifact_paths"] == ["artifacts/exported_model/saved_model.pb"]
    assert sections["workspace_tool_installer_bootstrap"]["metadata_json"]["config_review_paths"] == ["configs/train.yaml"]
    assert any(
        "configs/train.yaml" in command
        for command in sections["workspace_tool_installer_bootstrap"]["metadata_json"]["config_review_commands"]
    )
    assert sections["browser_evidence_pipeline"]["status"] == "ready"
    assert sections["context_pack_diffing"]["status"] == "ready"
    assert "## Mission Control Capability Report" in payload["report_markdown"]

    section_response = client.get(
        f"/api/projects/{project_id}/capability-report/semantic_code_impact_mapping",
        headers=bridge_headers,
    )
    assert section_response.status_code == 200, section_response.text
    section_payload = section_response.json()
    assert section_payload["key"] == "semantic_code_impact_mapping"
    assert section_payload["metadata_json"]["semantic_backend"] == "cross-language-workspace-graph"


def test_workspace_semantic_index_builds_cross_language_dependency_edges() -> None:
    workspace = Path(sample_workspace("capability-cross-language-graph"))
    (workspace / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "tests").mkdir(parents=True, exist_ok=True)
    (workspace / "frontend" / "src").mkdir(parents=True, exist_ok=True)
    (workspace / "frontend" / "generated").mkdir(parents=True, exist_ok=True)
    (workspace / "native").mkdir(parents=True, exist_ok=True)
    (workspace / "scripts").mkdir(parents=True, exist_ok=True)
    (workspace / "php").mkdir(parents=True, exist_ok=True)
    (workspace / "ruby" / "lib").mkdir(parents=True, exist_ok=True)
    (workspace / "schemas").mkdir(parents=True, exist_ok=True)
    (workspace / "dotnet" / "Support").mkdir(parents=True, exist_ok=True)
    (workspace / "api").mkdir(parents=True, exist_ok=True)
    (workspace / "frontend" / "package.json").write_text('{"name":"@demo/frontend","main":"src/index.ts"}\n', encoding="utf-8")
    (workspace / "frontend" / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}\n',
        encoding="utf-8",
    )
    (workspace / "frontend" / "src" / "util.ts").write_text("export const util = () => 'ok';\n", encoding="utf-8")
    (workspace / "frontend" / "src" / "index.ts").write_text("export * from './util';\n", encoding="utf-8")
    (workspace / "frontend" / "generated" / "api.ts").write_text(
        "// @generated\n// do not edit\nexport const generatedApi = () => 'generated';\n",
        encoding="utf-8",
    )
    (workspace / "schemas" / "api.proto").write_text('syntax = "proto3";\nmessage Api {}\n', encoding="utf-8")
    (workspace / "frontend" / "src" / "app.ts").write_text(
        "import { util } from '@/util';\nimport * as pkg from '@demo/frontend';\nimport { generatedApi } from '../generated/api';\nexport const boot = () => util() || generatedApi() || pkg;\n",
        encoding="utf-8",
    )
    (workspace / "CMakeLists.txt").write_text("project(Demo LANGUAGES CXX CUDA)\n", encoding="utf-8")
    (workspace / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
    (workspace / "native" / "helper.go").write_text("package native\nfunc Helper() string { return \"ok\" }\n", encoding="utf-8")
    (workspace / "native" / "worker.go").write_text(
        "package native\nimport \"example.com/demo/native\"\nfunc Run() string { return native.Helper() }\n",
        encoding="utf-8",
    )
    (workspace / "Cargo.toml").write_text("[package]\nname='demo'\nversion='0.1.0'\n", encoding="utf-8")
    (workspace / "src" / "lib.rs").write_text("pub mod engine;\n", encoding="utf-8")
    (workspace / "src" / "engine.rs").write_text("pub fn engine() {}\n", encoding="utf-8")
    (workspace / "native" / "common.h").write_text("#pragma once\n", encoding="utf-8")
    (workspace / "native" / "vector_add.cu").write_text('#include "common.h"\n__global__ void vector_add() {}\n', encoding="utf-8")
    (workspace / "scripts" / "shared.sh").write_text("echo shared\n", encoding="utf-8")
    (workspace / "scripts" / "build.sh").write_text("source ./shared.sh\n", encoding="utf-8")
    (workspace / "php" / "Helper.php").write_text("<?php\nnamespace Demo;\nclass Helper {}\n", encoding="utf-8")
    (workspace / "php" / "App.php").write_text("<?php\nnamespace Demo;\nuse Demo\\Helper;\nrequire_once './Helper.php';\n", encoding="utf-8")
    (workspace / "ruby" / "lib" / "helper.rb").write_text("module Helper\nend\n", encoding="utf-8")
    (workspace / "ruby" / "lib" / "app.rb").write_text("require_relative './helper'\n", encoding="utf-8")
    (workspace / "dotnet" / "Demo.csproj").write_text("<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
    (workspace / "dotnet" / "Support" / "Helper.cs").write_text("namespace Demo.Support; public class Helper {}\n", encoding="utf-8")
    (workspace / "dotnet" / "App.cs").write_text("using Demo.Support;\nnamespace Demo; public class App { private Helper _helper = new(); }\n", encoding="utf-8")
    (workspace / "api" / "routes.py").write_text(
        "from src.worker import ship_feature\n\nclass App:\n    def get(self, _path):\n        return lambda fn: fn\n\napp = App()\n\n@app.get('/ship')\ndef ship():\n    return ship_feature()\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_engine.py").write_text(
        "import src.worker\n\ndef test_engine():\n    assert src.worker.ship_feature() == 'done'\n",
        encoding="utf-8",
    )
    (workspace / "src" / "worker.py").write_text("def ship_feature():\n    return 'done'\n", encoding="utf-8")

    semantic_index = service._build_workspace_semantic_index(workspace)

    assert semantic_index["imports_by_file"]["frontend/src/app.ts"] == [
        "frontend/src/util.ts",
        "frontend/src/index.ts",
        "frontend/generated/api.ts",
    ]
    assert semantic_index["dependents_by_file"]["frontend/src/util.ts"] == ["frontend/src/app.ts", "frontend/src/index.ts"]
    assert semantic_index["transitive_dependents_by_file"]["frontend/src/util.ts"] == ["frontend/src/app.ts", "frontend/src/index.ts"]
    assert semantic_index["call_targets_by_file"]["frontend/src/app.ts"] == ["frontend/src/util.ts", "frontend/generated/api.ts"]
    assert semantic_index["reverse_call_targets_by_file"]["frontend/generated/api.ts"] == ["frontend/src/app.ts"]
    assert semantic_index["imports_by_file"]["native/vector_add.cu"] == ["native/common.h"]
    assert semantic_index["imports_by_file"]["src/lib.rs"] == ["src/engine.rs"]
    assert semantic_index["imports_by_file"]["native/worker.go"] == ["native/helper.go"]
    assert semantic_index["imports_by_file"]["dotnet/App.cs"] == ["dotnet/Support/Helper.cs"]
    assert semantic_index["imports_by_file"]["php/App.php"] == ["php/Helper.php"]
    assert semantic_index["imports_by_file"]["ruby/lib/app.rb"] == ["ruby/lib/helper.rb"]
    assert semantic_index["imports_by_file"]["scripts/build.sh"] == ["scripts/shared.sh"]
    assert semantic_index["call_targets_by_file"]["tests/test_engine.py"] == ["src/worker.py"]
    assert semantic_index["parser_backends_by_file"]["frontend/src/app.ts"] == "js-ts-import-graph"
    assert semantic_index["parser_backends_by_file"]["src/lib.rs"] == "rust-module-graph"
    assert semantic_index["parser_backends_by_file"]["native/worker.go"] == "go-package-graph"
    assert semantic_index["parser_backends_by_file"]["dotnet/App.cs"] == "dotnet-symbol-graph"
    assert semantic_index["parser_backends_by_file"]["php/App.php"] == "php-workspace-graph"
    assert semantic_index["parser_backends_by_file"]["scripts/build.sh"] == "shell-source-graph"
    assert "javascript-typescript" in semantic_index["graph_languages"]
    assert "dotnet" in semantic_index["graph_languages"]
    assert "php" in semantic_index["graph_languages"]
    assert "cargo" in semantic_index["build_systems"]
    assert "go" in semantic_index["build_systems"]
    assert "package-json" in semantic_index["build_systems"]
    assert "cmake" in semantic_index["build_systems"]
    assert "dotnet" in semantic_index["build_systems"]
    assert "frontend/src" in semantic_index["source_roots"]
    assert "native" in semantic_index["source_roots"]
    assert "frontend/generated" in semantic_index["generated_roots"]
    assert "frontend/generated/api.ts" in semantic_index["generated_source_files"]
    assert "generated-header" in semantic_index["generated_source_reasons"]["frontend/generated/api.ts"]
    generated_edge = next(
        edge
        for edge in semantic_index["dependency_edges"]
        if edge["source"] == "frontend/src/app.ts" and edge["target"] == "frontend/generated/api.ts"
    )
    assert generated_edge["backend"] == "js-ts-import-graph"
    assert generated_edge["target_generated"] is True
    assert generated_edge["provenance"].endswith("+generated_source")
    assert generated_edge["source_root"] == "frontend/src"
    assert generated_edge["target_generated_root"] == "frontend/generated"
    codegen_edge = next(
        edge
        for edge in semantic_index["codegen_edges"]
        if edge["source"] == "schemas/api.proto" and edge["target"] == "frontend/generated/api.ts"
    )
    assert codegen_edge["relation"] == "generates"
    assert semantic_index["codegen_edge_count"] >= 1
    runtime_edge = next(
        edge
        for edge in semantic_index["runtime_edges"]
        if edge["framework"] == "fastapi" and edge["target"] == "src/worker.py"
    )
    assert runtime_edge["relation"] == "route-handler-call"
    assert semantic_index["framework_counts"]["fastapi"] >= 1
    assert semantic_index["edge_confidence_counts"]["medium"] >= 1
    assert semantic_index["call_edge_count"] >= 3
    assert semantic_index["call_confidence_counts"]["low"] >= 1
    assert semantic_index["edge_count"] >= 8
    assert semantic_index["dependency_edges"] == sorted(
        semantic_index["dependency_edges"],
        key=lambda edge: (
            str(edge.get("relation") or ""),
            str(edge.get("framework") or ""),
            str(edge.get("generator_kind") or ""),
            str(edge.get("language") or ""),
            str(edge.get("source") or ""),
            str(edge.get("target") or ""),
        ),
    )
    cached_semantic_index = service._build_workspace_semantic_index(workspace)
    assert cached_semantic_index["cache_hit"] is True


def test_provider_runtime_status_falls_back_cleanly_when_detection_blows_up(monkeypatch) -> None:
    workspace = Path(sample_workspace("capability-provider-fallback"))
    workspace.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        project = Project(
            name="Capability Provider Fallback",
            idea="Exercise provider fallback behavior.",
            workspace_path=workspace.as_posix(),
            runner_mode="dry_run",
            manager_mode="auto",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        settings = service._project_settings(db, project)
        monkeypatch.setattr(
            "system_status.detect_provider_statuses",
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("probe failed")),
        )

        payload = service._provider_runtime_status(settings)

        assert payload["provider"] == "codex"
        assert payload["runtime_ready"] is False
        assert payload["runtime_status"] == "unknown"
        assert "probe failed" in payload["runtime_blockers"][0]
    finally:
        db.close()
