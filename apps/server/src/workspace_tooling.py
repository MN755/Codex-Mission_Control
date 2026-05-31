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
        "workspace_tokens": ["torchrun", "torch.distributed", "accelerate", "deepspeed", "fsdp"],
        "notes": ["Distributed PyTorch launcher and readiness lane."],
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


def _which(command: str) -> str | None:
    return shutil.which(command)


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _package_json_package_names(root: Path) -> set[str]:
    package_json = root / "package.json"
    if not package_json.exists():
        return set()
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    deps = {}
    deps.update(dict(payload.get("dependencies") or {}))
    deps.update(dict(payload.get("devDependencies") or {}))
    return {str(name) for name in deps}


def _workspace_signal_haystack(root: Path) -> str:
    text_parts = [
        _safe_read_text(root / relative_name).lower()
        for relative_name in _PROJECT_TEXT_CANDIDATES
        if (root / relative_name).exists()
    ]
    for path in sorted(root.rglob("*")):
        if len(text_parts) >= 40:
            break
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".json", ".toml", ".yaml", ".yml"}:
            continue
        if any(part.startswith(".") and part not in {".github"} for part in path.relative_to(root).parts):
            continue
        text_parts.append(_safe_read_text(path).lower())
    return "\n".join(text_parts)


def _config_matches(root: Path, spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    matched_files: list[str] = []
    matched_sections: list[str] = []
    for relative_name in spec.get("config_files", []):
        candidate = root / relative_name
        if candidate.exists():
            matched_files.append(relative_name)
    pyproject_sections = list(spec.get("pyproject_sections", []))
    if pyproject_sections:
        pyproject = root / "pyproject.toml"
        text = _safe_read_text(pyproject).lower()
        for section in pyproject_sections:
            lowered = str(section).lower()
            if lowered and lowered in text:
                matched_sections.append(section)
    package_names = set(spec.get("package_names", []))
    if package_names:
        installed_names = _package_json_package_names(root)
        for name in sorted(package_names & installed_names):
            matched_files.append(f"package.json::{name}")
    workspace_tokens = [str(token).strip().lower() for token in spec.get("workspace_tokens", []) if str(token).strip()]
    if workspace_tokens:
        haystack = _workspace_signal_haystack(root)
        for token in workspace_tokens:
            if token in haystack:
                matched_sections.append(f"signal:{token}")
    return sorted(set(matched_files)), sorted(set(matched_sections))


def _repo_profile(root: Path) -> dict[str, Any]:
    try:
        files = {entry.name for entry in root.iterdir()} if root.exists() else set()
    except OSError:
        files = set()
    python_repo = any(name in files for name in _PYTHON_SIGNALS)
    node_repo = any(name in files for name in _NODE_SIGNALS)
    rust_repo = "Cargo.toml" in files
    go_repo = "go.mod" in files
    tensorflow_mode = detect_tensorflow_repo_mode(root)
    pytorch_mode = detect_pytorch_repo_mode(root)
    return {
        "python_repo": python_repo,
        "node_repo": node_repo,
        "rust_repo": rust_repo,
        "go_repo": go_repo,
        "lockfiles": sorted(name for name in _SECURITY_LOCKFILES if name in files),
        "tensorflow_repo": bool(tensorflow_mode.get("enabled")),
        "tensorflow_mode": tensorflow_mode.get("mode"),
        "tensorflow_frameworks": list(tensorflow_mode.get("frameworks") or []),
        "pytorch_repo": bool(pytorch_mode.get("enabled")),
        "pytorch_mode": pytorch_mode.get("mode"),
        "pytorch_frameworks": list(pytorch_mode.get("frameworks") or []),
    }


def _tool_signal_summary(tool_id: str, *, root: Path) -> dict[str, Any]:
    spec = _TOOL_SPECS[tool_id]
    binary_path = _which(tool_id)
    config_files, config_sections = _config_matches(root, spec)
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


def detect_workspace_tooling(workspace_path: str | Path | None, *, project_name: str | None = None) -> dict[str, Any]:
    if not workspace_path:
        return {
            "project_name": project_name,
            "workspace_path": None,
            "available": False,
            "summary": "Workspace tooling detection requires a valid local workspace path.",
            "repo_profile": {},
            "tools": [],
            "packs": [],
            "recommended_next_steps": ["Attach a real workspace before asking Mission Control to reason about repo-native tooling."],
            "intake_commands": [],
            "validation_commands": [],
            "security_commands": [],
        }
    try:
        root = resolve_local_path(workspace_path, must_exist=True, must_be_dir=True)
    except PathValidationError:
        return {
            "project_name": project_name,
            "workspace_path": str(workspace_path),
            "available": False,
            "summary": "Workspace tooling detection could not resolve the requested workspace path.",
            "repo_profile": {},
            "tools": [],
            "packs": [],
            "recommended_next_steps": ["Reattach the workspace with a valid local directory before running tooling discovery."],
            "intake_commands": [],
            "validation_commands": [],
            "security_commands": [],
        }
    repo_profile = _repo_profile(root)
    tools = [_tool_signal_summary(tool_id, root=root) for tool_id in _TOOL_SPECS]
    tooling_by_id = {tool["id"]: tool for tool in tools}
    tensorflow_mode = detect_tensorflow_repo_mode(root)
    tensorflow_plan = build_tensorflow_validation_plan(root)
    pytorch_mode = detect_pytorch_repo_mode(root)
    pytorch_runtime = detect_pytorch_runtime_status(root)
    pytorch_plan = build_pytorch_validation_plan(root)
    validation_commands = []
    if tooling_by_id["ruff"]["installed"] and (tooling_by_id["ruff"]["configured"] or repo_profile.get("python_repo")):
        validation_commands.extend(["ruff check .", "ruff format --check ."])
    if tooling_by_id["pre-commit"]["installed"] and tooling_by_id["pre-commit"]["configured"]:
        validation_commands.append("pre-commit run --all-files")
    if tooling_by_id["nox"]["installed"] and tooling_by_id["nox"]["configured"]:
        validation_commands.append("nox --list")
    if tooling_by_id["playwright"]["installed"] and tooling_by_id["playwright"]["configured"]:
        validation_commands.append("playwright test")
    if tooling_by_id["tensorboard"]["installed"] and tooling_by_id["tensorboard"]["configured"]:
        validation_commands.append("tensorboard --logdir logs")
    if pytorch_mode.get("enabled"):
        validation_commands.extend(str(step.get("command")) for step in list(pytorch_plan.get("steps") or []) if step.get("type") in {"train", "eval", "observability", "checkpoint"} and step.get("command"))
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
    if tooling_by_id["saved_model_cli"]["installed"] and tooling_by_id["saved_model_cli"]["configured"]:
        deployment_commands.append("saved_model_cli show --dir <saved_model_dir> --all")
    if tooling_by_id["tflite_convert"]["installed"] and tooling_by_id["tflite_convert"]["configured"]:
        deployment_commands.append("tflite_convert --saved_model_dir <saved_model_dir> --output_file model.tflite")
    if tooling_by_id["tfx"]["installed"] and tooling_by_id["tfx"]["configured"]:
        deployment_commands.append("tfx pipeline list")
    if pytorch_mode.get("enabled"):
        deployment_commands.extend(str(step.get("command")) for step in list(pytorch_plan.get("steps") or []) if step.get("type") == "export" and step.get("command"))
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
            ["tensorboard", "torchrun"],
            title="PyTorch Training Pack",
            summary="PyTorch training, checkpoint, profiler, and distributed-readiness helpers.",
        ),
    ]
    recommended_next_steps: list[str] = []
    if tooling_by_id["uv"]["configured"] and not tooling_by_id["uv"]["installed"]:
        recommended_next_steps.append("Install uv so Mission Control can create isolated Python environments instead of freehanding your system interpreter.")
    if tooling_by_id["ruff"]["configured"] and not tooling_by_id["ruff"]["installed"]:
        recommended_next_steps.append("Install Ruff so Python lint and format checks can become a real validation gate.")
    if tooling_by_id["pre-commit"]["configured"] and not tooling_by_id["pre-commit"]["installed"]:
        recommended_next_steps.append("Install pre-commit so Mission Control can run the repo's declared hook contract before handoff.")
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
        "intake_commands": intake_commands[:6],
        "validation_commands": validation_commands[:8],
        "security_commands": security_commands[:8],
        "deployment_commands": deployment_commands[:8],
        "tensorflow_repo": tensorflow_mode,
        "tensorflow_validation_plan": tensorflow_plan,
        "pytorch_repo": pytorch_mode,
        "pytorch_runtime_status": pytorch_runtime,
        "pytorch_validation_plan": pytorch_plan,
    }
