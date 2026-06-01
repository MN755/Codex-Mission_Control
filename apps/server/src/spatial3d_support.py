from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


MAX_SCANNED_FILES = 1800
TEXT_EXTENSIONS = {".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml", ".md"}
PROJECT_TEXT_CANDIDATES = [
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "environment.yml",
    "environment.yaml",
    "setup.py",
    "README.md",
]
SKIPPED_SCAN_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".runtime",
    "dist",
    "build",
    "artifacts",
}
SKIPPED_DISCOVERY_DIRS = SKIPPED_SCAN_DIRS
ASSET_EXTENSIONS = {
    ".blend",
    ".ply",
    ".splat",
    ".spz",
    ".usda",
    ".usd",
    ".usdc",
    ".usdz",
    ".opf",
    ".obj",
    ".fbx",
    ".glb",
    ".gltf",
    ".las",
    ".laz",
    ".e57",
    ".tif",
    ".tiff",
}
POINT_CLOUD_EXTENSIONS = {".ply", ".las", ".laz", ".e57"}
SCENE_EXTENSIONS = {".blend", ".usd", ".usda", ".usdc", ".usdz", ".glb", ".gltf", ".fbx", ".obj"}
CONFIG_FILE_EXTENSIONS = {".yaml", ".yml", ".json", ".toml", ".cfg"}
CONFIG_DIR_HINTS = {"config", "configs", "conf", "settings", "render", "scene", "streaming", "gis", "capture", "reconstruction"}
CONFIG_FILE_HINTS = {"config", "render", "scene", "stream", "lod", "capture", "reconstruct", "crs", "gis", "benchmark"}
RENDER_SCRIPT_CANDIDATES = [
    "render.py",
    "scripts/render.py",
    "tools/render.py",
    "scripts/blender_validate.py",
    "tools/blender_scene_check.py",
    "tests/test_render.py",
]
BENCHMARK_FILE_CANDIDATES = [
    "benchmark.py",
    "scripts/benchmark.py",
    "benchmarks/render_benchmark.py",
    "benchmarks/streaming_benchmark.py",
]
CONVERSION_FILE_CANDIDATES = [
    "convert.py",
    "scripts/convert.py",
    "scripts/convert_splats.py",
    "tools/convert_assets.py",
]
CAPTURE_FILE_CANDIDATES = [
    "capture.py",
    "ingest.py",
    "scripts/ingest_capture.py",
    "pipeline/capture.py",
    "pipeline/reconstruct.py",
]
WORKFLOW_PRIORITY = [
    "three_d_asset_pipeline",
    "blender_automation",
    "usd_scene_graph",
    "splat_compression",
    "visual_regression",
    "browser_renderer",
    "lod_streaming",
    "drone_capture",
    "geospatial_gis",
    "simulation_real2sim",
    "asset_provenance",
    "codec_pipeline",
    "mobile_capture",
    "cloud_reconstruction",
    "dataset_quality",
    "scene_authoring",
    "virtual_production",
    "digital_preservation",
    "neural_graphics_benchmarking",
    "research_to_code",
]


def _scan_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    try:
        for path in root.rglob("*"):
            if any(part.lower() in SKIPPED_SCAN_DIRS for part in path.parts):
                continue
            try:
                if path.is_file():
                    files.append(path)
            except OSError:
                continue
            if len(files) >= MAX_SCANNED_FILES:
                break
    except OSError:
        return []
    return files


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _shell_quote(value: str) -> str:
    text = str(value or "")
    if not text:
        return "''"
    if all(char.isalnum() or char in "._/-:=+@" for char in text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _python_script_command(relative_path: str) -> str:
    return f"python {_shell_quote(relative_path)}"


def _relative_workspace_entries(root: Path) -> list[str]:
    entries: set[str] = set()
    for path in _scan_files(root):
        relative = path.relative_to(root)
        entries.add(relative.as_posix())
        for parent in relative.parents:
            if str(parent) != ".":
                entries.add(parent.as_posix())
    return sorted(entries)


def _find_workspace_candidate(root: Path, candidates: list[str]) -> str | None:
    normalized_candidates = [candidate.replace("\\", "/") for candidate in candidates]
    entries = _relative_workspace_entries(root)
    entry_set = set(entries)
    for candidate in normalized_candidates:
        if candidate in entry_set:
            return candidate
        path = root / candidate
        if path.exists():
            return candidate
    for candidate in normalized_candidates:
        suffix = f"/{candidate}"
        for entry in entries:
            if entry.endswith(suffix):
                return entry
            if "/" not in candidate and Path(entry).name == candidate:
                return entry
    return None


def _find_workspace_directory_candidate(root: Path, candidates: list[str]) -> str | None:
    normalized_candidates = [candidate.replace("\\", "/") for candidate in candidates]
    dirs: list[str] = []
    try:
        for path in root.rglob("*"):
            if not path.is_dir():
                continue
            relative = path.relative_to(root)
            if any(part.lower() in SKIPPED_DISCOVERY_DIRS for part in relative.parts):
                continue
            dirs.append(relative.as_posix())
    except OSError:
        return None
    dir_set = set(dirs)
    for candidate in normalized_candidates:
        if candidate in dir_set:
            return candidate
        suffix = f"/{candidate}"
        for entry in dirs:
            if entry.endswith(suffix):
                return entry
            if "/" not in candidate and Path(entry).name == candidate:
                return entry
    return None


def _config_paths(relative_paths: list[str]) -> list[str]:
    config_paths: list[str] = []
    for relative in relative_paths:
        path = Path(relative)
        suffix = path.suffix.lower()
        if suffix not in CONFIG_FILE_EXTENSIONS:
            continue
        if path.name in {"package.json", "pyproject.toml"}:
            continue
        stem = path.stem.lower()
        parent_names = {part.lower() for part in path.parts[:-1]}
        if parent_names & CONFIG_DIR_HINTS or any(hint in stem for hint in CONFIG_FILE_HINTS):
            config_paths.append(relative)
    return sorted(config_paths)


def _build_python_install_command(root: Path) -> str | None:
    root_pyproject = root / "pyproject.toml"
    root_setup = root / "setup.py"
    if root_pyproject.exists() or root_setup.exists():
        return "python -m pip install -e ."
    nested_editable = _find_workspace_candidate(root, ["pyproject.toml", "setup.py"])
    if nested_editable:
        install_root = Path(nested_editable).parent.as_posix()
        install_root = "." if install_root == "." else install_root
        return f"python -m pip install -e {install_root}"
    nested_requirements = _find_workspace_candidate(root, ["requirements.txt", "requirements-dev.txt"])
    if nested_requirements:
        return f"python -m pip install -r {nested_requirements}"
    return None


def _asset_paths(root: Path) -> list[str]:
    assets: list[str] = []
    for path in _scan_files(root):
        suffix = path.suffix.lower()
        if suffix in ASSET_EXTENSIONS:
            assets.append(path.relative_to(root).as_posix())
    return sorted(set(assets))


def _primary_scene_path(asset_paths: list[str]) -> str | None:
    for path in asset_paths:
        if Path(path).suffix.lower() in SCENE_EXTENSIONS:
            return path
    return None


def _first_video_path(root: Path) -> str | None:
    for path in _scan_files(root):
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
            return path.relative_to(root).as_posix()
    return None


def _first_image_dir(root: Path) -> str | None:
    for candidate in ("images", "frames", "captures", "dataset/images", "dataset/frames"):
        path = root / candidate
        if path.exists() and path.is_dir():
            return candidate.replace("\\", "/")
    return None


def detect_spatial3d_repo_mode(workspace_path: str | Path) -> dict[str, Any]:
    root = Path(workspace_path)
    if not root.exists() or not root.is_dir():
        return {
            "enabled": False,
            "mode": None,
            "signals": [],
            "languages": [],
            "frameworks": [],
            "build_commands": [],
            "test_commands": [],
            "render_commands": [],
            "validation_commands": [],
            "benchmark_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
            "asset_paths": [],
            "scene_paths": [],
            "config_paths": [],
        }

    files = _scan_files(root)
    relative_paths = [path.relative_to(root).as_posix() for path in files]
    languages: list[str] = []
    frameworks: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    render_commands: list[str] = []
    validation_commands: list[str] = []
    benchmark_commands: list[str] = []
    conversion_commands: list[str] = []
    capture_commands: list[str] = []
    product_workflows: list[str] = []
    validation_notes: list[str] = []
    signals: list[str] = []
    important_paths: list[str] = []
    asset_paths = _asset_paths(root)
    scene_paths = [path for path in asset_paths if Path(path).suffix.lower() in SCENE_EXTENSIONS]
    config_paths = _config_paths(relative_paths)

    if any(path.suffix.lower() in {".py", ".ipynb"} for path in files):
        languages.append("Python")
    if any(path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"} for path in files):
        languages.append("JavaScript/TypeScript")

    project_texts: list[str] = []
    supporting_texts: list[str] = []
    for candidate in PROJECT_TEXT_CANDIDATES:
        path = root / candidate
        if path.exists():
            important_paths.append(candidate.replace("\\", "/"))
            if candidate.lower() == "readme.md":
                supporting_texts.append(_safe_read_text(path))
            else:
                project_texts.append(_safe_read_text(path))
    code_texts: list[str] = []
    for path in files:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if path.name.lower() == "readme.md":
            continue
        code_texts.append(_safe_read_text(path))
        if len(code_texts) >= 32:
            break
    combined_text = "\n".join(project_texts + code_texts).lower()
    supporting_text = "\n".join(project_texts + code_texts + supporting_texts).lower()

    spatial_tokens = (
        "gaussian splat",
        "3dgs",
        "gsplat",
        ".splat",
        ".spz",
        "point cloud",
        "mesh",
        "camera pose",
        "reconstruction",
        "bpy",
        "blender",
        "usd",
        "hydra",
        "solaris",
        "lop",
        "houdini",
        "ffmpeg",
        "webgpu",
        "webgl",
        "playcanvas",
        "cesium",
        "mapbox",
        "arcgis",
        "qgis",
        "pix4d",
        "drone",
        "exif",
        "gps",
        "isaac sim",
        "carla",
        "unreal",
        "unity",
        "gazebo",
        "watermark",
        "provenance",
    )
    core_signal = bool(asset_paths) or any(token in combined_text for token in spatial_tokens)
    if not core_signal:
        return {
            "enabled": False,
            "mode": None,
            "signals": [],
            "languages": _dedupe(languages),
            "frameworks": [],
            "build_commands": [],
            "test_commands": [],
            "render_commands": [],
            "validation_commands": [],
            "benchmark_commands": [],
            "conversion_commands": [],
            "capture_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
            "asset_paths": [],
            "scene_paths": [],
            "config_paths": [],
        }

    _append_unique(frameworks, ["3D Asset Pipelines"])
    signals.append("Detected spatial or 3D asset repo signals in project files or asset paths.")
    if any(Path(path).suffix.lower() in {".ply", ".splat", ".spz", ".opf"} for path in asset_paths) or "gaussian splat" in combined_text or "gsplat" in combined_text:
        frameworks.append("3D Gaussian Splatting")
        _append_unique(product_workflows, ["three_d_asset_pipeline", "splat_compression"])
        signals.append("Detected Gaussian splat assets or repo signals.")
    if any(Path(path).suffix.lower() == ".blend" for path in asset_paths) or any(token in combined_text for token in ("bpy", "blender")):
        frameworks.append("Blender")
        _append_unique(product_workflows, ["blender_automation", "visual_regression"])
        signals.append("Detected Blender scene automation signals.")
    if any(Path(path).suffix.lower() in {".usd", ".usda", ".usdc", ".usdz"} for path in asset_paths) or any(token in combined_text for token in ("pxr", "usd", "hydra")):
        frameworks.append("OpenUSD")
        _append_unique(product_workflows, ["usd_scene_graph"])
        signals.append("Detected USD scene graph or Hydra renderer signals.")
    if any(token in combined_text for token in ("houdini", "solaris", "lop")):
        frameworks.append("Houdini / Solaris")
        _append_unique(product_workflows, ["usd_scene_graph"])
        signals.append("Detected Houdini or Solaris pipeline signals.")
    if any(token in combined_text for token in ("ffmpeg", "av1", "webm", "mp4", "image sequence")):
        frameworks.append("FFmpeg / Media Pipelines")
        _append_unique(product_workflows, ["codec_pipeline"])
        signals.append("Detected video or codec pipeline signals.")
    if any(token in combined_text for token in ("webgl", "webgpu", "three.js", "playcanvas", "verge3d", "viewer")):
        frameworks.append("Browser 3D")
        _append_unique(product_workflows, ["browser_renderer", "lod_streaming", "visual_regression"])
        signals.append("Detected browser-based renderer signals.")
    if any(token in combined_text for token in ("arcgis", "qgis", "cesium", "mapbox", "geotiff", "crs", "georeference", "pix4d")) or any(Path(path).suffix.lower() in {".tif", ".tiff", ".las", ".laz"} for path in asset_paths):
        frameworks.append("Geospatial / GIS")
        _append_unique(product_workflows, ["geospatial_gis", "dataset_quality"])
        signals.append("Detected geospatial or GIS validation signals.")
    if any(token in combined_text for token in ("drone", "exif", "gps", "site scan", "realityscan", "scaniverse", "capture")):
        frameworks.append("Capture / Reconstruction")
        _append_unique(product_workflows, ["drone_capture", "mobile_capture", "cloud_reconstruction", "dataset_quality"])
        signals.append("Detected capture, drone, or reconstruction workflow signals.")
    if any(token in combined_text for token in ("isaac sim", "carla", "unity", "unreal", "gazebo", "real2sim")):
        frameworks.append("Simulation")
        _append_unique(product_workflows, ["simulation_real2sim", "virtual_production"])
        signals.append("Detected simulation or virtual production signals.")
    if any(token in combined_text for token in ("watermark", "provenance", "lineage", "ownership", "license")):
        frameworks.append("Asset Provenance")
        _append_unique(product_workflows, ["asset_provenance", "digital_preservation"])
        signals.append("Detected provenance or ownership tracking signals.")
    if any(token in combined_text for token in ("benchmark", "fps", "frame time", "gpu memory", "compression ratio")):
        _append_unique(product_workflows, ["neural_graphics_benchmarking"])
        signals.append("Detected benchmarking or renderer-performance signals.")
    if any(token in supporting_text for token in ("paper", "arxiv", "research", "prototype", "baseline comparison")):
        _append_unique(product_workflows, ["research_to_code"])
        signals.append("Detected research-to-prototype workflow signals.")
    if any(token in combined_text for token in ("authoring", "hotspot", "tour", "annotation", "virtual staging")):
        _append_unique(product_workflows, ["scene_authoring"])
        signals.append("Detected scene-authoring workflow signals.")

    if "dataset_quality" in product_workflows:
        _append_unique(product_workflows, ["three_d_asset_pipeline"])
    if "virtual_production" in product_workflows:
        _append_unique(product_workflows, ["visual_regression"])
    if "asset_provenance" in product_workflows:
        _append_unique(product_workflows, ["digital_preservation"])

    build_command = _build_python_install_command(root)
    if build_command:
        build_commands.append(build_command)
    if "pytest" in combined_text or any("test" in path.lower() and path.endswith(".py") for path in relative_paths):
        test_commands.append("python -m pytest")

    render_entry = _find_workspace_candidate(root, RENDER_SCRIPT_CANDIDATES)
    benchmark_entry = _find_workspace_candidate(root, BENCHMARK_FILE_CANDIDATES)
    conversion_entry = _find_workspace_candidate(root, CONVERSION_FILE_CANDIDATES)
    capture_entry = _find_workspace_candidate(root, CAPTURE_FILE_CANDIDATES)
    primary_scene = _primary_scene_path(asset_paths)
    video_path = _first_video_path(root)
    image_dir = _first_image_dir(root)

    if render_entry:
        render_commands.append(_python_script_command(render_entry))
        important_paths.append(render_entry)
    if primary_scene and Path(primary_scene).suffix.lower() == ".blend":
        render_commands.append(f"blender --background {_shell_quote(primary_scene)} --render-frame 1")
    if benchmark_entry:
        benchmark_commands.append(_python_script_command(benchmark_entry))
        important_paths.append(benchmark_entry)
        _append_unique(product_workflows, ["neural_graphics_benchmarking"])
    if conversion_entry:
        conversion_commands.append(_python_script_command(conversion_entry))
        important_paths.append(conversion_entry)
    if capture_entry:
        capture_commands.append(_python_script_command(capture_entry))
        important_paths.append(capture_entry)

    if primary_scene and Path(primary_scene).suffix.lower() in {".usd", ".usda", ".usdc", ".usdz"} and shutil.which("python"):
        usd_literal = json.dumps(primary_scene)
        validation_commands.append(
            "python -c "
            f"\"from pathlib import Path; from pxr import Usd; stage = Usd.Stage.Open(str(Path({usd_literal}))); "
            "print({'opened': bool(stage)})\""
        )
    if primary_scene and Path(primary_scene).suffix.lower() == ".blend" and shutil.which("blender"):
        validation_commands.append(f"blender --background {_shell_quote(primary_scene)} --render-frame 1")
    if video_path and shutil.which("ffmpeg"):
        validation_commands.append(
            f"ffmpeg -hide_banner -loglevel error -i {_shell_quote(video_path)} -frames:v 1 {_shell_quote('artifacts/preview-frame.png')}"
        )
        _append_unique(product_workflows, ["codec_pipeline"])
    if image_dir and shutil.which("ffmpeg"):
        validation_commands.append(
            f"ffmpeg -hide_banner -loglevel error -pattern_type glob -i {_shell_quote(image_dir + '/*.jpg')} -frames:v 1 {_shell_quote('artifacts/capture-preview.mp4')}"
        )
    if asset_paths and shutil.which("python"):
        validation_commands.append(
            "python -c "
            f"\"from pathlib import Path; root = Path({json.dumps(str(root))}); "
            "assets = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.suffix.lower() in "
            f"{sorted(ASSET_EXTENSIONS)!r}); print({{'asset_count': len(assets), 'sample_assets': assets[:8]}})\""
        )

    if asset_paths:
        _append_unique(important_paths, asset_paths[:8])
    if config_paths:
        _append_unique(important_paths, config_paths[:4])

    validation_notes.extend(
        [
            "Keep asset inspection, render validation, streaming checks, and packaging checks separate instead of calling one screenshot the whole truth.",
            "Capture frame, scene, and artifact evidence after renderer or conversion changes so visual regressions stop hiding behind green unit tests.",
            "Treat coordinate systems, camera poses, capture metadata, and compression settings as evidence-bearing inputs, not optional folklore.",
        ]
    )
    if "browser_renderer" in product_workflows:
        validation_notes.append("For browser renderers, measure asset loading, frame pacing, and LOD behavior instead of assuming a successful build means the viewer is sane.")
    if "geospatial_gis" in product_workflows:
        validation_notes.append("For geospatial scenes, validate CRS assumptions and layer alignment before trusting any city-scale visualization.")
    if "dataset_quality" in product_workflows:
        validation_notes.append("For capture pipelines, fail fast on bad overlap, weak metadata, or missing angles before expensive reconstruction jobs start eating money.")

    mode = "spatial3d_general"
    if "simulation_real2sim" in product_workflows:
        mode = "spatial3d_simulation"
    elif "geospatial_gis" in product_workflows:
        mode = "spatial3d_geospatial"
    elif "usd_scene_graph" in product_workflows:
        mode = "spatial3d_usd"
    elif "blender_automation" in product_workflows:
        mode = "spatial3d_blender"

    return {
        "enabled": True,
        "mode": mode,
        "signals": _dedupe(signals),
        "languages": _dedupe(languages or ["Python"]),
        "frameworks": _dedupe(frameworks),
        "build_commands": _dedupe(build_commands),
        "test_commands": _dedupe(test_commands),
        "render_commands": _dedupe(render_commands),
        "validation_commands": _dedupe(validation_commands),
        "benchmark_commands": _dedupe(benchmark_commands),
        "conversion_commands": _dedupe(conversion_commands),
        "capture_commands": _dedupe(capture_commands),
        "product_workflows": [item for item in WORKFLOW_PRIORITY if item in set(product_workflows)],
        "validation_notes": _dedupe(validation_notes),
        "important_paths": _dedupe(important_paths),
        "asset_paths": _dedupe(asset_paths),
        "scene_paths": _dedupe(scene_paths),
        "config_paths": _dedupe(config_paths),
    }


def build_spatial3d_validation_plan(workspace_path: str | Path) -> dict[str, Any]:
    repo_mode = detect_spatial3d_repo_mode(workspace_path)
    if not repo_mode.get("enabled"):
        return {
            "available": False,
            "status": "not_applicable",
            "summary": "This workspace does not currently look like a spatial 3D or Gaussian-splat repo.",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "steps": [],
            "blockers": [],
            "recommended_fixes": [],
            "evidence_targets": [],
            "product_workflows": [],
        }

    steps: list[dict[str, Any]] = []
    for command in list(repo_mode.get("build_commands") or []):
        steps.append({"title": "Install or sync spatial pipeline dependencies", "command": command, "type": "build", "status": "pending"})
    for command in list(repo_mode.get("test_commands") or []):
        steps.append({"title": "Run repo-native spatial tests", "command": command, "type": "test", "status": "pending"})
    for command in list(repo_mode.get("render_commands") or []):
        steps.append({"title": "Run a scene render or validation pass", "command": command, "type": "render", "status": "pending"})
    for command in list(repo_mode.get("conversion_commands") or []):
        steps.append({"title": "Run a splat or asset conversion path", "command": command, "type": "convert", "status": "pending"})
    for command in list(repo_mode.get("capture_commands") or []):
        steps.append({"title": "Run the capture or reconstruction ingestion path", "command": command, "type": "capture", "status": "pending"})
    for command in list(repo_mode.get("benchmark_commands") or []):
        steps.append({"title": "Benchmark neural-graphics performance", "command": command, "type": "benchmark", "status": "pending"})
    for command in list(repo_mode.get("validation_commands") or []):
        steps.append({"title": "Inspect artifacts or runtime evidence", "command": command, "type": "inspect", "status": "pending"})

    blockers: list[str] = []
    recommended_fixes: list[str] = []
    python_available = bool(shutil.which("python"))
    blender_available = bool(shutil.which("blender"))
    ffmpeg_available = bool(shutil.which("ffmpeg"))
    workflows = list(repo_mode.get("product_workflows") or [])

    if not any(repo_mode.get(key) for key in ("test_commands", "render_commands", "conversion_commands", "capture_commands", "benchmark_commands", "validation_commands")):
        blockers.append("No executable spatial validation entrypoint was detected yet.")
        recommended_fixes.append("Add or document a repo-owned render, conversion, benchmark, or validation command so Mission Control can test something real.")
    if repo_mode.get("render_commands") and any(str(command).startswith("python ") for command in list(repo_mode.get("render_commands") or [])) and not python_available:
        blockers.append("Python is not available on PATH for the repo-owned spatial render or validation scripts.")
    if "blender_automation" in workflows and not blender_available and not any(str(command).startswith("python ") for command in list(repo_mode.get("render_commands") or [])):
        blockers.append("Blender workflows are detected, but Blender is not available and no repo-owned Python render-validation script was found.")
    if "blender_automation" in workflows and not blender_available and not any(str(command).startswith("python ") for command in list(repo_mode.get("render_commands") or [])):
        recommended_fixes.append("Install Blender or add a repo-owned Python render-validation script so Blender workflows are testable instead of mythical.")
    if "codec_pipeline" in workflows and not ffmpeg_available:
        recommended_fixes.append("Install FFmpeg so frame extraction and preview generation can be validated locally.")
    if "usd_scene_graph" in workflows and not python_available:
        recommended_fixes.append("Expose Python on PATH so USD scene inspection commands can run locally.")
    if "browser_renderer" in workflows and not any("render" in str(command).lower() or "benchmark" in str(command).lower() for command in list(repo_mode.get("benchmark_commands") or []) + list(repo_mode.get("validation_commands") or [])):
        recommended_fixes.append("Add a browser-render benchmark or visual-regression command so WebGL/WebGPU changes stop shipping on vibes.")
    if "geospatial_gis" in workflows and not repo_mode.get("config_paths"):
        recommended_fixes.append("Document the CRS, georeference, or layer config files so geospatial validation has something concrete to inspect.")
    if "cloud_reconstruction" in workflows and not any(str(command).startswith("python ") for command in list(repo_mode.get("capture_commands") or [])):
        recommended_fixes.append("Add a repo-owned reconstruction orchestration script or CLI wrapper so job monitoring is testable.")

    evidence_targets = _dedupe(
        [
            "Asset inventory and extension summary after intake.",
            "At least one render, scene graph, or artifact inspection output after code changes.",
            "Compression, benchmark, or streaming evidence when the workflow claims performance or size improvements.",
            *[str(item) for item in list(repo_mode.get("validation_notes") or [])],
        ]
    )

    status = "blocked" if blockers else "ready"
    summary = (
        "Mission Control can run a spatial 3D / Gaussian-splat validation lane for this workspace."
        if not blockers
        else "Mission Control detected a spatial 3D repo, but the validation lane still has real blockers."
    )
    return {
        "available": True,
        "status": status,
        "summary": summary,
        "repo_mode_enabled": True,
        "repo_mode": repo_mode.get("mode"),
        "steps": steps[:18],
        "blockers": _dedupe(blockers),
        "recommended_fixes": _dedupe(recommended_fixes)[:12],
        "evidence_targets": evidence_targets[:12],
        "product_workflows": workflows,
    }
