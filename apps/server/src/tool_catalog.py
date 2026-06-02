from __future__ import annotations

import platform
import shutil
from typing import Any

from config import REPO_ROOT
from nvidia_support import (
    build_nvidia_validation_plan,
    detect_nvidia_aiq_status,
    detect_nvidia_dynamo_status,
    detect_nvidia_nim_status,
    detect_nvidia_local_runtime_status,
    detect_project_nvidia_gpu_diagnostics,
)
from pytorch_support import (
    build_pytorch_validation_plan,
    detect_pytorch_repo_mode,
    detect_pytorch_runtime_status,
)
from spatial3d_support import build_spatial3d_validation_plan, detect_spatial3d_repo_mode
from tensorflow_support import build_tensorflow_validation_plan, detect_tensorflow_repo_mode
from webwright_support import detect_webwright_status


TOOL_CATALOG: list[dict[str, Any]] = [
    {"id": "file-search", "name": "File Search", "category": "Core tools", "summary": "Search the local workspace quickly.", "risk_level": "low"},
    {"id": "format-changer", "name": "Format Changer", "category": "Core tools", "summary": "Rewrite or normalize code and content formatting.", "risk_level": "low"},
    {"id": "write-publishable-docs", "name": "Write Publishable Docs", "category": "Docs tools", "summary": "Generate polished public-facing documentation.", "risk_level": "low"},
    {"id": "github-wiki-creator", "name": "GitHub Wiki Creator", "category": "Docs tools", "summary": "Publish docs to a connected GitHub wiki.", "risk_level": "medium"},
    {"id": "github-deployment-creator", "name": "GitHub Deployment Creator", "category": "Deployment tools", "summary": "Create deployment-related GitHub artifacts.", "risk_level": "medium"},
    {"id": "gitlab-merge-request-creator", "name": "GitLab Merge Request Creator", "category": "Deployment tools", "summary": "Create or guide merge-request work against a connected GitLab host.", "risk_level": "medium"},
    {"id": "skill-creator", "name": "Skill Creator", "category": "Core tools", "summary": "Create local Mission Control or Codex skills.", "risk_level": "medium"},
    {"id": "goal-reminder", "name": "Goal Reminder", "category": "Core tools", "summary": "Keep the current build goal visible to the manager and workers.", "risk_level": "low"},
    {"id": "security-review", "name": "Security Review", "category": "Testing tools", "summary": "Run a local security review checklist or specialist model.", "risk_level": "medium"},
    {"id": "python-workspace-with-uv", "name": "Python Workspace with uv", "category": "Core tools", "summary": "Prepare isolated Python environments and run Python repo tasks through uv when it is installed.", "risk_level": "medium"},
    {"id": "python-quality-with-ruff", "name": "Python Quality with Ruff", "category": "Testing tools", "summary": "Run Ruff lint and format checks for Python repos.", "risk_level": "low"},
    {"id": "repo-hooks-with-pre-commit", "name": "Repo Hooks with pre-commit", "category": "Testing tools", "summary": "Run repo-native hook contracts through pre-commit.", "risk_level": "medium"},
    {"id": "python-sessions-with-nox", "name": "Python Sessions with Nox", "category": "Testing tools", "summary": "Run project-defined Python sessions like tests, lint, and docs.", "risk_level": "medium"},
    {"id": "codebase-intake-with-ripgrep", "name": "Codebase Intake with ripgrep", "category": "Core tools", "summary": "Search the workspace quickly with ripgrep for intake, impact analysis, and targeted debugging.", "risk_level": "low"},
    {"id": "symbol-map-with-tree-sitter", "name": "Symbol Map with tree-sitter", "category": "Core tools", "summary": "Build parser-backed symbol maps and safer change impact hints when tree-sitter is available.", "risk_level": "medium"},
    {"id": "test-in-chromium", "name": "Test in Chromium", "category": "Testing tools", "summary": "Run browser checks in Chromium when available.", "risk_level": "low"},
    {"id": "browser-automation-with-webwright", "name": "Browser Automation with Webwright", "category": "Testing tools", "summary": "Use the local Webwright browser-agent harness for multi-step browser work when it is installed.", "risk_level": "medium"},
    {"id": "nvidia-dynamo-inference", "name": "NVIDIA Dynamo Inference", "category": "Infrastructure tools", "summary": "Route Mission Control coding workers through an NVIDIA Dynamo OpenAI-compatible frontend when available.", "risk_level": "high"},
    {"id": "nvidia-nim-inference", "name": "NVIDIA NIM Inference", "category": "Infrastructure tools", "summary": "Route Mission Control coding workers through an NVIDIA NIM inference microservice when available.", "risk_level": "high"},
    {"id": "nvidia-aiq-deep-research", "name": "NVIDIA AI-Q Deep Research", "category": "Search/research tools", "summary": "Delegate deep cited research to an NVIDIA AI-Q deployment when available.", "risk_level": "medium"},
    {"id": "nvidia-gpu-cluster-diagnostics", "name": "NVIDIA GPU Cluster Diagnostics", "category": "Infrastructure tools", "summary": "Inspect Prometheus and DCGM-backed GPU telemetry before blaming failing coding runs on the repo.", "risk_level": "medium"},
    {"id": "nvidia-local-runtime", "name": "NVIDIA Local Runtime", "category": "Infrastructure tools", "summary": "Inspect local CUDA, Nsight, and NVIDIA runtime readiness before trusting GPU validation results.", "risk_level": "medium"},
    {"id": "nvidia-validation-plan", "name": "NVIDIA Validation Plan", "category": "Testing tools", "summary": "Generate a concrete NVIDIA validation loop for CUDA-oriented work instead of improvising one badly.", "risk_level": "medium"},
    {"id": "tensorflow-project-scaffolding", "name": "TensorFlow Project Scaffolding", "category": "Core tools", "summary": "Plan Keras-first TensorFlow app structure and validation instead of hand-writing another doomed notebook maze.", "risk_level": "medium"},
    {"id": "tensorboard-observability", "name": "TensorBoard Observability", "category": "Testing tools", "summary": "Inspect TensorBoard-backed training evidence before trusting training or tuning claims.", "risk_level": "medium"},
    {"id": "tensorflow-serving-export", "name": "TensorFlow Serving Export", "category": "Deployment tools", "summary": "Inspect SavedModel and serving-export readiness before calling a model product-ready.", "risk_level": "medium"},
    {"id": "tfx-pipeline-validation", "name": "TFX Pipeline Validation", "category": "Deployment tools", "summary": "Surface TFX production-pipeline signals so product work does not stop at the trainer script.", "risk_level": "medium"},
    {"id": "tensorflow-lite-export", "name": "TensorFlow Lite Export", "category": "Deployment tools", "summary": "Check whether the repo can credibly ship TensorFlow Lite artifacts for edge targets.", "risk_level": "medium"},
    {"id": "tensorflow-notebook-rescue", "name": "TensorFlow Notebook Rescue", "category": "Core tools", "summary": "Promote notebook-only TensorFlow work into a repeatable repo-owned script before it becomes tribal lore.", "risk_level": "medium"},
    {"id": "pytorch-project-scaffolding", "name": "PyTorch Project Scaffolding", "category": "Core tools", "summary": "Plan a real PyTorch training and inference lane instead of another notebook graveyard with tensors in it.", "risk_level": "medium"},
    {"id": "pytorch-runtime-readiness", "name": "PyTorch Runtime Readiness", "category": "Infrastructure tools", "summary": "Check whether the local PyTorch runtime can actually run the repo before Mission Control starts making claims.", "risk_level": "medium"},
    {"id": "pytorch-profiler-observability", "name": "PyTorch Profiler Observability", "category": "Testing tools", "summary": "Inspect profiler and training-observability evidence instead of trusting performance folklore.", "risk_level": "medium"},
    {"id": "pytorch-checkpoint-validation", "name": "PyTorch Checkpoint Validation", "category": "Testing tools", "summary": "Verify checkpoint save, load, and resume behavior before pretending a model is reproducible.", "risk_level": "medium"},
    {"id": "pytorch-distributed-readiness", "name": "PyTorch Distributed Readiness", "category": "Infrastructure tools", "summary": "Surface torchrun, Accelerate, DeepSpeed, and rank-handling risks before distributed runs waste everyone's afternoon.", "risk_level": "high"},
    {"id": "pytorch-export-validation", "name": "PyTorch Export Validation", "category": "Deployment tools", "summary": "Check TorchScript or ONNX export readiness before calling a PyTorch repo product-ready.", "risk_level": "medium"},
    {"id": "pytorch-notebook-rescue", "name": "PyTorch Notebook Rescue", "category": "Core tools", "summary": "Promote notebook-only PyTorch work into a repeatable repo-owned script before the repo becomes a tensor scrapbook.", "risk_level": "medium"},
    {"id": "ml-config-audit", "name": "ML Config Audit", "category": "Testing tools", "summary": "Surface config-driven ML execution paths so validation evidence is tied to the config that actually ran.", "risk_level": "medium"},
    {"id": "spatial3d-asset-pipeline", "name": "Spatial 3D Asset Pipeline", "category": "Core tools", "summary": "Inventory, validate, and package splats, meshes, textures, and reconstruction outputs with a real asset lane.", "risk_level": "medium"},
    {"id": "blender-headless-validation", "name": "Blender Headless Validation", "category": "Testing tools", "summary": "Run or plan Blender scene checks and background renders instead of trusting renderer changes on vibes.", "risk_level": "medium"},
    {"id": "usd-scene-graph-validation", "name": "USD Scene Graph Validation", "category": "Testing tools", "summary": "Inspect USD stages, schema expectations, and Hydra-facing scene graph structure before pipeline handoff.", "risk_level": "medium"},
    {"id": "splat-conversion-compression", "name": "Splat Conversion and Compression", "category": "Deployment tools", "summary": "Plan or validate splat conversion, compatibility, and compression work for delivery targets.", "risk_level": "medium"},
    {"id": "scene-visual-regression", "name": "Scene Visual Regression", "category": "Testing tools", "summary": "Capture and compare rendered frames so broken shaders or missing assets stop hiding behind unit tests.", "risk_level": "medium"},
    {"id": "browser-3d-renderer-debugging", "name": "Browser 3D Renderer Debugging", "category": "Testing tools", "summary": "Exercise WebGL or WebGPU viewer behavior, load waterfalls, and scene readiness instead of just checking the build.", "risk_level": "medium"},
    {"id": "geospatial-3d-validation", "name": "Geospatial 3D Validation", "category": "Testing tools", "summary": "Validate CRS, georeference, and city-scale 3D layer assumptions before shipping spatial scenes.", "risk_level": "medium"},
    {"id": "capture-reconstruction-orchestration", "name": "Capture and Reconstruction Orchestration", "category": "Infrastructure tools", "summary": "Validate capture metadata and reconstruction job orchestration instead of babysitting cloud jobs by hand.", "risk_level": "high"},
    {"id": "neural-graphics-benchmarking", "name": "Neural Graphics Benchmarking", "category": "Testing tools", "summary": "Benchmark FPS, memory, streaming latency, and artifact quality before calling a renderer optimized.", "risk_level": "medium"},
    {"id": "research-to-code-prototyping", "name": "Research to Code Prototyping", "category": "Search/research tools", "summary": "Convert graphics or spatial research ideas into benchmarked prototypes with explicit experimental boundaries.", "risk_level": "medium"},
    {"id": "secret-scan-with-gitleaks", "name": "Secret Scan with Gitleaks", "category": "Testing tools", "summary": "Run a redacted local secret scan before handoff or release.", "risk_level": "medium"},
    {"id": "dependency-audit-with-osv-scanner", "name": "Dependency Audit with OSV-Scanner", "category": "Testing tools", "summary": "Scan repo lockfiles for known dependency vulnerabilities.", "risk_level": "medium"},
    {"id": "python-audit-with-pip-audit", "name": "Python Audit with pip-audit", "category": "Testing tools", "summary": "Audit Python dependencies for known vulnerabilities.", "risk_level": "medium"},
    {"id": "deploy-with-vercel", "name": "Deploy with Vercel", "category": "Deployment tools", "summary": "Deploy through a configured Vercel account.", "risk_level": "high"},
    {"id": "deploy-with-netlify", "name": "Deploy with Netlify", "category": "Deployment tools", "summary": "Deploy through a configured Netlify account.", "risk_level": "high"},
    {"id": "deploy-with-cloudflare-pages", "name": "Deploy with Cloudflare Pages", "category": "Deployment tools", "summary": "Deploy through a configured Cloudflare Pages lane.", "risk_level": "high"},
    {"id": "deploy-with-railway", "name": "Deploy with Railway", "category": "Deployment tools", "summary": "Deploy through a configured Railway project.", "risk_level": "high"},
    {"id": "deploy-with-render", "name": "Deploy with Render", "category": "Deployment tools", "summary": "Deploy through a configured Render service.", "risk_level": "high"},
    {"id": "web-search-with-approval", "name": "Web Search with Approval", "category": "Search/research tools", "summary": "Use live web search with explicit approval.", "risk_level": "medium"},
    {"id": "extra-sandbox", "name": "Extra Sandbox", "category": "Experimental environments", "summary": "Use a broader or alternate local sandbox when configured.", "risk_level": "high"},
    {"id": "test-in-linux-wsl", "name": "Test in Linux / WSL", "category": "Testing tools", "summary": "Run validation in Linux or WSL when available.", "risk_level": "medium"},
    {"id": "convert-sound-to-text", "name": "Convert Sound to Text", "category": "Docs tools", "summary": "Transcribe local audio artifacts into text notes.", "risk_level": "medium"},
    {"id": "ascii-image-creator", "name": "ASCII Image Creator", "category": "Docs tools", "summary": "Produce ASCII art or terminal-friendly image previews.", "risk_level": "low"},
    {"id": "platform-creator", "name": "Platform Creator", "category": "Experimental environments", "summary": "Scaffold additional platform surfaces around the current project.", "risk_level": "high"},
    {"id": "cuda-test-environment", "name": "CUDA Test Environment", "category": "Experimental environments", "summary": "Run GPU-targeted checks when CUDA is installed.", "risk_level": "high"},
    {"id": "test-in-windows", "name": "Test in Windows", "category": "Testing tools", "summary": "Run validation flows on Windows.", "risk_level": "medium"},
    {"id": "test-in-android", "name": "Test in Android", "category": "Testing tools", "summary": "Use an Android testing environment when configured.", "risk_level": "high"},
    {"id": "test-in-macos", "name": "Test in MacOS", "category": "Testing tools", "summary": "Use local macOS-specific validation when available.", "risk_level": "high"},
    {"id": "test-in-ios", "name": "Test in iOS", "category": "Testing tools", "summary": "Use local iOS validation when available.", "risk_level": "high"},
    {"id": "test-in-safari", "name": "Test in Safari", "category": "Testing tools", "summary": "Use Safari-specific browser checks when available.", "risk_level": "medium"},
    {"id": "test-in-raspberry-pi-os", "name": "Test in Raspberry Pi OS", "category": "Testing tools", "summary": "Run validation on Raspberry Pi OS when configured.", "risk_level": "high"},
    {"id": "test-in-chromebook-os", "name": "Test in Chromebook OS", "category": "Testing tools", "summary": "Run validation against a ChromeOS-like environment when configured.", "risk_level": "high"},
]

_PROCESS_PROBE_CACHE: dict[tuple[str, tuple[Any, ...], tuple[Any, ...]], Any] = {}


def _is_windows() -> bool:
    return platform.system().lower().startswith("win")


def _is_macos() -> bool:
    return platform.system().lower() == "darwin"


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _cached_context_value(context: dict[str, Any], key: str, factory) -> Any:
    if key not in context:
        context[key] = factory()
    return context[key]


def _factory_cache_identity(factory) -> tuple[Any, ...]:
    code = getattr(factory, "__code__", None)
    if code is not None:
        return (
            getattr(factory, "__module__", ""),
            getattr(factory, "__qualname__", getattr(factory, "__name__", "")),
            code.co_filename,
            code.co_firstlineno,
        )
    return (
        getattr(factory, "__module__", ""),
        getattr(factory, "__qualname__", getattr(factory, "__name__", "")),
        id(factory),
    )


def _cached_probe(context: dict[str, Any], key: str, factory, *args: Any) -> Any:
    if key in context:
        return context[key]
    cache_key = (key, tuple(args), _factory_cache_identity(factory))
    if cache_key not in _PROCESS_PROBE_CACHE:
        _PROCESS_PROBE_CACHE[cache_key] = factory(*args)
    context[key] = _PROCESS_PROBE_CACHE[cache_key]
    return context[key]


def _python_available() -> bool:
    return bool(shutil.which("python"))


def _integration_connection_status(integration_registry: dict[str, Any], family_id: str) -> dict[str, Any]:
    connection = dict(dict(integration_registry or {}).get("connections", {}).get(family_id) or {})
    connection.setdefault("status", "disconnected")
    connection.setdefault("host_imported", False)
    connection.setdefault("connection_source", "mission_control")
    connection.setdefault("providers", [])
    return connection


def _integration_supports_provider(connection: dict[str, Any], provider: str) -> bool:
    return provider in {str(item) for item in list(connection.get("providers") or [])}


def _integration_provider_available(connection: dict[str, Any], provider: str) -> bool:
    return _integration_supports_provider(connection, provider) and (
        connection.get("status") == "connected" or bool(connection.get("host_imported"))
    )


def _connected_provider_label(connection: dict[str, Any]) -> str:
    providers = [str(item) for item in list(connection.get("providers") or []) if str(item).strip()]
    if not providers:
        return "none"
    return ", ".join(providers)


def _availability(
    tool_id: str,
    *,
    provider: str,
    connected_accounts: dict[str, Any],
    integration_registry: dict[str, Any],
    context: dict[str, Any],
) -> tuple[str, list[str]]:
    notes: list[str] = []
    if tool_id in {"file-search", "format-changer", "write-publishable-docs", "goal-reminder", "ascii-image-creator"}:
        return "available", notes
    if tool_id == "python-workspace-with-uv":
        return ("available" if shutil.which("uv") else "needs_setup"), ["Mission Control can use uv for isolated Python sync and execution when the CLI is installed."]
    if tool_id == "python-quality-with-ruff":
        return ("available" if shutil.which("ruff") else "needs_setup"), ["Ruff gives Mission Control a fast Python lint and format gate."]
    if tool_id == "repo-hooks-with-pre-commit":
        return ("available" if shutil.which("pre-commit") else "needs_setup"), ["Use this when the repo already has a pre-commit config instead of inventing a fake hygiene contract."]
    if tool_id == "python-sessions-with-nox":
        return ("available" if shutil.which("nox") else "needs_setup"), ["Nox is useful when pytest alone is not the project's real validation entry point."]
    if tool_id == "codebase-intake-with-ripgrep":
        return ("available" if shutil.which("rg") else "needs_setup"), ["ripgrep is the preferred search backend for intake and impact analysis."]
    if tool_id == "symbol-map-with-tree-sitter":
        return ("available" if shutil.which("tree-sitter") else "needs_setup"), ["tree-sitter is optional, but it unlocks parser-backed codebase maps instead of shallow file scans."]
    if tool_id == "security-review":
        notes.append("Uses the configured security workflow when available, otherwise falls back to the normal security checklist.")
        return "available", notes
    if tool_id == "test-in-chromium":
        notes.append("Browser availability depends on local Chromium or browser tooling.")
        return "available", notes
    if tool_id == "browser-automation-with-webwright":
        status = _cached_probe(context, "webwright_status", detect_webwright_status)
        notes.append(str(status.get("summary") or "Webwright runtime status is unknown."))
        if status.get("workspace_signals"):
            notes.append("Project-specific Webwright readiness is available through the dedicated Mission Control Webwright status surface.")
        if status.get("available"):
            return "available", notes
        return ("needs_setup" if status.get("install_status") in {"missing", "partial"} else "coming_soon"), notes
    if tool_id == "nvidia-dynamo-inference":
        status = _cached_probe(context, "nvidia_dynamo_status", detect_nvidia_dynamo_status)
        notes.append(str(status.get("summary") or "NVIDIA Dynamo status is unknown."))
        return ("available" if status.get("reachable") else "needs_setup"), notes
    if tool_id == "nvidia-nim-inference":
        status = _cached_probe(context, "nvidia_nim_status", detect_nvidia_nim_status)
        notes.append(str(status.get("summary") or "NVIDIA NIM status is unknown."))
        return ("available" if status.get("reachable") else "needs_setup"), notes
    if tool_id == "nvidia-aiq-deep-research":
        status = _cached_probe(context, "nvidia_aiq_status", detect_nvidia_aiq_status)
        notes.append(str(status.get("summary") or "NVIDIA AI-Q status is unknown."))
        return ("available" if status.get("available") else "needs_setup"), notes
    if tool_id == "nvidia-gpu-cluster-diagnostics":
        status = _cached_probe(context, "nvidia_gpu_diag_status", detect_project_nvidia_gpu_diagnostics, REPO_ROOT)
        notes.append(str(status.get("summary") or "NVIDIA GPU diagnostics status is unknown."))
        if status.get("available"):
            return "available", notes
        return ("needs_setup" if status.get("status") in {"missing", "unreachable", "unknown"} else "experimental"), notes
    if tool_id == "nvidia-local-runtime":
        status = _cached_probe(context, "nvidia_local_runtime_status", detect_nvidia_local_runtime_status, REPO_ROOT)
        notes.append(str(status.get("summary") or "NVIDIA local runtime status is unknown."))
        return ("available" if status.get("available") else "needs_setup"), notes
    if tool_id == "nvidia-validation-plan":
        status = _cached_probe(context, "nvidia_validation_plan", build_nvidia_validation_plan, REPO_ROOT)
        notes.append(str(status.get("summary") or "NVIDIA validation plan status is unknown."))
        if status.get("status") == "not_applicable":
            return "experimental", notes
        return ("available" if status.get("available") else "needs_setup"), notes
    if tool_id == "tensorflow-project-scaffolding":
        mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        validation = _cached_probe(context, "tensorflow_validation_plan", build_tensorflow_validation_plan, REPO_ROOT)
        if mode.get("enabled"):
            notes.append(f"Detected TensorFlow mode `{mode.get('mode')}` with frameworks: {', '.join(list(mode.get('frameworks') or [])[:4])}.")
            notes.append(str(validation.get("summary") or "TensorFlow validation planning is available."))
            python_required = bool(mode.get("build_commands") or mode.get("training_commands") or mode.get("export_commands"))
            return (("available" if _python_available() or not python_required else "needs_setup"), notes)
        notes.append("No TensorFlow or Keras repo signals were detected in the current workspace.")
        return "needs_setup", notes
    if tool_id == "tensorboard-observability":
        tensorflow_mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        pytorch_mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        if not tensorflow_mode.get("enabled") and "training_observability" not in list(pytorch_mode.get("product_workflows") or []):
            notes.append("TensorBoard only matters when the repo actually signals TensorFlow, Keras, or PyTorch observability work.")
            return "experimental", notes
        tensorboard_path = shutil.which("tensorboard")
        pytorch_observability_commands = list(pytorch_mode.get("observability_commands") or [])
        has_pytorch_alt_observability = bool(shutil.which("wandb") or shutil.which("mlflow"))
        notes.append("Use TensorBoard to prove training behavior with logs and curves instead of optimistic narration.")
        if tensorboard_path or has_pytorch_alt_observability or (pytorch_observability_commands and _python_available()):
            return "available", notes
        return "needs_setup", notes
    if tool_id == "tensorflow-serving-export":
        mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        notes.append("SavedModel export checks keep training artifacts and serving artifacts from being treated like the same thing.")
        if "SavedModel / Serving" not in list(mode.get("frameworks") or []):
            return "experimental", notes
        has_repo_export = bool(mode.get("export_commands") or mode.get("existing_savedmodel_artifacts"))
        has_inspection_runtime = bool(shutil.which("saved_model_cli") or _python_available())
        return ("available" if has_repo_export and has_inspection_runtime or shutil.which("saved_model_cli") else "needs_setup"), notes
    if tool_id == "tfx-pipeline-validation":
        mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        notes.append("TFX validation is only interesting when the repo actually carries production-pipeline signals.")
        if "TFX" not in list(mode.get("frameworks") or []):
            return "experimental", notes
        has_repo_pipeline = any(str(command).strip().startswith("python ") for command in list(mode.get("training_commands") or []))
        return ("available" if shutil.which("tfx") or (has_repo_pipeline and _python_available()) else "needs_setup"), notes
    if tool_id == "tensorflow-lite-export":
        mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        notes.append("Lite export checks matter for edge or mobile targets, not every model repo under the sun.")
        if "TensorFlow Lite" not in list(mode.get("frameworks") or []):
            return "experimental", notes
        has_repo_export = bool(mode.get("export_commands") or mode.get("existing_tflite_artifacts"))
        has_inspection_runtime = bool(shutil.which("tflite_convert") or _python_available())
        return ("available" if has_repo_export and has_inspection_runtime or shutil.which("tflite_convert") else "needs_setup"), notes
    if tool_id == "tensorflow-notebook-rescue":
        mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        if "notebook_experiments" not in list(mode.get("product_workflows") or []):
            notes.append("Notebook rescue only matters when the TensorFlow repo still hides real work inside notebooks.")
            return "experimental", notes
        notes.append("Use this lane to turn TensorFlow notebooks into repo-owned scripts before validation claims get theatrical.")
        return ("available" if shutil.which("jupyter") else "needs_setup"), notes
    if tool_id == "pytorch-project-scaffolding":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        validation = _cached_probe(context, "pytorch_validation_plan", build_pytorch_validation_plan, REPO_ROOT)
        if mode.get("enabled"):
            notes.append(f"Detected PyTorch mode `{mode.get('mode')}` with frameworks: {', '.join(list(mode.get('frameworks') or [])[:4])}.")
            notes.append(str(validation.get("summary") or "PyTorch validation planning is available."))
            python_required = any(
                mode.get(key)
                for key in ("build_commands", "training_commands", "evaluation_commands", "inference_commands", "export_commands")
            )
            return (("available" if _python_available() or not python_required else "needs_setup"), notes)
        notes.append("No PyTorch repo signals were detected in the current workspace.")
        return "needs_setup", notes
    if tool_id == "pytorch-runtime-readiness":
        runtime = _cached_probe(context, "pytorch_runtime_status", detect_pytorch_runtime_status, REPO_ROOT)
        notes.append(str(runtime.get("summary") or "PyTorch runtime status is unknown."))
        if runtime.get("status") == "not_applicable":
            return "experimental", notes
        return ("available" if runtime.get("status") in {"ready", "partial"} else "needs_setup"), notes
    if tool_id == "pytorch-profiler-observability":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        notes.append("Profiler evidence matters more than performance storytelling for PyTorch work.")
        if not mode.get("enabled"):
            return "experimental", notes
        if "training_observability" not in list(mode.get("product_workflows") or []):
            return "available", notes
        observability_cli_detected = any(shutil.which(command) for command in ("tensorboard", "wandb", "mlflow"))
        has_repo_observability_command = bool(mode.get("observability_commands"))
        return ("available" if observability_cli_detected or (has_repo_observability_command and _python_available()) else "needs_setup"), notes
    if tool_id == "pytorch-checkpoint-validation":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        notes.append("Checkpoint validation keeps resume claims attached to reality instead of wishful config files.")
        if not mode.get("enabled"):
            return "experimental", notes
        return ("available" if (mode.get("checkpoint_paths") or mode.get("training_commands")) and _python_available() else "needs_setup"), notes
    if tool_id == "pytorch-distributed-readiness":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        runtime = _cached_probe(context, "pytorch_runtime_status", detect_pytorch_runtime_status, REPO_ROOT)
        notes.append("Distributed readiness checks should prove launcher and device assumptions before torchrun starts acting expensive.")
        if "distributed_training" not in list(mode.get("product_workflows") or []):
            return "experimental", notes
        if runtime.get("status") == "not_applicable":
            return "needs_setup", notes
        distributed_stack = {str(item) for item in list(mode.get("distributed_stack") or [])}
        missing_requirements: list[str] = []
        if "Accelerate" in distributed_stack and not shutil.which("accelerate"):
            missing_requirements.append("accelerate")
        if "DeepSpeed" in distributed_stack and not shutil.which("deepspeed"):
            missing_requirements.append("deepspeed")
        if "DDP/FSDP" in distributed_stack:
            if not shutil.which("torchrun"):
                missing_requirements.append("torchrun")
        return ("needs_setup" if missing_requirements else "available"), notes
    if tool_id == "pytorch-export-validation":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        notes.append("Export checks matter when TorchScript or ONNX artifacts are part of the product path.")
        if not mode.get("enabled"):
            return "experimental", notes
        if "model_export" not in list(mode.get("product_workflows") or []) and not mode.get("export_commands") and not mode.get("existing_onnx_artifacts") and not mode.get("existing_torchscript_artifacts"):
            return "experimental", notes
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "pytorch-notebook-rescue":
        mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        if "notebook_experiments" not in list(mode.get("product_workflows") or []):
            notes.append("Notebook rescue only matters when the PyTorch repo still hides real work inside notebooks.")
            return "experimental", notes
        notes.append("Use this lane to turn PyTorch notebooks into repo-owned scripts before validation claims become fiction.")
        return ("available" if shutil.which("jupyter") else "needs_setup"), notes
    if tool_id == "ml-config-audit":
        tensorflow_mode = _cached_probe(context, "tensorflow_mode", detect_tensorflow_repo_mode, REPO_ROOT)
        pytorch_mode = _cached_probe(context, "pytorch_mode", detect_pytorch_repo_mode, REPO_ROOT)
        if "config_driven_runs" not in list(tensorflow_mode.get("product_workflows") or []) and "config_driven_runs" not in list(pytorch_mode.get("product_workflows") or []):
            notes.append("Config audit only matters when the repo actually has ML config files worth treating seriously.")
            return "experimental", notes
        notes.append("Use config audit to tie validation evidence to the exact ML config files that drove the run.")
        return ("available" if shutil.which("python") else "needs_setup"), notes
    if tool_id == "spatial3d-asset-pipeline":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        validation = _cached_probe(context, "spatial3d_validation_plan", build_spatial3d_validation_plan, REPO_ROOT)
        if mode.get("enabled"):
            notes.append(f"Detected spatial mode `{mode.get('mode')}` with frameworks: {', '.join(list(mode.get('frameworks') or [])[:5])}.")
            notes.append(str(validation.get("summary") or "Spatial validation planning is available."))
            return ("available" if mode.get("asset_paths") or _python_available() else "needs_setup"), notes
        notes.append("No spatial 3D or Gaussian-splat repo signals were detected in the current workspace.")
        return "needs_setup", notes
    if tool_id == "blender-headless-validation":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "Blender" not in list(mode.get("frameworks") or []):
            notes.append("Blender validation only matters when the repo actually contains Blender assets or bpy automation.")
            return "experimental", notes
        notes.append("Background Blender rendering keeps scene changes attached to evidence instead of artist folklore.")
        return ("available" if shutil.which("blender") or any(str(command).startswith("python ") for command in list(mode.get("render_commands") or [])) else "needs_setup"), notes
    if tool_id == "usd-scene-graph-validation":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "OpenUSD" not in list(mode.get("frameworks") or []):
            notes.append("USD validation only matters when the repo actually carries USD assets or scene-graph code.")
            return "experimental", notes
        notes.append("Scene-graph validation should prove the USD stage opens and traverses cleanly before pipeline handoff.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "splat-conversion-compression":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "splat_compression" not in list(mode.get("product_workflows") or []):
            notes.append("Splat conversion matters when the repo actually handles Gaussian splat assets.")
            return "experimental", notes
        notes.append("Conversion and compression work should leave behind compatibility and size evidence, not just a renamed blob.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "scene-visual-regression":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "visual_regression" not in list(mode.get("product_workflows") or []):
            notes.append("Visual regression only matters when the repo changes rendered scene output.")
            return "experimental", notes
        notes.append("Rendered-frame diffs catch broken transparency, missing assets, and haunted shader regressions that unit tests miss.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "browser-3d-renderer-debugging":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "browser_renderer" not in list(mode.get("product_workflows") or []):
            notes.append("Browser 3D debugging only matters when the repo ships a viewer or web renderer.")
            return "experimental", notes
        notes.append("Use this lane to check viewer readiness, load waterfalls, and renderer diagnostics instead of blessing a passing build.")
        return "available", notes
    if tool_id == "geospatial-3d-validation":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if "geospatial_gis" not in list(mode.get("product_workflows") or []):
            notes.append("Geospatial validation only matters when the repo actually carries GIS or CRS-sensitive assets.")
            return "experimental", notes
        notes.append("Coordinate systems are quiet sabotage; validate them before city-scale scenes go on tour.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "capture-reconstruction-orchestration":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if not {"drone_capture", "cloud_reconstruction", "mobile_capture"} & set(mode.get("product_workflows") or []):
            notes.append("Capture orchestration only matters when the repo actually handles spatial ingestion or reconstruction jobs.")
            return "experimental", notes
        notes.append("Capture and reconstruction pipelines are long-running failure magnets, which is exactly why they should be scripted.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "neural-graphics-benchmarking":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if not mode.get("enabled"):
            notes.append("Benchmarking only matters when the repo actually renders or ships spatial assets.")
            return "experimental", notes
        notes.append("Benchmarking keeps optimization claims attached to FPS, memory, latency, and artifact quality instead of ego.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "research-to-code-prototyping":
        mode = _cached_probe(context, "spatial3d_mode", detect_spatial3d_repo_mode, REPO_ROOT)
        if not mode.get("enabled"):
            notes.append("Research-to-code prototyping only matters when the repo is exploring new graphics or spatial workflows.")
            return "experimental", notes
        notes.append("Keep research prototypes behind explicit experimental boundaries so paper enthusiasm does not become default production behavior.")
        return ("available" if _python_available() else "needs_setup"), notes
    if tool_id == "secret-scan-with-gitleaks":
        return ("available" if shutil.which("gitleaks") else "needs_setup"), ["Redacted secret scanning is the sane default gate before handoff or release."]
    if tool_id == "dependency-audit-with-osv-scanner":
        return ("available" if shutil.which("osv-scanner") else "needs_setup"), ["Use OSV-Scanner when dependency risk matters across languages."]
    if tool_id == "python-audit-with-pip-audit":
        return ("available" if shutil.which("pip-audit") else "needs_setup"), ["Use pip-audit for Python dependency vulnerability checks."]
    if tool_id in {"github-wiki-creator", "github-deployment-creator"}:
        source_control = _integration_connection_status(integration_registry, "source_control")
        github_status = connected_accounts.get("github", {})
        is_available = _integration_provider_available(source_control, "github") or github_status.get("status") == "connected"
        notes.append(f"Connection source: {source_control.get('connection_source')}.")
        notes.append(f"Resolved source-control providers: {_connected_provider_label(source_control)}.")
        if not is_available and list(source_control.get("providers") or []):
            notes.append("This tool is GitHub-specific. The current source-control provider does not look like GitHub.")
        return ("available" if is_available else "needs_setup"), notes
    if tool_id == "gitlab-merge-request-creator":
        source_control = _integration_connection_status(integration_registry, "source_control")
        is_available = _integration_provider_available(source_control, "gitlab")
        notes.append(f"Connection source: {source_control.get('connection_source')}.")
        notes.append(f"Resolved source-control providers: {_connected_provider_label(source_control)}.")
        if not is_available and list(source_control.get("providers") or []):
            notes.append("This tool is GitLab-specific. The current source-control provider does not look like GitLab.")
        return ("available" if is_available else "needs_setup"), notes
    if tool_id in {
        "deploy-with-vercel",
        "deploy-with-netlify",
        "deploy-with-cloudflare-pages",
        "deploy-with-railway",
        "deploy-with-render",
    }:
        hosting = _integration_connection_status(integration_registry, "hosting_deploy")
        vercel_status = connected_accounts.get("vercel", {})
        tool_provider = {
            "deploy-with-vercel": "vercel",
            "deploy-with-netlify": "netlify",
            "deploy-with-cloudflare-pages": "cloudflare_pages",
            "deploy-with-railway": "railway",
            "deploy-with-render": "render",
        }[tool_id]
        is_available = _integration_provider_available(hosting, tool_provider) or (
            tool_provider == "vercel" and vercel_status.get("status") == "connected"
        )
        notes.append(f"Connection source: {hosting.get('connection_source')}.")
        notes.append(f"Resolved hosting providers: {_connected_provider_label(hosting)}.")
        if not is_available and list(hosting.get("providers") or []):
            notes.append(f"This tool is {tool_provider.replace('_', ' ')}-specific. The current hosting provider does not match.")
        return ("available" if is_available else "needs_setup"), notes
    if tool_id == "web-search-with-approval":
        notes.append("Web search stays approval-gated unless the user explicitly enables it.")
        return "needs_setup", notes
    if tool_id in {"extra-sandbox", "platform-creator"}:
        return "experimental", notes
    if tool_id == "skill-creator":
        notes.append("External Codex skill discovery depends on local Codex configuration.")
        return "available", notes
    if tool_id == "test-in-linux-wsl":
        if _is_linux():
            return "available", notes
        if _is_windows():
            notes.append("WSL or another Linux runtime must be configured first.")
            return "needs_setup", notes
        return "experimental", notes
    if tool_id == "convert-sound-to-text":
        return "needs_setup", notes
    if tool_id == "cuda-test-environment":
        notes.append("GPU validation depends on local CUDA support.")
        return "needs_setup", notes
    if tool_id == "test-in-windows":
        return ("available" if _is_windows() else "unsupported_on_device"), notes
    if tool_id in {"test-in-macos", "test-in-ios", "test-in-safari"}:
        return ("available" if _is_macos() else "unsupported_on_device"), notes
    if tool_id in {"test-in-android", "test-in-raspberry-pi-os", "test-in-chromebook-os"}:
        return "needs_setup", notes
    if provider == "codex" and tool_id == "security-review":
        notes.append("Codex-backed security review can stay local-first without API keys.")
    return "coming_soon", notes


def default_permission_policy(tool_id: str) -> str:
    if tool_id in {"file-search", "format-changer", "write-publishable-docs", "goal-reminder", "ascii-image-creator"}:
        return "ask_once_per_project"
    if tool_id in {
        "deploy-with-vercel",
        "deploy-with-netlify",
        "deploy-with-cloudflare-pages",
        "deploy-with-railway",
        "deploy-with-render",
        "github-deployment-creator",
        "gitlab-merge-request-creator",
        "extra-sandbox",
        "cuda-test-environment",
    }:
        return "ask_every_time"
    return "ask_every_time"


def catalog_with_permissions(
    *,
    provider: str,
    connected_accounts: dict[str, Any],
    integration_registry: dict[str, Any] | None = None,
    permission_overrides: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    context: dict[str, Any] = {}
    for item in TOOL_CATALOG:
        availability, notes = _availability(
            item["id"],
            provider=provider,
            connected_accounts=connected_accounts,
            integration_registry=dict(integration_registry or {}),
            context=context,
        )
        permission_policy = str(permission_overrides.get(item["id"]) or default_permission_policy(item["id"]))
        items.append(
            {
                **item,
                "availability": availability,
                "permission_policy": permission_policy,
                "notes": notes,
            }
        )
    return items
