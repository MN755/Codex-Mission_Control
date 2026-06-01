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
SKIPPED_DISCOVERY_DIRS = {
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
OBSERVABILITY_DIR_CANDIDATES = [
    "artifacts/tensorboard",
    "artifacts/logs",
    "runs",
    "logs",
    "mlruns",
    "wandb",
]
PRIORITY_SIGNAL_FILE_CANDIDATES = [
    "train.py",
    "eval.py",
    "evaluate.py",
    "infer.py",
    "inference.py",
    "serve.py",
    "export.py",
    "scripts/train.py",
    "scripts/eval.py",
    "scripts/evaluate.py",
    "scripts/infer.py",
    "scripts/inference.py",
    "scripts/export.py",
    "training/train.py",
    "training/eval.py",
    "training/evaluate.py",
    "deployment/export.py",
    "serving/export.py",
]
CONFIG_DIR_HINTS = {"config", "configs", "conf", "hydra", "settings"}
CONFIG_FILE_HINTS = {"config", "configs", "params", "hparams", "hyperparams", "trainer", "launch"}
CONFIG_FILE_EXTENSIONS = {".yaml", ".yml", ".json", ".toml"}


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
    return _find_workspace_candidate(root, candidates)


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


def _first_existing_path(root: Path, candidates: list[str]) -> str | None:
    return _find_workspace_candidate(root, candidates)


def _priority_signal_paths(root: Path, files: list[Path]) -> list[Path]:
    by_relative = {path.relative_to(root).as_posix(): path for path in files}
    ordered: list[Path] = []
    seen: set[Path] = set()
    for candidate in PRIORITY_SIGNAL_FILE_CANDIDATES:
        path = by_relative.get(candidate)
        if path is not None and path not in seen:
            ordered.append(path)
            seen.add(path)
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        if path.suffix.lower() not in PYTHON_FILE_EXTENSIONS:
            continue
        if path in seen:
            continue
        ordered.append(path)
        seen.add(path)
    return ordered


def _notebook_paths(relative_paths: list[str]) -> list[str]:
    return sorted(path for path in relative_paths if Path(path).suffix.lower() == ".ipynb")


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
    nested_requirements = _find_workspace_candidate(root, ["requirements.txt", "requirements-dev.txt", "requirements.in"])
    if nested_requirements:
        return f"python -m pip install -r {nested_requirements}"
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
            "notebook_paths": [],
            "config_paths": [],
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
    notebook_paths = _notebook_paths(relative_paths)
    config_paths = _config_paths(relative_paths)

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
    for path in _priority_signal_paths(root, files):
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
            "notebook_paths": [],
            "config_paths": [],
        }

    if any(token in combined_text for token in ("torchvision", "imagenet", "albumentations", "timm")):
        frameworks.append("TorchVision")
        product_workflows.append("vision_training")
        signals.append("Detected TorchVision or vision-training signals.")
    if any(token in combined_text for token in ("torchaudio", "librosa", "wav2vec", "whisper")):
        frameworks.append("TorchAudio")
        product_workflows.append("audio_training")
        signals.append("Detected TorchAudio or audio-model signals.")
    if any(token in combined_text for token in ("pytorch-lightning", "lightning.pytorch")):
        frameworks.append("Lightning")
        product_workflows.append("structured_training")
        signals.append("Detected Lightning trainer signals.")
    if "accelerate" in combined_text:
        frameworks.append("Accelerate")
        distributed_stack.append("Accelerate")
        product_workflows.append("distributed_training")
        signals.append("Detected Accelerate launch or config signals.")
    if any(token in combined_text for token in ("deepspeed", "zero stage", "zero_stage", "ds_config")):
        frameworks.append("DeepSpeed")
        distributed_stack.append("DeepSpeed")
        product_workflows.append("distributed_training")
        signals.append("Detected DeepSpeed distributed-training signals.")
    if any(token in combined_text for token in ("torch.distributed", "torchrun", "ddp", "fsdp")):
        distributed_stack.append("DDP/FSDP")
        product_workflows.append("distributed_training")
        signals.append("Detected DDP or FSDP distributed-training signals.")
    if any(token in combined_text for token in ("diffusers", "stable diffusion")):
        frameworks.append("Diffusers")
        product_workflows.append("diffusion_inference")
        signals.append("Detected Diffusers or image-generation signals.")
    if any(token in combined_text for token in ("transformers", "peft", "lora")):
        frameworks.append("Transformers / PEFT")
        product_workflows.append("llm_finetuning")
        signals.append("Detected Hugging Face Transformers or PEFT signals.")
    if any(token in combined_text for token in ("onnx", "torchscript", "jit.trace", "jit.script")):
        product_workflows.append("model_export")
        signals.append("Detected TorchScript or ONNX export signals.")
    if any(token in combined_text for token in ("torch.profiler", "tensorboard", "wandb", "mlflow")):
        product_workflows.append("training_observability")
        signals.append("Detected training observability or profiler signals.")
    if notebook_paths:
        product_workflows.append("notebook_experiments")
        signals.append("Detected PyTorch notebook experiments that need a repeatable script path instead of vibes.")
        _append_unique(important_paths, notebook_paths[:3])
    if config_paths:
        product_workflows.append("config_driven_runs")
        signals.append("Detected PyTorch config files that likely control launcher, optimizer, or export behavior.")
        _append_unique(important_paths, config_paths[:4])

    build_command = _build_python_install_command(root)
    if build_command:
        build_commands.append(build_command)

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
        if "torch.profiler" in combined_text and training_entry:
            observability_commands.append(f"python -m torch.utils.bottleneck {training_entry}")
        logdir = _find_workspace_directory_candidate(root, OBSERVABILITY_DIR_CANDIDATES) or "artifacts/tensorboard"
        if "tensorboard" in combined_text or "torch.profiler" in combined_text:
            observability_commands.append(f"python -m tensorboard.main --logdir {logdir}")
        if "wandb" in combined_text:
            wandb_dir = _find_workspace_directory_candidate(root, ["wandb"]) or "wandb"
            observability_commands.append(f"wandb sync {wandb_dir}")
        if "mlflow" in combined_text:
            mlruns_dir = _find_workspace_directory_candidate(root, ["mlruns"]) or "mlruns"
            observability_commands.append(f"mlflow ui --backend-store-uri {mlruns_dir}")
    if "distributed_training" in product_workflows and training_entry:
        if "Accelerate" in distributed_stack:
            training_commands.append(f"accelerate launch {training_entry}")
        if "DeepSpeed" in distributed_stack:
            training_commands.append(f"deepspeed {training_entry} --deepspeed ds_config.json")
        if "DDP/FSDP" in distributed_stack:
            training_commands.append(f"torchrun --nproc_per_node 2 {training_entry}")

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
    if notebook_paths:
        validation_notes.append("If the real PyTorch workflow still lives in notebooks, promote the repeatable path into a repo-owned script before calling validation complete.")
    if config_paths:
        validation_notes.append("Capture the config file used for each training or export run so PyTorch evidence stops depending on memory and luck.")

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
        "notebook_paths": _dedupe(notebook_paths),
        "config_paths": _dedupe(config_paths),
    }


def detect_pytorch_runtime_status(workspace_path: str | Path) -> dict[str, Any]:
    repo_mode = detect_pytorch_repo_mode(workspace_path)
    python_available = bool(shutil.which("python"))
    if not repo_mode.get("enabled"):
        return {
            "available": False,
            "status": "not_applicable",
            "summary": "This workspace does not currently look like a PyTorch repo.",
            "torch_installed": False,
            "python_available": python_available,
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
    repo_owned_commands = [
        str(command)
        for key in ("build_commands", "test_commands", "training_commands", "evaluation_commands", "inference_commands", "export_commands")
        for command in list(repo_mode.get(key) or [])
        if str(command).strip().startswith("python ")
    ]
    if repo_owned_commands and not python_available:
        blockers.append("Python is not available on PATH for the repo-owned PyTorch commands this workspace expects to run.")
        recommended_fixes.append("Expose Python on PATH before asking Mission Control to run repo-owned PyTorch validation commands.")
    distributed_stack = {str(item) for item in list(repo_mode.get("distributed_stack") or [])}
    if {"DeepSpeed", "DDP/FSDP"} & distributed_stack and not cuda_available:
        recommended_fixes.append("Some distributed PyTorch workflows in this repo usually expect CUDA, but the current runtime does not provide it.")
    if "Accelerate" in distributed_stack and not shutil.which("accelerate"):
        recommended_fixes.append("Install the Accelerate CLI if this repo expects accelerate launch flows instead of pretending torchrun covers everything.")
    if "DeepSpeed" in distributed_stack and not shutil.which("deepspeed"):
        recommended_fixes.append("Install the DeepSpeed CLI if this repo expects deepspeed launch flows.")
    if "DDP/FSDP" in distributed_stack and not shutil.which("torchrun"):
        recommended_fixes.append("Install or expose torchrun on PATH before treating DDP or FSDP validation like a real option.")
    if "model_export" in list(repo_mode.get("product_workflows") or []) and not shutil.which("python"):
        recommended_fixes.append("Python is not available on PATH for export validation, which would be a deeply creative way to fail.")
    if not shutil.which("nvidia-smi") and cuda_available:
        recommended_fixes.append("CUDA appears available through torch, but nvidia-smi is missing, so lower-level GPU diagnostics may be annoyingly incomplete.")
    if cuda_available and device_count <= 0:
        blockers.append("PyTorch reported CUDA availability, but no visible CUDA devices were detected.")
        recommended_fixes.append("Fix the CUDA runtime or device visibility before trusting GPU validation results from this environment.")

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
        "python_available": python_available,
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

    smoke_command = next(
        iter(
            list(repo_mode.get("evaluation_commands") or [])
            or list(repo_mode.get("inference_commands") or [])
            or list(repo_mode.get("training_commands") or [])
            or list(repo_mode.get("test_commands") or [])
        ),
        None,
    )
    if smoke_command:
        steps.append(
            {
                "title": "Run the smallest repo-owned PyTorch smoke command",
                "command": smoke_command,
                "type": "sanity",
                "status": "pending",
            }
        )

    blockers = list(runtime.get("blockers") or [])
    recommended_fixes = list(runtime.get("recommended_fixes") or [])
    python_available = bool(runtime.get("python_available", shutil.which("python")))
    has_execution_entry = any(
        repo_mode.get(key)
        for key in ("training_commands", "test_commands", "evaluation_commands", "inference_commands", "export_commands")
    )
    if not has_execution_entry:
        blockers.append("No obvious PyTorch train, test, eval, infer, or export entry point was detected yet.")
        recommended_fixes.append("Add or document a concrete train, evaluate, infer, export, or pytest command so Mission Control can validate PyTorch work honestly.")
        if repo_mode.get("notebook_paths"):
            recommended_fixes.append("Promote the detected PyTorch notebook flow into a repo-owned script or test command so Mission Control can validate something repeatable.")
    elif not smoke_command:
        recommended_fixes.append("Document the smallest repo-owned train, eval, infer, or pytest command so Mission Control can run a real PyTorch smoke pass.")
    if steps and not python_available and any(str(step.get("command") or "").startswith("python ") for step in steps):
        blockers.append("Python is not available on PATH for the repo-owned PyTorch validation commands in this plan.")
        recommended_fixes.append("Expose Python on PATH before running the generated PyTorch validation lane.")
    distributed_stack = {str(item) for item in list(repo_mode.get("distributed_stack") or [])}
    if {"DeepSpeed", "DDP/FSDP"} & distributed_stack and not runtime.get("cuda_available"):
        recommended_fixes.append("Some distributed PyTorch workflows in this repo usually expect GPUs, but the current runtime looks CPU-only.")
    if repo_mode.get("checkpoint_paths"):
        checkpoint_path = str(list(repo_mode.get("checkpoint_paths") or [])[0]).replace("\\", "/")
        checkpoint_literal = json.dumps(checkpoint_path)
        steps.append(
            {
                "title": "Inspect existing checkpoints",
                "command": f"python -c \"import torch; payload = torch.load({checkpoint_literal}, map_location='cpu', weights_only=False); print(sorted(payload.keys()) if hasattr(payload, 'keys') else type(payload).__name__)\"",
                "type": "checkpoint",
                "status": "pending",
            }
        )
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
