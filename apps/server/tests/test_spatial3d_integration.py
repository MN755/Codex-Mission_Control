from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from models import Agent, Project, Task
from prompts import manager_action_prompt, worker_task_prompt
from tool_catalog import catalog_with_permissions
from workspace_tooling import detect_workspace_tooling


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_tool_catalog_surfaces_spatial3d_tools_when_repo_signals_exist(monkeypatch) -> None:
    monkeypatch.setattr(
        "tool_catalog.detect_spatial3d_repo_mode",
        lambda _root: {
            "enabled": True,
            "mode": "spatial3d_blender",
            "frameworks": ["3D Gaussian Splatting", "Blender", "OpenUSD", "Geospatial / GIS"],
            "product_workflows": ["blender_automation", "usd_scene_graph", "splat_compression", "visual_regression", "geospatial_gis", "cloud_reconstruction"],
            "asset_paths": ["scene.blend", "assets/capture.spz"],
            "render_commands": ["python scripts/render.py"],
        },
    )
    monkeypatch.setattr(
        "tool_catalog.build_spatial3d_validation_plan",
        lambda _root: {"summary": "Spatial validation planning is available.", "available": True},
    )
    monkeypatch.setattr(
        "tool_catalog.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"python", "blender"} else None,
    )

    payload = catalog_with_permissions(provider="codex", connected_accounts={}, permission_overrides={})
    tools = {item["id"]: item for item in payload}

    assert tools["spatial3d-asset-pipeline"]["availability"] == "available"
    assert tools["blender-headless-validation"]["availability"] == "available"
    assert tools["usd-scene-graph-validation"]["availability"] == "available"
    assert tools["splat-conversion-compression"]["availability"] == "available"
    assert tools["scene-visual-regression"]["availability"] == "available"
    assert tools["geospatial-3d-validation"]["availability"] == "available"
    assert tools["capture-reconstruction-orchestration"]["availability"] == "available"
    assert tools["neural-graphics-benchmarking"]["availability"] == "available"


def test_workspace_tooling_surfaces_spatial3d_lane(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "spatial3d-tooling"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\nname='spatial-tooling'\n")
    _write(workspace / "scene.blend", "blend\n")
    _write(workspace / "assets" / "capture.spz", "spz\n")
    _write(workspace / "scripts" / "convert_splats.py", "print('convert')\n")
    _write(workspace / "benchmarks" / "render_benchmark.py", "print('bench')\n")
    _write(workspace / "configs" / "scene.yaml", "lod: true\n")
    _write(workspace / "README.md", "blender ffmpeg qgis drone capture webgpu benchmark\n")

    monkeypatch.setattr(
        "spatial3d_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"python", "blender", "ffmpeg"} else None,
    )

    payload = detect_workspace_tooling(workspace.as_posix(), project_name="Spatial Tooling")

    assert "spatial3d:ready" in payload["product_lane_statuses"]
    assert any("Spatial lane `" in item for item in payload["execution_lane_summaries"])
    assert "scene.blend" in payload["artifact_paths"]
    assert any("convert_splats.py" in item for item in payload["execution_entrypoints"])
    assert payload["spatial3d_repo"]["enabled"] is True
    assert payload["spatial3d_validation_plan"]["status"] == "ready"


def test_prompts_surface_spatial3d_mode_and_evidence(monkeypatch) -> None:
    project = Project(name="Spatial Prompt Demo", idea="Ship a spatial viewer", workspace_path=sample_workspace("prompt-spatial"), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Spatial Worker", role="renderer", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=9,
        project_id=1,
        title="Implement the scene validation lane",
        goal="Build and validate the spatial render path honestly.",
        scope="Touch the Blender and conversion path only.",
        agent_role="renderer",
        milestone="Milestone 1",
        allowed_paths_json=["scene.blend", "scripts/render.py"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the spatial validation loop"],
        success_criteria_json=["The render path is validated honestly"],
        estimated_complexity="medium",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    monkeypatch.setattr(
        "spatial3d_support.detect_spatial3d_repo_mode",
        lambda _workspace: {
            "enabled": True,
            "mode": "spatial3d_blender",
            "frameworks": ["3D Gaussian Splatting", "Blender", "Browser 3D"],
            "product_workflows": ["blender_automation", "visual_regression", "browser_renderer"],
            "important_paths": ["scene.blend", "scripts/render.py"],
            "asset_paths": ["scene.blend", "assets/capture.spz"],
            "render_commands": ["python scripts/render.py"],
            "conversion_commands": [],
            "capture_commands": [],
            "benchmark_commands": ["python benchmarks/render_benchmark.py"],
        },
    )
    monkeypatch.setattr(
        "spatial3d_support.build_spatial3d_validation_plan",
        lambda _workspace: {
            "available": True,
            "status": "blocked",
            "steps": [
                {"title": "Run a scene render or validation pass", "command": "python scripts/render.py", "type": "render", "status": "pending"},
            ],
            "blockers": ["Install Blender or add a repo-owned Python render-validation script so Blender workflows are testable instead of mythical."],
            "recommended_fixes": ["Install Blender or add a repo-owned Python render-validation script so Blender workflows are testable instead of mythical."],
            "evidence_targets": ["At least one render, scene graph, or artifact inspection output after code changes."],
            "product_workflows": ["blender_automation", "visual_regression", "browser_renderer"],
        },
    )

    worker_prompt = worker_task_prompt(project, agent, task, docs_path="docs")
    manager_prompt = manager_action_prompt(
        project,
        docs_path="docs",
        action="tasks.decompose",
        objective="Plan the spatial renderer work",
        response_schema={"ok": True},
        payload={"project": "spatial"},
    )

    assert "Spatial 3D product mode" in worker_prompt
    assert "scene.blend" in worker_prompt
    assert "spatial evidence to capture" in worker_prompt.lower()
    assert "Spatial 3D product mode" in manager_prompt
    assert "blender_automation" in manager_prompt
