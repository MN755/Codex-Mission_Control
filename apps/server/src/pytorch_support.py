from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


MAX_SCANNED_FILES = 1500
PYTHON_FILE_EXTENSIONS = {".py", ".ipynb"}
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
PROJECT_TEXT_CANDIDATES = [
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "environment.yml",
    "environment.yaml",
    "setup.py",
    "README.md",
]
TRAINING_FILE_CANDIDATES = [
    "train.py",
    "scripts/train.py",
    "scripts/training.py",
    "training/train.py",
    "tools/train.py",
]
EVAL_FILE_CANDIDATES = [
    "eval.py",
    "evaluate.py",
    "scripts/eval.py",
    "scripts/evaluate.py",
    "validation/eval.py",
]
EXPORT_FILE_CANDIDATES = [
    "export.py",
    "scripts/export.py",
    "deployment/export.py",
    "serving/export.py",
]
INFERENCE_FILE_CANDIDATES = [
    "infer.py",
    "inference.py",
    "scripts/infer.py",
    "scripts/inference.py",
    "serve.py",
]
CHECKPOINT_DIR_HINTS = {"checkpoints", "checkpoint", "ckpt", "weights", "artifacts"}
CHECKPOINT_FILE_EXTENSIONS = {".pt", ".pth", ".ckpt", ".bin", ".safetensors"}


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


def _parse_probe_payload(output: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    if not lines:
        return {"ok": False, "error": "PyTorch runtime probe produced no output."}
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            return json.loads(line)
    return json.loads(lines[-1])


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


def _first_existing_command(root: Path, candidates: list[str]) -> str | None:
    for candidate in candidates:
        path = root / candidate
        if path.exists():
            return candidate.replace("\\", "/")
    return None


def detect_pytorch_repo_mode(workspace_path: str | Path) -> dict[str, Any]:
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
            "training_commands": [],
            "evaluation_commands": [],
            "inference_commands": [],
            "export_commands": [],
            "observability_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
            "checkpoint_paths": [],
            "distributed_stack": [],
        }

    files = _scan_files(root)
    relative_paths = [path.relative_to(root).as_posix() for path in files]
    languages: list[str] = []
    frameworks: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    training_commands: list[str] = []
    evaluation_commands: list[str] = []
    inference_commands: list[str] = []
    export_commands: list[str] = []
    observability_commands: list[str] = []
    product_workflows: list[str] = []
    validation_notes: list[str] = []
    signals: list[str] = []
    important_paths: list[str] = []
    checkpoint_paths: list[str] = []
    distributed_stack: list[str] = []

    if any(path.suffix.lower() in PYTHON_FILE_EXTENSIONS for path in files):
        languages.append("Python")

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
        if path.suffix.lower() not in PYTHON_FILE_EXTENSIONS:
            continue
        code_texts.append(_safe_read_text(path))
        if len(code_texts) >= 24:
            break
    combined_text = "\n".join(project_texts + code_texts).lower()
    supporting_text = "\n".join(project_texts + code_texts + supporting_texts).lower()

    pytorch_tokens = (
        "torch",
        "pytorch",
        "torchvision",
        "torchaudio",
        "torch.nn",
        "torch.optim",
        "torch.utils.data",
        "pytorch-lightning",
        "lightning.pytorch",
        "accelerate",
        "diffusers",
        "transformers",
        "peft",
        "deepspeed",
        "fsdp",
        "torchrun",
        "torch.distributed",
        "torch.compile",
        "torchscript",
        "onnx",
    )
    checkpoint_signal = any(Path(path).suffix.lower() in CHECKPOINT_FILE_EXTENSIONS for path in relative_paths)
    core_signal = any(token in combined_text for token in pytorch_tokens) or checkpoint_signal
    if core_signal:
        frameworks.append("PyTorch")
        signals.append("Detected PyTorch dependency or checkpoint signals in project files.")
    if not core_signal:
        return {
            "enabled": False,
            "mode": None,
            "signals": [],
            "languages": _dedupe(languages),
            "frameworks": [],
            "build_commands": [],
            "test_commands": [],
            "training_commands": [],
            "evaluation_commands": [],
            "inference_commands": [],
            "export_commands": [],
            "observability_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
            "checkpoint_paths": [],
            "distributed_stack": [],
        }

    if any(token in supporting_text for token in ("torchvision", "imagenet", "albumentations", "timm")):
        frameworks.append("TorchVision")
        product_workflows.append("vision_training")
        signals.append("Detected TorchVision or vision-training signals.")
    if any(token in supporting_text for token in ("torchaudio", "librosa", "wav2vec", "whisper")):
        frameworks.append("TorchAudio")
        product_workflows.append("audio_training")
        signals.append("Detected TorchAudio or audio-model signals.")
    if any(token in supporting_text for token in ("pytorch-lightning", "lightning.pytorch")):
        frameworks.append("Lightning")
        product_workflows.append("structured_training")
        signals.append("Detected Lightning trainer signals.")
    if "accelerate" in supporting_text:
        frameworks.append("Accelerate")
        distributed_stack.append("Accelerate")
        product_workflows.append("distributed_training")
        signals.append("Detected Accelerate launch or config signals.")
    if any(token in supporting_text for token in ("deepspeed", "zero stage", "zero_stage", "ds_config")):
        frameworks.append("DeepSpeed")
        distributed_stack.append("DeepSpeed")
        product_workflows.append("distributed_training")
        signals.append("Detected DeepSpeed distributed-training signals.")
    if any(token in supporting_text for token in ("torch.distributed", "torchrun", "ddp", "fsdp")):
        distributed_stack.append("DDP/FSDP")
        product_workflows.append("distributed_training")
        signals.append("Detected DDP or FSDP distributed-training signals.")
    if any(token in supporting_text for token in ("diffusers", "stable diffusion")):
        frameworks.append("Diffusers")
        product_workflows.append("diffusion_inference")
        signals.append("Detected Diffusers or image-generation signals.")
    if any(token in supporting_text for token in ("transformers", "peft", "lora")):
        frameworks.append("Transformers / PEFT")
        product_workflows.append("llm_finetuning")
        signals.append("Detected Hugging Face Transformers or PEFT signals.")
    if any(token in supporting_text for token in ("onnx", "torchscript", "jit.trace", "jit.script")):
        product_workflows.append("model_export")
        signals.append("Detected TorchScript or ONNX export signals.")
    if any(token in supporting_text for token in ("torch.profiler", "tensorboard", "wandb", "mlflow")):
        product_workflows.append("training_observability")
        signals.append("Detected training observability or profiler signals.")

    requirements_exists = any((root / name).exists() for name in ("requirements.txt", "requirements-dev.txt", "requirements.in"))
    pyproject_exists = (root / "pyproject.toml").exists()
    if pyproject_exists or (root / "setup.py").exists():
        build_commands.append("python -m pip install -e .")
    elif requirements_exists:
        build_commands.append("python -m pip install -r requirements.txt")

    if "pytest" in combined_text or any("test" in path.lower() and path.endswith(".py") for path in relative_paths):
        test_commands.append("python -m pytest")

    training_entry = _first_existing_command(root, TRAINING_FILE_CANDIDATES)
    if training_entry:
        training_commands.append(f"python {training_entry}")
        important_paths.append(training_entry)
    eval_entry = _first_existing_command(root, EVAL_FILE_CANDIDATES)
    if eval_entry:
        evaluation_commands.append(f"python {eval_entry}")
        important_paths.append(eval_entry)
    inference_entry = _first_existing_command(root, INFERENCE_FILE_CANDIDATES)
    if inference_entry:
        inference_commands.append(f"python {inference_entry}")
        important_paths.append(inference_entry)
    export_entry = _first_existing_command(root, EXPORT_FILE_CANDIDATES)
    if export_entry:
        export_commands.append(f"python {export_entry}")
        important_paths.append(export_entry)

    if "training_observability" in product_workflows:
        observability_commands.extend(
            [
                "python -m torch.utils.bottleneck <train_script>",
                "python -m tensorboard.main --logdir runs",
            ]
        )
    if "distributed_training" in product_workflows and training_entry:
        training_commands.append(f"torchrun --nproc_per_node 2 {training_entry}")
    if "model_export" in product_workflows and not export_entry:
        export_commands.append("python -c \"import torch; print('wire your export entry point here')\"")

    for relative in relative_paths:
        path_obj = Path(relative)
        if path_obj.suffix.lower() in CHECKPOINT_FILE_EXTENSIONS or any(part.lower() in CHECKPOINT_DIR_HINTS for part in path_obj.parts):
            checkpoint_paths.append(relative)

    mode = "pytorch_general"
    if "distributed_training" in product_workflows:
        mode = "pytorch_distributed"
    elif "llm_finetuning" in product_workflows:
        mode = "pytorch_finetuning"
    elif "diffusion_inference" in product_workflows:
        mode = "pytorch_diffusion"

    validation_notes.extend(
        [
            "Separate dataloader sanity, forward/backward smoke, checkpoint validation, and export checks instead of calling one green test the whole story.",
            "Record the exact device, precision, and batch size used during validation so PyTorch results do not become folklore.",
            "Treat checkpoint load/save paths as evidence-bearing artifacts, not decorative leftovers in the repo root.",
        ]
    )
    if "distributed_training" in product_workflows:
        validation_notes.append("For distributed runs, prove launcher assumptions, rank/world-size handling, and checkpoint behavior instead of treating torchrun like a personality trait.")
    if "model_export" in product_workflows:
        validation_notes.append("For TorchScript or ONNX exports, prove the artifact loads and runs on a representative inference path.")
    if "llm_finetuning" in product_workflows:
        validation_notes.append("For PEFT or LoRA flows, verify trainable-parameter counts and merged-adapter behavior instead of trusting the config file on vibes.")

    return {
        "enabled": True,
        "mode": mode,
        "signals": _dedupe(signals),
        "languages": _dedupe(languages or ["Python"]),
        "frameworks": _dedupe(frameworks),
        "build_commands": _dedupe(build_commands),
        "test_commands": _dedupe(test_commands),
        "training_commands": _dedupe(training_commands),
        "evaluation_commands": _dedupe(evaluation_commands),
        "inference_commands": _dedupe(inference_commands),
        "export_commands": _dedupe(export_commands),
        "observability_commands": _dedupe(observability_commands),
        "product_workflows": _dedupe(product_workflows),
        "validation_notes": _dedupe(validation_notes),
        "important_paths": _dedupe(important_paths),
        "checkpoint_paths": _dedupe(checkpoint_paths),
        "distributed_stack": _dedupe(distributed_stack),
    }


def detect_pytorch_runtime_status(workspace_path: str | Path) -> dict[str, Any]:
    repo_mode = detect_pytorch_repo_mode(workspace_path)
    if not repo_mode.get("enabled"):
        return {
            "available": False,
            "status": "not_applicable",
            "summary": "This workspace does not currently look like a PyTorch repo.",
            "torch_installed": False,
            "cuda_available": False,
            "mps_available": False,
            "device_count": 0,
            "torch_version": None,
            "cuda_version": None,
            "distributed_backends": [],
            "blockers": [],
            "recommended_fixes": [],
        }

    probe = (
        "import json\n"
        "try:\n"
        "    import torch\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'ok': False, 'error': str(exc)}))\n"
        "    raise SystemExit(0)\n"
        "payload = {\n"
        "    'ok': True,\n"
        "    'torch_version': getattr(torch, '__version__', None),\n"
        "    'cuda_available': bool(getattr(torch.cuda, 'is_available', lambda: False)()),\n"
        "    'cuda_version': getattr(torch.version, 'cuda', None),\n"
        "    'mps_available': bool(getattr(getattr(torch, 'backends', None), 'mps', None) and torch.backends.mps.is_available()),\n"
        "    'device_count': int(getattr(torch.cuda, 'device_count', lambda: 0)()),\n"
        "    'cudnn_available': bool(getattr(getattr(torch.backends, 'cudnn', None), 'is_available', lambda: False)()),\n"
        "}\n"
        "print(json.dumps(payload))\n"
    )
    payload: dict[str, Any] = {}
    blockers: list[str] = []
    recommended_fixes: list[str] = []
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        output = completed.stdout or ""
        payload = _parse_probe_payload(output)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}

    torch_installed = bool(payload.get("ok"))
    cuda_available = bool(payload.get("cuda_available"))
    mps_available = bool(payload.get("mps_available"))
    device_count = int(payload.get("device_count") or 0)
    distributed_backends: list[str] = []
    if cuda_available:
        distributed_backends.append("nccl")
    if torch_installed:
        distributed_backends.append("gloo")

    if not torch_installed:
        blockers.append(f"PyTorch runtime probe failed: {payload.get('error') or 'unknown error'}")
        recommended_fixes.append("Install a working PyTorch build for this Python environment before asking Mission Control to validate training or inference.")
    if repo_mode.get("distributed_stack") and not cuda_available:
        recommended_fixes.append("Distributed PyTorch signals were detected, but CUDA is not available in the current runtime.")
    if "model_export" in list(repo_mode.get("product_workflows") or []) and not shutil.which("python"):
        recommended_fixes.append("Python is not available on PATH for export validation, which would be a deeply creative way to fail.")
    if not shutil.which("nvidia-smi") and cuda_available:
        recommended_fixes.append("CUDA appears available through torch, but nvidia-smi is missing, so lower-level GPU diagnostics may be annoyingly incomplete.")

    status = "ready"
    if blockers:
        status = "blocked"
    elif not cuda_available and not mps_available:
        status = "partial"

    summary = "PyTorch runtime is ready for Mission Control validation."
    if status == "blocked":
        summary = "Mission Control detected a PyTorch repo, but the local runtime is not actually ready yet."
    elif status == "partial":
        summary = "PyTorch runtime is available, but only CPU validation is currently obvious."

    return {
        "available": torch_installed,
        "status": status,
        "summary": summary,
        "torch_installed": torch_installed,
        "cuda_available": cuda_available,
        "mps_available": mps_available,
        "device_count": device_count,
        "torch_version": payload.get("torch_version"),
        "cuda_version": payload.get("cuda_version"),
        "cudnn_available": bool(payload.get("cudnn_available")),
        "distributed_backends": _dedupe(distributed_backends),
        "blockers": _dedupe(blockers),
        "recommended_fixes": _dedupe(recommended_fixes),
    }


def build_pytorch_validation_plan(workspace_path: str | Path) -> dict[str, Any]:
    repo_mode = detect_pytorch_repo_mode(workspace_path)
    runtime = detect_pytorch_runtime_status(workspace_path)
    if not repo_mode.get("enabled"):
        return {
            "available": False,
            "status": "not_applicable",
            "summary": "This workspace does not currently look like a PyTorch repo.",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "runtime_status": None,
            "steps": [],
            "blockers": [],
            "recommended_fixes": [],
            "evidence_targets": [],
            "product_workflows": [],
        }

    steps: list[dict[str, Any]] = []
    for command in list(repo_mode.get("build_commands") or []):
        steps.append({"title": "Install or sync PyTorch dependencies", "command": command, "type": "build", "status": "pending"})
    for command in list(repo_mode.get("test_commands") or []):
        steps.append({"title": "Run PyTorch-focused tests", "command": command, "type": "test", "status": "pending"})
    for command in list(repo_mode.get("training_commands") or []):
        steps.append({"title": "Run the training entry point", "command": command, "type": "train", "status": "pending"})
    for command in list(repo_mode.get("evaluation_commands") or []):
        steps.append({"title": "Run the evaluation entry point", "command": command, "type": "eval", "status": "pending"})
    for command in list(repo_mode.get("inference_commands") or []):
        steps.append({"title": "Run the inference or serve entry point", "command": command, "type": "inference", "status": "pending"})
    for command in list(repo_mode.get("export_commands") or []):
        steps.append({"title": "Validate export artifacts", "command": command, "type": "export", "status": "pending"})
    for command in list(repo_mode.get("observability_commands") or []):
        steps.append({"title": "Inspect PyTorch profiler or observability evidence", "command": command, "type": "observability", "status": "pending"})

    steps.extend(
        [
            {"title": "Run a one-step forward/backward smoke pass", "command": "python -c \"print('wire repo-specific forward/backward smoke here')\"", "type": "sanity", "status": "pending"},
            {"title": "Verify checkpoint load/save behavior", "command": "python -c \"print('wire repo-specific checkpoint round-trip here')\"", "type": "checkpoint", "status": "pending"},
        ]
    )

    blockers = list(runtime.get("blockers") or [])
    recommended_fixes = list(runtime.get("recommended_fixes") or [])
    if not repo_mode.get("training_commands") and not repo_mode.get("test_commands"):
        blockers.append("No obvious PyTorch training or test entry point was detected yet.")
        recommended_fixes.append("Add or document a concrete train, evaluate, or pytest command so Mission Control can validate PyTorch work honestly.")
    if repo_mode.get("distributed_stack") and not runtime.get("cuda_available"):
        recommended_fixes.append("Distributed PyTorch workflows are configured, but the current runtime looks CPU-only.")
    if repo_mode.get("checkpoint_paths"):
        steps.append({"title": "Inspect existing checkpoints", "command": "python -c \"print('inspect checkpoint metadata and compatibility')\"", "type": "checkpoint", "status": "pending"})
    else:
        recommended_fixes.append("Document where checkpoints are written so Mission Control can verify resume behavior without rummaging blindly.")

    evidence_targets = _dedupe(
        [
            "Record the exact training, evaluation, export, and checkpoint commands that actually ran.",
            "Capture device, precision, and batch-size evidence for every PyTorch validation run.",
            "Show checkpoint artifact paths and whether resume or load actually succeeded.",
            *[str(item) for item in list(repo_mode.get("validation_notes") or [])],
        ]
    )

    status = "blocked" if blockers else str(runtime.get("status") or "ready")
    summary = (
        "Mission Control can run a PyTorch-aware validation lane for this workspace."
        if not blockers
        else "Mission Control detected PyTorch repo signals, but the validation lane still has real blockers."
    )
    return {
        "available": True,
        "status": status,
        "summary": summary,
        "repo_mode_enabled": True,
        "repo_mode": repo_mode.get("mode"),
        "runtime_status": runtime.get("status"),
        "steps": steps[:18],
        "blockers": _dedupe(blockers),
        "recommended_fixes": _dedupe(recommended_fixes)[:12],
        "evidence_targets": evidence_targets[:12],
        "product_workflows": list(repo_mode.get("product_workflows") or []),
    }
