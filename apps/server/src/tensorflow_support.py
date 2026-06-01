from __future__ import annotations

import re
import shutil
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
MODEL_FILE_HINTS = {"saved_model.pb", "keras_metadata.pb"}
EXPORT_FILE_EXTENSIONS = {".tflite"}
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
    "pipelines/train.py",
]
TUNING_FILE_CANDIDATES = [
    "tune.py",
    "scripts/tune.py",
    "scripts/tuning.py",
    "training/tune.py",
]
EXPORT_FILE_CANDIDATES = [
    "export.py",
    "scripts/export.py",
    "serving/export.py",
    "deployment/export.py",
]
TFX_FILE_CANDIDATES = [
    "pipeline.py",
    "pipelines/pipeline.py",
    "tfx_pipeline.py",
]
SERVING_FILE_CANDIDATES = [
    "serve.py",
    "serving/serve.py",
    "api/server.py",
    "app.py",
]
OBSERVABILITY_DIR_CANDIDATES = [
    "artifacts/tensorboard",
    "artifacts/logs",
    "logs",
    "runs",
]
PRIORITY_SIGNAL_FILE_CANDIDATES = [
    "train.py",
    "export.py",
    "serve.py",
    "pipeline.py",
    "tfx_pipeline.py",
    "scripts/train.py",
    "scripts/tune.py",
    "scripts/export.py",
    "training/train.py",
    "training/tune.py",
    "serving/export.py",
    "deployment/export.py",
    "pipelines/pipeline.py",
    "api/server.py",
    "app.py",
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


def detect_tensorflow_repo_mode(workspace_path: str | Path) -> dict[str, Any]:
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
            "observability_commands": [],
            "export_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
        }

    files = _scan_files(root)
    relative_paths = [path.relative_to(root).as_posix() for path in files]
    file_set = set(relative_paths)
    languages: list[str] = []
    frameworks: list[str] = []
    build_commands: list[str] = []
    test_commands: list[str] = []
    training_commands: list[str] = []
    observability_commands: list[str] = []
    export_commands: list[str] = []
    product_workflows: list[str] = []
    validation_notes: list[str] = []
    signals: list[str] = []
    important_paths: list[str] = []
    existing_tflite_artifacts: list[str] = []
    existing_savedmodel_artifacts: list[str] = []

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

    tensorflow_tokens = (
        "tensorflow",
        "tf.keras",
        "keras",
        "tensorflow_hub",
        "tensorflow-serving",
        "tensorflow_serving",
        "tensorflow_lite",
        "tflite",
        "tfmot",
        "keras_tuner",
        "keras-tuner",
        "tensorboard",
        "tfx",
        "tensorflow_data_validation",
        "tensorflow_transform",
        "tensorflow_model_analysis",
    )
    file_hints = any(path.name in MODEL_FILE_HINTS or path.suffix.lower() in EXPORT_FILE_EXTENSIONS for path in files)
    core_tensorflow_signal = any(token in combined_text for token in tensorflow_tokens) or file_hints
    if core_tensorflow_signal:
        _append_unique(frameworks, ["TensorFlow", "Keras"])
        signals.append("Detected TensorFlow or Keras dependency signals in project files.")

    if not core_tensorflow_signal:
        return {
            "enabled": False,
            "mode": None,
            "signals": [],
            "languages": _dedupe(languages),
            "frameworks": [],
            "build_commands": [],
            "test_commands": [],
            "training_commands": [],
            "observability_commands": [],
            "export_commands": [],
            "product_workflows": [],
            "validation_notes": [],
            "important_paths": [],
        }

    if any(token in combined_text for token in ("keras_tuner", "keras-tuner", "hyperband", "bayesianoptimization")):
        frameworks.append("KerasTuner")
        product_workflows.append("hyperparameter_tuning")
        signals.append("Detected KerasTuner or hyperparameter search signals.")
    if "tensorboard" in combined_text:
        frameworks.append("TensorBoard")
        product_workflows.append("training_observability")
        signals.append("Detected TensorBoard observability signals.")
    if any(token in combined_text for token in ("tensorflow_hub", "tfhub")):
        frameworks.append("TensorFlow Hub")
        product_workflows.append("transfer_learning")
        signals.append("Detected TensorFlow Hub or transfer-learning signals.")
    if any(token in combined_text for token in ("tfx", "tensorflow_data_validation", "tensorflow_transform", "tensorflow_model_analysis")):
        frameworks.append("TFX")
        product_workflows.append("production_ml_pipelines")
        signals.append("Detected TFX or TensorFlow Extended pipeline signals.")
    if any(token in combined_text for token in ("tensorflow-serving", "tensorflow_serving", "saved_model_cli", "tf.saved_model")):
        frameworks.append("SavedModel / Serving")
        product_workflows.append("serving_export")
        signals.append("Detected SavedModel or serving/export signals.")
    if any(token in combined_text for token in ("tflite", "tensorflow_lite", "tf.lite")) or any(path.endswith(".tflite") for path in relative_paths):
        frameworks.append("TensorFlow Lite")
        product_workflows.append("edge_deployment")
        signals.append("Detected TensorFlow Lite export or edge deployment signals.")
    if any(token in combined_text for token in ("tfmot", "model_optimization", "quantization", "pruning")):
        frameworks.append("Model Optimization Toolkit")
        product_workflows.append("model_optimization")
        signals.append("Detected TensorFlow model-optimization signals.")
    if any(token in combined_text for token in ("tf.data", "from_tensor_slices", "tfrecord", "image_dataset_from_directory", "text_dataset_from_directory")):
        product_workflows.append("data_pipelines")
        signals.append("Detected tf.data or TensorFlow dataset pipeline signals.")

    build_command = _build_python_install_command(root)
    if build_command:
        build_commands.append(build_command)

    if "pytest" in combined_text or any("test" in path.lower() and path.endswith(".py") for path in relative_paths):
        test_commands.append("python -m pytest")

    training_entry = _first_existing_command(root, TRAINING_FILE_CANDIDATES)
    if training_entry:
        training_commands.append(f"python {training_entry}")
        important_paths.append(training_entry)
    elif any(path.startswith("notebooks/") for path in relative_paths):
        important_paths.append("notebooks")

    tuning_entry = _first_existing_command(root, TUNING_FILE_CANDIDATES)
    if tuning_entry:
        training_commands.append(f"python {tuning_entry}")
        important_paths.append(tuning_entry)

    export_entry = _first_existing_command(root, EXPORT_FILE_CANDIDATES)
    if export_entry:
        export_commands.append(f"python {export_entry}")
        important_paths.append(export_entry)

    serving_entry = _first_existing_command(root, SERVING_FILE_CANDIDATES)
    if serving_entry and "SavedModel / Serving" in frameworks:
        export_commands.append(f"python {serving_entry}")
        important_paths.append(serving_entry)

    tfx_entry = _first_existing_command(root, TFX_FILE_CANDIDATES)
    if tfx_entry and "TFX" in frameworks:
        training_commands.append(f"python {tfx_entry}")
        important_paths.append(tfx_entry)

    if "TensorBoard" in frameworks:
        logdir = _find_workspace_directory_candidate(root, OBSERVABILITY_DIR_CANDIDATES) or "artifacts/tensorboard"
        observability_commands.append(f"tensorboard --logdir {logdir}")
    for relative in relative_paths:
        relative_path = Path(relative)
        if relative_path.suffix.lower() == ".tflite":
            existing_tflite_artifacts.append(relative)
        if relative_path.name == "saved_model.pb" or relative_path.name == "keras_metadata.pb":
            existing_savedmodel_artifacts.append(relative)
    if "SavedModel / Serving" in frameworks and shutil.which("saved_model_cli"):
        export_commands.append("saved_model_cli show --dir <saved_model_dir> --all")
    if "TensorFlow Lite" in frameworks and shutil.which("tflite_convert"):
        export_commands.append("tflite_convert --saved_model_dir <saved_model_dir> --output_file model.tflite")

    mode = "tensorflow_product"
    if "TFX" in frameworks:
        mode = "tensorflow_tfx"
    elif "TensorFlow Lite" in frameworks and "SavedModel / Serving" not in frameworks:
        mode = "tensorflow_edge"
    elif "TensorFlow Hub" in frameworks:
        mode = "tensorflow_transfer_learning"

    validation_notes.extend(
        [
            "Treat data pipelines, model training, export, and serving checks as separate validation stages.",
            "Use TensorBoard or equivalent run artifacts so training claims have evidence instead of motivational speeches.",
            "Keep training-time preprocessing aligned with inference/export flows so serving skew does not become your personality.",
        ]
    )
    if "TFX" in frameworks:
        validation_notes.append("For TFX-style repos, validate schema, transform, trainer, evaluator, and pusher expectations instead of only running a model script.")
    if "TensorFlow Lite" in frameworks:
        validation_notes.append("For edge targets, prove the exported Lite artifact exists and still meets latency, memory, or accuracy constraints.")
    if "KerasTuner" in frameworks:
        validation_notes.append("Treat tuning results as evidence-backed comparisons, not a slot machine that excuses missing baselines.")

    return {
        "enabled": True,
        "mode": mode,
        "signals": _dedupe(signals),
        "languages": _dedupe(languages or ["Python"]),
        "frameworks": _dedupe(frameworks),
        "build_commands": _dedupe(build_commands),
        "test_commands": _dedupe(test_commands),
        "training_commands": _dedupe(training_commands),
        "observability_commands": _dedupe(observability_commands),
        "export_commands": _dedupe(export_commands),
        "product_workflows": _dedupe(product_workflows),
        "validation_notes": _dedupe(validation_notes),
        "important_paths": _dedupe(important_paths),
        "existing_tflite_artifacts": _dedupe(existing_tflite_artifacts),
        "existing_savedmodel_artifacts": _dedupe(existing_savedmodel_artifacts),
    }


def build_tensorflow_validation_plan(workspace_path: str | Path) -> dict[str, Any]:
    repo_mode = detect_tensorflow_repo_mode(workspace_path)
    if not repo_mode.get("enabled"):
        return {
            "available": False,
            "status": "not_applicable",
            "summary": "This workspace does not currently look like a TensorFlow or Keras repo.",
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
        steps.append({"title": "Install or sync TensorFlow dependencies", "command": command, "type": "build", "status": "pending"})
    for command in list(repo_mode.get("test_commands") or []):
        steps.append({"title": "Run TensorFlow-focused tests", "command": command, "type": "test", "status": "pending"})
    for command in list(repo_mode.get("training_commands") or []):
        steps.append({"title": "Run the training or pipeline entry point", "command": command, "type": "train", "status": "pending"})
    for command in list(repo_mode.get("observability_commands") or []):
        steps.append({"title": "Inspect training telemetry", "command": command, "type": "observability", "status": "pending"})
    for command in list(repo_mode.get("export_commands") or []):
        steps.append({"title": "Validate export or serving artifacts", "command": command, "type": "export", "status": "pending"})

    repo_owned_execution_commands = [
        command
        for command in (
            list(repo_mode.get("training_commands") or [])
            + list(repo_mode.get("test_commands") or [])
            + list(repo_mode.get("export_commands") or [])
        )
        if str(command).strip().startswith("python ")
    ]

    smoke_command = next(
        iter(
            list(repo_mode.get("test_commands") or [])
            or list(repo_mode.get("training_commands") or [])
            or repo_owned_execution_commands
        ),
        None,
    )
    if smoke_command:
        steps.append(
            {
                "title": "Run the smallest repo-owned TensorFlow smoke command",
                "command": smoke_command,
                "type": "sanity",
                "status": "pending",
            }
        )

    blockers: list[str] = []
    recommended_fixes: list[str] = []
    has_execution_entry = bool(repo_mode.get("training_commands") or repo_mode.get("test_commands") or repo_owned_execution_commands)
    if not has_execution_entry:
        blockers.append("No obvious TensorFlow train, test, or repo-owned export entry point was detected yet.")
        recommended_fixes.append("Add or document a concrete TensorFlow train, test, export, or pytest command so Mission Control can validate changes honestly.")
    elif not smoke_command:
        recommended_fixes.append("Document the smallest repo-owned TensorFlow train, test, or export command so Mission Control can run a real smoke pass.")
    if "TensorBoard" in list(repo_mode.get("frameworks") or []) and not shutil.which("tensorboard"):
        recommended_fixes.append("Install TensorBoard if you expect Mission Control to review training curves instead of pretending logs explain themselves.")
    if "TFX" in list(repo_mode.get("frameworks") or []) and not shutil.which("tfx"):
        recommended_fixes.append("Install the TFX CLI or document the repo's pipeline entry point before claiming production-pipeline validation exists.")
    if "TensorFlow Lite" in list(repo_mode.get("frameworks") or []) and not shutil.which("tflite_convert"):
        recommended_fixes.append("Install TensorFlow Lite conversion tooling if this repo is supposed to ship edge artifacts.")
    if "SavedModel / Serving" in list(repo_mode.get("frameworks") or []) and not shutil.which("saved_model_cli"):
        recommended_fixes.append("Install TensorFlow SavedModel tooling so export inspection does not depend on blind faith.")
    if "SavedModel / Serving" in list(repo_mode.get("frameworks") or []) and not (
        repo_mode.get("export_commands") or repo_mode.get("existing_savedmodel_artifacts")
    ):
        recommended_fixes.append("Add or document a concrete TensorFlow export entry point or checked-in SavedModel artifact so Mission Control can validate serving artifacts instead of just talking about them.")
    if "TensorFlow Lite" in list(repo_mode.get("frameworks") or []) and not (
        repo_mode.get("export_commands") or repo_mode.get("existing_tflite_artifacts")
    ):
        recommended_fixes.append("Add or document a concrete TensorFlow export entry point so Mission Control can validate deployment artifacts instead of just talking about them.")

    evidence_targets = _dedupe(
        [
            "Record training, evaluation, and export commands that actually ran.",
            "Capture TensorBoard, test, or metric evidence instead of declaring model quality from memory.",
            "Show the produced artifact path for SavedModel or TFLite exports when deployment claims are made.",
            *[str(item) for item in list(repo_mode.get("validation_notes") or [])],
        ]
    )

    status = "blocked" if blockers else "ready"
    summary = (
        "Mission Control can run a TensorFlow-aware product validation lane for this workspace."
        if not blockers
        else "Mission Control detected TensorFlow repo signals, but the validation lane still needs an explicit entry point."
    )
    return {
        "available": True,
        "status": status,
        "summary": summary,
        "repo_mode_enabled": True,
        "repo_mode": repo_mode.get("mode"),
        "steps": steps[:16],
        "blockers": _dedupe(blockers),
        "recommended_fixes": _dedupe(recommended_fixes)[:12],
        "evidence_targets": evidence_targets[:12],
        "product_workflows": list(repo_mode.get("product_workflows") or []),
    }
