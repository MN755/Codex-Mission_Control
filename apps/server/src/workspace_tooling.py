from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pytorch_support import (
    build_pytorch_validation_plan,
    detect_pytorch_repo_mode,
    detect_pytorch_runtime_status,
)
from security.path_validation import PathValidationError, resolve_local_path
from tensorflow_support import build_tensorflow_validation_plan, detect_tensorflow_repo_mode


_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "python": {
        "label": "Python",
        "category": "bootstrap",
        "commands": ["python -m pytest"],
        "notes": ["Baseline Python runtime for repo-owned validation, inspection, and audit commands."],
    },
    "uv": {
        "label": "uv",
        "category": "bootstrap",
        "commands": ["uv sync", "uv run pytest"],
        "config_files": ["pyproject.toml", "uv.lock"],
        "pyproject_sections": ["[tool.uv]", "[project]"],
        "notes": ["Fast Python environment sync and isolated task execution."],
    },
    "ruff": {
        "label": "Ruff",
        "category": "validation",
        "commands": ["ruff check .", "ruff format --check ."],
        "config_files": ["pyproject.toml", "ruff.toml", ".ruff.toml"],
        "pyproject_sections": ["[tool.ruff]"],
        "notes": ["Fast Python lint and format gate."],
    },
    "pre-commit": {
        "label": "pre-commit",
        "category": "validation",
        "commands": ["pre-commit run --all-files"],
        "config_files": [".pre-commit-config.yaml", ".pre-commit-config.yml"],
        "notes": ["Repo-native hook runner for hygiene checks."],
    },
    "nox": {
        "label": "Nox",
        "category": "validation",
        "commands": ["nox --list"],
        "config_files": ["noxfile.py"],
        "notes": ["Python session runner for tests, lint, and docs."],
    },
    "rg": {
        "label": "ripgrep",
        "category": "intake",
        "commands": ["rg --files", "rg TODO ."],
        "notes": ["Fast repo search that respects .gitignore."],
    },
    "tree-sitter": {
        "label": "tree-sitter",
        "category": "intake",
        "commands": ["tree-sitter parse <file>"],
        "notes": ["Language-aware symbol and syntax parsing backend."],
    },
    "playwright": {
        "label": "Playwright",
        "category": "validation",
        "commands": ["playwright test"],
        "config_files": [
            "playwright.config.ts",
            "playwright.config.js",
            "playwright.config.mjs",
            "playwright.config.cjs",
        ],
        "package_names": ["playwright", "@playwright/test"],
        "notes": ["Headless browser validation lane."],
    },
    "jupyter": {
        "label": "Jupyter nbconvert",
        "category": "intake",
        "commands": ["jupyter nbconvert --to script <notebook.ipynb>"],
        "notes": ["Notebook rescue lane for turning one-off experiments into repo-owned scripts."],
    },
    "tensorboard": {
        "label": "TensorBoard",
        "category": "validation",
        "commands": ["tensorboard --logdir logs"],
        "workspace_tokens": ["tensorboard", "keras.callbacks.tensorboard"],
        "notes": ["Training-observability lane for TensorFlow and Keras projects."],
    },
    "tfx": {
        "label": "TFX",
        "category": "deployment",
        "commands": ["tfx pipeline list"],
        "workspace_tokens": ["tfx", "tensorflow_data_validation", "tensorflow_transform", "tensorflow_model_analysis"],
        "notes": ["Production ML pipeline lane for TensorFlow Extended projects."],
    },
    "saved_model_cli": {
        "label": "SavedModel CLI",
        "category": "deployment",
        "commands": ["saved_model_cli show --dir <saved_model_dir> --all"],
        "workspace_tokens": ["tf.saved_model", "saved_model_cli", "tensorflow-serving", "tensorflow_serving"],
        "notes": ["Inspect exported TensorFlow serving artifacts before shipping them into the void."],
    },
    "tflite_convert": {
        "label": "TensorFlow Lite Converter",
        "category": "deployment",
        "commands": ["tflite_convert --saved_model_dir <saved_model_dir> --output_file model.tflite"],
        "workspace_tokens": ["tflite", "tensorflow_lite", "tf.lite"],
        "notes": ["Convert SavedModel artifacts into TensorFlow Lite deliverables for edge targets."],
    },
    "torchrun": {
        "label": "torchrun",
        "category": "validation",
        "commands": ["torchrun --nproc_per_node 2 train.py"],
        "workspace_tokens": ["torchrun", "torch.distributed", "ddp", "fsdp"],
        "notes": ["Distributed PyTorch launcher and readiness lane."],
    },
    "accelerate": {
        "label": "Accelerate",
        "category": "validation",
        "commands": ["accelerate launch train.py"],
        "workspace_tokens": ["accelerate"],
        "notes": ["Launcher-aware distributed and mixed-precision PyTorch helper."],
    },
    "deepspeed": {
        "label": "DeepSpeed",
        "category": "validation",
        "commands": ["deepspeed train.py --deepspeed ds_config.json"],
        "workspace_tokens": ["deepspeed", "zero stage", "zero_stage", "ds_config"],
        "notes": ["Large-model distributed launcher and optimizer/runtime stack."],
    },
    "wandb": {
        "label": "Weights & Biases",
        "category": "validation",
        "commands": ["wandb sync wandb"],
        "workspace_tokens": ["wandb"],
        "package_names": ["wandb"],
        "notes": ["Experiment tracking and observability for training runs."],
    },
    "mlflow": {
        "label": "MLflow",
        "category": "validation",
        "commands": ["mlflow ui --backend-store-uri mlruns"],
        "workspace_tokens": ["mlflow", "mlruns"],
        "package_names": ["mlflow"],
        "notes": ["Model training metadata, experiment tracking, and artifact review."],
    },
    "gitleaks": {
        "label": "Gitleaks",
        "category": "security",
        "commands": ["gitleaks dir . --redact"],
        "config_files": [".gitleaks.toml", ".gitleaksignore"],
        "notes": ["Secret scanning gate before handoff or release."],
    },
    "trufflehog": {
        "label": "TruffleHog",
        "category": "security",
        "commands": ["trufflehog filesystem ."],
        "notes": ["Deeper verified credential scan when needed."],
    },
    "osv-scanner": {
        "label": "OSV-Scanner",
        "category": "security",
        "commands": ["osv-scanner --recursive ."],
        "notes": ["Cross-language dependency vulnerability scan."],
    },
    "pip-audit": {
        "label": "pip-audit",
        "category": "security",
        "commands": ["pip-audit"],
        "config_files": ["requirements.txt", "pyproject.toml", "uv.lock", "poetry.lock"],
        "notes": ["Python vulnerability audit for environments and lockfiles."],
    },
}

_PYTHON_SIGNALS = ["pyproject.toml", "requirements.txt", "uv.lock", "poetry.lock", "noxfile.py"]
_NODE_SIGNALS = ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb"]
_PROJECT_TEXT_CANDIDATES = [
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
    "environment.yml",
    "environment.yaml",
    "setup.py",
    "README.md",
]
_SECURITY_LOCKFILES = [
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "uv.lock",
    "requirements.txt",
    "poetry.lock",
    "go.sum",
    "Cargo.lock",
]
_WORKSPACE_SIGNAL_SKIP_DIRS = {
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


def _which(command: str) -> str | None:
    return shutil.which(command)


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _workspace_relative_files(root: Path) -> list[str]:
    relative_paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        parent_parts = parts[:-1]
        if any(part.lower() in _WORKSPACE_SIGNAL_SKIP_DIRS for part in parts):
            continue
        if any(part.startswith(".") and part not in {".github"} for part in parent_parts):
            continue
        relative_paths.append(relative.as_posix())
    return relative_paths


def _matching_relative_paths(relative_files: list[str], expected: str) -> list[str]:
    normalized_expected = expected.replace("\\", "/")
    if "/" in normalized_expected:
        return [path for path in relative_files if path == normalized_expected]
    return [path for path in relative_files if Path(path).name == normalized_expected]


def _package_json_package_names(root: Path, relative_files: list[str] | None = None) -> set[str]:
    relative_files = relative_files or _workspace_relative_files(root)
    package_json_paths = _matching_relative_paths(relative_files, "package.json")
    if not package_json_paths:
        return set()
    package_names: set[str] = set()
    for relative_name in package_json_paths:
        package_json = root / relative_name
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        deps = {}
        deps.update(dict(payload.get("dependencies") or {}))
        deps.update(dict(payload.get("devDependencies") or {}))
        deps.update(dict(payload.get("optionalDependencies") or {}))
        deps.update(dict(payload.get("peerDependencies") or {}))
        package_names.update(str(name) for name in deps)
    return package_names


def _workspace_signal_haystack(root: Path) -> str:
    return _workspace_signal_haystack_from_files(root, _workspace_relative_files(root))


def _workspace_signal_haystack_from_files(root: Path, relative_files: list[str]) -> str:
    text_parts: list[str] = []
    for relative_name in _PROJECT_TEXT_CANDIDATES:
        for matched_path in _matching_relative_paths(relative_files, relative_name):
            text_parts.append(_safe_read_text(root / matched_path).lower())
    for path in sorted(root.rglob("*")):
        if len(text_parts) >= 40:
            break
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part.lower() in _WORKSPACE_SIGNAL_SKIP_DIRS for part in relative_parts):
            continue
        if path.suffix.lower() not in {".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml"}:
            continue
        if any(part.startswith(".") and part not in {".github"} for part in relative_parts):
            continue
        text_parts.append(_safe_read_text(path).lower())
    return "\n".join(text_parts)


def _has_prefixed_command(commands: list[str], prefixes: tuple[str, ...]) -> bool:
    lowered_prefixes = tuple(prefix.lower() for prefix in prefixes)
    return any(str(command).strip().lower().startswith(lowered_prefixes) for command in commands)


def _config_matches(
    root: Path,
    spec: dict[str, Any],
    *,
    relative_files: list[str] | None = None,
    workspace_package_names: set[str] | None = None,
    haystack: str | None = None,
) -> tuple[list[str], list[str]]:
    relative_files = relative_files or _workspace_relative_files(root)
    matched_files: list[str] = []
    matched_sections: list[str] = []
    for relative_name in spec.get("config_files", []):
        matched_files.extend(_matching_relative_paths(relative_files, str(relative_name)))
    pyproject_sections = list(spec.get("pyproject_sections", []))
    if pyproject_sections:
        for pyproject_relative in _matching_relative_paths(relative_files, "pyproject.toml"):
            text = _safe_read_text(root / pyproject_relative).lower()
            for section in pyproject_sections:
                lowered = str(section).lower()
                if lowered and lowered in text:
                    matched_sections.append(section)
    declared_package_names = set(spec.get("package_names", []))
    if declared_package_names:
        installed_names = set(workspace_package_names or ())
        for name in sorted(declared_package_names & installed_names):
            matched_files.append(f"package.json::{name}")
    workspace_tokens = [str(token).strip().lower() for token in spec.get("workspace_tokens", []) if str(token).strip()]
    if workspace_tokens:
        workspace_haystack = haystack or ""
        for token in workspace_tokens:
            if token in workspace_haystack:
                matched_sections.append(f"signal:{token}")
    return sorted(set(matched_files)), sorted(set(matched_sections))


def _repo_profile(
    root: Path,
    *,
    relative_files: list[str] | None = None,
    tensorflow_mode: dict[str, Any] | None = None,
    pytorch_mode: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relative_files = relative_files or _workspace_relative_files(root)
    filenames = {Path(path).name for path in relative_files}
    python_repo = any(name in filenames for name in _PYTHON_SIGNALS)
    node_repo = any(name in filenames for name in _NODE_SIGNALS)
    rust_repo = "Cargo.toml" in filenames
    go_repo = "go.mod" in filenames
    tensorflow_mode = tensorflow_mode or detect_tensorflow_repo_mode(root)
    pytorch_mode = pytorch_mode or detect_pytorch_repo_mode(root)
    return {
        "python_repo": python_repo,
        "node_repo": node_repo,
        "rust_repo": rust_repo,
        "go_repo": go_repo,
        "lockfiles": sorted(path for path in relative_files if Path(path).name in _SECURITY_LOCKFILES),
        "tensorflow_repo": bool(tensorflow_mode.get("enabled")),
        "tensorflow_mode": tensorflow_mode.get("mode"),
        "tensorflow_frameworks": list(tensorflow_mode.get("frameworks") or []),
        "pytorch_repo": bool(pytorch_mode.get("enabled")),
        "pytorch_mode": pytorch_mode.get("mode"),
        "pytorch_frameworks": list(pytorch_mode.get("frameworks") or []),
    }


def _tool_signal_summary(
    tool_id: str,
    *,
    root: Path,
    relative_files: list[str],
    package_names: set[str],
    haystack: str,
) -> dict[str, Any]:
    spec = _TOOL_SPECS[tool_id]
    binary_path = _which(tool_id)
    config_files, config_sections = _config_matches(
        root,
        spec,
        relative_files=relative_files,
        workspace_package_names=package_names,
        haystack=haystack,
    )
    configured = bool(config_files or config_sections)
    installed = bool(binary_path)
    commands = list(spec.get("commands", []))
    notes = list(spec.get("notes", []))
    if configured and not installed:
        notes.append(f"{spec['label']} is referenced by this workspace but the CLI is not currently detectable.")
    elif installed and configured:
        notes.append(f"{spec['label']} is both installed and signaled by the current workspace.")
    elif installed:
        notes.append(f"{spec['label']} is installed, but this workspace does not clearly opt into it yet.")
    status = "ready" if installed and configured else "available" if installed else "needs_setup" if configured else "optional"
    return {
        "id": tool_id,
        "label": spec["label"],
        "category": spec["category"],
        "installed": installed,
        "binary_path": binary_path,
        "configured": configured,
        "config_files": config_files,
        "config_sections": config_sections,
        "status": status,
        "recommended_commands": commands[:4],
        "notes": notes[:6],
    }


def _pack_status(tools: list[dict[str, Any]], tool_ids: list[str], *, title: str, summary: str) -> dict[str, Any]:
    selected = [tool for tool in tools if tool["id"] in tool_ids]
    ready = [tool for tool in selected if tool["status"] == "ready"]
    missing = [tool for tool in selected if tool["configured"] and not tool["installed"]]
    available = [tool for tool in selected if tool["installed"]]
    if missing:
        status = "needs_setup"
    elif ready:
        status = "ready"
    elif available:
        status = "available"
    else:
        status = "optional"
    return {
        "id": title.lower().replace(" ", "_"),
        "title": title,
        "status": status,
        "summary": summary,
        "tool_ids": [tool["id"] for tool in selected],
        "installed_tool_ids": [tool["id"] for tool in available],
        "missing_tool_ids": [tool["id"] for tool in missing],
    }


def _base_workspace_tooling_payload(
    *,
    project_name: str | None,
    workspace_path: str | None,
    available: bool,
    summary: str,
    recommended_next_steps: list[str],
) -> dict[str, Any]:
    return {
        "project_name": project_name,
        "workspace_path": workspace_path,
        "available": available,
        "summary": summary,
        "repo_profile": {},
        "tools": [],
        "packs": [],
        "recommended_next_steps": recommended_next_steps,
        "repo_mode_summaries": [],
        "important_paths": [],
        "execution_entrypoints": [],
        "runtime_blockers": [],
        "validation_evidence_targets": [],
        "intake_commands": [],
        "notebook_paths": [],
        "notebook_commands": [],
        "validation_commands": [],
        "security_commands": [],
        "deployment_commands": [],
        "artifact_paths": [],
        "artifact_inspection_commands": [],
        "config_review_paths": [],
        "config_review_commands": [],
        "tensorflow_repo": {"enabled": False, "frameworks": [], "product_workflows": []},
        "tensorflow_validation_plan": {"available": False, "status": "not_applicable", "steps": [], "recommended_fixes": []},
        "pytorch_repo": {"enabled": False, "frameworks": [], "product_workflows": [], "distributed_stack": []},
        "pytorch_runtime_status": {"available": False, "status": "not_applicable", "recommended_fixes": []},
        "pytorch_validation_plan": {"available": False, "status": "not_applicable", "steps": [], "recommended_fixes": []},
    }


def _config_review_command(path: str) -> str:
    path_literal = repr(path.replace("\\", "/"))
    return (
        "python -c "
        f"\"from pathlib import Path; p = Path({path_literal}); "
        "print(p.read_text(encoding='utf-8', errors='ignore'))\""
    )


def detect_workspace_tooling(workspace_path: str | Path | None, *, project_name: str | None = None) -> dict[str, Any]:
    if not workspace_path:
        return _base_workspace_tooling_payload(
            project_name=project_name,
            workspace_path=None,
            available=False,
            summary="Workspace tooling detection requires a valid local workspace path.",
            recommended_next_steps=["Attach a real workspace before asking Mission Control to reason about repo-native tooling."],
        )
    try:
        root = resolve_local_path(workspace_path, must_exist=True, must_be_dir=True)
    except PathValidationError:
        return _base_workspace_tooling_payload(
            project_name=project_name,
            workspace_path=str(workspace_path),
            available=False,
            summary="Workspace tooling detection could not resolve the requested workspace path.",
            recommended_next_steps=["Reattach the workspace with a valid local directory before running tooling discovery."],
        )
    tensorflow_mode = detect_tensorflow_repo_mode(root)
    pytorch_mode = detect_pytorch_repo_mode(root)
    relative_files = _workspace_relative_files(root)
    repo_profile = _repo_profile(root, relative_files=relative_files, tensorflow_mode=tensorflow_mode, pytorch_mode=pytorch_mode)
    package_names = _package_json_package_names(root, relative_files)
    haystack = _workspace_signal_haystack_from_files(root, relative_files)
    tools = [
        _tool_signal_summary(tool_id, root=root, relative_files=relative_files, package_names=package_names, haystack=haystack)
        for tool_id in _TOOL_SPECS
    ]
    tooling_by_id = {tool["id"]: tool for tool in tools}
    tensorflow_plan = build_tensorflow_validation_plan(root)
    pytorch_runtime = detect_pytorch_runtime_status(root)
    pytorch_plan = build_pytorch_validation_plan(root)
    repo_mode_summaries = _dedupe(
        [
            (
                f"TensorFlow mode `{tensorflow_mode.get('mode')}` with frameworks: "
                f"{', '.join(str(item) for item in list(tensorflow_mode.get('frameworks') or [])[:5])}"
            )
            if tensorflow_mode.get("enabled")
            else "",
            (
                f"PyTorch mode `{pytorch_mode.get('mode')}` with frameworks: "
                f"{', '.join(str(item) for item in list(pytorch_mode.get('frameworks') or [])[:5])}"
            )
            if pytorch_mode.get("enabled")
            else "",
        ]
    )
    important_paths = _dedupe(
        [str(item) for item in list(tensorflow_mode.get("important_paths") or [])]
        + [str(item) for item in list(pytorch_mode.get("important_paths") or [])]
    )
    notebook_paths = _dedupe(
        [str(item) for item in list(tensorflow_mode.get("notebook_paths") or [])]
        + [str(item) for item in list(pytorch_mode.get("notebook_paths") or [])]
    )
    artifact_paths = _dedupe(
        [str(item) for item in list(tensorflow_mode.get("existing_savedmodel_artifacts") or [])]
        + [str(item) for item in list(tensorflow_mode.get("existing_tflite_artifacts") or [])]
        + [str(item) for item in list(pytorch_mode.get("checkpoint_paths") or [])]
        + [str(item) for item in list(pytorch_mode.get("existing_onnx_artifacts") or [])]
        + [str(item) for item in list(pytorch_mode.get("existing_torchscript_artifacts") or [])]
    )
    config_review_paths = _dedupe(
        [str(item) for item in list(tensorflow_mode.get("config_paths") or [])]
        + [str(item) for item in list(pytorch_mode.get("config_paths") or [])]
    )
    config_review_commands = [_config_review_command(path) for path in config_review_paths[:6]]
    execution_entrypoints = _dedupe(
        [str(item) for item in list(tensorflow_mode.get("test_commands") or [])]
        + [str(item) for item in list(tensorflow_mode.get("training_commands") or [])]
        + [str(item) for item in list(tensorflow_mode.get("export_commands") or [])]
        + [str(item) for item in list(pytorch_mode.get("test_commands") or [])]
        + [str(item) for item in list(pytorch_mode.get("training_commands") or [])]
        + [str(item) for item in list(pytorch_mode.get("evaluation_commands") or [])]
        + [str(item) for item in list(pytorch_mode.get("inference_commands") or [])]
        + [str(item) for item in list(pytorch_mode.get("export_commands") or [])]
    )
    runtime_blockers = _dedupe(
        [str(item) for item in list(tensorflow_plan.get("blockers") or [])]
        + [str(item) for item in list(pytorch_runtime.get("blockers") or [])]
        + [str(item) for item in list(pytorch_plan.get("blockers") or [])]
    )
    validation_evidence_targets = _dedupe(
        [str(item) for item in list(tensorflow_plan.get("evidence_targets") or [])]
        + [str(item) for item in list(pytorch_plan.get("evidence_targets") or [])]
    )
    notebook_commands: list[str] = [
        f"jupyter nbconvert --to script {path}" for path in notebook_paths[:4]
    ]
    if "jupyter" in tooling_by_id and notebook_paths:
        tooling_by_id["jupyter"]["configured"] = True
        tooling_by_id["jupyter"]["status"] = "ready" if tooling_by_id["jupyter"]["installed"] else "needs_setup"
        tooling_by_id["jupyter"]["notes"] = _dedupe(
            list(tooling_by_id["jupyter"].get("notes") or [])
            + ["Notebook rescue is signaled by repo-owned notebook paths."]
        )[:6]
        tooling_by_id["jupyter"]["recommended_commands"] = notebook_commands[:4] or list(tooling_by_id["jupyter"].get("recommended_commands") or [])
    if "python" in tooling_by_id and (config_review_paths or artifact_paths):
        tooling_by_id["python"]["configured"] = True
        tooling_by_id["python"]["status"] = "ready" if tooling_by_id["python"]["installed"] else "needs_setup"
        tooling_by_id["python"]["notes"] = _dedupe(
            list(tooling_by_id["python"].get("notes") or [])
            + ["Python-backed review commands are needed for config or artifact inspection in this workspace."]
        )[:6]
    validation_commands = []
    if tooling_by_id["ruff"]["installed"] and (tooling_by_id["ruff"]["configured"] or repo_profile.get("python_repo")):
        validation_commands.extend(["ruff check .", "ruff format --check ."])
    if tooling_by_id["pre-commit"]["installed"] and tooling_by_id["pre-commit"]["configured"]:
        validation_commands.append("pre-commit run --all-files")
    if tooling_by_id["nox"]["installed"] and tooling_by_id["nox"]["configured"]:
        validation_commands.append("nox --list")
    if tooling_by_id["playwright"]["installed"] and tooling_by_id["playwright"]["configured"]:
        validation_commands.append("playwright test")
    if tensorflow_mode.get("enabled"):
        validation_commands.extend(
            str(step.get("command"))
            for step in list(tensorflow_plan.get("steps") or [])
            if step.get("type") in {"test", "train", "observability", "sanity"} and step.get("command")
        )
    if pytorch_mode.get("enabled"):
        validation_commands.extend(
            str(step.get("command"))
            for step in list(pytorch_plan.get("steps") or [])
            if step.get("type") in {"train", "eval", "inference", "observability", "checkpoint", "sanity"} and step.get("command")
        )
    if tooling_by_id["tensorboard"]["installed"] and tooling_by_id["tensorboard"]["configured"] and not _has_prefixed_command(
        validation_commands,
        ("tensorboard --logdir", "python -m tensorboard.main --logdir"),
    ):
        validation_commands.append("tensorboard --logdir logs")
    if tooling_by_id["uv"]["installed"] and repo_profile.get("python_repo"):
        validation_commands.insert(0, "uv run pytest")
    intake_commands = []
    if tooling_by_id["rg"]["installed"]:
        intake_commands.extend(["rg --files", "rg TODO ."])
    if tooling_by_id["tree-sitter"]["installed"]:
        intake_commands.append("tree-sitter parse <file>")
    security_commands = []
    if tooling_by_id["gitleaks"]["installed"]:
        security_commands.append("gitleaks dir . --redact")
    if tooling_by_id["osv-scanner"]["installed"] and repo_profile.get("lockfiles"):
        security_commands.append("osv-scanner --recursive .")
    if tooling_by_id["pip-audit"]["installed"] and repo_profile.get("python_repo"):
        security_commands.append("pip-audit")
    if tooling_by_id["trufflehog"]["installed"]:
        security_commands.append("trufflehog filesystem .")
    deployment_commands = []
    if tensorflow_mode.get("enabled"):
        deployment_commands.extend(
            str(step.get("command"))
            for step in list(tensorflow_plan.get("steps") or [])
            if step.get("type") == "export" and step.get("command")
        )
    if pytorch_mode.get("enabled"):
        deployment_commands.extend(str(step.get("command")) for step in list(pytorch_plan.get("steps") or []) if step.get("type") == "export" and step.get("command"))
    artifact_inspection_commands = _dedupe(
        [
            str(step.get("command"))
            for step in list(tensorflow_plan.get("steps") or [])
            if step.get("type") == "export" and step.get("command")
        ]
        + [
            str(step.get("command"))
            for step in list(pytorch_plan.get("steps") or [])
            if step.get("type") in {"checkpoint", "export"} and step.get("command")
        ]
    )
    if tooling_by_id["saved_model_cli"]["installed"] and tooling_by_id["saved_model_cli"]["configured"] and not _has_prefixed_command(
        deployment_commands,
        ("saved_model_cli show --dir",),
    ):
        deployment_commands.append("saved_model_cli show --dir <saved_model_dir> --all")
    if tooling_by_id["tflite_convert"]["installed"] and tooling_by_id["tflite_convert"]["configured"] and not _has_prefixed_command(
        deployment_commands,
        ("tflite_convert --saved_model_dir", "python -c "),
    ):
        deployment_commands.append("tflite_convert --saved_model_dir <saved_model_dir> --output_file model.tflite")
    if tooling_by_id["tfx"]["installed"] and tooling_by_id["tfx"]["configured"] and not _has_prefixed_command(
        deployment_commands,
        ("tfx pipeline list",),
    ):
        deployment_commands.append("tfx pipeline list")
    packs = [
        _pack_status(
            tools,
            ["rg", "tree-sitter", "uv", "nox", "pre-commit"],
            title="Codebase Intake Pack",
            summary="Repo search, symbol-aware intake, and workspace setup helpers.",
        ),
        _pack_status(
            tools,
            ["uv", "ruff", "pre-commit", "nox", "playwright"],
            title="Validation Evidence Pack",
            summary="Repo-native validation, formatting, session, and browser-test lanes.",
        ),
        _pack_status(
            tools,
            ["gitleaks", "trufflehog", "osv-scanner", "pip-audit"],
            title="Security Gate Pack",
            summary="Secrets and dependency security checks before handoff or release.",
        ),
        _pack_status(
            tools,
            ["tensorboard", "tfx", "saved_model_cli", "tflite_convert"],
            title="TensorFlow Product Pack",
            summary="TensorFlow training observability, production pipeline, export, and edge-delivery helpers.",
        ),
        _pack_status(
            tools,
            ["tensorboard", "wandb", "mlflow", "torchrun", "accelerate", "deepspeed"],
            title="PyTorch Training Pack",
            summary="PyTorch training, checkpoint, profiler, and distributed-readiness helpers.",
        ),
        _pack_status(
            tools,
            ["jupyter", "python"],
            title="Notebook Recovery Pack",
            summary="Promote notebook-only ML work into repo-owned scripts before validation evidence turns into folklore.",
        ),
        _pack_status(
            tools,
            ["python"],
            title="ML Config Audit Pack",
            summary="Review config-driven ML execution inputs directly instead of pretending the defaults ran themselves.",
        ),
        _pack_status(
            tools,
            ["python", "saved_model_cli", "tflite_convert", "tensorboard", "wandb", "mlflow"],
            title="Artifact Review Pack",
            summary="Inspect real model artifacts, checkpoints, and observability outputs before claiming deployment or reproducibility success.",
        ),
    ]
    recommended_next_steps: list[str] = []
    if tooling_by_id["uv"]["configured"] and not tooling_by_id["uv"]["installed"]:
        recommended_next_steps.append("Install uv so Mission Control can create isolated Python environments instead of freehanding your system interpreter.")
    if tooling_by_id["ruff"]["configured"] and not tooling_by_id["ruff"]["installed"]:
        recommended_next_steps.append("Install Ruff so Python lint and format checks can become a real validation gate.")
    if tooling_by_id["pre-commit"]["configured"] and not tooling_by_id["pre-commit"]["installed"]:
        recommended_next_steps.append("Install pre-commit so Mission Control can run the repo's declared hook contract before handoff.")
    if notebook_paths and not tooling_by_id["jupyter"]["installed"]:
        recommended_next_steps.append("Install Jupyter so notebook rescue commands can turn ad-hoc experiments into repo-owned scripts instead of oral history.")
    if (config_review_paths or artifact_paths) and not tooling_by_id["python"]["installed"]:
        recommended_next_steps.append("Install or expose a working Python CLI so config review and artifact inspection commands can run locally instead of remaining theoretical.")
    if tooling_by_id["accelerate"]["configured"] and not tooling_by_id["accelerate"]["installed"]:
        recommended_next_steps.append("Install Accelerate so Mission Control can validate the repo's actual PyTorch launcher path instead of pretending torchrun covers everything.")
    if tooling_by_id["deepspeed"]["configured"] and not tooling_by_id["deepspeed"]["installed"]:
        recommended_next_steps.append("Install DeepSpeed so Mission Control can run the repo's distributed training path instead of stopping at config-file archaeology.")
    if tooling_by_id["wandb"]["configured"] and not tooling_by_id["wandb"]["installed"]:
        recommended_next_steps.append("Install the Weights & Biases CLI so experiment-tracking evidence can be synced and inspected instead of hand-waved.")
    if tooling_by_id["mlflow"]["configured"] and not tooling_by_id["mlflow"]["installed"]:
        recommended_next_steps.append("Install MLflow so Mission Control can inspect experiment artifacts and tracking metadata without improvising.")
    if repo_profile.get("lockfiles") and not tooling_by_id["osv-scanner"]["installed"]:
        recommended_next_steps.append("Install OSV-Scanner to turn dependency-risk claims into an actual scan instead of optimistic storytelling.")
    if repo_profile.get("python_repo") and not tooling_by_id["pip-audit"]["installed"]:
        recommended_next_steps.append("Install pip-audit for Python-specific dependency auditing when release or security review matters.")
    if tensorflow_mode.get("enabled"):
        recommended_next_steps.extend(list(tensorflow_plan.get("recommended_fixes") or []))
    if pytorch_mode.get("enabled"):
        recommended_next_steps.extend(list(pytorch_plan.get("recommended_fixes") or []))
    if not recommended_next_steps:
        recommended_next_steps.append("The highest-value repo-native tooling lanes are already detectable from this workspace.")
    summary_parts = [
        f"Detected {sum(1 for tool in tools if tool['installed'])} installed helper CLIs",
        f"{sum(1 for tool in tools if tool['configured'])} workspace-signaled integrations",
    ]
    if notebook_paths:
        summary_parts.append(f"{len(notebook_paths)} notebook flow(s) need scriptable rescue")
    if artifact_paths:
        summary_parts.append(f"{len(artifact_paths)} artifact path(s) are ready for direct inspection")
    if config_review_paths:
        summary_parts.append(f"{len(config_review_paths)} config-driven path(s) detected")
    if runtime_blockers:
        summary_parts.append(f"{len(runtime_blockers)} runtime blocker(s) still need attention")
    if execution_entrypoints:
        summary_parts.append(f"{len(execution_entrypoints)} repo-owned execution path(s) are explicitly mapped")
    if intake_commands:
        summary_parts.append("fast intake ready")
    if validation_commands:
        summary_parts.append("validation evidence lane available")
    if security_commands:
        summary_parts.append("security gate lane available")
    if tensorflow_mode.get("enabled"):
        summary_parts.append("tensorflow product lane available")
    if pytorch_mode.get("enabled"):
        summary_parts.append("pytorch product lane available")
    summary = ". ".join(summary_parts).strip() + "."
    return {
        "project_name": project_name,
        "workspace_path": str(root),
        "available": True,
        "summary": summary,
        "repo_profile": repo_profile,
        "tools": tools,
        "packs": packs,
        "recommended_next_steps": recommended_next_steps[:8],
        "repo_mode_summaries": repo_mode_summaries[:4],
        "important_paths": important_paths[:12],
        "execution_entrypoints": execution_entrypoints[:12],
        "runtime_blockers": runtime_blockers[:8],
        "validation_evidence_targets": validation_evidence_targets[:12],
        "intake_commands": _dedupe(intake_commands)[:6],
        "notebook_paths": notebook_paths[:8],
        "notebook_commands": notebook_commands[:6],
        "validation_commands": _dedupe(validation_commands)[:8],
        "security_commands": _dedupe(security_commands)[:8],
        "deployment_commands": _dedupe(deployment_commands)[:8],
        "artifact_paths": artifact_paths[:8],
        "artifact_inspection_commands": artifact_inspection_commands[:8],
        "config_review_paths": config_review_paths[:8],
        "config_review_commands": config_review_commands[:6],
        "tensorflow_repo": tensorflow_mode,
        "tensorflow_validation_plan": tensorflow_plan,
        "pytorch_repo": pytorch_mode,
        "pytorch_runtime_status": pytorch_runtime,
        "pytorch_validation_plan": pytorch_plan,
    }
