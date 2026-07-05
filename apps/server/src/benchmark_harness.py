from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import tempfile
import time
import hashlib
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

try:
    import pyarrow.dataset as pa_dataset
except Exception:  # noqa: BLE001
    pa_dataset = None


SUMMARY_VERSION = 1
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_OUTPUT_DIRNAME = "swe-bench-lite-runs"
DEFAULT_MAX_FILE_BYTES = 1_000_000
DEFAULT_VALIDATION_TIMEOUT_SECONDS = 300
DEFAULT_DATASET_SPLIT = "test"
DEFAULT_MAX_AUTO_TASK_STARTS = 16
LOCAL_PATH_PLACEHOLDER = "[local path omitted]"
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
NOISY_IDENTIFIER_REFERENCES = {
    "appdata",
    "error",
    "errors",
    "exception",
    "exceptions",
    "fail",
    "failed",
    "failure",
    "failures",
    "importerror",
    "license",
    "licenses",
    "stderr",
    "stdout",
    "temp",
    "tmp",
    "traceback",
    "users",
    "warning",
    "warnings",
}
IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".pytest_cache",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "mission-control",
    "node_modules",
    "venv",
}
TERMINAL_TASK_STATUSES = {"blocked", "completed", "done", "error", "failed", "needs_review", "stopped"}
COMPLETED_TASK_FLOW_STATUSES = {"completed", "done", "superseded"}
ACTIVE_TASK_STATUSES = {"assigned", "working", "waiting_on_paths"}
STARTABLE_TASK_STATUSES = {"assigned", "backlog", "waiting_on_paths"}
SENSITIVE_MANIFEST_FIELDS = {"gold_patch", "patch", "solution", "test_patch"}
NON_PATCH_ARTIFACT_PREFIXES = (
    ".pytest_cache/",
    "__pycache__/",
    "artifacts/",
    "mission-control/",
)
BENCHMARK_PROTECTED_PATHS_MANIFEST = "mission-control/benchmark-protected-paths.json"


def _task_has_superseded_waiting_reason(task: dict[str, Any]) -> bool:
    return "superseded after" in str(task.get("waiting_reason") or "").strip().lower()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")


def _short_evaluator_workspace_paths(output_dir: str | Path) -> tuple[Path, Path]:
    output_root = Path(output_dir).resolve()
    suffix = hashlib.sha1(output_root.as_posix().encode("utf-8")).hexdigest()[:10]
    temp_root = Path(tempfile.gettempdir()).resolve() / "mc-swe-eval" / suffix
    return temp_root / "ws", temp_root / "auth"


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return [stripped]
            if isinstance(decoded, list):
                return [str(item).strip() for item in decoded if str(item).strip()]
        return [line.strip() for line in stripped.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _coerce_patch_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value
        stripped = candidate.strip()
        if not stripped:
            return None
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                return candidate
            if isinstance(decoded, list):
                lines = [str(item) for item in decoded if str(item).strip()]
                return "\n".join(lines) if lines else None
        return candidate
    if isinstance(value, list):
        lines = [str(item) for item in value if str(item).strip()]
        return "\n".join(lines) if lines else None
    candidate = str(value)
    return candidate if candidate.strip() else None


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _resolve_path_text(path_text: str, *, base_dir: Path | None = None) -> Path:
    candidate = Path(path_text)
    if candidate.is_absolute():
        return candidate.resolve()
    anchor = base_dir or Path.cwd()
    return (anchor / candidate).resolve()


def _git_command_for_path(repo_root: str | Path, *args: str) -> list[str]:
    path_text = Path(repo_root).resolve().as_posix()
    return ["git", "-c", f"safe.directory={path_text}", *args]


def _safe_path_fragment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().strip("/\\")).strip("-")


def _repo_candidate_fragments(repo_name: str) -> list[str]:
    normalized = repo_name.strip().replace("\\", "/").strip("/")
    if not normalized:
        return []
    parts = [part.strip() for part in normalized.split("/") if part.strip()]
    leaf = parts[-1] if parts else normalized
    return _dedupe_strings(
        [
            normalized,
            normalized.replace("/", "__"),
            normalized.replace("/", "-"),
            normalized.replace("/", "_"),
            leaf,
            _safe_path_fragment(normalized),
        ]
    )


def _instance_candidate_fragments(instance_id: str) -> list[str]:
    return _dedupe_strings([instance_id, _safe_path_fragment(instance_id)])


def preferred_repo_dirname(repo_name: str | None, instance_id: str | None = None) -> str:
    normalized_repo = str(repo_name or "").strip().replace("\\", "/").strip("/")
    if normalized_repo:
        return normalized_repo.replace("/", "__")
    normalized_instance = _safe_path_fragment(str(instance_id or "repo"))
    return normalized_instance or "repo"


def _normalize_repo_path_map(
    payload: Any,
    *,
    base_dir: Path,
) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {"instances": {}, "repos": {}, "generic": {}}

    def store(bucket: str, key: Any, value: Any) -> None:
        text_key = str(key or "").strip()
        text_value = str(value or "").strip()
        if not text_key or not text_value:
            return
        mapping[bucket][text_key] = _resolve_path_text(text_value, base_dir=base_dir).as_posix()

    if isinstance(payload, dict):
        for alias, bucket in (("instances", "instances"), ("instance_ids", "instances"), ("repos", "repos"), ("repo_names", "repos")):
            bucket_payload = payload.get(alias)
            if not isinstance(bucket_payload, dict):
                continue
            for key, value in bucket_payload.items():
                store(bucket, key, value)
        for key, value in payload.items():
            if isinstance(value, str):
                store("generic", key, value)
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            path_value = item.get("path") or item.get("repo_path") or item.get("workspace_path")
            if item.get("instance_id"):
                store("instances", item.get("instance_id"), path_value)
            if item.get("repo"):
                store("repos", item.get("repo"), path_value)
            if item.get("key"):
                store("generic", item.get("key"), path_value)
    return mapping


def _load_repo_path_map(path: str | Path) -> dict[str, dict[str, str]]:
    repo_map_path = Path(path)
    decoded = json.loads(repo_map_path.read_text(encoding="utf-8"))
    return _normalize_repo_path_map(decoded, base_dir=repo_map_path.resolve().parent)


def _resolve_repo_path_for_record(
    record: dict[str, Any],
    *,
    instance_id: str,
    manifest_path: Path | None = None,
    prepared_repos_root: str | Path | None = None,
    repo_path_map: dict[str, dict[str, str]] | None = None,
) -> str:
    manifest_dir = manifest_path.resolve().parent if manifest_path is not None else Path.cwd()
    explicit_repo_path = str(
        record.get("repo_path")
        or record.get("workspace_path")
        or record.get("prepared_repo_path")
        or record.get("local_repo_path")
        or ""
    ).strip()
    if explicit_repo_path:
        return _resolve_path_text(explicit_repo_path, base_dir=manifest_dir).as_posix()

    repo_name = str(record.get("repo") or record.get("repo_name") or "").strip()
    if repo_path_map:
        for bucket, key in (
            ("instances", instance_id),
            ("repos", repo_name),
            ("generic", instance_id),
            ("generic", repo_name),
        ):
            if key and repo_path_map.get(bucket, {}).get(key):
                return str(repo_path_map[bucket][key])

    if prepared_repos_root:
        root = _resolve_path_text(str(prepared_repos_root), base_dir=manifest_dir)
        checked: list[str] = []
        candidate_fragments = _dedupe_strings(
            [preferred_repo_dirname(repo_name, instance_id)]
            + _instance_candidate_fragments(instance_id)
            + _repo_candidate_fragments(repo_name)
        )
        for fragment in candidate_fragments:
            candidate = (root / fragment).resolve()
            checked.append(candidate.as_posix())
            if candidate.exists():
                return candidate.as_posix()
        if candidate_fragments:
            return (root / candidate_fragments[0]).resolve().as_posix()
        preview = ", ".join(checked[:8]) if checked else root.as_posix()
        raise ValueError(
            f"Task {instance_id} is missing repo_path/workspace_path and no prepared repo matched under "
            f"{root.as_posix()}. Checked: {preview}"
        )

    raise ValueError(
        f"Task {instance_id} is missing repo_path/workspace_path. Supply repo_path, --prepared-repos-root, or --repo-map."
    )


def stage_workspace_snapshot(
    source_repo_path: str | Path,
    destination: str | Path,
    *,
    base_commit: str | None = None,
    git_timeout_seconds: int = 120,
) -> list[str]:
    source = Path(source_repo_path).resolve()
    target = Path(destination).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Repo path does not exist: {source}")
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    source_git_dir = source / ".git"
    if source_git_dir.exists():
        clone_command = [
            "git",
            "-c",
            f"safe.directory={source.as_posix()}",
            "-c",
            f"safe.directory={source_git_dir.as_posix()}",
            "clone",
            "--local",
            source.as_posix(),
            target.as_posix(),
        ]
        completed = subprocess.run(
            clone_command,
            cwd=str(target.parent),
            capture_output=True,
            text=True,
            timeout=git_timeout_seconds,
            check=False,
        )
        notes.append(f"$ {' '.join(clone_command)}")
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"Failed to clone staged workspace from {source.as_posix()}: {' '.join(clone_command)} -> "
                f"{completed.returncode} {stderr}"
            )
    else:
        shutil.copytree(source, target, symlinks=True)

    if not base_commit:
        return notes

    git_dir = target / ".git"
    if not git_dir.exists():
        notes.append("Base commit provided, but prepared repo snapshot has no .git directory; workspace used as-is.")
        return notes

    notes.extend(checkout_workspace_commit(target, base_commit, git_timeout_seconds=git_timeout_seconds, clean=True))
    return notes


def checkout_workspace_commit(
    workspace_root: str | Path,
    commit: str | None,
    *,
    git_timeout_seconds: int = 120,
    clean: bool = False,
) -> list[str]:
    target = Path(workspace_root).resolve()
    normalized_commit = str(commit or "").strip()
    if not normalized_commit:
        return []
    git_dir = target / ".git"
    if not git_dir.exists():
        raise FileNotFoundError(f"Workspace has no .git directory: {target}")
    notes: list[str] = []
    commands = [_git_command_for_path(target, "checkout", "--force", normalized_commit)]
    if clean:
        commands.append(_git_command_for_path(target, "clean", "-fdx"))
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=git_timeout_seconds,
            check=False,
        )
        notes.append(f"$ {' '.join(command)}")
        if completed.returncode == 0:
            continue
        stderr = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"Failed to switch staged workspace to commit {normalized_commit}: {' '.join(command)} -> "
            f"{completed.returncode} {stderr}"
        )
    return notes


def default_output_root(repo_root: Path) -> Path:
    return (repo_root / "Tests" / DEFAULT_OUTPUT_DIRNAME).resolve()


def ollama_available_models(*, timeout_seconds: int = 20) -> list[str]:
    try:
        completed = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if completed.returncode != 0:
        return []
    lines = [line.rstrip() for line in (completed.stdout or "").splitlines() if line.strip()]
    if not lines:
        return []
    models: list[str] = []
    for line in lines[1:]:
        name = line.split()[0].strip()
        if name:
            models.append(name)
    return models


def benchmark_preflight(config: "HarnessRunConfig", *, available_models: list[str] | None = None) -> dict[str, Any]:
    manager_model, worker_model = config.normalized_models()
    model_requirements = sorted({manager_model, worker_model})
    blockers: list[str] = []
    notes: list[str] = []
    ollama_models = list(available_models) if available_models is not None else ollama_available_models()
    if config.provider == "ollama":
        if not ollama_models:
            blockers.append("ollama_unavailable_or_no_models")
        else:
            missing_models = [model for model in model_requirements if model not in ollama_models]
            if config.strict_model and missing_models:
                blockers.extend(f"missing_exact_model:{model}" for model in missing_models)
            elif missing_models:
                notes.append(
                    "Some requested models are not installed locally. Non-strict mode may still attempt a weaker or alternate local model."
                )
    adapter_command = str(config.adapter_command or "").strip()
    if adapter_command and not Path(adapter_command).exists():
        notes.append("Custom adapter command path does not exist as a local file. It may still resolve via PATH at runtime.")
    task_audit: dict[str, Any] | None = None
    manifest_path = str(config.tasks_path or "").strip()
    if manifest_path:
        try:
            tasks = load_task_manifest(
                manifest_path,
                dataset_split=config.dataset_split,
                prepared_repos_root=config.prepared_repos_root or config.repo_cache_root,
                repo_map_path=config.repo_map_path,
            )
            selected_tasks = select_tasks(
                tasks,
                start_index=config.start_index,
                max_tasks=config.max_tasks,
                task_ids=config.task_ids,
            )
            task_audit = audit_task_readiness(selected_tasks)
            blockers.extend(str(item) for item in list(task_audit.get("blockers") or []) if str(item).strip())
            notes.extend(str(item) for item in list(task_audit.get("notes") or []) if str(item).strip())
        except Exception as exc:  # noqa: BLE001
            blockers.append(f"manifest_load_failed:{type(exc).__name__}")
            notes.append(str(exc))
    return {
        "provider": config.provider,
        "strict_model": config.strict_model,
        "requested_models": model_requirements,
        "available_ollama_models": ollama_models,
        "blockers": _dedupe_strings(blockers),
        "notes": _dedupe_strings(notes),
        "task_audit": task_audit,
        "ready": not blockers,
    }


@dataclass(slots=True)
class BenchmarkTaskSpec:
    instance_id: str
    problem_statement: str
    repo_path: str
    repo_name: str | None = None
    base_commit: str | None = None
    hints_text: str | None = None
    validation_commands: list[str] = field(default_factory=list)
    fail_to_pass: list[str] = field(default_factory=list)
    pass_to_pass: list[str] = field(default_factory=list)
    setup_commands: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    test_patch: str | None = field(default=None, repr=False)

    @classmethod
    def from_record(
        cls,
        record: dict[str, Any],
        *,
        manifest_path: Path | None = None,
        prepared_repos_root: str | Path | None = None,
        repo_path_map: dict[str, dict[str, str]] | None = None,
    ) -> "BenchmarkTaskSpec":
        instance_id = str(
            record.get("instance_id")
            or record.get("id")
            or record.get("task_id")
            or record.get("name")
            or ""
        ).strip()
        if not instance_id:
            raise ValueError("Task record is missing instance_id/id/task_id.")
        repo_path = _resolve_repo_path_for_record(
            record,
            instance_id=instance_id,
            manifest_path=manifest_path,
            prepared_repos_root=prepared_repos_root,
            repo_path_map=repo_path_map,
        )
        problem_statement = str(
            record.get("problem_statement")
            or record.get("issue_text")
            or record.get("prompt")
            or record.get("problem")
            or ""
        ).strip()
        if not problem_statement:
            raise ValueError(f"Task {instance_id} is missing problem_statement/issue_text.")
        nested_metadata = record.get("metadata")
        metadata = dict(nested_metadata) if isinstance(nested_metadata, dict) else {}
        metadata.update(
            {
                key: value
                for key, value in record.items()
                if key not in SENSITIVE_MANIFEST_FIELDS and key != "metadata"
            }
        )
        return cls(
            instance_id=instance_id,
            problem_statement=problem_statement,
            repo_path=repo_path,
            repo_name=str(record.get("repo") or record.get("repo_name") or "").strip() or None,
            base_commit=str(record.get("base_commit") or "").strip() or None,
            hints_text=str(record.get("hints_text") or record.get("hints") or "").strip() or None,
            validation_commands=_coerce_string_list(
                record.get("validation_commands") or record.get("test_command") or record.get("test_cmd")
            ),
            fail_to_pass=_coerce_string_list(record.get("FAIL_TO_PASS") or record.get("fail_to_pass")),
            pass_to_pass=_coerce_string_list(record.get("PASS_TO_PASS") or record.get("pass_to_pass")),
            setup_commands=_coerce_string_list(record.get("setup_commands") or record.get("setupCommands")),
            metadata=metadata,
            test_patch=_coerce_patch_text(record.get("test_patch")),
        )

    def to_dict(self, *, include_sensitive: bool = False) -> dict[str, Any]:
        payload = _json_ready(asdict(self))
        if not include_sensitive:
            payload.pop("test_patch", None)
        return payload

    def with_sensitive_payload(self, payload: dict[str, Any] | None) -> "BenchmarkTaskSpec":
        return replace(self, test_patch=_coerce_patch_text((payload or {}).get("test_patch")))

    def sensitive_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.test_patch:
            payload["test_patch"] = self.test_patch
        return _json_ready(payload)


@dataclass(slots=True)
class HarnessRunConfig:
    tasks_path: str
    output_root: str
    run_label: str
    dataset_split: str = DEFAULT_DATASET_SPLIT
    model: str = DEFAULT_MODEL
    manager_model: str | None = None
    worker_model: str | None = None
    provider: str = "ollama"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "never"
    manager_reasoning_effort: str = "medium"
    worker_reasoning_effort: str = "medium"
    poll_interval_seconds: float = 2.0
    task_timeout_seconds: int = 900
    idle_timeout_seconds: int = 90
    validation_timeout_seconds: int = DEFAULT_VALIDATION_TIMEOUT_SECONDS
    max_task_attempts: int = 2
    max_auto_task_starts: int = DEFAULT_MAX_AUTO_TASK_STARTS
    swarm_max_agents: int = 4
    enable_swarm_planning: bool = False
    auto_answer_pending_decisions: bool = True
    auto_approve_commands: bool = False
    preserve_workspace: bool = True
    strict_model: bool = True
    start_index: int = 0
    max_tasks: int | None = None
    task_ids: list[str] = field(default_factory=list)
    prepared_repos_root: str | None = None
    repo_map_path: str | None = None
    repo_cache_root: str | None = None
    auto_prepare_repos: bool = False
    adapter_command: str | None = None
    adapter_args: list[str] = field(default_factory=list)

    def normalized_models(self) -> tuple[str, str]:
        manager = (self.manager_model or self.model).strip() or DEFAULT_MODEL
        worker = (self.worker_model or self.model).strip() or DEFAULT_MODEL
        return manager, worker

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HarnessRunConfig":
        adapter_args = payload.get("adapter_args")
        return cls(
            tasks_path=str(payload.get("tasks_path") or ""),
            output_root=str(payload.get("output_root") or ""),
            run_label=str(payload.get("run_label") or "manual-run"),
            dataset_split=str(payload.get("dataset_split") or DEFAULT_DATASET_SPLIT),
            model=str(payload.get("model") or DEFAULT_MODEL),
            manager_model=str(payload.get("manager_model") or "").strip() or None,
            worker_model=str(payload.get("worker_model") or "").strip() or None,
            provider=str(payload.get("provider") or "ollama"),
            sandbox_mode=str(payload.get("sandbox_mode") or "workspace-write"),
            approval_policy=str(payload.get("approval_policy") or "never"),
            manager_reasoning_effort=str(payload.get("manager_reasoning_effort") or "medium"),
            worker_reasoning_effort=str(payload.get("worker_reasoning_effort") or "medium"),
            poll_interval_seconds=float(payload.get("poll_interval_seconds") or 2.0),
            task_timeout_seconds=int(payload.get("task_timeout_seconds") or 900),
            idle_timeout_seconds=int(payload.get("idle_timeout_seconds") or 90),
            validation_timeout_seconds=int(payload.get("validation_timeout_seconds") or DEFAULT_VALIDATION_TIMEOUT_SECONDS),
            max_task_attempts=max(int(payload.get("max_task_attempts") or 2), 1),
            max_auto_task_starts=int(payload.get("max_auto_task_starts") or DEFAULT_MAX_AUTO_TASK_STARTS),
            swarm_max_agents=int(payload.get("swarm_max_agents") or 4),
            enable_swarm_planning=bool(payload.get("enable_swarm_planning", False)),
            auto_answer_pending_decisions=bool(payload.get("auto_answer_pending_decisions", True)),
            auto_approve_commands=bool(payload.get("auto_approve_commands", False)),
            preserve_workspace=bool(payload.get("preserve_workspace", True)),
            strict_model=bool(payload.get("strict_model", True)),
            start_index=max(int(payload.get("start_index") or 0), 0),
            max_tasks=int(payload["max_tasks"]) if payload.get("max_tasks") is not None else None,
            task_ids=_coerce_string_list(payload.get("task_ids")),
            prepared_repos_root=str(payload.get("prepared_repos_root") or "").strip() or None,
            repo_map_path=str(payload.get("repo_map_path") or "").strip() or None,
            repo_cache_root=str(payload.get("repo_cache_root") or "").strip() or None,
            auto_prepare_repos=bool(payload.get("auto_prepare_repos", False)),
            adapter_command=str(payload.get("adapter_command") or "").strip() or None,
            adapter_args=_coerce_string_list(adapter_args),
        )


@dataclass(slots=True)
class ValidationCommandResult:
    command: str
    returncode: int | None
    timed_out: bool
    runtime_seconds: float
    stdout_path: str
    stderr_path: str

    def to_dict(self) -> dict[str, Any]:
        return _json_ready(asdict(self))


@dataclass(slots=True)
class PostRunValidationSummary:
    attempted: bool
    succeeded: bool
    commands: list[str] = field(default_factory=list)
    results: list[ValidationCommandResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    test_patch_applied: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["results"] = [item.to_dict() for item in self.results]
        return _json_ready(payload)


@dataclass(slots=True)
class BenchmarkTaskResult:
    instance_id: str
    repo_name: str | None
    status: str
    attempted: bool
    completed: bool
    resolved: bool
    patch_applied: bool
    validation_succeeded: bool
    failure_category: str | None
    runtime_seconds: float
    changed_files: list[str] = field(default_factory=list)
    validation_commands: list[str] = field(default_factory=list)
    validation_results: list[ValidationCommandResult] = field(default_factory=list)
    worker_validation_commands: list[str] = field(default_factory=list)
    worker_validation_results: list[ValidationCommandResult] = field(default_factory=list)
    observed_commands: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    model_settings: dict[str, Any] = field(default_factory=dict)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    task_summary: str | None = None
    retry_count: int = 0
    unblock_task_count: int = 0
    manager_parse_failures: int = 0
    event_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["validation_results"] = [item.to_dict() for item in self.validation_results]
        payload["worker_validation_results"] = [item.to_dict() for item in self.worker_validation_results]
        return _json_ready(payload)


def _load_json_if_exists(path: str | Path) -> Any | None:
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def recover_git_changed_files(workspace_path: str | Path) -> list[str]:
    workspace = Path(workspace_path)
    if not workspace.exists():
        return []
    try:
        completed = subprocess.run(
            _git_command_for_path(workspace, "status", "--porcelain"),
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    changed_files: list[str] = []
    for line in (completed.stdout or "").splitlines():
        entry = line.rstrip()
        if len(entry) < 4:
            continue
        path_text = entry[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        normalized = path_text.replace("\\", "/")
        if normalized:
            changed_files.append(normalized)
    return meaningful_patch_paths(_dedupe_strings(changed_files))


def recover_timeout_task_result(
    task: BenchmarkTaskSpec,
    config: HarnessRunConfig,
    task_output_dir: str | Path,
    *,
    note: str = "Harness worker subprocess timed out before returning a result.",
    workspace_path_override: str | Path | None = None,
) -> BenchmarkTaskResult | None:
    task_root = Path(task_output_dir)
    snapshot_root = task_root / "runtime-snapshots"
    tasks = _load_json_if_exists(snapshot_root / "latest-tasks.json")
    agents = _load_json_if_exists(snapshot_root / "latest-agents.json")
    events = _load_json_if_exists(snapshot_root / "latest-events.json")
    pending_decisions = _load_json_if_exists(snapshot_root / "latest-pending-decisions.json")
    pending_approvals = _load_json_if_exists(snapshot_root / "latest-pending-approvals.json")
    meta = _load_json_if_exists(snapshot_root / "latest-meta.json")
    if not isinstance(tasks, list) and not isinstance(agents, list) and not isinstance(events, list):
        return None

    normalized_tasks = list(tasks or []) if isinstance(tasks, list) else []
    normalized_agents = list(agents or []) if isinstance(agents, list) else []
    normalized_events = list(events or []) if isinstance(events, list) else []
    normalized_decisions = list(pending_decisions or []) if isinstance(pending_decisions, list) else []
    normalized_approvals = list(pending_approvals or []) if isinstance(pending_approvals, list) else []
    workspace_path = Path(workspace_path_override).resolve() if workspace_path_override else (task_root / "workspace")
    validation_commands = (
        detect_validation_commands(
            workspace_path,
            task.validation_commands,
            fail_to_pass=task.fail_to_pass,
            pass_to_pass=task.pass_to_pass,
        )
        if workspace_path.exists()
        else list(task.validation_commands or [])
    )
    validation_payload = _load_json_if_exists(task_root / "validation-results.json")
    validation_results = [
        ValidationCommandResult(
            command=str(item.get("command") or ""),
            returncode=item.get("returncode"),
            timed_out=bool(item.get("timed_out")),
            runtime_seconds=float(item.get("runtime_seconds") or 0.0),
            stdout_path=str(item.get("stdout_path") or ""),
            stderr_path=str(item.get("stderr_path") or ""),
        )
        for item in list(validation_payload or [])
        if isinstance(item, dict)
    ] if isinstance(validation_payload, list) else []
    run_analysis = analyze_task_execution(normalized_tasks, normalized_events, normalized_agents)
    task_statuses = [str(item.get("status") or "") for item in normalized_tasks if isinstance(item, dict)]
    changed_files = recover_git_changed_files(workspace_path)
    candidate_changed_files, skipped_protected_files = filter_benchmark_protected_changed_files(
        changed_files,
        task.test_patch,
    )
    patch_applied = bool(candidate_changed_files)
    final_validation_commands = list(validation_commands)
    final_validation_results = list(validation_results)
    evaluator_artifact_paths: dict[str, str] = {}
    notes = [note, "Recovered partial task state from runtime snapshots after subprocess timeout."]
    if task.test_patch and workspace_path.exists() and patch_applied:
        try:
            evaluator_summary = run_evaluator_validation(
                task,
                workspace_path,
                candidate_changed_files,
                task_root / "evaluator",
                timeout_seconds=config.validation_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Evaluator replay failed during timeout recovery: {type(exc).__name__}: {exc}")
        else:
            final_validation_commands = list(evaluator_summary.commands)
            final_validation_results = list(evaluator_summary.results)
            evaluator_artifact_paths = dict(evaluator_summary.artifact_paths)
    validation_attempted = bool(final_validation_results)
    validation_succeeded = patch_applied and bool(final_validation_results) and all(
        not item.timed_out and item.returncode == 0 for item in final_validation_results
    )
    if validation_attempted and not patch_applied:
        notes.append(
            "Validation passed during timeout recovery, but no candidate source patch was detected, so this is not counted as candidate validation success."
        )
    completed = task_flow_completed(task_statuses, timed_out=False)
    active_task_count = int(run_analysis.get("active_task_count") or 0)
    deadlock_reason = str((meta or {}).get("deadlock_reason") or "").strip() if isinstance(meta, dict) else ""
    orchestration_deadlocked = (
        not completed
        and bool(normalized_tasks)
        and active_task_count == 0
        and not normalized_decisions
        and not normalized_approvals
    )
    if completed:
        orchestration_deadlocked = False
        deadlock_reason = ""
    runner_failed = any(int(agent.get("failure_count") or 0) > 0 for agent in normalized_agents if isinstance(agent, dict))
    failure_category = classify_failure_category(
        timed_out=not orchestration_deadlocked and not completed,
        setup_failed=False,
        orchestration_deadlocked=orchestration_deadlocked,
        patch_applied=patch_applied,
        runner_failed=runner_failed,
        validation_attempted=validation_attempted,
        validation_succeeded=validation_succeeded,
        pending_approvals=len(normalized_approvals),
        pending_decisions=len(normalized_decisions),
        tasks_generated=len(normalized_tasks),
        task_statuses=task_statuses,
        manager_parse_failures=int(run_analysis.get("manager_parse_failures") or 0),
        retry_count=int(run_analysis.get("retry_count") or 0),
        unblock_task_count=int(run_analysis.get("unblock_task_count") or 0),
    )
    resolved = patch_applied and validation_succeeded
    if resolved:
        failure_category = None
    status = "resolved_with_open_tasks" if resolved and not completed else ("resolved" if resolved else failure_category or ("completed" if completed else "unresolved"))
    if deadlock_reason:
        notes.append(f"Recovered deadlock reason: {deadlock_reason}")
    notes.extend(str(item) for item in run_analysis.get("notes") or [] if str(item).strip())
    if skipped_protected_files:
        notes.append(
            "Ignored candidate edits that overlapped the authoritative SWE-bench test_patch when recovering the evaluator replay."
        )
    if validation_attempted and not patch_applied:
        if all(not item.timed_out and item.returncode == 0 for item in final_validation_results):
            notes.append(
                "Validation commands passed, but no accepted candidate workspace edits were recorded, so the run was not counted as validation success."
            )
        else:
            notes.append(
                "Validation commands ran, but no accepted candidate workspace edits were recorded, so the run could not count as validation success."
            )
    if task.test_patch and patch_applied:
        evaluator_summary_path = task_root / "evaluator" / "summary.json"
        evaluator_payload = _load_json_if_exists(evaluator_summary_path)
        if isinstance(evaluator_payload, dict):
            notes.extend(str(item) for item in list(evaluator_payload.get("notes") or []) if str(item).strip())
    return BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status=status,
        attempted=bool(normalized_tasks),
        completed=completed,
        resolved=resolved,
        patch_applied=patch_applied,
        validation_succeeded=validation_succeeded,
        failure_category=failure_category,
        runtime_seconds=float(config.task_timeout_seconds + config.validation_timeout_seconds + 120),
        changed_files=candidate_changed_files,
        validation_commands=final_validation_commands,
        validation_results=final_validation_results,
        worker_validation_commands=validation_commands,
        worker_validation_results=validation_results,
        observed_commands=list(final_validation_commands),
        notes=notes,
        model_settings={"provider": config.provider, "model": config.model},
        artifact_paths={
            "task_output_dir": task_root.as_posix(),
            "trajectory_path": (task_root / "trajectory.jsonl").as_posix(),
            "workspace_path": workspace_path.as_posix(),
            "runtime_snapshot_dir": snapshot_root.as_posix(),
            **evaluator_artifact_paths,
        },
        retry_count=int(run_analysis.get("retry_count") or 0),
        unblock_task_count=int(run_analysis.get("unblock_task_count") or 0),
        manager_parse_failures=int(run_analysis.get("manager_parse_failures") or 0),
        event_counts=dict(run_analysis.get("event_counts") or {}),
    )


def _load_parquet_records(path: str | Path, *, dataset_split: str = DEFAULT_DATASET_SPLIT) -> list[dict[str, Any]]:
    if pa_dataset is None:
        raise RuntimeError("pyarrow is required to read SWE-bench parquet files. Install pyarrow locally first.")
    manifest_path = Path(path)
    if manifest_path.is_dir():
        data_root = manifest_path / "data"
        search_root = data_root if data_root.exists() else manifest_path
        matches = sorted(search_root.glob(f"{dataset_split}-*.parquet"))
        if not matches:
            raise FileNotFoundError(
                f"Could not find parquet files for split '{dataset_split}' under {search_root.as_posix()}."
            )
        dataset = pa_dataset.dataset([item.as_posix() for item in matches], format="parquet")
        return list(dataset.to_table().to_pylist())
    if manifest_path.suffix.lower() == ".parquet":
        dataset = pa_dataset.dataset(manifest_path.as_posix(), format="parquet")
        return list(dataset.to_table().to_pylist())
    raise ValueError(f"Unsupported parquet source: {manifest_path.as_posix()}")


def load_task_manifest(
    path: str | Path,
    *,
    dataset_split: str = DEFAULT_DATASET_SPLIT,
    prepared_repos_root: str | Path | None = None,
    repo_map_path: str | Path | None = None,
) -> list[BenchmarkTaskSpec]:
    manifest_path = Path(path)
    if manifest_path.is_dir() or manifest_path.suffix.lower() == ".parquet":
        records = _load_parquet_records(manifest_path, dataset_split=dataset_split)
    else:
        raw = manifest_path.read_text(encoding="utf-8")
        if manifest_path.suffix.lower() == ".jsonl":
            records = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            decoded = json.loads(raw)
            if isinstance(decoded, dict) and isinstance(decoded.get("tasks"), list):
                records = decoded["tasks"]
            elif isinstance(decoded, list):
                records = decoded
            else:
                raise ValueError("Manifest must be a JSON array, a {\"tasks\": [...]} object, JSONL, a parquet file, or a SWE-bench dataset directory.")
    repo_path_map = _load_repo_path_map(repo_map_path) if repo_map_path else None
    return [
        BenchmarkTaskSpec.from_record(
            dict(record),
            manifest_path=manifest_path,
            prepared_repos_root=prepared_repos_root,
            repo_path_map=repo_path_map,
        )
        for record in records
    ]


def _git_commit_is_available(repo_root: str | Path, commit: str, *, timeout_seconds: int = 30) -> tuple[bool, str | None]:
    completed = subprocess.run(
        _git_command_for_path(repo_root, "rev-parse", "--verify", f"{commit}^{{commit}}"),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode == 0:
        return True, None
    message = (completed.stderr or completed.stdout or "").strip() or f"git rev-parse exited with {completed.returncode}"
    return False, message


def audit_task_readiness(tasks: list[BenchmarkTaskSpec]) -> dict[str, Any]:
    blockers: list[str] = []
    notes: list[str] = []
    duplicates = sorted([instance_id for instance_id, count in Counter(task.instance_id for task in tasks).items() if count > 1])
    task_reports: list[dict[str, Any]] = []
    missing_repo_count = 0
    missing_base_commit_count = 0
    no_validation_count = 0

    if not tasks:
        blockers.append("no_tasks_selected")
    for instance_id in duplicates:
        blockers.append(f"duplicate_instance_id:{instance_id}")

    for task in tasks:
        task_notes: list[str] = []
        task_blockers: list[str] = []
        repo_root = Path(task.repo_path)
        repo_exists = repo_root.exists()
        repo_has_git = (repo_root / ".git").exists() if repo_exists else False
        base_commit_ready: bool | None = None
        validation_commands: list[str] = []

        if not repo_exists:
            missing_repo_count += 1
            task_blockers.append("missing_repo")
            blockers.append(f"missing_repo:{task.instance_id}")
        else:
            validation_commands = detect_validation_commands(
                repo_root,
                task.validation_commands,
                fail_to_pass=task.fail_to_pass,
                pass_to_pass=task.pass_to_pass,
            )
            if task.base_commit:
                if not repo_has_git:
                    task_notes.append("base_commit_not_verifiable_no_git")
                    notes.append(f"Task {task.instance_id} has base_commit {task.base_commit} but prepared repo has no .git metadata.")
                else:
                    base_commit_ready, commit_error = _git_commit_is_available(repo_root, task.base_commit)
                    if not base_commit_ready:
                        missing_base_commit_count += 1
                        task_blockers.append("missing_base_commit")
                        task_notes.append(f"base_commit_lookup_failed:{commit_error}")
                        blockers.append(f"missing_base_commit:{task.instance_id}")
        if repo_exists and not validation_commands:
            no_validation_count += 1
            task_notes.append("no_validation_detected")
            notes.append(f"Task {task.instance_id} has no explicit or detectable validation command.")

        task_reports.append(
            {
                "instance_id": task.instance_id,
                "repo_name": task.repo_name,
                "repo_path": repo_root.resolve().as_posix() if repo_exists else task.repo_path,
                "repo_exists": repo_exists,
                "repo_has_git": repo_has_git,
                "base_commit": task.base_commit,
                "base_commit_ready": base_commit_ready,
                "validation_commands": validation_commands,
                "blockers": task_blockers,
                "notes": task_notes,
            }
        )

    return {
        "task_count": len(tasks),
        "duplicate_instance_ids": duplicates,
        "missing_repo_count": missing_repo_count,
        "missing_base_commit_count": missing_base_commit_count,
        "no_validation_count": no_validation_count,
        "blockers": _dedupe_strings(blockers),
        "notes": _dedupe_strings(notes),
        "tasks": task_reports,
        "ready": not blockers,
    }


def select_tasks(
    tasks: list[BenchmarkTaskSpec],
    *,
    start_index: int = 0,
    max_tasks: int | None = None,
    task_ids: list[str] | None = None,
) -> list[BenchmarkTaskSpec]:
    selected = list(tasks)
    requested_ids = [item.strip() for item in list(task_ids or []) if item.strip()]
    if requested_ids:
        requested_set = set(requested_ids)
        selected = [task for task in selected if task.instance_id in requested_set]
    if start_index > 0:
        selected = selected[start_index:]
    if max_tasks is not None:
        selected = selected[:max_tasks]
    return selected


def _pytest_target_file(node_id: str) -> str | None:
    candidate = str(node_id or "").strip()
    if not candidate:
        return None
    path_text = candidate.split("::", 1)[0].strip()
    if not path_text:
        return None
    normalized = path_text.replace("\\", "/")
    if normalized.endswith(".py"):
        return normalized
    return None


def _django_test_target(node_id: str) -> str | None:
    candidate = str(node_id or "").strip()
    if not candidate:
        return None
    match = re.match(r"^([A-Za-z0-9_]+)\s+\(([A-Za-z0-9_.]+)\)$", candidate)
    if match is not None:
        test_name = str(match.group(1) or "").strip()
        dotted_owner = str(match.group(2) or "").strip()
        if test_name and dotted_owner:
            return f"{dotted_owner}.{test_name}"
    if " " not in candidate and "(" not in candidate and ")" not in candidate and candidate.count(".") >= 2:
        return candidate
    return None


def _parse_django_target_parts(node_id: str) -> tuple[str, str | None, str | None] | None:
    candidate = str(node_id or "").strip()
    if not candidate:
        return None
    match = re.match(r"^([A-Za-z0-9_]+)\s+\(([A-Za-z0-9_.]+)\)$", candidate)
    if match is not None:
        test_name = str(match.group(1) or "").strip() or None
        dotted_owner = str(match.group(2) or "").strip()
        owner_parts = [part for part in dotted_owner.split(".") if part]
        if len(owner_parts) >= 2:
            return ".".join(owner_parts[:-1]), owner_parts[-1], test_name
        return dotted_owner, None, test_name
    if " " in candidate or "(" in candidate or ")" in candidate:
        return None
    parts = [part for part in candidate.split(".") if part]
    if len(parts) < 2:
        return None
    if len(parts) >= 3 and parts[-1].startswith("test_") and parts[-2][:1].isupper():
        return ".".join(parts[:-2]), parts[-2], parts[-1]
    if parts[-1][:1].isupper():
        return ".".join(parts[:-1]), parts[-1], None
    return candidate, None, None


def _django_module_candidate_paths(module_name: str) -> list[str]:
    module_path = module_name.replace(".", "/").strip("/")
    if not module_path:
        return []
    candidates = [f"tests/{module_path}.py", f"{module_path}.py"]
    if module_path.endswith("/tests"):
        candidates.append(f"tests/{module_path[:-6]}/tests.py")
    return _dedupe_strings(candidates)


def _resolve_existing_django_module_path(repo_root: str | Path, module_name: str) -> str | None:
    root = Path(repo_root)
    for relative in _django_module_candidate_paths(module_name):
        if (root / relative).is_file():
            return relative
    return None


def _django_target_file(node_id: str, repo_root: str | Path) -> str | None:
    parts = _parse_django_target_parts(node_id)
    if parts is None:
        return None
    module_name, _, _ = parts
    return _resolve_existing_django_module_path(repo_root, module_name)


def _file_contains_python_symbol(path: Path, symbol_name: str, *, symbol_kind: str) -> bool:
    if not path.is_file() or not symbol_name:
        return False
    text = _read_small_text_file(path)
    if not text:
        return False
    escaped = re.escape(symbol_name)
    if symbol_kind == "class":
        pattern = rf"(?m)^\s*class\s+{escaped}\b"
    else:
        pattern = rf"(?m)^\s*def\s+{escaped}\b"
    return re.search(pattern, text) is not None


def _normalize_django_validation_target(repo_root: str | Path, node_id: str) -> str | None:
    fallback = _django_test_target(node_id)
    parts = _parse_django_target_parts(node_id)
    if parts is None:
        return fallback
    module_name, class_name, test_name = parts
    module_path = _resolve_existing_django_module_path(repo_root, module_name)
    if module_path is None:
        return fallback
    source_path = Path(repo_root) / module_path
    class_exists = bool(class_name) and _file_contains_python_symbol(source_path, class_name or "", symbol_kind="class")
    test_exists = bool(test_name) and _file_contains_python_symbol(source_path, test_name or "", symbol_kind="function")
    if class_name and test_name:
        if class_exists and test_exists:
            return f"{module_name}.{class_name}.{test_name}"
        if class_exists:
            return f"{module_name}.{class_name}"
        return module_name
    if class_name:
        return f"{module_name}.{class_name}" if class_exists else module_name
    return module_name


def _collapse_overlapping_django_targets(targets: list[str]) -> list[str]:
    normalized = _dedupe_strings([str(item).strip() for item in list(targets or []) if str(item).strip()])
    parsed: dict[str, tuple[str, str | None, str | None]] = {}
    class_labels: set[str] = set()
    module_labels: set[str] = set()
    for target in normalized:
        parts = _parse_django_target_parts(target)
        if parts is None:
            continue
        parsed[target] = parts
        module_name, class_name, test_name = parts
        if class_name and not test_name:
            class_labels.add(f"{module_name}.{class_name}")
        if not class_name and not test_name:
            module_labels.add(module_name)
    collapsed: list[str] = []
    for target in normalized:
        parts = parsed.get(target)
        if parts is None:
            collapsed.append(target)
            continue
        module_name, class_name, test_name = parts
        if module_name in module_labels and target != module_name:
            continue
        if class_name and test_name and f"{module_name}.{class_name}" in class_labels:
            continue
        collapsed.append(target)
    return collapsed


def _normalize_explicit_django_runtests_command(repo_root: str | Path, command: str) -> str | None:
    candidate = str(command or "").strip()
    if not candidate or "tests/runtests.py" not in candidate:
        return None
    try:
        tokens = shlex.split(candidate, posix=True)
    except ValueError:
        return None
    script_index = next(
        (
            index
            for index, token in enumerate(tokens)
            if token == "tests/runtests.py" or token.endswith("/tests/runtests.py") or token.endswith("\\tests\\runtests.py")
        ),
        -1,
    )
    if script_index < 0:
        return None
    prefix = tokens[: script_index + 1]
    cursor = script_index + 1
    while cursor < len(tokens):
        token = tokens[cursor]
        if not token.startswith("-"):
            break
        prefix.append(token)
        if "=" not in token and cursor + 1 < len(tokens) and not tokens[cursor + 1].startswith("-"):
            prefix.append(tokens[cursor + 1])
            cursor += 2
            continue
        cursor += 1
    target_tokens = [str(item).strip() for item in tokens[cursor:] if str(item).strip()]
    if not target_tokens:
        return None
    normalized_targets = _collapse_overlapping_django_targets(
        [_normalize_django_validation_target(repo_root, item) or "" for item in target_tokens]
    )
    if not normalized_targets:
        return None
    return " ".join([*prefix, *normalized_targets])


def detect_validation_commands(
    repo_root: str | Path,
    explicit_commands: list[str] | None = None,
    *,
    fail_to_pass: list[str] | None = None,
    pass_to_pass: list[str] | None = None,
) -> list[str]:
    commands = [item for item in list(explicit_commands or []) if item.strip()]
    if commands:
        normalized_commands: list[str] = []
        for command in commands:
            normalized_commands.append(_normalize_explicit_django_runtests_command(repo_root, command) or command)
        return _dedupe_strings(normalized_commands)
    pytest_targets = _dedupe_strings(
        [
            *[_pytest_target_file(item) or "" for item in list(fail_to_pass or [])],
            *[_pytest_target_file(item) or "" for item in list(pass_to_pass or [])],
        ]
    )
    if pytest_targets:
        return [f"python -m pytest {' '.join(pytest_targets)} -q"]
    root = Path(repo_root)
    django_targets = _collapse_overlapping_django_targets(
        [
            *[_normalize_django_validation_target(root, item) or "" for item in list(fail_to_pass or [])],
            *[_normalize_django_validation_target(root, item) or "" for item in list(pass_to_pass or [])],
        ]
    )
    if (root / "tests" / "runtests.py").exists() and django_targets:
        return [f"python tests/runtests.py --settings=test_sqlite {' '.join(django_targets)}"]
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or (root / "tests").exists():
        return ["python -m pytest"]
    if (root / "package.json").exists():
        return ["npm test -- --runInBand"]
    return []


def detect_setup_commands(repo_root: str | Path, explicit_commands: list[str] | None = None) -> list[str]:
    commands = [item for item in list(explicit_commands or []) if item.strip()]
    if commands:
        return commands
    root = Path(repo_root)
    detected: list[str] = []
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or (root / "setup.cfg").exists():
        detected.extend(
            [
                'python -m pip install --disable-pip-version-check --no-input --no-index --no-build-isolation -e ".[test]"',
                'python -m pip install --disable-pip-version-check --no-input --no-index --no-build-isolation -e "."',
            ]
        )
    elif (root / "requirements.txt").exists():
        detected.append("python -m pip install --disable-pip-version-check --no-input --no-index -r requirements.txt")
    return _dedupe_strings(detected)


def _quote_shell_argument(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return '""'
    if re.search(r"[<>&|\[\]\s]", text):
        return f'"{text}"'
    return text


def _parse_toml_string_array(pyproject_path: str | Path, section_name: str, key: str) -> list[str]:
    path = Path(pyproject_path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    section_match = re.search(rf"(?ms)^\[{re.escape(section_name)}\]\s*(.*?)(?=^\[|\Z)", text)
    if section_match is None:
        return []
    section_body = section_match.group(1)
    key_match = re.search(rf"(?ms)^{re.escape(key)}\s*=\s*\[(.*?)\]", section_body)
    if key_match is None:
        return []
    values: list[str] = []
    for match in re.finditer(r'"([^"]+)"|\'([^\']+)\'', key_match.group(1)):
        candidate = str(match.group(1) or match.group(2) or "").strip()
        if candidate:
            values.append(candidate)
    return _dedupe_strings(values)


def _workspace_uses_legacy_setuptools_dep_util(repo_root: str | Path) -> bool:
    root = Path(repo_root)
    for candidate in [root / "setup.py", root / "setup_package.py", *root.rglob("*setup_package.py")]:
        try:
            if candidate.exists() and "setuptools.dep_util" in candidate.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def _workspace_needs_inplace_extension_build(
    repo_root: str | Path,
    *,
    build_requires: list[str] | None = None,
    uses_legacy_setuptools_dep_util: bool = False,
) -> bool:
    root = Path(repo_root)
    setup_py = root / "setup.py"
    if not setup_py.exists():
        return False
    if uses_legacy_setuptools_dep_util:
        return True
    normalized_requires = [str(item).strip().lower() for item in list(build_requires or []) if str(item).strip()]
    if any(
        any(token in requirement for token in ("cython", "extension-helpers", "oldest-supported-numpy", "pybind11", "setuptools-rust"))
        for requirement in normalized_requires
    ):
        return True
    try:
        setup_text = setup_py.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(token in setup_text for token in ("Extension(", "cythonize(", "ext_modules"))


def detect_python_bootstrap_commands(repo_root: str | Path) -> list[str]:
    root = Path(repo_root)
    pyproject_path = root / "pyproject.toml"
    setup_py = root / "setup.py"
    if not any((pyproject_path.exists(), setup_py.exists(), (root / "setup.cfg").exists())):
        return []
    commands: list[str] = []
    uses_legacy_setuptools_dep_util = _workspace_uses_legacy_setuptools_dep_util(root)
    if uses_legacy_setuptools_dep_util:
        commands.append('python -m pip install --disable-pip-version-check --no-input --no-index "setuptools<70"')
    build_requires = _parse_toml_string_array(pyproject_path, "build-system", "requires")
    if build_requires:
        rendered = " ".join(_quote_shell_argument(item) for item in build_requires)
        commands.append(f"python -m pip install --disable-pip-version-check --no-input --no-index {rendered}")
    if setup_py.exists():
        commands.append("python setup.py egg_info")
    if _workspace_needs_inplace_extension_build(
        root,
        build_requires=build_requires,
        uses_legacy_setuptools_dep_util=uses_legacy_setuptools_dep_util,
    ):
        commands.append("python setup.py build_ext --inplace --build-temp build-temp --build-lib build-lib")
    return _dedupe_strings(commands)


def _redact_local_path_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(
        r"(?i)\b[a-z]:[\\/][^\s'\"`()\[\]{}]+",
        LOCAL_PATH_PLACEHOLDER,
        normalized,
    )
    normalized = re.sub(
        r"(?<![A-Za-z0-9_])/(?:[^/\s'\"`()\[\]{}]+/){2,}[^/\s'\"`()\[\]{}]+",
        LOCAL_PATH_PLACEHOLDER,
        normalized,
    )
    return normalized


def _extract_path_like_references(text: str) -> list[str]:
    references: list[str] = []
    for match in re.finditer(r"([A-Za-z0-9_.\-/\\]+\.[A-Za-z0-9_]+)", text or ""):
        candidate = str(match.group(1) or "").strip().strip("\"'`,:;()[]{}")
        if not candidate:
            continue
        normalized = candidate.replace("\\", "/")
        suffix = Path(normalized).suffix.lower()
        if suffix in TEXT_EXTENSIONS or Path(normalized).name in {"Dockerfile", "Makefile"}:
            references.append(normalized)
    return _dedupe_strings(references)


def _normalize_repo_reference_path(root: Path, candidate: str) -> str | None:
    normalized = str(candidate or "").strip().strip("\"'`,:;()[]{}").replace("\\", "/")
    if not normalized:
        return None
    normalized = normalized.split("::", 1)[0].strip()
    if not normalized:
        return None
    if re.match(r"(?i)^[a-z]:/", normalized) or normalized.startswith("/"):
        try:
            resolved = Path(normalized).resolve()
            relative = resolved.relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return None
        normalized = relative
    else:
        normalized = normalized.lstrip("./")
    path = Path(normalized)
    if not normalized or any(part in {"", ".", ".."} for part in path.parts):
        return None
    suffix = path.suffix.lower()
    if suffix not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
        return None
    return path.as_posix()


def _identifier_reference_is_noise(candidate: str) -> bool:
    normalized = str(candidate or "").strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if lowered in NOISY_IDENTIFIER_REFERENCES:
        return True
    if normalized.isupper() and "_" not in normalized:
        return True
    if normalized.endswith(("Error", "Exception", "Warning")):
        return True
    return False


def _extract_identifier_references(text: str, *, limit: int = 16) -> list[str]:
    references: list[str] = []
    normalized = _redact_local_path_text(str(text or "").replace("\u200b", " ").replace("\ufeff", " "))
    patterns = (
        r"\b[A-Z][A-Z0-9_]{3,}\b",
        r"\b[A-Z]{2,}[A-Za-z0-9_]*[a-z][A-Za-z0-9_]*\b",
        r"\b[A-Z][a-z0-9_]+(?:[A-Z][A-Za-z0-9_]*)+\b",
        r"\b[a-z]+(?:_[a-z0-9]+){1,}\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, normalized):
            candidate = str(match.group(0) or "").strip()
            if candidate.startswith(("HTTP", "HTTPS")):
                continue
            if _identifier_reference_is_noise(candidate):
                continue
            references.append(candidate)
            if len(_dedupe_strings(references)) >= limit:
                return _dedupe_strings(references)[:limit]
    return _dedupe_strings(references)[:limit]


def _read_small_text_file(path: Path, *, max_bytes: int = 512_000) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _is_test_like_path(path_text: str) -> bool:
    normalized = str(path_text or "").replace("\\", "/").strip("/")
    if not normalized:
        return False
    path = Path(normalized)
    parts = {part.lower() for part in path.parts}
    return (
        "tests" in parts
        or "test" in parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
        or path.name == "tests.py"
    )


def _find_candidate_source_files(root: Path, basename: str) -> list[str]:
    normalized = str(basename or "").strip()
    if not normalized:
        return []
    matches: list[str] = []
    for path in sorted(root.rglob(normalized)):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_DIR_NAMES for part in Path(relative).parts):
            continue
        if _is_test_like_path(relative):
            continue
        matches.append(relative)
    return _dedupe_strings(matches)


def _inferred_source_candidates(root: Path, focus_paths: list[str]) -> list[str]:
    candidates: list[str] = []
    for focus_path in focus_paths:
        normalized = str(focus_path or "").replace("\\", "/").strip("/")
        if not normalized or not _is_test_like_path(normalized):
            continue
        path = Path(normalized)
        parts = list(path.parts)
        filename = path.name
        stem = path.stem
        if filename.startswith("test_"):
            source_name = filename[len("test_") :]
            for index, part in enumerate(parts):
                if part.lower() not in {"tests", "test"}:
                    continue
                candidate = Path(*parts[:index], source_name)
                if (root / candidate).is_file():
                    candidates.append(candidate.as_posix())
            candidates.extend(_find_candidate_source_files(root, source_name))
        if stem.endswith("_test"):
            source_name = f"{stem[:-5]}{path.suffix}"
            for index, part in enumerate(parts):
                if part.lower() not in {"tests", "test"}:
                    continue
                candidate = Path(*parts[:index], source_name)
                if (root / candidate).is_file():
                    candidates.append(candidate.as_posix())
            candidates.extend(_find_candidate_source_files(root, source_name))
    return _dedupe_strings(candidates)


def _rank_related_files(
    root: Path,
    *,
    focus_paths: list[str],
    candidate_stems: list[str],
    identifier_terms: list[str],
    limit: int = 8,
) -> list[str]:
    existing_focus_set = {item.replace("\\", "/") for item in focus_paths}
    normalized_identifier_terms = [item.lower() for item in identifier_terms if item.strip()]
    scored: list[tuple[int, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in existing_focus_set:
            continue
        if any(part in IGNORED_DIR_NAMES for part in Path(relative).parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
            continue
        if ".egg-info/" in relative or relative.endswith(".egg-info"):
            continue
        if _is_test_like_path(relative):
            continue
        score = 0
        if path.stem in candidate_stems:
            score += 4
        lowered_relative = relative.lower()
        if lowered_relative.startswith(("src/", "lib/", "app/", "django/", "astropy/")):
            score += 2
        if lowered_relative.startswith("docs/"):
            score += 1
        if normalized_identifier_terms:
            for term in normalized_identifier_terms:
                if term in lowered_relative:
                    score += 6
            file_text = _read_small_text_file(path)
            if file_text:
                lowered_text = file_text.lower()
                score += 5 * sum(1 for term in normalized_identifier_terms if term in lowered_text)
        if score > 0:
            scored.append((score, relative))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [relative for _, relative in scored[:limit]]


def _sanitize_prompt_text(text: str | None, *, max_chars: int) -> str:
    if not text:
        return ""
    normalized = str(text).replace("\u200b", " ").replace("\ufeff", " ")
    normalized = re.sub(r"https?://\S+", "[url omitted]", normalized)
    normalized = _redact_local_path_text(normalized)
    lines = [" ".join(line.split()) for line in normalized.splitlines()]
    compact = "\n".join(line for line in lines if line)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 24].rstrip() + "\n[truncated for local prompt]"


def _summarize_targets_for_prompt(targets: list[str], *, limit: int = 12) -> list[str]:
    cleaned = [str(item).strip() for item in list(targets or []) if str(item).strip()]
    if len(cleaned) <= limit:
        return cleaned
    remaining = len(cleaned) - limit
    return cleaned[:limit] + [f"... and {remaining} more target(s)."]


def _summarize_validation_command_for_prompt(command: str, task: BenchmarkTaskSpec) -> str:
    normalized = " ".join(str(command or "").split())
    if len(normalized) <= 240:
        return normalized
    fail_count = len([item for item in list(task.fail_to_pass or []) if str(item).strip()])
    pass_count = len([item for item in list(task.pass_to_pass or []) if str(item).strip()])
    if fail_count or pass_count:
        return (
            f"{normalized[:160].rstrip()} ... "
            f"[focused on {fail_count} FAIL_TO_PASS and {pass_count} PASS_TO_PASS target(s)]"
    )
    return normalized[:200].rstrip() + " ... [truncated for prompt]"


def _normalized_issue_validation_commands(
    task: BenchmarkTaskSpec,
    commands: list[str] | None,
    *,
    fail_to_pass: list[str] | None,
    pass_to_pass: list[str] | None,
) -> list[str]:
    normalized_commands = [str(item).strip() for item in list(commands or []) if str(item).strip()]
    if normalized_commands:
        return detect_validation_commands(
            task.repo_path,
            normalized_commands,
            fail_to_pass=fail_to_pass,
            pass_to_pass=pass_to_pass,
        )
    if fail_to_pass or pass_to_pass:
        return detect_validation_commands(
            task.repo_path,
            [],
            fail_to_pass=fail_to_pass,
            pass_to_pass=pass_to_pass,
        )
    return []


def build_project_issue_context(
    task: BenchmarkTaskSpec,
    validation_commands: list[str],
    repo_context: dict[str, Any] | None = None,
) -> str:
    repo_context = dict(repo_context or {})
    focused_validation_commands = _normalized_issue_validation_commands(
        task,
        list(repo_context.get("focused_validation_commands") or []),
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=[],
    )
    broader_validation_commands = _normalized_issue_validation_commands(
        task,
        validation_commands,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
    )
    existing_focus_paths = [str(item) for item in list(repo_context.get("existing_focus_paths") or []) if str(item).strip()]
    related_files = [str(item) for item in list(repo_context.get("related_files") or []) if str(item).strip()]
    code_search_hits = [str(item) for item in list(repo_context.get("code_search_hits") or []) if str(item).strip()]
    implementation_anchors = [str(item) for item in list(repo_context.get("implementation_anchors") or []) if str(item).strip()]
    lines: list[str] = []
    if focused_validation_commands:
        lines.extend(["Focused reproduction commands:"])
        lines.extend(
            f"- {_summarize_validation_command_for_prompt(command, task)}" for command in focused_validation_commands
        )
    if existing_focus_paths or related_files:
        lines.extend(["", "Workspace clues:"])
        if existing_focus_paths:
            lines.append(f"- Files to inspect first: {', '.join(existing_focus_paths[:6])}")
        if related_files:
            lines.append(f"- Likely related implementation files: {', '.join(related_files[:6])}")
    if code_search_hits:
        lines.extend(["", "Exact repo matches for issue snippets:"])
        lines.extend(f"- {item}" for item in code_search_hits[:4])
    if implementation_anchors:
        lines.extend(["", "Implementation anchors:"])
        lines.extend(f"- {item}" for item in implementation_anchors[:4])
    lines.extend(["", "Issue:", _sanitize_prompt_text(task.problem_statement, max_chars=2200)])
    if task.hints_text:
        lines.extend(["", "Hints:", _sanitize_prompt_text(task.hints_text, max_chars=900)])
    if broader_validation_commands:
        lines.extend(["", "Broader validation commands after a fix:"])
        lines.extend(
            f"- {_summarize_validation_command_for_prompt(command, task)}" for command in broader_validation_commands
        )
    if task.fail_to_pass:
        lines.extend(["", "FAIL_TO_PASS targets:"])
        lines.extend(f"- {item}" for item in _summarize_targets_for_prompt(task.fail_to_pass, limit=8))
    return "\n".join(line for line in lines if line is not None).strip()


def _looks_like_code_search_needle(text: str) -> bool:
    candidate = " ".join(str(text or "").strip().split())
    if len(candidate) < 12 or len(candidate) > 180:
        return False
    if "http://" in candidate or "https://" in candidate:
        return False
    if not any(token in candidate for token in ("=", "(", ")", ".", "[", "]")):
        return False
    if sum(char.isalpha() for char in candidate) < 6:
        return False
    return True


def _extract_code_search_needles(*texts: str, limit: int = 6) -> list[str]:
    needles: list[str] = []
    for text in texts:
        for raw_line in str(text or "").splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            for inline_match in re.finditer(r"`([^`\n]{4,180})`", line):
                snippet = " ".join(str(inline_match.group(1) or "").strip().split())
                if _looks_like_code_search_needle(snippet):
                    needles.append(snippet)
                for call_match in re.finditer(r"[A-Za-z_][A-Za-z0-9_.]*\([^)]+\)", snippet):
                    call_snippet = " ".join(str(call_match.group(0) or "").strip().split())
                    if _looks_like_code_search_needle(call_snippet):
                        needles.append(call_snippet)
            if _looks_like_code_search_needle(line):
                needles.append(line)
            for call_match in re.finditer(r"[A-Za-z_][A-Za-z0-9_.]*\([^)]+\)", line):
                call_snippet = " ".join(str(call_match.group(0) or "").strip().split())
                if _looks_like_code_search_needle(call_snippet):
                    needles.append(call_snippet)
    return _dedupe_strings(needles)[:limit]


def _find_repo_code_search_hits(root: Path, candidate_files: list[str], needles: list[str], *, limit: int = 6) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    if not needles:
        return hits
    prioritized_candidates = _dedupe_strings(
        [path for path in candidate_files if not _is_test_like_path(path)]
        + [path for path in candidate_files if _is_test_like_path(path)]
    )
    for relative_path in prioritized_candidates:
        path = root / relative_path
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            collapsed = " ".join(line.strip().split())
            if not collapsed:
                continue
            for needle in needles:
                if needle not in collapsed:
                    continue
                entry = f"{relative_path}:{lineno}: {collapsed[:160]}"
                if entry in seen:
                    continue
                seen.add(entry)
                hits.append(entry)
                if len(hits) >= limit:
                    return hits
                break
    return hits


def _find_identifier_line_hits(root: Path, candidate_files: list[str], identifiers: list[str], *, limit: int = 6) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    if not identifiers:
        return hits
    prioritized_candidates = _dedupe_strings(
        [path for path in candidate_files if not _is_test_like_path(path)]
        + [path for path in candidate_files if _is_test_like_path(path)]
    )
    useful_identifiers = [
        term
        for term in _dedupe_strings(identifiers)
        if len(term) >= 5 and (any(char.isupper() for char in term) or "_" in term or term.islower())
    ]
    scored_hits: list[tuple[int, int, str]] = []
    for relative_path in prioritized_candidates:
        if _is_test_like_path(relative_path):
            continue
        path = root / relative_path
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            collapsed = " ".join(line.strip().split())
            lowered = collapsed.lower()
            if not collapsed:
                continue
            for identifier in useful_identifiers:
                normalized_identifier = identifier.lower()
                if normalized_identifier not in lowered:
                    continue
                entry = f"{relative_path}:{lineno}: {collapsed[:160]}"
                if entry in seen:
                    continue
                score = 0
                if re.search(rf"\bdef\s+{re.escape(identifier)}\b", collapsed):
                    score += 200
                elif re.search(rf"\bclass\s+{re.escape(identifier)}\b", collapsed):
                    score += 180
                elif re.search(rf"\b{re.escape(identifier)}\s*\(", collapsed):
                    score += 120
                elif re.search(rf"\b{re.escape(identifier)}\b", collapsed):
                    score += 80
                if collapsed.startswith(("def ", "class ")):
                    score += 40
                if collapsed.startswith((">>>", '"""', "'''", "#")):
                    score -= 40
                if "__all__" in collapsed:
                    score += 20
                scored_hits.append((score, lineno, entry))
                seen.add(entry)
                break
    scored_hits.sort(key=lambda item: (-item[0], item[1], item[2]))
    hits.extend(entry for _score, _lineno, entry in scored_hits[:limit])
    return hits


def _same_file_neighbor_definition_anchors(
    root: Path,
    anchor_entry: str,
    *,
    limit: int = 4,
) -> list[str]:
    match = re.match(r"([^:]+):(\d+):\s*(.+)$", str(anchor_entry or "").strip())
    if not match:
        return []
    relative_path = str(match.group(1) or "").strip()
    anchor_line = int(match.group(2))
    if not relative_path or _is_test_like_path(relative_path):
        return []
    path = root / relative_path
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    candidates: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        collapsed = " ".join(line.strip().split())
        if not collapsed:
            continue
        if not re.match(r"^(def|class)\s+[A-Za-z_][A-Za-z0-9_]*", collapsed):
            continue
        candidates.append((abs(lineno - anchor_line), f"{relative_path}:{lineno}: {collapsed[:160]}"))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return [entry for _distance, entry in candidates[:limit]]


def _list_repo_text_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_DIR_NAMES for part in Path(relative).parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
            continue
        files.append(relative)
    return files


def build_repo_context(task: BenchmarkTaskSpec, workspace_root: str | Path, validation_commands: list[str]) -> dict[str, Any]:
    root = Path(workspace_root)
    top_level_entries = sorted(
        f"{path.name}/" if path.is_dir() else path.name
        for path in root.iterdir()
        if path.name not in IGNORED_DIR_NAMES
    )[:12]
    referenced_paths = _dedupe_strings(
        [
            *task.fail_to_pass,
            *task.pass_to_pass,
            *validation_commands,
            task.problem_statement,
            task.hints_text or "",
        ]
    )
    focus_paths: list[str] = []
    for text in referenced_paths:
        for path_ref in _extract_path_like_references(text):
            normalized = _normalize_repo_reference_path(root, path_ref)
            if normalized:
                focus_paths.append(normalized)
    for target in [*task.fail_to_pass, *task.pass_to_pass]:
        django_focus_path = _django_target_file(target, root)
        if django_focus_path:
            focus_paths.append(django_focus_path)
    focus_paths = _dedupe_strings(focus_paths)
    inferred_source_paths = _inferred_source_candidates(root, focus_paths)

    candidate_stems: list[str] = []
    for focus_path in [*focus_paths, *inferred_source_paths]:
        stem = Path(focus_path).stem
        candidate_stems.append(stem)
        if stem.startswith("test_"):
            candidate_stems.append(stem[len("test_"):])
        if stem.endswith("_test"):
            candidate_stems.append(stem[:-5])
    candidate_stems = _dedupe_strings(candidate_stems)
    identifier_terms = _extract_identifier_references(
        " ".join(
            [
                task.problem_statement,
                task.hints_text or "",
                *task.fail_to_pass,
                *task.pass_to_pass,
            ]
        )
    )

    existing_focus_paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in IGNORED_DIR_NAMES for part in Path(relative).parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
            continue
        if relative in focus_paths:
            existing_focus_paths.append(relative)
    related_files = _rank_related_files(
        root,
        focus_paths=focus_paths,
        candidate_stems=candidate_stems,
        identifier_terms=identifier_terms,
    )
    related_files = _dedupe_strings([*inferred_source_paths, *related_files])
    focused_validation_commands = detect_validation_commands(
        root,
        [],
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=[],
    )
    code_search_needles = _extract_code_search_needles(task.problem_statement, task.hints_text or "")
    preferred_code_search_files = _dedupe_strings([*related_files, *existing_focus_paths])
    code_search_hits = _find_repo_code_search_hits(root, preferred_code_search_files, code_search_needles)
    if code_search_needles and len(code_search_hits) < min(2, len(code_search_needles)):
        fallback_hits = _find_repo_code_search_hits(root, _list_repo_text_files(root), code_search_needles)
        code_search_hits = _dedupe_strings([*code_search_hits, *fallback_hits])[:6]
    non_test_code_search_hits = [
        item for item in code_search_hits if not _is_test_like_path(item.split(":", 1)[0].strip())
    ]
    if non_test_code_search_hits:
        code_search_hits = non_test_code_search_hits[:6]
    elif any(not _is_test_like_path(path) for path in related_files):
        code_search_hits = []
    implementation_anchors = _find_identifier_line_hits(
        root,
        _dedupe_strings([*existing_focus_paths, *related_files]),
        identifier_terms,
    )
    if implementation_anchors:
        neighbor_anchors = _same_file_neighbor_definition_anchors(root, implementation_anchors[0], limit=4)
        primary_anchor = implementation_anchors[0]
        remaining_anchors = implementation_anchors[1:]
        implementation_anchors = _dedupe_strings([primary_anchor, *neighbor_anchors, *remaining_anchors])

    return {
        "top_level_entries": top_level_entries,
        "focus_paths": focus_paths,
        "existing_focus_paths": _dedupe_strings(existing_focus_paths)[:8],
        "related_files": _dedupe_strings(related_files)[:8],
        "focused_validation_commands": focused_validation_commands[:2],
        "identifier_terms": identifier_terms[:8],
        "code_search_needles": code_search_needles,
        "code_search_hits": code_search_hits,
        "implementation_anchors": implementation_anchors[:6],
    }


def build_manager_issue_prompt(
    task: BenchmarkTaskSpec,
    validation_commands: list[str],
    repo_context: dict[str, Any] | None = None,
) -> str:
    lines = [
        "Run this as a prepared local SWE-bench-style coding task.",
        "Use only the local workspace and local commands.",
        "No internet access, no hosted APIs, no gold-patch lookup, and no pretending validation ran when it did not.",
        "",
        f"Instance ID: {task.instance_id}",
    ]
    if task.repo_name:
        lines.append(f"Repository: {task.repo_name}")
    if task.base_commit:
        lines.append(f"Base commit: {task.base_commit}")
    lines.extend(
        [
            "",
            "Issue:",
            _sanitize_prompt_text(task.problem_statement, max_chars=3200),
        ]
    )
    repo_context = dict(repo_context or {})
    top_level_entries = [str(item) for item in list(repo_context.get("top_level_entries") or []) if str(item).strip()]
    existing_focus_paths = [str(item) for item in list(repo_context.get("existing_focus_paths") or []) if str(item).strip()]
    related_files = [str(item) for item in list(repo_context.get("related_files") or []) if str(item).strip()]
    implementation_anchors = [str(item) for item in list(repo_context.get("implementation_anchors") or []) if str(item).strip()]
    focused_validation_commands = _normalized_issue_validation_commands(
        task,
        list(repo_context.get("focused_validation_commands") or []),
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=[],
    )
    broader_validation_commands = _normalized_issue_validation_commands(
        task,
        validation_commands,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
    )
    code_search_hits = [str(item) for item in list(repo_context.get("code_search_hits") or []) if str(item).strip()]
    if top_level_entries or existing_focus_paths or related_files:
        lines.extend(["", "Workspace clues:"])
        if top_level_entries:
            lines.append(f"- Top-level entries: {', '.join(top_level_entries)}")
        if existing_focus_paths:
            lines.append(f"- Files to inspect first: {', '.join(existing_focus_paths)}")
        if related_files:
            lines.append(f"- Likely related implementation files: {', '.join(related_files)}")
        if code_search_hits:
            lines.append("- Exact repo matches for issue snippets:")
            lines.extend(f"  {item}" for item in code_search_hits[:6])
        if implementation_anchors:
            lines.append("- Implementation anchors:")
            lines.extend(f"  {item}" for item in implementation_anchors[:6])
    if task.hints_text:
        lines.extend(["", "Hints:", _sanitize_prompt_text(task.hints_text, max_chars=2200)])
    if focused_validation_commands:
        lines.extend(["", "Focused reproduction commands:"])
        lines.extend(
            f"- {_summarize_validation_command_for_prompt(command, task)}" for command in focused_validation_commands
        )
    if broader_validation_commands:
        lines.extend(["", "Broader validation commands after a fix:"])
        lines.extend(
            f"- {_summarize_validation_command_for_prompt(command, task)}" for command in broader_validation_commands
        )
    if task.fail_to_pass:
        lines.extend(["", "FAIL_TO_PASS targets:"])
        lines.extend(f"- {item}" for item in _summarize_targets_for_prompt(task.fail_to_pass, limit=12))
    if task.pass_to_pass:
        lines.extend(["", "PASS_TO_PASS targets:"])
        lines.extend(f"- {item}" for item in _summarize_targets_for_prompt(task.pass_to_pass, limit=12))
    lines.extend(
        [
            "",
            "Required behavior:",
            "- Produce a manager-led plan grounded in the checked-out repo.",
            "- Generate and apply the smallest safe patch you can justify.",
            "- Run available validation before calling the task done.",
            "- If blocked, report the blocker honestly instead of inventing success.",
        ]
    )
    return "\n".join(lines)


def snapshot_workspace(root: str | Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict[str, str]:
    workspace = Path(root)
    snapshot: dict[str, str] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.relative_to(workspace).parts):
            continue
        if path.stat().st_size > max_file_bytes:
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "Makefile"}:
            continue
        try:
            snapshot[path.relative_to(workspace).as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return snapshot


def build_workspace_diff(before: dict[str, str], after: dict[str, str]) -> tuple[str, list[str]]:
    changed_files = sorted(set(before) | set(after))
    diffs: list[str] = []
    touched: list[str] = []
    for relative in changed_files:
        if before.get(relative) == after.get(relative):
            continue
        touched.append(relative)
        before_lines = before.get(relative, "").splitlines(keepends=True)
        after_lines = after.get(relative, "").splitlines(keepends=True)
        diffs.extend(
            unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
    return "".join(diffs), touched


def build_meaningful_workspace_diff(before: dict[str, str], after: dict[str, str]) -> tuple[str, list[str]]:
    meaningful_paths = meaningful_patch_paths(sorted(set(before) | set(after)))
    diffs: list[str] = []
    touched: list[str] = []
    for relative in meaningful_paths:
        if before.get(relative) == after.get(relative):
            continue
        touched.append(relative)
        before_lines = before.get(relative, "").splitlines(keepends=True)
        after_lines = after.get(relative, "").splitlines(keepends=True)
        diffs.extend(
            unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{relative}",
                tofile=f"b/{relative}",
            )
        )
    return "".join(diffs), touched


def meaningful_patch_paths(paths: list[str]) -> list[str]:
    filtered: list[str] = []
    for path in paths:
        normalized = str(path).replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if not normalized:
            continue
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in NON_PATCH_ARTIFACT_PREFIXES):
            continue
        filtered.append(normalized)
    return filtered


def _remove_empty_parent_dirs(path: Path, *, stop_at: Path) -> None:
    current = path.parent
    boundary = stop_at.resolve()
    while current != boundary and current.exists():
        try:
            next(current.iterdir())
            break
        except StopIteration:
            current.rmdir()
            current = current.parent
        except OSError:
            break


def benchmark_test_patch_files(patch_text: str | None) -> list[str]:
    if not str(patch_text or "").strip():
        return []
    touched: list[str] = []
    for raw_line in str(patch_text).splitlines():
        line = raw_line.strip()
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        candidates = [parts[3], parts[2]]
        for raw_path in candidates:
            if raw_path == "/dev/null":
                continue
            normalized = raw_path[2:] if raw_path.startswith(("a/", "b/")) else raw_path
            normalized = normalized.strip()
            if normalized:
                touched.append(normalized)
                break
    return _dedupe_strings(touched)


def write_benchmark_protected_paths_manifest(
    workspace_path: str | Path,
    test_patch: str | None,
) -> dict[str, Any]:
    workspace_root = Path(workspace_path)
    protected_paths = benchmark_test_patch_files(test_patch)
    manifest_path = workspace_root / BENCHMARK_PROTECTED_PATHS_MANIFEST
    if not protected_paths:
        if manifest_path.exists():
            try:
                manifest_path.unlink()
            except OSError:
                pass
        return {
            "manifest_path": manifest_path.as_posix(),
            "protected_paths": [],
            "written": False,
        }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"protected_paths": protected_paths}, indent=2),
        encoding="utf-8",
    )
    return {
        "manifest_path": manifest_path.as_posix(),
        "protected_paths": protected_paths,
        "written": True,
    }


def filter_benchmark_protected_changed_files(
    changed_files: list[str],
    test_patch: str | None,
) -> tuple[list[str], list[str]]:
    meaningful = meaningful_patch_paths(changed_files)
    protected = set(benchmark_test_patch_files(test_patch))
    if not protected:
        return meaningful, []
    kept = [path for path in meaningful if path not in protected]
    skipped = [path for path in meaningful if path in protected]
    return kept, skipped


def replay_changed_workspace_files(
    source_workspace: str | Path,
    destination_workspace: str | Path,
    changed_files: list[str],
) -> dict[str, list[str]]:
    source_root = Path(source_workspace).resolve()
    destination_root = Path(destination_workspace).resolve()
    replayed_files: list[str] = []
    deleted_files: list[str] = []
    for relative in meaningful_patch_paths(changed_files):
        source_path = source_root / relative
        destination_path = destination_root / relative
        if source_path.is_file():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            replayed_files.append(relative)
            continue
        if destination_path.exists():
            if destination_path.is_dir():
                shutil.rmtree(destination_path)
            else:
                destination_path.unlink()
            _remove_empty_parent_dirs(destination_path, stop_at=destination_root)
            deleted_files.append(relative)
    return {
        "replayed_files": replayed_files,
        "deleted_files": deleted_files,
    }


def restore_workspace_files_from_snapshot(
    workspace_path: str | Path,
    snapshot: dict[str, str],
    relative_paths: list[str],
) -> dict[str, list[str]]:
    workspace_root = Path(workspace_path).resolve()
    restored_files: list[str] = []
    deleted_files: list[str] = []
    for relative in meaningful_patch_paths(relative_paths):
        target = (workspace_root / relative).resolve()
        try:
            target.relative_to(workspace_root)
        except ValueError:
            continue
        baseline_text = snapshot.get(relative)
        if baseline_text is None:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                _remove_empty_parent_dirs(target, stop_at=workspace_root)
                deleted_files.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(baseline_text, encoding="utf-8")
        restored_files.append(relative)
    return {
        "restored_files": restored_files,
        "deleted_files": deleted_files,
    }


def apply_git_patch_text(
    workspace_path: str | Path,
    patch_text: str,
    output_dir: str | Path,
    *,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    stdout_path = root / "apply.stdout.txt"
    stderr_path = root / "apply.stderr.txt"
    if not str(patch_text or "").strip():
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        return {
            "applied": False,
            "timed_out": False,
            "returncode": None,
            "stdout_path": stdout_path.as_posix(),
            "stderr_path": stderr_path.as_posix(),
        }
    timed_out = False
    returncode: int | None = None
    stdout_text = ""
    stderr_text = ""
    try:
        completed = subprocess.run(
            _git_command_for_path(workspace_path, "apply", "--recount", "--whitespace=nowarn"),
            cwd=str(workspace_path),
            input=patch_text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout_text = completed.stdout or ""
        stderr_text = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    return {
        "applied": not timed_out and returncode == 0,
        "timed_out": timed_out,
        "returncode": returncode,
        "stdout_path": stdout_path.as_posix(),
        "stderr_path": stderr_path.as_posix(),
    }


def apply_solver_test_patch(
    task: BenchmarkTaskSpec,
    workspace_path: str | Path,
    output_dir: str | Path,
    *,
    timeout_seconds: int = 120,
) -> dict[str, Any] | None:
    if not task.test_patch:
        return None
    return {
        **apply_git_patch_text(
            workspace_path,
            task.test_patch,
            Path(output_dir) / "solver-test-patch",
            timeout_seconds=timeout_seconds,
        ),
        "enabled": True,
    }


def run_evaluator_validation(
    task: BenchmarkTaskSpec,
    candidate_workspace: str | Path,
    changed_files: list[str],
    output_dir: str | Path,
    *,
    timeout_seconds: int = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
) -> PostRunValidationSummary:
    evaluator_root = Path(output_dir)
    evaluator_root.mkdir(parents=True, exist_ok=True)
    workspace_path, authoritative_workspace_path = _short_evaluator_workspace_paths(evaluator_root)
    artifact_paths = {
        "workspace_path": workspace_path.as_posix(),
        "authoritative_workspace_path": authoritative_workspace_path.as_posix(),
    }
    notes: list[str] = []
    if not task.test_patch:
        summary = PostRunValidationSummary(
            attempted=False,
            succeeded=False,
            notes=["No SWE-bench test_patch was available for authoritative evaluator validation."],
            artifact_paths=artifact_paths,
            test_patch_applied=None,
        )
        _write_json(evaluator_root / "summary.json", summary.to_dict())
        return summary

    candidate_changed_files, skipped_protected_files = filter_benchmark_protected_changed_files(
        changed_files,
        task.test_patch,
    )
    candidate_root = Path(candidate_workspace).resolve()
    if workspace_path.exists():
        shutil.rmtree(workspace_path)
    if authoritative_workspace_path.exists():
        shutil.rmtree(authoritative_workspace_path)
    shutil.copytree(candidate_root, workspace_path, symlinks=True)
    notes.append(f"Copied the prepared candidate workspace from {candidate_root.as_posix()} into the evaluator sandbox.")
    replay_report = {
        "replayed_files": list(candidate_changed_files),
        "deleted_files": [],
    }
    if skipped_protected_files:
        replay_report["skipped_protected_files"] = skipped_protected_files
    _write_json(evaluator_root / "candidate-change-replay.json", replay_report)
    artifact_paths["candidate_change_replay_path"] = (evaluator_root / "candidate-change-replay.json").as_posix()
    if replay_report["replayed_files"]:
        notes.append(f"Replayed {len(replay_report['replayed_files'])} changed file(s) into an isolated evaluator workspace.")
    if skipped_protected_files:
        notes.append(
            "Ignored candidate edits that overlapped the authoritative SWE-bench test_patch so evaluator validation stays benchmark-honest."
        )

    notes.extend(stage_workspace_snapshot(task.repo_path, authoritative_workspace_path, base_commit=task.base_commit))
    patch_report = apply_git_patch_text(
        authoritative_workspace_path,
        task.test_patch,
        evaluator_root / "test-patch",
        timeout_seconds=120,
    )
    _write_json(evaluator_root / "test-patch-apply.json", patch_report)
    artifact_paths["test_patch_apply_path"] = (evaluator_root / "test-patch-apply.json").as_posix()
    if not bool(patch_report.get("applied")):
        summary = PostRunValidationSummary(
            attempted=False,
            succeeded=False,
            notes=notes + ["Evaluator could not apply SWE-bench test_patch to the isolated workspace."],
            artifact_paths=artifact_paths,
            test_patch_applied=False,
        )
        _write_json(evaluator_root / "summary.json", summary.to_dict())
        return summary
    protected_paths = benchmark_test_patch_files(task.test_patch)
    protected_restore_report = replay_changed_workspace_files(authoritative_workspace_path, workspace_path, protected_paths)
    if protected_restore_report["replayed_files"]:
        notes.append(
            f"Restored {len(protected_restore_report['replayed_files'])} authoritative benchmark test file(s) into the evaluator workspace."
        )
    if protected_restore_report["deleted_files"]:
        notes.append(
            f"Deleted {len(protected_restore_report['deleted_files'])} protected file(s) in the evaluator workspace to match the authoritative benchmark tests."
        )

    validation_commands = detect_validation_commands(
        workspace_path,
        task.validation_commands,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
    )
    if not validation_commands:
        summary = PostRunValidationSummary(
            attempted=False,
            succeeded=False,
            notes=notes + ["Evaluator could not determine validation commands after applying SWE-bench test_patch."],
            artifact_paths=artifact_paths,
            test_patch_applied=True,
        )
        _write_json(evaluator_root / "summary.json", summary.to_dict())
        return summary

    validation_results = run_validation_commands(
        workspace_path,
        validation_commands,
        evaluator_root / "validation",
        timeout_seconds=timeout_seconds,
    )
    _write_json(
        evaluator_root / "validation-results.json",
        [item.to_dict() for item in validation_results],
    )
    artifact_paths["validation_results_path"] = (evaluator_root / "validation-results.json").as_posix()
    summary = PostRunValidationSummary(
        attempted=bool(validation_results),
        succeeded=bool(validation_results) and all(not item.timed_out and item.returncode == 0 for item in validation_results),
        commands=validation_commands,
        results=validation_results,
        notes=notes,
        artifact_paths=artifact_paths,
        test_patch_applied=True,
    )
    _write_json(evaluator_root / "summary.json", summary.to_dict())
    return summary


def _parse_json_object(text: str | None) -> tuple[dict[str, Any] | None, bool]:
    if not text:
        return None, False
    stripped = str(text).strip()
    if not stripped:
        return None, False
    try:
        payload = json.loads(stripped)
        return payload if isinstance(payload, dict) else None, False
    except json.JSONDecodeError:
        cleaned = stripped.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        candidate = match.group(0) if match else cleaned
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            payload = json.loads(candidate)
            return payload if isinstance(payload, dict) else None, True
        except json.JSONDecodeError:
            return None, True


def unwrap_nested_result_payload(payload: dict[str, Any] | None, *, max_depth: int = 3) -> tuple[dict[str, Any] | None, bool]:
    if not isinstance(payload, dict):
        return None, False
    repaired = False
    candidate = dict(payload)
    for _ in range(max_depth):
        next_candidate: dict[str, Any] | None = None
        result_value = candidate.get("result")
        if isinstance(result_value, str):
            parsed, parsed_repaired = _parse_json_object(result_value)
            if isinstance(parsed, dict):
                next_candidate = parsed
                repaired = repaired or parsed_repaired
        report_value = candidate.get("report")
        if next_candidate is None and isinstance(report_value, str):
            parsed, parsed_repaired = _parse_json_object(report_value)
            if isinstance(parsed, dict):
                next_candidate = dict(candidate)
                next_candidate["report"] = parsed
                repaired = repaired or parsed_repaired
        if next_candidate is None:
            break
        candidate = next_candidate
    return candidate, repaired


def extract_task_summary(manager_messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(manager_messages):
        if str(message.get("role") or "") != "manager":
            continue
        content = str(message.get("content_markdown") or "").strip()
        if not content:
            continue
        parsed, _ = _parse_json_object(content)
        candidate, _ = unwrap_nested_result_payload(parsed) if parsed is not None else (None, False)
        report = candidate.get("report") if isinstance(candidate, dict) else None
        if isinstance(report, dict):
            summary = str(report.get("summary") or report.get("message") or "").strip()
            if summary:
                return summary[:500]
        if isinstance(candidate, dict):
            summary = str(candidate.get("summary") or candidate.get("message") or "").strip()
            if summary:
                return summary[:500]
        if not content.startswith("{"):
            return content[:500]
    return None


def analyze_task_execution(
    tasks: list[dict[str, Any]],
    events: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> dict[str, Any]:
    event_counts = Counter(str(event.get("event_type") or "").strip() for event in events if str(event.get("event_type") or "").strip())
    retry_count = sum(max(int(task.get("failure_count") or 0), 0) for task in tasks)
    unblock_task_count = sum(1 for task in tasks if str(task.get("title") or "").startswith("Unblock:"))
    agent_failure_count = sum(max(int(agent.get("failure_count") or 0), 0) for agent in agents)
    statuses = Counter(str(task.get("status") or "").strip() for task in tasks if str(task.get("status") or "").strip())
    active_task_count = sum(
        1
        for task in tasks
        if str(task.get("status") or "").strip() in ACTIVE_TASK_STATUSES and not _task_has_superseded_waiting_reason(task)
    )
    notes: list[str] = []
    if event_counts.get("manager.parse_failed", 0):
        notes.append(f"Manager parse failures observed: {event_counts['manager.parse_failed']}.")
    if unblock_task_count:
        notes.append(f"Generated unblock follow-up tasks: {unblock_task_count}.")
    if retry_count:
        notes.append(f"Task retries recorded from failure counters: {retry_count}.")
    if active_task_count:
        notes.append(f"Harness stopped with {active_task_count} active task(s) still open.")
    return {
        "task_count": len(tasks),
        "task_status_counts": dict(sorted(statuses.items())),
        "active_task_count": active_task_count,
        "retry_count": retry_count,
        "unblock_task_count": unblock_task_count,
        "manager_parse_failures": int(event_counts.get("manager.parse_failed", 0)),
        "manager_fallback_count": int(event_counts.get("manager.mode.fallback", 0)),
        "agent_failure_count": agent_failure_count,
        "event_counts": dict(sorted(event_counts.items())),
        "notes": notes,
    }


def classify_failure_category(
    *,
    timed_out: bool,
    setup_failed: bool,
    orchestration_deadlocked: bool = False,
    patch_applied: bool,
    runner_failed: bool,
    validation_attempted: bool,
    validation_succeeded: bool,
    pending_approvals: int,
    pending_decisions: int,
    tasks_generated: int,
    task_statuses: list[str],
    manager_parse_failures: int = 0,
    retry_count: int = 0,
    unblock_task_count: int = 0,
) -> str | None:
    if setup_failed:
        return "setup_failed"
    if timed_out:
        return "timeout"
    if patch_applied and validation_attempted and not validation_succeeded:
        return "validation_failed"
    if orchestration_deadlocked:
        return "orchestration_deadlock"
    if pending_approvals > 0:
        return "approval_blocked"
    if pending_decisions > 0:
        return "pending_decision"
    if tasks_generated == 0:
        return "no_tasks_generated"
    if manager_parse_failures > 0 and not patch_applied:
        return "manager_contract_failed"
    if runner_failed:
        return "runner_failed"
    if retry_count >= 3 and not validation_succeeded:
        return "retry_exhausted"
    if unblock_task_count >= 2 and not patch_applied:
        return "retry_exhausted"
    if not patch_applied:
        return "no_patch_applied"
    if not validation_attempted:
        return "validation_not_run"
    if any(status in {"blocked", "error", "failed"} for status in task_statuses):
        return "worker_failed"
    return None


def task_flow_terminal(task_statuses: list[str]) -> bool:
    normalized = [str(status or "").strip() for status in task_statuses if str(status or "").strip()]
    return bool(normalized) and all(status in COMPLETED_TASK_FLOW_STATUSES for status in normalized)


def task_flow_completed(task_statuses: list[str], *, timed_out: bool) -> bool:
    return task_flow_terminal(task_statuses) and not timed_out


def summarize_results(results: list[BenchmarkTaskResult], *, run_label: str, generated_at: str | None = None) -> dict[str, Any]:
    total_tasks = len(results)
    attempted_tasks = sum(1 for item in results if item.attempted)
    completed_tasks = sum(1 for item in results if item.completed)
    resolved_tasks = sum(1 for item in results if item.resolved)
    resolved_with_open_tasks_count = sum(1 for item in results if item.resolved and not item.completed)
    patch_applied_tasks = sum(1 for item in results if item.patch_applied)
    validation_success_tasks = sum(1 for item in results if item.validation_succeeded)
    timeout_count = sum(1 for item in results if item.failure_category == "timeout")
    setup_failure_count = sum(1 for item in results if item.failure_category == "setup_failed")
    total_retry_count = sum(max(int(item.retry_count or 0), 0) for item in results)
    total_unblock_task_count = sum(max(int(item.unblock_task_count or 0), 0) for item in results)
    total_manager_parse_failures = sum(max(int(item.manager_parse_failures or 0), 0) for item in results)
    runtimes = [item.runtime_seconds for item in results if item.runtime_seconds > 0]
    solved_examples = [item.instance_id for item in results if item.resolved][:5]
    failed_examples = [item.instance_id for item in results if not item.resolved][:5]
    resolved_with_open_tasks_examples = [item.instance_id for item in results if item.resolved and not item.completed][:5]
    failure_categories = Counter(item.failure_category or "none" for item in results if not item.resolved)
    return {
        "summary_version": SUMMARY_VERSION,
        "run_label": run_label,
        "generated_at": generated_at or _utc_now_iso(),
        "total_tasks": total_tasks,
        "attempted_tasks": attempted_tasks,
        "completed_tasks": completed_tasks,
        "resolved_tasks": resolved_tasks,
        "resolved_with_open_tasks_count": resolved_with_open_tasks_count,
        "resolved_rate": (resolved_tasks / total_tasks) if total_tasks else 0.0,
        "resolved_rate_attempted": (resolved_tasks / attempted_tasks) if attempted_tasks else 0.0,
        "patch_applied_tasks": patch_applied_tasks,
        "patch_apply_rate": (patch_applied_tasks / attempted_tasks) if attempted_tasks else 0.0,
        "validation_success_tasks": validation_success_tasks,
        "validation_success_rate": (validation_success_tasks / attempted_tasks) if attempted_tasks else 0.0,
        "timeout_count": timeout_count,
        "setup_failure_count": setup_failure_count,
        "total_retry_count": total_retry_count,
        "total_unblock_task_count": total_unblock_task_count,
        "total_manager_parse_failures": total_manager_parse_failures,
        "average_runtime_seconds": statistics.fmean(runtimes) if runtimes else 0.0,
        "failure_categories": dict(sorted(failure_categories.items())),
        "solved_examples": solved_examples,
        "failed_examples": failed_examples,
        "resolved_with_open_tasks_examples": resolved_with_open_tasks_examples,
        "results": [item.to_dict() for item in results],
    }


def render_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Mission Control SWE-bench Lite Report",
        "",
        f"- Run label: `{summary['run_label']}`",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Total tasks: `{summary['total_tasks']}`",
        f"- Attempted tasks: `{summary['attempted_tasks']}`",
        f"- Completed tasks: `{summary['completed_tasks']}`",
        f"- Resolved tasks: `{summary['resolved_tasks']}`",
        f"- Resolved with open tasks: `{summary['resolved_with_open_tasks_count']}`",
        f"- Resolved %: `{summary['resolved_rate']:.2%}`",
        f"- Patch-apply rate: `{summary['patch_apply_rate']:.2%}`",
        f"- Validation success rate: `{summary['validation_success_rate']:.2%}`",
        f"- Timeout count: `{summary['timeout_count']}`",
        f"- Setup-failure count: `{summary['setup_failure_count']}`",
        f"- Total retry count: `{summary['total_retry_count']}`",
        f"- Total unblock-task count: `{summary['total_unblock_task_count']}`",
        f"- Total manager parse failures: `{summary['total_manager_parse_failures']}`",
        f"- Average runtime (s): `{summary['average_runtime_seconds']:.2f}`",
        "",
        "## Failure Categories",
    ]
    failure_categories = dict(summary.get("failure_categories") or {})
    if failure_categories:
        lines.extend(f"- `{name}`: `{count}`" for name, count in failure_categories.items())
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Solved Examples",
        ]
    )
    solved_examples = list(summary.get("solved_examples") or [])
    if solved_examples:
        lines.extend(f"- `{item}`" for item in solved_examples)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Failed Examples",
        ]
    )
    failed_examples = list(summary.get("failed_examples") or [])
    if failed_examples:
        lines.extend(f"- `{item}`" for item in failed_examples)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Resolved With Open Tasks",
        ]
    )
    resolved_with_open_tasks_examples = list(summary.get("resolved_with_open_tasks_examples") or [])
    if resolved_with_open_tasks_examples:
        lines.extend(f"- `{item}`" for item in resolved_with_open_tasks_examples)
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def persist_summary(output_root: str | Path, summary: dict[str, Any]) -> dict[str, str]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "summary.json"
    report_path = root / "report.md"
    _write_json(summary_path, summary)
    report_path.write_text(render_markdown_report(summary), encoding="utf-8")
    return {
        "summary_path": summary_path.as_posix(),
        "report_path": report_path.as_posix(),
    }


def run_validation_commands(
    workspace_path: str | Path,
    commands: list[str],
    output_dir: str | Path,
    *,
    timeout_seconds: int = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
) -> list[ValidationCommandResult]:
    results: list[ValidationCommandResult] = []
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    workspace_entry = str(Path(workspace_path).resolve())
    existing_pythonpath = str(environment.get("PYTHONPATH") or "").strip()
    environment["PYTHONPATH"] = (
        workspace_entry
        if not existing_pythonpath
        else os.pathsep.join([workspace_entry, existing_pythonpath])
    )
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INPUT"] = "1"
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_RETRIES"] = "0"
    for index, command in enumerate(commands, start=1):
        started = time.monotonic()
        stdout_path = root / f"validation-{index}.stdout.txt"
        stderr_path = root / f"validation-{index}.stderr.txt"
        timed_out = False
        returncode: int | None = None
        stdout_text = ""
        stderr_text = ""
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                shell=True,
                timeout=timeout_seconds,
                check=False,
                env=environment,
            )
            returncode = completed.returncode
            stdout_text = completed.stdout or ""
            stderr_text = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_text = exc.stdout or ""
            stderr_text = exc.stderr or ""
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        results.append(
            ValidationCommandResult(
                command=command,
                returncode=returncode,
                timed_out=timed_out,
                runtime_seconds=round(time.monotonic() - started, 3),
                stdout_path=stdout_path.as_posix(),
                stderr_path=stderr_path.as_posix(),
            )
        )
    return results
