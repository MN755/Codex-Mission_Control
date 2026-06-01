from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from spatial3d_support import build_spatial3d_validation_plan, detect_spatial3d_repo_mode


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_spatial3d_repo_mode_finds_blender_usd_and_capture_signals() -> None:
    workspace = Path(sample_workspace("spatial3d-detect"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "pyproject.toml",
        """
        [project]
        name = "spatial-demo"
        dependencies = ["openusd", "pyproj"]
        """,
    )
    _write(workspace / "scene.blend", "blend\n")
    _write(workspace / "assets" / "scene.usda", "usd\n")
    _write(workspace / "assets" / "capture.spz", "spz\n")
    _write(workspace / "scripts" / "convert_splats.py", "print('convert')\n")
    _write(workspace / "benchmarks" / "render_benchmark.py", "print('bench')\n")
    _write(workspace / "pipeline" / "capture.py", "print('capture')\n")
    _write(workspace / "configs" / "streaming.yaml", "lod: enabled\n")
    _write(
        workspace / "README.md",
        "Blender, Hydra, drone capture, ffmpeg, QGIS, and benchmark workflows live here.\n",
    )

    payload = detect_spatial3d_repo_mode(workspace)

    assert payload["enabled"] is True
    assert payload["mode"] in {"spatial3d_blender", "spatial3d_usd", "spatial3d_geospatial"}
    assert "Blender" in payload["frameworks"]
    assert "OpenUSD" in payload["frameworks"]
    assert "3D Gaussian Splatting" in payload["frameworks"]
    assert "python -m pip install -e ." in payload["build_commands"]
    assert "python scripts/convert_splats.py" in payload["conversion_commands"]
    assert "python benchmarks/render_benchmark.py" in payload["benchmark_commands"]
    assert "python pipeline/capture.py" in payload["capture_commands"]
    assert "assets/capture.spz" in payload["asset_paths"]
    assert "configs/streaming.yaml" in payload["config_paths"]
    assert "blender_automation" in payload["product_workflows"]
    assert "cloud_reconstruction" in payload["product_workflows"]


def test_detect_spatial3d_repo_mode_does_not_treat_marketing_readme_as_repo_signal(tmp_path: Path) -> None:
    workspace = tmp_path / "spatial3d-readme-only"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(
        workspace / "README.md",
        "Mission Control can help with Blender, USD, GIS, FFmpeg, drone capture, and Gaussian splatting.\n",
    )

    payload = detect_spatial3d_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["mode"] is None


def test_spatial3d_validation_plan_surfaces_render_convert_and_inspect_steps(monkeypatch) -> None:
    workspace = Path(sample_workspace("spatial3d-plan"))
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "pyproject.toml", "[project]\nname='spatial-plan'\n")
    _write(workspace / "scene.blend", "blend\n")
    _write(workspace / "capture.mp4", "video\n")
    _write(workspace / "scripts" / "convert_splats.py", "print('convert')\n")
    _write(workspace / "benchmarks" / "render_benchmark.py", "print('bench')\n")
    _write(workspace / "README.md", "blender ffmpeg webgpu benchmark\n")

    monkeypatch.setattr(
        "spatial3d_support.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"python", "blender", "ffmpeg"} else None,
    )

    payload = build_spatial3d_validation_plan(workspace)

    assert payload["available"] is True
    assert payload["status"] == "ready"
    assert any(step["type"] == "render" for step in payload["steps"])
    assert any(step["type"] == "convert" for step in payload["steps"])
    assert any(step["type"] == "benchmark" for step in payload["steps"])
    assert any(step["type"] == "inspect" for step in payload["steps"])
    assert any("render, scene graph, or artifact inspection" in target.lower() for target in payload["evidence_targets"])


def test_spatial3d_validation_plan_flags_missing_blender_and_repo_commands(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "spatial3d-no-runtime"
    workspace.mkdir(parents=True, exist_ok=True)
    _write(workspace / "scene.blend", "blend\n")
    _write(workspace / "README.md", "blender hydra\n")

    monkeypatch.setattr("spatial3d_support.shutil.which", lambda _command: None)

    payload = build_spatial3d_validation_plan(workspace)

    assert payload["status"] == "blocked"
    assert any("blender workflows are detected" in item.lower() for item in payload["blockers"])
    assert any("install blender" in item.lower() or "python render-validation script" in item.lower() for item in payload["recommended_fixes"])


def test_detect_spatial3d_repo_mode_handles_deleted_workspace_gracefully() -> None:
    workspace = Path(sample_workspace("spatial3d-deleted"))
    workspace.mkdir(parents=True, exist_ok=True)
    workspace.rmdir()

    payload = detect_spatial3d_repo_mode(workspace)

    assert payload["enabled"] is False
    assert payload["frameworks"] == []
    assert payload["asset_paths"] == []
