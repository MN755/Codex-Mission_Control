from __future__ import annotations

from dataclasses import asdict, dataclass
from textwrap import dedent
from typing import Any


@dataclass(frozen=True)
class Spatial3DFeatureBundle:
    feature_id: str
    variant: str
    title: str
    summary: str
    dependencies: list[str]
    files: dict[str, str]
    validation_steps: list[str]
    evidence_targets: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_FEATURES: dict[str, dict[str, Any]] = {
    "asset_pipeline": {
        "title": "3D Asset Pipeline Integration",
        "summary": "Inspect, validate, package, and inventory 3DGS, mesh, texture, and reconstruction assets with one repo-owned lane.",
        "dependencies": ["python", "pathlib"],
        "files": {
            "spatial3d_starters/asset_manifest.py": """
                from pathlib import Path

                SUPPORTED_EXTENSIONS = {".ply", ".splat", ".spz", ".usd", ".usda", ".usdc", ".usdz", ".opf", ".obj", ".fbx", ".glb", ".gltf"}


                def build_asset_manifest(root: str) -> dict:
                    root_path = Path(root)
                    assets = []
                    for path in root_path.rglob("*"):
                        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                            assets.append(
                                {
                                    "path": str(path.relative_to(root_path)).replace("\\\\", "/"),
                                    "extension": path.suffix.lower(),
                                    "size_bytes": path.stat().st_size,
                                }
                            )
                    return {"asset_count": len(assets), "assets": assets}
            """,
            "spatial3d_starters/asset_validation.md": """
                - Validate point clouds, meshes, textures, and camera-pose folders separately.
                - Fail if required texture folders or reconstruction metadata are missing.
                - Package asset manifests with every handoff so the next worker is not spelunking blind.
            """,
        },
        "validation_steps": [
            "python -c \"from spatial3d_starters.asset_manifest import build_asset_manifest; print(build_asset_manifest('.'))\"",
            "Verify the manifest includes splats, meshes, textures, and reconstruction outputs separately.",
        ],
        "evidence_targets": ["asset manifest", "extension coverage summary", "missing dependency report"],
    },
    "blender_integration": {
        "title": "Blender Integration",
        "summary": "Generate Blender Python automation, render test scenes headlessly, and validate output frames.",
        "dependencies": ["blender", "python", "bpy"],
        "files": {
            "spatial3d_starters/blender_scene_check.py": """
                import bpy


                def main() -> None:
                    bpy.ops.object.select_all(action="SELECT")
                    object_names = sorted(obj.name for obj in bpy.data.objects)
                    print({"object_count": len(object_names), "objects": object_names[:12]})


                if __name__ == "__main__":
                    main()
            """,
            "spatial3d_starters/blender_ci.md": """
                Example headless validation:

                blender --background scene.blend --python spatial3d_starters/blender_scene_check.py --render-frame 1
            """,
        },
        "validation_steps": [
            "Run Blender in background mode with the generated scene-check script.",
            "Store a rendered frame or thumbnail and compare it to the previous baseline.",
        ],
        "evidence_targets": ["headless Blender output", "rendered frame", "scene object summary"],
    },
    "houdini_usd": {
        "title": "Houdini / USD Integration",
        "summary": "Inspect USD scene graphs, validate schemas, and script Solaris/LOP pipelines instead of treating USD like a mysterious binary blob.",
        "dependencies": ["python", "openusd", "pxr"],
        "files": {
            "spatial3d_starters/usd_stage_check.py": """
                from pxr import Usd


                def inspect_stage(path: str) -> dict:
                    stage = Usd.Stage.Open(path)
                    if stage is None:
                        raise RuntimeError(f"Failed to open USD stage: {path}")
                    prims = [prim.GetPath().pathString for prim in stage.Traverse()]
                    return {"prim_count": len(prims), "sample_prims": prims[:12]}
            """,
            "spatial3d_starters/houdini_lop_notes.md": """
                - Keep USD schema validation separate from Hydra renderer configuration.
                - Treat Solaris/LOP scripts as repo-owned pipeline assets, not local artist magic.
                - Capture dependency graphs for stage inputs before changing render delegates.
            """,
        },
        "validation_steps": [
            "Open the USD stage with pxr.Usd and record the prim count.",
            "Validate render-delegate or Hydra settings before approving a pipeline change.",
        ],
        "evidence_targets": ["USD prim inventory", "schema validation output", "Hydra or render-delegate config summary"],
    },
    "spz_conversion": {
        "title": "SPZ Compression / Conversion Integration",
        "summary": "Convert splat assets, benchmark compression ratios, and produce compatibility reports for delivery targets.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/splat_conversion_plan.py": """
                TARGET_PROFILES = {
                    "web": {"goal": "small download size", "compression": "aggressive"},
                    "mobile": {"goal": "memory-aware delivery", "compression": "balanced"},
                    "vr": {"goal": "quality-preserving playback", "compression": "quality_first"},
                    "archive": {"goal": "high-fidelity retention", "compression": "loss_minimized"},
                }


                def recommend_profile(target: str) -> dict:
                    return TARGET_PROFILES[target]
            """,
        },
        "validation_steps": [
            "Compare file size before and after compression.",
            "Generate a compatibility report for web, mobile, VR, or archive targets.",
        ],
        "evidence_targets": ["compression ratio table", "format compatibility report", "corruption check results"],
    },
    "visual_regression_3d": {
        "title": "Visual Regression Testing for 3D Scenes",
        "summary": "Compare rendered frames, detect pixel drift, and flag missing assets or broken shaders after scene changes.",
        "dependencies": ["python", "Pillow"],
        "files": {
            "spatial3d_starters/visual_regression.py": """
                from pathlib import Path

                from PIL import Image, ImageChops


                def compare_frames(reference_path: str, candidate_path: str) -> dict:
                    reference = Image.open(reference_path).convert("RGBA")
                    candidate = Image.open(candidate_path).convert("RGBA")
                    diff = ImageChops.difference(reference, candidate)
                    bbox = diff.getbbox()
                    changed = bbox is not None
                    return {"changed": changed, "diff_bbox": bbox}
            """,
        },
        "validation_steps": [
            "Render a reference frame and a changed frame.",
            "Compare their diff bounds before merging renderer or shader changes.",
        ],
        "evidence_targets": ["reference frame", "candidate frame", "pixel-diff summary"],
    },
    "browser_renderer": {
        "title": "Browser-Based 3D Renderer Integration",
        "summary": "Instrument WebGL or WebGPU viewers, watch asset-loading waterfalls, and smoke-test browser rendering with real scene inputs.",
        "dependencies": ["playwright", "node", "webgl/webgpu runtime"],
        "files": {
            "spatial3d_starters/browser_render_probe.ts": """
                // Playwright-driven scene readiness probe for browser renderers.
                import { test, expect } from "@playwright/test";

                test("viewer loads the scene and exposes timing marks", async ({ page }) => {
                  await page.goto("http://127.0.0.1:4173");
                  await expect(page.locator("[data-scene-ready='true']")).toBeVisible();
                  const diagnostics = await page.evaluate(() => (window as any).__viewerDiagnostics ?? null);
                  expect(diagnostics).not.toBeNull();
                });
            """,
        },
        "validation_steps": [
            "Run a browser smoke test that waits for scene readiness instead of just DOM readiness.",
            "Record loading waterfalls, frame rate, and renderer error output.",
        ],
        "evidence_targets": ["browser render test output", "asset loading diagnostics", "frame-rate sample"],
    },
    "lod_streaming": {
        "title": "LOD Streaming / Asset Streaming Integration",
        "summary": "Exercise chunk loading, LOD transitions, weak-network behavior, and memory pressure for large 3D scenes.",
        "dependencies": ["python", "playwright"],
        "files": {
            "spatial3d_starters/streaming_benchmark.py": """
                def summarize_streaming_metrics(chunk_latencies_ms: list[int], peak_gpu_memory_mb: int) -> dict:
                    return {
                        "chunk_count": len(chunk_latencies_ms),
                        "max_latency_ms": max(chunk_latencies_ms) if chunk_latencies_ms else 0,
                        "avg_latency_ms": (sum(chunk_latencies_ms) / len(chunk_latencies_ms)) if chunk_latencies_ms else 0,
                        "peak_gpu_memory_mb": peak_gpu_memory_mb,
                    }
            """,
        },
        "validation_steps": [
            "Measure chunk latency under at least one throttled network profile.",
            "Track LOD transition glitches and peak GPU memory during streaming.",
        ],
        "evidence_targets": ["chunk latency summary", "LOD transition notes", "GPU memory trace"],
    },
    "drone_capture": {
        "title": "Drone Capture Pipeline Integration",
        "summary": "Ingest capture metadata, validate GPS and EXIF fields, and prepare reconstruction-ready job payloads.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/capture_ingest.py": """
                from pathlib import Path


                REQUIRED_SIDECARS = {".jpg", ".jpeg", ".png"}


                def summarize_capture_folder(root: str) -> dict:
                    image_count = 0
                    for path in Path(root).rglob("*"):
                        if path.is_file() and path.suffix.lower() in REQUIRED_SIDECARS:
                            image_count += 1
                    return {"image_count": image_count, "root": root}
            """,
        },
        "validation_steps": [
            "Reject capture folders with missing imagery or obvious metadata gaps.",
            "Create a reconstruction job payload only after capture QA passes.",
        ],
        "evidence_targets": ["capture inventory", "EXIF/GPS validation summary", "reconstruction job payload"],
    },
    "geospatial_gis": {
        "title": "Geospatial / GIS Integration",
        "summary": "Validate CRS assumptions, georeferencing metadata, and layer composition for city-scale 3D projects.",
        "dependencies": ["python", "pyproj"],
        "files": {
            "spatial3d_starters/crs_validator.py": """
                from pyproj import CRS


                def validate_crs(crs_code: str) -> dict:
                    crs = CRS.from_user_input(crs_code)
                    return {"name": crs.name, "is_projected": crs.is_projected, "to_authority": crs.to_authority()}
            """,
        },
        "validation_steps": [
            "Validate every claimed CRS or georeference identifier before loading layers together.",
            "Record projected-versus-geographic assumptions with the scene package.",
        ],
        "evidence_targets": ["CRS validation report", "layer alignment notes", "georeference audit summary"],
    },
    "simulation_real2sim": {
        "title": "Simulation / Real2Sim2Real Integration",
        "summary": "Turn captured scenes into simulator-ready assets, validate collision geometry, and benchmark policy behavior in reconstructed worlds.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/simulation_scene_manifest.json": """
                {
                  "scene_name": "capture_world",
                  "collision_mesh_path": "sim/collision.glb",
                  "visual_asset_path": "sim/environment.usd",
                  "sensor_profiles": ["rgb_camera", "depth_camera"],
                  "target_simulators": ["isaac_sim", "carla", "unity", "unreal"]
                }
            """,
        },
        "validation_steps": [
            "Validate collision geometry and simulator asset paths before behavior tests.",
            "Compare at least one simulated sensor output against a real capture reference.",
        ],
        "evidence_targets": ["simulator scene manifest", "collision validation note", "sensor-output comparison"],
    },
    "provenance_watermarking": {
        "title": "Watermarking / Ownership / Provenance Integration",
        "summary": "Track asset lineage, attach ownership metadata, and verify release-time provenance before publishing 3D content.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/provenance_manifest.json": """
                {
                  "asset_id": "scene-001",
                  "source_capture": "drone-flight-2026-05-01",
                  "license": "internal",
                  "watermark_status": "pending_verification",
                  "lineage": []
                }
            """,
        },
        "validation_steps": [
            "Record asset lineage before editing derived splats or scenes.",
            "Verify watermark or provenance status before release packaging.",
        ],
        "evidence_targets": ["asset lineage manifest", "license summary", "watermark verification status"],
    },
    "codec_video_pipeline": {
        "title": "Codec / FFmpeg / Video Pipeline Integration",
        "summary": "Extract frames, generate previews, and benchmark media codecs for 3D capture and volumetric pipelines.",
        "dependencies": ["ffmpeg"],
        "files": {
            "spatial3d_starters/ffmpeg_workflow.md": """
                Example extraction:

                ffmpeg -hide_banner -loglevel error -i input.mp4 -vf fps=2 frames/frame_%04d.png

                Example preview:

                ffmpeg -hide_banner -loglevel error -pattern_type glob -i "frames/*.png" -c:v libx264 previews/capture-preview.mp4
            """,
        },
        "validation_steps": [
            "Validate frame count and timing after extraction.",
            "Generate a preview clip so dataset and reconstruction quality can be reviewed quickly.",
        ],
        "evidence_targets": ["frame extraction log", "preview video artifact", "codec benchmark summary"],
    },
    "mobile_capture": {
        "title": "Capture App / Mobile Pipeline Integration",
        "summary": "Validate mobile capture metadata, upload queues, and reconstruction-ready packaging for phone-based input flows.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/mobile_capture_checklist.md": """
                - Verify device model, focal length, sensor orientation, and capture timestamps.
                - Verify upload queue retry behavior and local-storage pressure.
                - Package captures into a reconstruction-ready folder with stable naming.
            """,
        },
        "validation_steps": [
            "Run metadata checks on a representative mobile capture batch.",
            "Verify upload retry and local-storage handling before release.",
        ],
        "evidence_targets": ["mobile metadata summary", "upload-queue behavior note", "reconstruction-ready package structure"],
    },
    "cloud_reconstruction": {
        "title": "Cloud Reconstruction Job Orchestration",
        "summary": "Start, monitor, retry, and compare reconstruction jobs instead of leaving long-running spatial processing as manual suffering.",
        "dependencies": ["python", "httpx"],
        "files": {
            "spatial3d_starters/reconstruction_job_client.py": """
                import httpx


                class ReconstructionJobs:
                    def __init__(self, base_url: str, api_key: str) -> None:
                        self._client = httpx.Client(base_url=base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)

                    def list_jobs(self) -> dict:
                        response = self._client.get("/jobs")
                        response.raise_for_status()
                        return response.json()
            """,
        },
        "validation_steps": [
            "Exercise job listing, start, and failure-report paths against a non-production environment.",
            "Record retry behavior and estimated processing cost per dataset.",
        ],
        "evidence_targets": ["job status payload", "failure and retry trace", "cost estimate summary"],
    },
    "dataset_quality": {
        "title": "Dataset Quality / Capture Coverage Agent",
        "summary": "Catch weak overlap, missing angles, blur, bad GPS, and bad exposure before compute turns the dataset into expensive soup.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/dataset_quality_gate.py": """
                def score_dataset(image_count: int, overlap_ratio: float, gps_quality: float) -> dict:
                    score = (image_count >= 40) + (overlap_ratio >= 0.65) + (gps_quality >= 0.7)
                    return {"gate": "pass" if score >= 2 else "review", "score": score}
            """,
        },
        "validation_steps": [
            "Run dataset QA before dispatching reconstruction.",
            "Reject or flag batches with weak overlap, missing angles, or low GPS quality.",
        ],
        "evidence_targets": ["dataset QA score", "coverage-gap note", "pre-reconstruction risk summary"],
    },
    "scene_authoring": {
        "title": "AI Authoring / Scene Editing Integration",
        "summary": "Generate hotspots, routes, object labels, and walkthrough packages so captured scenes become usable products instead of inert demos.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/scene_authoring_manifest.json": """
                {
                  "scene_id": "tour-demo",
                  "hotspots": [],
                  "tour_route": [],
                  "labels": [],
                  "translations": []
                }
            """,
        },
        "validation_steps": [
            "Verify hotspot coordinates and labels against the source scene before publishing.",
            "Render at least one walkthrough preview after route generation.",
        ],
        "evidence_targets": ["scene authoring manifest", "tour route preview", "annotation export"],
    },
    "virtual_production": {
        "title": "Virtual Production Integration",
        "summary": "Prepare stage-ready assets, camera-match checks, and engine import scripts for LED-volume or real-time production workflows.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/unreal_import_stub.py": """
                def build_import_plan(scene_path: str) -> dict:
                    return {
                        "scene_path": scene_path,
                        "target_engine": "unreal",
                        "needs_scale_validation": True,
                        "needs_camera_match_validation": True,
                    }
            """,
        },
        "validation_steps": [
            "Validate scale, camera alignment, and playback assumptions before production handoff.",
            "Generate a test-shot plan instead of shipping raw captures to stage crews.",
        ],
        "evidence_targets": ["import plan", "camera-match checklist", "test-shot summary"],
    },
    "digital_preservation": {
        "title": "Museum / Digital Preservation Workflow Integration",
        "summary": "Preserve artifact metadata, restoration versions, and archive packages for cultural-heritage reconstruction workflows.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/preservation_record.json": """
                {
                  "artifact_id": "heritage-object-001",
                  "capture_date": "2026-06-01",
                  "restoration_versions": [],
                  "curator_notes": [],
                  "archive_package_path": "archives/object-001.zip"
                }
            """,
        },
        "validation_steps": [
            "Version restoration edits instead of overwriting them.",
            "Package provenance, annotation, and archive metadata together for preservation handoff.",
        ],
        "evidence_targets": ["preservation record", "restoration version list", "archive package manifest"],
    },
    "neural_graphics_benchmarking": {
        "title": "Performance Benchmark Agent for Neural Graphics",
        "summary": "Track FPS, memory, load time, file size, streaming latency, and quality so renderer optimization stops being decorative mythology.",
        "dependencies": ["python"],
        "files": {
            "spatial3d_starters/benchmark_report.py": """
                def summarize_benchmark(fps: float, frame_time_ms: float, gpu_memory_mb: int, file_size_mb: float) -> dict:
                    return {
                        "fps": fps,
                        "frame_time_ms": frame_time_ms,
                        "gpu_memory_mb": gpu_memory_mb,
                        "file_size_mb": file_size_mb,
                    }
            """,
        },
        "validation_steps": [
            "Record baseline metrics before optimization work starts.",
            "Compare before/after renderer metrics with artifact quality notes, not just one lucky FPS number.",
        ],
        "evidence_targets": ["benchmark table", "baseline-versus-candidate delta", "quality tradeoff note"],
    },
    "research_to_code": {
        "title": "Research-to-Code Agent",
        "summary": "Turn papers into implementation plans, prototype code, benchmark scripts, and limits documentation with controlled scope.",
        "dependencies": ["python", "markdown"],
        "files": {
            "spatial3d_starters/research_implementation_template.md": """
                # Paper-to-prototype template

                - Paper title:
                - Core algorithm:
                - Claimed metrics:
                - Official repo:
                - Prototype scope:
                - Benchmark plan:
                - Known limitations:
            """,
            "spatial3d_starters/experimental_flag_example.py": """
                EXPERIMENTAL_FEATURE_FLAGS = {
                    "paper_to_prototype_mode": True,
                    "benchmark_required_before_default": True,
                }
            """,
        },
        "validation_steps": [
            "Capture the claimed paper metrics before writing prototype code.",
            "Keep prototypes behind explicit experimental flags until benchmark evidence exists.",
        ],
        "evidence_targets": ["paper implementation plan", "benchmark comparison", "limitations note"],
    },
}


def spatial3d_feature_catalog() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for feature_id, payload in _FEATURES.items():
        entries.append(
            {
                "feature_id": feature_id,
                "title": payload["title"],
                "variants": ["default"],
                "summary": payload["summary"],
            }
        )
    return entries


def get_spatial3d_feature_catalog_entry(feature_id: str) -> dict[str, Any]:
    normalized = str(feature_id or "").strip().lower()
    if normalized not in _FEATURES:
        raise ValueError(f"Unknown spatial 3D feature bundle `{feature_id}`.")
    entry = _FEATURES[normalized]
    return {
        "feature_id": normalized,
        "title": entry["title"],
        "variants": ["default"],
        "summary": entry["summary"],
    }


def generate_spatial3d_feature_bundle(feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
    normalized = str(feature_id or "").strip().lower()
    normalized_variant = str(variant or "default").strip().lower() or "default"
    if normalized not in _FEATURES:
        raise ValueError(f"Unknown spatial 3D feature bundle `{feature_id}`.")
    if normalized_variant != "default":
        raise ValueError(f"Unsupported spatial 3D feature variant `{normalized_variant}`.")
    payload = _FEATURES[normalized]
    bundle = Spatial3DFeatureBundle(
        feature_id=normalized,
        variant="default",
        title=payload["title"],
        summary=payload["summary"],
        dependencies=list(payload["dependencies"]),
        files={path: dedent(content).strip() + "\n" for path, content in payload["files"].items()},
        validation_steps=list(payload["validation_steps"]),
        evidence_targets=list(payload["evidence_targets"]),
    )
    return bundle.to_dict()
