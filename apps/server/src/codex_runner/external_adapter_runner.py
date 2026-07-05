from __future__ import annotations

import asyncio
import copy
import fnmatch
import json
import os
import re
import shutil
import subprocess
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle, RunnerSettings
from config import RUNTIME_LOGS_ROOT
from prompts import RUNNER_RESULT_ENVELOPE_SCHEMA, WORKER_REPORT_SCHEMA, build_prompt_profile, worker_task_prompt
from provider_support import default_label
from usage_tracking import build_prompt_usage_estimate


ADAPTER_EDIT_RESPONSE_SCHEMA = {
    **RUNNER_RESULT_ENVELOPE_SCHEMA,
    "edits": [
        {
            "path": "relative/path/from/workspace",
            "content": "full updated file content",
            "search": "exact existing text to replace when returning a surgical patch",
            "replace": "updated text for the matched block",
            "summary": "why this edit exists",
        }
    ],
}
COMPACT_ADAPTER_EDIT_RESPONSE_SCHEMA = {
    "report": {
        "agent": "worker role name",
        "task_id": "task id as string",
        "status": "done|blocked|needs_review|error",
        "summary": "what happened",
        "files_changed": ["relative/path.py"],
        "tests_run": ["python -m pytest path/to/test.py -q"],
        "blockers": ["why you are blocked"],
        "risks": ["important risk"],
        "recommended_next_task": "next concrete step",
    },
    "edits": [
        {
            "path": "relative/path/from/workspace",
            "content": "full updated file content",
            "search": "exact existing text to replace when returning a surgical patch",
            "replace": "updated text for the matched block",
            "summary": "why this edit exists",
        }
    ],
}
COMPACT_ADAPTER_SEARCH_REPLACE_RESPONSE_SCHEMA = {
    "report": {
        "agent": "worker role name",
        "task_id": "task id as string",
        "status": "done|blocked|needs_review|error",
        "summary": "what happened",
        "files_changed": ["relative/path.py"],
        "tests_run": ["python -m pytest path/to/test.py -q"],
        "blockers": ["why you are blocked"],
        "risks": ["important risk"],
        "recommended_next_task": "next concrete step",
    },
    "edits": [
        {
            "path": "relative/path/from/workspace",
            "search": "exact existing text to replace",
            "replace": "updated text for the matched block",
            "summary": "why this edit exists",
        }
    ],
}
BENCHMARK_PROTECTED_PATHS_MANIFEST = "mission-control/benchmark-protected-paths.json"


@dataclass
class ExternalAdapterRunState:
    process: asyncio.subprocess.Process | None = None
    status: str = "starting"
    events: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    logs_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    final_text: str | None = None
    reader_task: asyncio.Task | None = None
    stdin_writer_task: asyncio.Task | None = None
    exit_code: int | None = None
    effective_settings: dict[str, Any] = field(default_factory=dict)
    workspace_path: str | None = None
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    applied_edits: list[str] = field(default_factory=list)
    edit_issues: list[str] = field(default_factory=list)
    runtime_manifest_path: str | None = None
    runtime_manifest_payload: dict[str, Any] = field(default_factory=dict)
    process_timeout_seconds: float | None = None
    timeout_summary: str | None = None
    quota_contract: dict[str, Any] = field(default_factory=dict)
    quota_enforcement_status: str | None = None
    quota_blocking_reasons: list[str] = field(default_factory=list)
    task_query_text: str | None = None
    required_validation_commands: list[str] = field(default_factory=list)
    enforce_command_execution: bool = False
    editing_expected: bool = False
    scoped_workspace_baseline: dict[str, bytes] = field(default_factory=dict)
    discarded_workspace_changes: list[str] = field(default_factory=list)
    protected_paths: list[str] = field(default_factory=list)


class ExternalAdapterRunner(BaseCodexRunner):
    runner_type = "external_adapter"

    def __init__(self) -> None:
        self.runs: dict[str, ExternalAdapterRunState] = {}

    @staticmethod
    def _command_available(command: str | None) -> bool:
        normalized = str(command or "").strip()
        if not normalized:
            return False
        return shutil.which(normalized) is not None

    async def handshake(self, settings: RunnerSettings | None = None) -> bool:
        if settings is None or not settings.adapter_command:
            return False
        return self._command_available(settings.adapter_command)

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = await asyncio.to_thread(self._build_adapter_prompt, context)
        return await self._start_process(context, prompt)

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        return await self._start_process(context, message)

    async def stop_run(self, run_id: str) -> None:
        state = self.runs.get(run_id)
        if not state or not state.process:
            return
        if state.stdin_writer_task is not None:
            state.stdin_writer_task.cancel()
        state.process.terminate()
        state.status = "stopped"

    async def read_events(self, run_id: str) -> list[dict[str, Any]]:
        state = self.runs.get(run_id)
        if not state:
            return []
        events = state.events[state.cursor :]
        state.cursor = len(state.events)
        return events

    async def get_status(self, run_id: str) -> str:
        state = self.runs.get(run_id)
        return state.status if state else "error"

    @staticmethod
    def _expand_workspace_candidates(root: Path, relative: str) -> list[Path]:
        normalized = str(relative or "").strip().replace("\\", "/")
        if not normalized:
            return []
        if any(token in normalized for token in "*?[]"):
            matches: list[Path] = []
            for candidate in root.glob(normalized):
                try:
                    candidate.resolve().relative_to(root.resolve())
                except ValueError:
                    continue
                matches.append(candidate)
            return sorted(matches)
        candidate = (root / normalized).resolve() if normalized not in {"", "."} else root
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return []
        return [candidate] if candidate.exists() else []

    @classmethod
    def _iter_scoped_workspace_files(cls, root: Path, allowed: list[str]) -> list[Path]:
        scoped_files: list[Path] = []
        seen: set[str] = set()
        for relative in list(allowed or []):
            for candidate in cls._expand_workspace_candidates(root, relative):
                files = [candidate] if candidate.is_file() else sorted(path for path in candidate.rglob("*") if path.is_file())
                for file_path in files:
                    try:
                        rel_path = file_path.resolve().relative_to(root.resolve()).as_posix()
                    except ValueError:
                        continue
                    if cls._is_ephemeral_runtime_artifact(rel_path):
                        continue
                    if rel_path in seen:
                        continue
                    seen.add(rel_path)
                    scoped_files.append(file_path)
        return scoped_files

    @staticmethod
    def _is_ephemeral_runtime_artifact(path_text: str) -> bool:
        normalized = str(path_text or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            return False
        parts = [part for part in normalized.split("/") if part]
        if any(
            part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis"}
            for part in parts
        ):
            return True
        leaf = parts[-1]
        return leaf.endswith((".pyc", ".pyo"))

    @staticmethod
    def _is_mission_control_runtime_artifact(path_text: str) -> bool:
        normalized = str(path_text or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            return False
        return (
            normalized == "mission-control/TASK_BOARD.md"
            or normalized.startswith("artifacts/remote-execution-governance/")
        )

    @staticmethod
    def _baseline_scope_paths(allowed_paths: list[str], protected_paths: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for raw_path in [*(allowed_paths or []), *(protected_paths or [])]:
            normalized = str(raw_path or "").strip().replace("\\", "/").strip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @classmethod
    def _capture_scoped_workspace_baseline(
        cls,
        workspace_root: Path,
        allowed: list[str],
        *,
        protected_paths: list[str] | None = None,
    ) -> dict[str, bytes]:
        baseline: dict[str, bytes] = {}
        baseline_scope_paths = cls._baseline_scope_paths(allowed, list(protected_paths or []))
        for file_path in cls._iter_scoped_workspace_files(workspace_root, baseline_scope_paths):
            try:
                relative_path = file_path.resolve().relative_to(workspace_root.resolve()).as_posix()
            except ValueError:
                continue
            try:
                baseline[relative_path] = file_path.read_bytes()
            except OSError:
                continue
        return baseline

    @classmethod
    def _workspace_git_status_entries(cls, workspace_root: Path) -> tuple[list[tuple[str, bool]], bool]:
        try:
            probe = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(workspace_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return [], False
        if probe.returncode != 0:
            return [], False
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=str(workspace_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return [], True
        if status.returncode != 0:
            return [], True
        entries: list[tuple[str, bool]] = []
        seen: set[str] = set()
        for line in (status.stdout or "").splitlines():
            entry = line.rstrip()
            if len(entry) < 4:
                continue
            path_text = entry[3:] if entry[:2] == "??" else entry[3:]
            if " -> " in path_text:
                path_text = path_text.split(" -> ", 1)[1]
            normalized = path_text.strip().replace("\\", "/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            entries.append((normalized, entry[:2] == "??"))
        return entries, True

    @classmethod
    def _restore_out_of_scope_git_changes(
        cls,
        workspace_root: Path,
        *,
        allowed_paths: list[str],
        forbidden_paths: list[str],
    ) -> tuple[list[str], bool]:
        entries, repo_available = cls._workspace_git_status_entries(workspace_root)
        if not repo_available:
            return [], False
        restored: set[str] = set()
        tracked_paths = [
            path
            for path, is_untracked in entries
            if not is_untracked and not cls._path_is_allowed(path, allowed_paths, forbidden_paths)
        ]
        if tracked_paths:
            try:
                completed = subprocess.run(
                    ["git", "restore", "--worktree", "--source=HEAD", "--", *tracked_paths],
                    cwd=str(workspace_root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode == 0:
                    restored.update(tracked_paths)
            except (OSError, subprocess.SubprocessError):
                pass
        for relative_path, is_untracked in entries:
            if not is_untracked:
                continue
            if cls._path_is_allowed(relative_path, allowed_paths, forbidden_paths):
                continue
            ignored_ephemeral = cls._is_ephemeral_runtime_artifact(relative_path)
            ignored_runtime_artifact = cls._is_mission_control_runtime_artifact(relative_path)
            target = (workspace_root / relative_path).resolve()
            try:
                target.relative_to(workspace_root.resolve())
            except ValueError:
                continue
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                if not ignored_ephemeral and not ignored_runtime_artifact:
                    restored.add(relative_path)
            except OSError:
                continue
        return sorted(restored), True

    @classmethod
    def _restore_scoped_workspace_baseline(cls, state: ExternalAdapterRunState) -> list[str]:
        workspace_root = Path(state.workspace_path or "").resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            return []
        baseline_scope_paths = cls._baseline_scope_paths(state.allowed_paths, state.protected_paths)
        restored, _used_git_reset = cls._restore_out_of_scope_git_changes(
            workspace_root,
            allowed_paths=baseline_scope_paths,
            forbidden_paths=[],
        )
        baseline = dict(state.scoped_workspace_baseline or {})
        restored_paths: set[str] = set(restored)
        current_files = cls._iter_scoped_workspace_files(workspace_root, baseline_scope_paths)
        for file_path in current_files:
            try:
                relative_path = file_path.resolve().relative_to(workspace_root.resolve()).as_posix()
            except ValueError:
                continue
            baseline_bytes = baseline.get(relative_path)
            if baseline_bytes is None:
                try:
                    file_path.unlink()
                    restored_paths.add(relative_path)
                except OSError:
                    continue
                continue
            try:
                current_bytes = file_path.read_bytes()
            except OSError:
                current_bytes = None
            if current_bytes != baseline_bytes:
                try:
                    file_path.write_bytes(baseline_bytes)
                    restored_paths.add(relative_path)
                except OSError:
                    continue
        for relative_path, baseline_bytes in baseline.items():
            target = (workspace_root / relative_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                continue
            if target.exists():
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(baseline_bytes)
                restored_paths.add(relative_path)
            except OSError:
                continue
        return sorted(restored_paths)

    @classmethod
    def _synthesize_scoped_workspace_edits(
        cls,
        state: ExternalAdapterRunState,
    ) -> tuple[list[dict[str, str]], list[str]]:
        workspace_root = Path(state.workspace_path or "").resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            return [], []
        baseline = dict(state.scoped_workspace_baseline or {})
        baseline_scope_paths = cls._baseline_scope_paths(state.allowed_paths, state.protected_paths)
        current_files = cls._iter_scoped_workspace_files(workspace_root, baseline_scope_paths)
        current_contents: dict[str, bytes] = {}
        for file_path in current_files:
            try:
                relative_path = file_path.resolve().relative_to(workspace_root.resolve()).as_posix()
            except ValueError:
                continue
            try:
                current_contents[relative_path] = file_path.read_bytes()
            except OSError:
                continue
        changed_paths = sorted(
            {
                relative_path
                for relative_path in {*baseline.keys(), *current_contents.keys()}
                if baseline.get(relative_path) != current_contents.get(relative_path)
            }
        )
        synthesized: list[dict[str, str]] = []
        issues: list[str] = []
        for relative_path in changed_paths:
            if cls._path_is_benchmark_protected(relative_path, state.protected_paths):
                issues.append(
                    f"Mission Control rejected direct edits to benchmark-protected path: {relative_path}"
                )
                continue
            current_bytes = current_contents.get(relative_path)
            if current_bytes is None:
                issues.append(
                    f"Mission Control detected a direct deletion in {relative_path}, but deletion recovery without "
                    "accepted edits[] is not supported."
                )
                continue
            try:
                current_text = current_bytes.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(
                    f"Mission Control detected a direct binary or non-UTF-8 edit in {relative_path}, but only text "
                    "files can be recovered without accepted edits[]."
                )
                continue
            synthesized.append(
                {
                    "path": relative_path,
                    "content": current_text,
                    "summary": "Recovered from scoped workspace changes because the adapter omitted accepted edits[].",
                }
            )
        return synthesized, issues

    @staticmethod
    def _edit_path_set(edits: list[dict[str, Any]]) -> set[str]:
        paths: set[str] = set()
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            relative_path = str(edit.get("path") or "").strip().replace("\\", "/")
            if relative_path:
                paths.add(relative_path)
        return paths

    @staticmethod
    def _synthesized_workspace_drift_paths(
        state: ExternalAdapterRunState,
        synthesized_edits: list[dict[str, Any]],
    ) -> list[str]:
        workspace_root = Path(state.workspace_path or "").resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            return []
        drifted: list[str] = []
        for edit in synthesized_edits:
            if not isinstance(edit, dict):
                continue
            relative_path = str(edit.get("path") or "").strip().replace("\\", "/")
            expected_content = edit.get("content")
            if not relative_path or not isinstance(expected_content, str):
                continue
            target = (workspace_root / relative_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                continue
            try:
                current_content = target.read_text(encoding="utf-8")
            except OSError:
                drifted.append(relative_path)
                continue
            if current_content != expected_content:
                drifted.append(relative_path)
        return drifted

    @staticmethod
    def _path_matches_pattern(path_text: str, pattern_text: str) -> bool:
        normalized_path = str(path_text or "").strip().replace("\\", "/").strip("/")
        normalized_pattern = str(pattern_text or "").strip().replace("\\", "/").strip("/")
        if not normalized_path or not normalized_pattern:
            return False
        if any(token in normalized_pattern for token in "*?[]"):
            return fnmatch.fnmatch(normalized_path, normalized_pattern)
        return (
            normalized_path == normalized_pattern
            or normalized_path.startswith(f"{normalized_pattern}/")
            or normalized_pattern == "."
        )

    @classmethod
    def _load_benchmark_protected_paths(cls, workspace_root: Path) -> list[str]:
        manifest_path = workspace_root / BENCHMARK_PROTECTED_PATHS_MANIFEST
        if manifest_path.exists() and manifest_path.is_file():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            raw_paths = list(payload.get("protected_paths") or []) if isinstance(payload, dict) else []
            protected_paths = [
                str(item).strip().replace("\\", "/")
                for item in raw_paths
                if str(item).strip()
            ]
            if protected_paths:
                return protected_paths
        return cls._infer_benchmark_protected_paths_from_workspace(workspace_root)

    @classmethod
    def _infer_benchmark_protected_paths_from_workspace(cls, workspace_root: Path) -> list[str]:
        entries, repo_available = cls._workspace_git_status_entries(workspace_root)
        if not repo_available:
            return []
        inferred: list[str] = []
        for relative_path, _is_untracked in entries:
            normalized = str(relative_path or "").strip().replace("\\", "/")
            if not normalized or normalized.startswith("mission-control/"):
                continue
            parts = [part.lower() for part in normalized.split("/") if part]
            filename = parts[-1] if parts else ""
            if "tests" not in parts and not filename.startswith("test"):
                continue
            inferred.append(normalized)
        return cls._dedupe_ordered(inferred)

    @classmethod
    def _path_is_benchmark_protected(cls, path_text: str, protected_paths: list[str]) -> bool:
        return any(cls._path_matches_pattern(path_text, pattern_text) for pattern_text in protected_paths)

    @staticmethod
    def _extract_reference_paths(text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        matches = re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", text)
        references: list[str] = []
        for match in matches:
            normalized = str(match).strip().strip(",.:;()[]{}")
            if normalized:
                references.append(normalized)
        return references

    @staticmethod
    def _dedupe_ordered(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _extract_identifier_terms(text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        matches = re.findall(
            r"\b[A-Z][A-Z0-9_]{2,}\b|"
            r"\b[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]+)+\b|"
            r"\b[a-z][a-z0-9]*_[a-z0-9_]*\b",
            text,
        )
        ordered: list[str] = []
        seen: set[str] = set()
        for match in matches:
            normalized = str(match).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered[:12]

    @staticmethod
    def _extract_query_tokens(text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "into",
            "your",
            "task",
            "goal",
            "scope",
            "file",
            "files",
            "path",
            "paths",
            "test",
            "tests",
            "python",
        }
        ordered: list[str] = []
        seen: set[str] = set()
        for token in re.split(r"[^a-z0-9_]+", text.lower()):
            normalized = token.strip("_")
            if len(normalized) < 4 or normalized in stop_words or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered[:16]

    @staticmethod
    def _module_reference_candidates(root: Path, text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        matches = re.findall(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.){1,}[A-Za-z_][A-Za-z0-9_]*\b", text)
        ordered: list[str] = []
        seen: set[str] = set()
        for match in matches:
            segments = [segment for segment in match.split(".") if segment]
            if len(segments) < 2:
                continue
            candidates = [
                "/".join(segments) + ".py",
                "/".join(segments[:-1]) + ".py",
                "tests/" + "/".join(segments) + ".py",
                "tests/" + "/".join(segments[:-1]) + ".py",
            ]
            for candidate in candidates:
                if not candidate or candidate in seen:
                    continue
                if (root / candidate).exists():
                    seen.add(candidate)
                    ordered.append(candidate)
        return ordered[:12]

    def _prioritized_workspace_paths(self, root: Path, allowed: list[str], query_text: str) -> list[str]:
        identifier_terms = self._extract_identifier_terms(query_text)
        query_tokens = self._extract_query_tokens(query_text)
        candidate_files: list[tuple[int, str]] = []
        seen: set[str] = set()
        scanned = 0
        max_candidates = 200

        for relative in allowed:
            for candidate in self._expand_workspace_candidates(root, relative):
                files = [candidate] if candidate.is_file() else sorted(path for path in candidate.rglob("*") if path.is_file())
                for file_path in files:
                    rel_path = file_path.relative_to(root).as_posix()
                    if rel_path in seen:
                        continue
                    if any(part in {"__pycache__", ".git", "node_modules", ".venv", "venv", "mission-control"} for part in file_path.parts):
                        continue
                    seen.add(rel_path)
                    scanned += 1
                    rel_lower = rel_path.lower()
                    score = 0
                    for term in identifier_terms:
                        if term.lower() in rel_lower:
                            score += 40
                    for token in query_tokens:
                        if token in rel_lower:
                            score += 8
                    if score <= 0:
                        try:
                            preview_text = file_path.read_text(encoding="utf-8", errors="ignore")
                        except OSError:
                            preview_text = ""
                        if preview_text:
                            preview_lower = preview_text.lower()
                            for term in identifier_terms:
                                if term.lower() in preview_lower:
                                    score += 28
                            for token in query_tokens[:10]:
                                if token in preview_lower:
                                    score += 4
                    candidate_files.append((score, rel_path))
                    if scanned >= max_candidates:
                        break
                if scanned >= max_candidates:
                    break
            if scanned >= max_candidates:
                break

        ranked = [path for score, path in sorted(candidate_files, key=lambda item: (-item[0], item[1])) if score > 0]
        return ranked[:8]

    @classmethod
    def _ranked_excerpt_terms(cls, query_text: str, rel_path: str) -> list[str]:
        query_tokens = cls._extract_query_tokens(query_text)
        identifier_terms = cls._extract_identifier_terms(query_text)
        exact_repo_identifiers: list[str] = []
        for snippet in cls._exact_repo_match_snippets(query_text, rel_path):
            exact_repo_identifiers.extend(cls._extract_identifier_terms(snippet))
        path_terms = [
            segment
            for segment in re.split(r"[^A-Za-z0-9_]+", rel_path)
            if len(segment) >= 4 and segment.lower() not in {"tests", "docs", "models", "fields", "django"}
        ]
        weighted_terms: list[tuple[int, str]] = []
        for term in query_tokens:
            weight = 60 + min(len(term), 24)
            if "_" in term:
                weight += 80
            weighted_terms.append((weight, term))
        for term in identifier_terms:
            weight = 70 + min(len(term), 24)
            weighted_terms.append((weight, term))
        for term in exact_repo_identifiers:
            weight = 160 + min(len(term), 24)
            weighted_terms.append((weight, term))
        for term in path_terms:
            weighted_terms.append((20 + min(len(term), 24), term))
        weighted_terms.sort(key=lambda item: (-item[0], item[1].lower()))
        return cls._dedupe_ordered([term for _, term in weighted_terms])

    @staticmethod
    def _excerpt_pattern_matches(text: str, term: str) -> list[tuple[int, int, int]]:
        normalized = str(term or "").strip()
        if len(normalized) < 4:
            return []
        patterns = [
            (180, rf"\bdef\s+{re.escape(normalized)}\b"),
            (170, rf"\bclass\s+{re.escape(normalized)}\b"),
            (120, rf"\b{re.escape(normalized)}\b"),
            (80, re.escape(normalized)),
        ]
        matches: list[tuple[int, int, int]] = []
        for base_score, pattern in patterns:
            try:
                iterator = re.finditer(pattern, text, flags=re.IGNORECASE)
            except re.error:
                continue
            for match in iterator:
                matches.append((base_score, match.start(), match.end()))
                if len(matches) >= 6:
                    break
            if matches:
                break
        return matches

    @staticmethod
    def _exact_repo_match_snippets(query_text: str, rel_path: str) -> list[str]:
        normalized_path = str(rel_path or "").strip().replace("\\", "/")
        if not normalized_path:
            return []
        pattern = re.compile(
            rf"{re.escape(normalized_path)}:\d+:\s*(.+?)(?=(?:\s+[A-Za-z0-9_./-]+:\d+:)|(?:\r?\n)|$)",
            flags=re.IGNORECASE,
        )
        snippets: list[str] = []
        for match in pattern.finditer(str(query_text or "")):
            snippet = str(match.group(1) or "").strip()
            if len(snippet) >= 8:
                snippets.append(snippet)
        return ExternalAdapterRunner._dedupe_ordered(snippets)

    @classmethod
    def _enclosing_code_symbol_start(cls, text: str, position: int, *, max_lookback: int = 2400) -> int | None:
        start = max(0, int(position) - max_lookback)
        prefix = text[start:int(position)]
        matches = list(re.finditer(r"(?m)^[ \t]*(?:def|class)\s+[A-Za-z_][A-Za-z0-9_]*", prefix))
        if not matches:
            return None
        return start + matches[-1].start()

    @classmethod
    def _targeted_file_excerpt(
        cls,
        text: str,
        *,
        query_text: str,
        rel_path: str,
        max_chars: int = 4000,
    ) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        ranked_terms = cls._ranked_excerpt_terms(query_text, rel_path)
        exact_match_snippets = cls._exact_repo_match_snippets(query_text, rel_path)
        scored_matches: list[tuple[int, int, int]] = []
        for snippet in exact_match_snippets[:4]:
            for start in cls._search_positions(text, snippet):
                scored_matches.append((400, start, start + len(snippet)))
                if len(scored_matches) >= 12:
                    break
            if len(scored_matches) >= 12:
                break
        for index, term in enumerate(ranked_terms):
            term_bonus = max(0, 120 - (index * 8))
            for base_score, start, end in cls._excerpt_pattern_matches(text, term):
                scored_matches.append((base_score + term_bonus, start, end))
            if len(scored_matches) >= 16:
                break
        if not scored_matches:
            return text[:max_chars], True

        scored_matches.sort(key=lambda item: (-item[0], item[1]))
        selected_ranges: list[tuple[int, int]] = []
        for _, start, end in scored_matches:
            line_start = text.rfind("\n", 0, start)
            if line_start < 0:
                line_start = 0
            else:
                line_start += 1
            symbol_start = cls._enclosing_code_symbol_start(text, line_start)
            window_start = symbol_start if symbol_start is not None else max(0, line_start - 160)
            blank_line_markers = [
                ("\n\n", 2),
                ("\r\n\r\n", 4),
            ]
            for marker, marker_len in blank_line_markers:
                last_blank_line = text.rfind(marker, window_start, line_start)
                if last_blank_line >= 0:
                    window_start = max(window_start, last_blank_line + marker_len)
            window_end = min(len(text), end + 1000)
            if any(abs(window_start - existing_start) < 300 for existing_start, _ in selected_ranges):
                continue
            selected_ranges.append((window_start, window_end))
            if len(selected_ranges) >= 4:
                break
        if not selected_ranges:
            return text[:max_chars], True

        selected_ranges.sort()
        merged_ranges: list[list[int]] = []
        for start, end in selected_ranges:
            if not merged_ranges or start > merged_ranges[-1][1] + 120:
                merged_ranges.append([start, end])
                continue
            merged_ranges[-1][1] = max(merged_ranges[-1][1], end)

        parts: list[str] = []
        used_chars = 0
        for index, (start, end) in enumerate((tuple(item) for item in merged_ranges)):
            prefix = "\n... [omitted unrelated lines] ...\n" if index > 0 else ""
            available = max_chars - used_chars - len(prefix)
            if available <= 0:
                break
            excerpt = text[start:end]
            if len(excerpt) > available:
                excerpt = excerpt[:available]
            if not excerpt:
                continue
            parts.append(prefix + excerpt)
            used_chars += len(prefix) + len(excerpt)
            if used_chars >= max_chars:
                break

        excerpt_text = "".join(parts).strip("\n")
        if not excerpt_text:
            return text[:max_chars], True
        return excerpt_text, True

    @staticmethod
    def _line_window_excerpt(text: str, start: int, end: int, *, context_lines: int = 4) -> str:
        normalized = str(text or "")
        line_starts = [0]
        for match in re.finditer(r"\n", normalized):
            line_starts.append(match.end())
        line_ranges: list[tuple[int, int]] = []
        for index, line_start in enumerate(line_starts):
            line_end = line_starts[index + 1] - 1 if index + 1 < len(line_starts) else len(normalized)
            line_ranges.append((line_start, line_end))
        target_indexes = [
            index
            for index, (line_start, line_end) in enumerate(line_ranges)
            if not (line_end <= start or line_start >= end)
        ]
        if not target_indexes:
            return normalized[max(0, start - 160) : min(len(normalized), end + 240)].strip()
        first_index = max(0, target_indexes[0] - context_lines)
        last_index = min(len(line_ranges) - 1, target_indexes[-1] + context_lines)
        excerpt_start = line_ranges[first_index][0]
        excerpt_end = line_ranges[last_index][1]
        return normalized[excerpt_start:excerpt_end].strip("\n")

    @staticmethod
    def _line_number_excerpt(text: str, line_number: int, *, context_lines: int = 6) -> str:
        normalized = str(text or "")
        if line_number <= 0:
            return normalized[:800].strip("\n")
        lines = normalized.splitlines()
        if not lines:
            return ""
        target_index = min(max(line_number - 1, 0), len(lines) - 1)
        start_index = max(0, target_index - context_lines)
        end_index = min(len(lines), target_index + context_lines + 1)
        return "\n".join(lines[start_index:end_index]).strip("\n")

    @staticmethod
    def _definition_block_excerpt(
        text: str,
        line_number: int,
        *,
        max_lines: int = 80,
        max_chars: int = 2200,
    ) -> str:
        normalized = str(text or "")
        if line_number <= 0:
            return normalized[:max_chars].strip("\n")
        lines = normalized.splitlines()
        if not lines:
            return ""
        start_index = min(max(line_number - 1, 0), len(lines) - 1)
        header = lines[start_index]
        stripped_header = header.lstrip(" \t")
        if not stripped_header.startswith(("def ", "async def ", "class ")):
            return ExternalAdapterRunner._line_number_excerpt(normalized, line_number, context_lines=10)
        header_indent = len(header) - len(stripped_header)
        selected: list[str] = []
        used_chars = 0
        body_started = False
        for index in range(start_index, len(lines)):
            line = lines[index]
            stripped = line.lstrip(" \t")
            current_indent = len(line) - len(stripped)
            if index > start_index and stripped:
                if body_started and current_indent <= header_indent and stripped.startswith(("def ", "async def ", "class ")):
                    break
                body_started = True
            projected = used_chars + len(line) + (1 if selected else 0)
            if projected > max_chars:
                break
            selected.append(line)
            used_chars = projected
            if len(selected) >= max_lines:
                break
        excerpt = "\n".join(selected).strip("\n")
        return excerpt or ExternalAdapterRunner._line_number_excerpt(normalized, line_number, context_lines=10)

    @staticmethod
    def _query_focus_symbol_names(text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        patterns = (
            re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)\s*\([^`]*\)`"),
            re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`"),
            re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
            re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b"),
            re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+(?:helper|function)\b", re.IGNORECASE),
            re.compile(r"\b(?:helper|function)\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE),
        )
        banned = {
            "actual",
            "python",
            "different",
            "exact",
            "true",
            "false",
            "none",
            "task",
            "requirements",
            "implementation",
            "validation",
            "command",
            "issue",
            "live",
            "logic",
            "model",
            "compoundmodels",
            "provided",
            "signatures",
            "workspace",
        }
        ranked: list[tuple[int, int, str]] = []
        seen: set[str] = set()
        for index, pattern in enumerate(patterns):
            for match in pattern.finditer(text):
                symbol = str(match.group(1) or "").strip()
                lowered = symbol.lower()
                if not symbol or lowered in banned or lowered in seen:
                    continue
                if index >= 3 and "_" not in symbol and not any(char.isupper() for char in symbol):
                    continue
                seen.add(lowered)
                score = 0
                if index == 0:
                    score += 20
                elif index == 1:
                    score += 16
                elif index == 2:
                    score += 12
                else:
                    score += 8
                if symbol.startswith("_"):
                    score += 40
                elif "_" in symbol:
                    score += 16
                if any(char.isupper() for char in symbol):
                    score += 4
                context_window = text[max(0, match.start() - 90) : min(len(text), match.end() + 90)].lower()
                if "helper" in context_window:
                    score += 18
                if any(
                    marker in context_window
                    for marker in (
                        "same-file helper",
                        "patch this same-file helper first",
                        "inspect and patch",
                        "patch the `",
                        "patch `_",
                    )
                ):
                    score += 24
                if "instead of patching" in context_window or "instead of changing" in context_window:
                    score += 10
                ranked.append((-score, match.start(), symbol))
        ranked.sort()
        return [symbol for _score, _position, symbol in ranked]

    @staticmethod
    def _find_symbol_definition_line(text: str, symbol: str) -> int | None:
        if not text or not symbol:
            return None
        pattern = re.compile(rf"^[ \t]*(?:def|async def|class)\s+{re.escape(symbol)}\b", re.MULTILINE)
        match = pattern.search(text)
        if not match:
            return None
        return text[: match.start()].count("\n") + 1

    @staticmethod
    def _definition_name_from_snippet(snippet: str | None) -> str | None:
        normalized = str(snippet or "").strip()
        if not normalized:
            return None
        first_line = normalized.splitlines()[0].strip()
        match = re.match(r"^(?:def|async def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", first_line)
        if not match:
            return None
        return str(match.group(1) or "").strip() or None

    @classmethod
    def _definition_block_for_symbol(
        cls,
        text: str,
        symbol: str,
        *,
        max_chars: int = 3200,
        max_lines: int = 100,
    ) -> str:
        if not text or not symbol:
            return ""
        pattern = re.compile(rf"^\s*(?:def|async def|class)\s+{re.escape(symbol)}\b", re.MULTILINE)
        match = pattern.search(text)
        if not match:
            return ""
        lines = text.splitlines()
        start_index = text[: match.start()].count("\n")
        if start_index < 0 or start_index >= len(lines):
            return ""
        header_line = lines[start_index]
        header_indent = len(header_line) - len(header_line.lstrip(" \t"))
        selected: list[str] = []
        used_chars = 0
        body_started = False
        for index in range(start_index, len(lines)):
            line = lines[index]
            stripped = line.lstrip(" \t")
            current_indent = len(line) - len(stripped)
            if index > start_index and stripped:
                if body_started and current_indent <= header_indent and stripped.startswith(("def ", "async def ", "class ")):
                    break
                body_started = True
            projected = used_chars + len(line) + (1 if selected else 0)
            if projected > max_chars:
                break
            selected.append(line)
            used_chars = projected
            if len(selected) >= max_lines:
                break
        return "\n".join(selected).strip("\n")

    @classmethod
    def _same_file_helper_callee_symbols(
        cls,
        text: str,
        symbol_line: int,
    ) -> list[tuple[str, int]]:
        excerpt = cls._definition_block_excerpt(text, symbol_line, max_chars=3200, max_lines=100)
        if not excerpt.strip():
            return []
        current_symbol = cls._definition_name_from_snippet(excerpt)
        call_symbols = cls._dedupe_ordered(
            [
                str(match.group(1) or "").strip()
                for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", excerpt)
                if str(match.group(1) or "").strip()
            ]
        )
        ignored = {
            current_symbol or "",
            "if",
            "for",
            "while",
            "return",
            "isinstance",
            "len",
            "range",
            "list",
            "dict",
            "set",
            "tuple",
            "int",
            "str",
            "bool",
            "float",
            "np",
        }
        ranked: list[tuple[int, str, int]] = []
        for symbol in call_symbols:
            if symbol in ignored:
                continue
            definition_line = cls._find_symbol_definition_line(text, symbol)
            if definition_line is None:
                continue
            score = 0
            if symbol.startswith("_"):
                score += 100
            if "_" in symbol:
                score += 20
            ranked.append((score, symbol, definition_line))
        ranked.sort(key=lambda item: (-item[0], item[2], item[1].lower()))
        return [(symbol, definition_line) for _, symbol, definition_line in ranked]

    @staticmethod
    def _query_line_anchors(text: str | None) -> list[tuple[str, int, str]]:
        if not isinstance(text, str) or not text.strip():
            return []
        anchors: list[tuple[str, int, str]] = []
        seen: set[tuple[str, int, str]] = set()
        pattern = re.compile(r"([A-Za-z0-9_.\-/]+):(\d+):\s*([^\n]+)")
        for match in pattern.finditer(text):
            rel_path = str(match.group(1) or "").strip().replace("\\", "/")
            line_number = int(match.group(2))
            snippet = str(match.group(3) or "").strip()
            normalized = (rel_path, line_number, snippet)
            if not rel_path or line_number <= 0 or normalized in seen:
                continue
            seen.add(normalized)
            anchors.append(normalized)
        return anchors

    @staticmethod
    def _top_level_definition_names(text: str | None) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        return ExternalAdapterRunner._dedupe_ordered(
            [
                str(match.group(1) or "").strip()
                for match in re.finditer(r"^\s*(?:def|async def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", text, flags=re.MULTILINE)
                if str(match.group(1) or "").strip()
            ]
        )

    @staticmethod
    def _exported_symbol_names(text: str | None) -> set[str]:
        normalized = str(text or "")
        if not normalized.strip():
            return set()
        exported: set[str] = set()
        for match in re.finditer(r"__all__\s*=\s*\[(.*?)\]", normalized, flags=re.DOTALL):
            body = str(match.group(1) or "")
            for symbol_match in re.finditer(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", body):
                symbol = str(symbol_match.group(1) or "").strip()
                if symbol:
                    exported.add(symbol)
        return exported

    @classmethod
    def _anchored_symbol_names(cls, query_text: str | None, relative_path: str) -> set[str]:
        symbols: set[str] = set()
        normalized_path = str(relative_path or "").strip().replace("\\", "/")
        if not normalized_path:
            return symbols
        for anchor_path, _line_number, snippet in cls._query_line_anchors(query_text):
            if anchor_path != normalized_path:
                continue
            symbol = cls._definition_name_from_snippet(snippet)
            if symbol:
                symbols.add(symbol)
        return symbols

    @classmethod
    def _renames_protected_definition(
        cls,
        *,
        relative_path: str,
        existing_text: str,
        updated_text: str,
        query_text: str | None,
    ) -> tuple[bool, str | None]:
        existing_defs = set(cls._top_level_definition_names(existing_text))
        updated_defs = set(cls._top_level_definition_names(updated_text))
        removed_defs = existing_defs - updated_defs
        added_defs = updated_defs - existing_defs
        protected_defs = cls._exported_symbol_names(existing_text) | cls._anchored_symbol_names(query_text, relative_path)
        removed_protected = sorted(symbol for symbol in removed_defs if symbol in protected_defs)
        if not removed_protected or not added_defs:
            return False, None
        return (
            True,
            f"Rejected edit that renames anchored or exported top-level symbol(s) in {relative_path}: {', '.join(removed_protected[:4])}.",
        )

    @classmethod
    def _bypasses_anchored_same_file_helper(
        cls,
        *,
        relative_path: str,
        existing_text: str,
        updated_text: str,
        query_text: str | None,
    ) -> tuple[bool, str | None]:
        normalized_path = str(relative_path or "").strip().replace("\\", "/")
        query_anchors = [anchor for anchor in cls._query_line_anchors(query_text) if anchor[0] == normalized_path]
        if not query_anchors:
            return False, None
        anchor_line, anchor_snippet = query_anchors[0][1], query_anchors[0][2]
        anchor_name = cls._definition_name_from_snippet(anchor_snippet)
        if not anchor_name:
            return False, None
        existing_anchor_line = cls._find_symbol_definition_line(existing_text, anchor_name)
        updated_anchor_line = cls._find_symbol_definition_line(updated_text, anchor_name)
        if existing_anchor_line is None or updated_anchor_line is None:
            return False, None
        helper_candidates = cls._same_file_helper_callee_symbols(existing_text, existing_anchor_line)
        if not helper_candidates:
            return False, None
        helper_symbol, helper_line = helper_candidates[0]
        existing_anchor_excerpt = cls._definition_block_for_symbol(existing_text, anchor_name, max_chars=3200, max_lines=100)
        updated_anchor_excerpt = cls._definition_block_for_symbol(updated_text, anchor_name, max_chars=3200, max_lines=100)
        if f"{helper_symbol}(" not in existing_anchor_excerpt or f"{helper_symbol}(" in updated_anchor_excerpt:
            return False, None
        updated_helper_line = cls._find_symbol_definition_line(updated_text, helper_symbol)
        if updated_helper_line is None:
            return False, None
        existing_helper_excerpt = cls._definition_block_for_symbol(existing_text, helper_symbol, max_chars=3200, max_lines=100)
        updated_helper_excerpt = cls._definition_block_for_symbol(updated_text, helper_symbol, max_chars=3200, max_lines=100)
        if existing_helper_excerpt == updated_helper_excerpt:
            return (
                True,
                f"Rejected edit that bypasses same-file helper `{helper_symbol}` from anchored definition `{anchor_name}` in {relative_path}; patch the helper logic instead of replacing its call site.",
            )
        return False, None

    def _exact_live_edit_anchor_markdown(self, context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return ""
        allowed = list(task.allowed_paths_json or [])
        if not allowed:
            return ""
        root = Path(self.effective_workspace_path(context)).resolve()
        if not root.exists() or not root.is_dir():
            return ""
        query_text = self._task_query_text(context)
        anchors: list[tuple[str, str]] = []
        for relative in self._prioritized_workspace_paths(root, allowed, query_text):
            if len(anchors) >= 2:
                break
            for candidate in self._expand_workspace_candidates(root, relative):
                if len(anchors) >= 2:
                    break
                if not candidate.is_file():
                    continue
                rel_path = candidate.relative_to(root).as_posix()
                snippets = self._exact_repo_match_snippets(query_text, rel_path)
                if not snippets:
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
                for snippet in snippets[:2]:
                    positions = self._search_positions(text, snippet)
                    if not positions:
                        continue
                    position = positions[0]
                    excerpt = self._line_window_excerpt(text, position, position + len(snippet))
                    if excerpt:
                        anchors.append((rel_path, excerpt))
                    if len(anchors) >= 2:
                        break
        if not anchors:
            return ""
        lines = [
            "Exact live edit anchors:",
            "- Copy search text exactly from these live workspace lines if you return search/replace edits.",
            "- Never shorten identifiers or invent abbreviated code such as `self.o`.",
        ]
        for rel_path, excerpt in anchors:
            lines.append(f"\nFILE: {rel_path}\n```text\n{excerpt}\n```")
        return "\n".join(lines)

    def _live_symbol_presence_records(
        self,
        root: Path,
        allowed: list[str],
        query_text: str | None,
    ) -> list[tuple[str, str, int, str]]:
        if not allowed or not root.exists() or not root.is_dir():
            return []
        focus_symbols = self._query_focus_symbol_names(query_text)
        if not focus_symbols:
            for _rel_path, _line_number, snippet in self._query_line_anchors(query_text):
                symbol = self._definition_name_from_snippet(snippet)
                if symbol and symbol not in focus_symbols:
                    focus_symbols.append(symbol)
        if not focus_symbols:
            return []
        records: list[tuple[str, str, int, str]] = []
        seen: set[tuple[str, str]] = set()
        candidate_paths = self._dedupe_ordered(
            [
                *self._prioritized_workspace_paths(root, allowed, str(query_text or "")),
                *allowed,
            ]
        )
        for relative in candidate_paths:
            for candidate in self._expand_workspace_candidates(root, relative):
                if not candidate.is_file():
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if not text.strip():
                    continue
                rel_path = candidate.relative_to(root).as_posix()
                lines = text.splitlines()
                for symbol in focus_symbols:
                    symbol_line = self._find_symbol_definition_line(text, symbol)
                    if symbol_line is None:
                        continue
                    header = lines[symbol_line - 1].strip() if 0 < symbol_line <= len(lines) else f"def {symbol}"
                    key = (rel_path, symbol.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append((rel_path, symbol, symbol_line, header))
        return records

    def _live_symbol_presence_markdown(self, context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return ""
        allowed = list(task.allowed_paths_json or [])
        if not allowed:
            return ""
        root = Path(self.effective_workspace_path(context)).resolve()
        records = self._live_symbol_presence_records(root, allowed, self._task_query_text(context))
        if not records:
            return ""
        lines = [
            "Authoritative live symbol presence:",
            "- Treat these as verified facts from the current workspace.",
            "- If a report claims one of these symbols is missing from the allowed file, a blocker that says it is missing is invalid.",
        ]
        for rel_path, _symbol, symbol_line, header in records[:4]:
            lines.append(f"- `{rel_path}` contains `{header}` at line {symbol_line}.")
        return "\n".join(lines)

    def _scoped_live_file_focus_markdown(self, context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return ""
        root = Path(self.effective_workspace_path(context)).resolve()
        if not root.exists() or not root.is_dir():
            return ""
        allowed = list(task.allowed_paths_json or [])
        if not allowed:
            return ""
        query_text = self._task_query_text(context)
        candidate_paths = self._dedupe_ordered(
            [
                *self._prioritized_workspace_paths(root, allowed, query_text),
                *allowed,
            ]
        )
        for relative in candidate_paths:
            for candidate in self._expand_workspace_candidates(root, relative):
                if not candidate.is_file():
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if not text.strip():
                    continue
                rel_path = candidate.relative_to(root).as_posix()
                focus_symbols = self._query_focus_symbol_names(query_text)
                for symbol in focus_symbols:
                    symbol_line = self._find_symbol_definition_line(text, symbol)
                    if symbol_line is None:
                        continue
                    excerpt = self._definition_block_excerpt(text, symbol_line)
                    if excerpt.strip():
                        helper_sections = ""
                        helper_candidates = self._same_file_helper_callee_symbols(text, symbol_line)
                        if helper_candidates:
                            helper_symbol, helper_line = helper_candidates[0]
                            helper_excerpt = self._definition_block_excerpt(text, helper_line)
                            if helper_excerpt.strip():
                                helper_sections = (
                                    "\n"
                                    "- This live definition calls the same-file helper shown below; inspect it before changing downstream wrappers or final normalization.\n"
                                    f"FILE: {rel_path} (same-file helper `{helper_symbol}`)\n```text\n{helper_excerpt}\n```"
                                )
                        return (
                            "Scoped live file focus:\n"
                            "- Start from this allowed file before proposing a retarget.\n"
                            "- The excerpt below is centered on the same-file helper or function explicitly named in the retry context.\n"
                            "- If this helper exists in the live file, patch it directly before falling back to downstream wrappers.\n"
                            f"FILE: {rel_path}\n```text\n{excerpt}\n```"
                            f"{helper_sections}"
                        )
                query_anchors = [
                    anchor
                    for anchor in self._query_line_anchors(query_text)
                    if anchor[0] == rel_path
                ]
                if query_anchors:
                    anchor_line, anchor_snippet = query_anchors[0][1], query_anchors[0][2]
                    if str(anchor_snippet).lstrip(" \t").startswith(("def ", "async def ", "class ")):
                        excerpt = self._definition_block_excerpt(text, anchor_line)
                    else:
                        excerpt = self._line_number_excerpt(text, anchor_line, context_lines=10)
                    if excerpt.strip():
                        helper_sections = ""
                        if str(anchor_snippet).lstrip(" \t").startswith(("def ", "async def ", "class ")):
                            helper_candidates = self._same_file_helper_callee_symbols(text, anchor_line)
                            if helper_candidates:
                                helper_symbol, helper_line = helper_candidates[0]
                                helper_excerpt = self._definition_block_excerpt(text, helper_line)
                                if helper_excerpt.strip():
                                    helper_sections = (
                                        "\n"
                                        "- The anchored live definition calls this same-file helper; inspect it before changing downstream wrappers or final normalization.\n"
                                        f"FILE: {rel_path} (same-file helper `{helper_symbol}`)\n```text\n{helper_excerpt}\n```"
                                    )
                        return (
                            "Scoped live file focus:\n"
                            "- Start from this allowed file before proposing a retarget.\n"
                            "- The excerpt below is centered on the explicit live implementation anchor from the task.\n"
                            "- If the anchor is a function or class definition, the excerpt includes its live body so you can patch inside it instead of inventing a replacement shell.\n"
                            f"FILE: {rel_path}\n```text\n{excerpt}\n```"
                            f"{helper_sections}"
                        )
                excerpt, _used_targeted_excerpt = self._targeted_file_excerpt(
                    text,
                    query_text=query_text,
                    rel_path=rel_path,
                    max_chars=1400,
                )
                if not excerpt.strip():
                    continue
                return (
                    "Scoped live file focus:\n"
                    "- Start from this allowed file before proposing a retarget.\n"
                    f"FILE: {rel_path}\n```text\n{excerpt}\n```"
                )
        return ""

    @staticmethod
    def _issue_fix_clue_markdown(context: RunnerContext) -> str:
        idea = str(getattr(context.project, "idea", "") or "")
        if not idea:
            return ""
        lines = idea.splitlines()
        collected: list[str] = []
        capture = False
        for raw_line in lines:
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if not capture and any(marker in lowered for marker in ("quick fix", "quick/temporal fix", "quick/temporary fix", "workaround")):
                capture = True
                continue
            if capture and (
                not stripped
                or lowered.startswith(("note:", "example of my query", "workspace clues:", "hints:", "focused reproduction commands:"))
            ):
                break
            if capture and any(token in stripped for token in ("=", "(", ")", "[", "]", "split", "search", "sql")):
                collected.append(stripped)
            if len(collected) >= 3:
                break
        collected = ExternalAdapterRunner._dedupe_ordered(collected)
        if not collected:
            return ""
        return (
            "Issue-provided fix clues:\n"
            "- Prefer concrete transformation hints already present in the issue when they fit the live file.\n"
            "- Do not invent unrelated string-contains heuristics if the issue already points to a narrower normalization fix.\n"
            "```text\n"
            + "\n".join(collected)
            + "\n```"
        )

    @staticmethod
    def _issue_named_symbol_markdown(context: RunnerContext) -> str:
        task = getattr(context, "task", None)
        candidate_texts = [
            str(getattr(context.project, "idea", "") or ""),
            str(getattr(task, "title", "") or ""),
            str(getattr(task, "goal", "") or ""),
            str(getattr(task, "scope", "") or ""),
        ]
        symbols = ExternalAdapterRunner._dedupe_ordered(
            [
                str(match.group(1) or "").strip()
                for text in candidate_texts
                for match in re.finditer(r"`([A-Za-z_][A-Za-z0-9_]*)`", text)
                if str(match.group(1) or "").strip().lower() not in {"true", "false", "none", "python"}
            ]
        )
        if not symbols:
            return ""
        lines = [
            "Issue-named primary symbols:",
            *[f"- `{symbol}`" for symbol in symbols[:3]],
            "- If one of these symbols already exists in the allowed file or exact live anchors below, start there unless stronger same-file live evidence points to a sibling helper or return path.",
            "- Do not switch to a different helper in the same file unless exact failing evidence, retry evidence, or neighboring same-file anchors show the issue-named symbol delegates incorrectly there.",
            "- Do not invent a new internal helper-call chain unless the live file already shows that helper signature and argument count.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _same_file_anchor_markdown(context: RunnerContext) -> str:
        task = getattr(context, "task", None)
        if task is None:
            return ""
        allowed = [str(path).strip().replace("\\", "/") for path in list(task.allowed_paths_json or []) if str(path).strip()]
        if not allowed:
            return ""
        grouped: dict[str, list[tuple[int, str]]] = {}
        for rel_path, line_number, snippet in ExternalAdapterRunner._query_line_anchors(ExternalAdapterRunner._task_query_text(context)):
            grouped.setdefault(rel_path, []).append((line_number, snippet))
        for allowed_path in allowed:
            anchors = grouped.get(allowed_path) or []
            if len(anchors) < 2:
                continue
            lines = [
                "Same-file implementation anchors:",
                *[
                    f"- `{allowed_path}:{line_number}: {snippet}`"
                    for line_number, snippet in anchors[:4]
                ],
                "- If a prior patch in one of these anchors leaves the original FAIL_TO_PASS targets failing, inspect the other same-file anchors before repeating the same logic.",
                "- A benchmark issue may be named after one symbol while the minimal fix lives in a sibling helper or return path in the same file.",
                "- The signatures shown above are exact live signatures. Do not guess helper arity or compose those helpers into a new call chain unless the live file already uses that exact pattern.",
            ]
            return "\n".join(lines)
        return ""

    @staticmethod
    def _model_specific_adapter_note(model: str | None) -> str:
        lowered = (model or "").lower()
        if any(marker in lowered for marker in ("qwen", "llama", "gemma", "deepseek-r1")):
            return (
                "Model-specific reminder: weak local models often explain edits in prose instead of emitting them. "
                "Do not do that here. If you report a finished implementation step, include edits[]. "
                "On an implementation retry, a reproduce-only answer is a failure unless you cite exact scoped blocker evidence."
            )
        if "gpt-oss" in lowered or "coder" in lowered or "codestral" in lowered:
            return "Model-specific reminder: prefer a single minimal edit set over speculative cleanup."
        return "Model-specific reminder: stay literal and match the schema exactly."

    @staticmethod
    def _adapter_examples() -> str:
        return (
            "Example values below are placeholders only. Never reuse the example filenames, summaries, or commands "
            "unless they match the actual workspace evidence.\n\n"
            "Valid example for a reproduce-or-validate task with no file edits:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Validation Specialist",\n'
            '    "task_id": "1",\n'
            '    "status": "done",\n'
            '    "summary": "Reproduced the failure in <relevant/test/path> and isolated <relevant/code/path> as the broken path.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": ["python -m pytest <relevant/test/path> -q"],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Implement the smallest safe code fix."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n\n'
            "Valid example when you really changed a file:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "done",\n'
            '    "summary": "Fixed the targeted implementation change and kept the diff scoped.",\n'
            '    "files_changed": ["<allowed/code/path>"],\n'
            '    "tests_run": ["python -m pytest <relevant/test/path> -q"],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Re-run focused validation."\n'
            '  },\n'
            '  "edits": [\n'
            '    {\n'
            '      "path": "<allowed/code/path>",\n'
            '      "content": "def apply_fix(value):\\n    return value.strip()\\n"\n'
            '    }\n'
            '  ]\n'
            '}\n\n'
            "Valid example when a large file only needs a small targeted patch:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "done",\n'
            '    "summary": "Updated the ordering logic with a targeted replacement instead of rewriting the whole file.",\n'
            '    "files_changed": ["<allowed/code/path>"],\n'
            '    "tests_run": [],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Re-run focused validation."\n'
            '  },\n'
            '  "edits": [\n'
            '    {\n'
            '      "path": "<allowed/code/path>",\n'
            '      "search": "if old_flag:\\n    return legacy_value\\nreturn fallback_value",\n'
            '      "replace": "if old_flag:\\n    return normalized_value\\nreturn fallback_value"\n'
            '    }\n'
            '  ]\n'
            '}\n\n'
            "Valid example when you cannot safely complete the task:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "needs_review",\n'
            '    "summary": "I could not determine a safe edit from the available workspace evidence.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": [],\n'
            '    "blockers": [],\n'
            '    "risks": ["Need clearer evidence before editing."],\n'
            '    "recommended_next_task": "Clarify the failing behavior or inspect more files."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n\n'
            "Valid example for an implementation task that returns empty edits only because the scoped path is proven wrong:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "blocked",\n'
            '    "summary": "Did not edit src/target.py because the scoped file never defines `build_target` and the only implementation definition in the repo is in src/other_module.py.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": ["python -m pytest <relevant/test/path> -q"],\n'
            '    "blockers": ["Scoped file src/target.py does not contain the failing implementation symbol; repo evidence points to src/other_module.py."],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Retarget the implementation task to src/other_module.py."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n\n'
            "Invalid example that must be rejected:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "done",\n'
            '    "summary": "Fixed the bug.",\n'
            '    "files_changed": ["<allowed/code/path>"],\n'
            '    "tests_run": [],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Run validation."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n'
            "Why invalid: it claims a completed code change without any concrete edit payload.\n\n"
            "Also invalid for an implementation retry:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "blocked",\n'
            '    "summary": "Reproduced the failing test again and need more investigation.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": ["python -m pytest <relevant/test/path> -q"],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Investigate more."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n'
            "Why invalid: on an implementation retry it only re-runs a known failing command and returns no edit plus no exact scoped blocker evidence.\n\n"
            "Also invalid when live anchors contradict the blocker:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "blocked",\n'
            '    "summary": "Did not edit src/target.py because the only implementation definition is in tests/test_target.py.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": ["python -m pytest tests/test_target.py -q"],\n'
            '    "blockers": ["Scoped file src/target.py does not contain the failing implementation symbol; repo evidence points to tests/test_target.py."],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Retarget the implementation task to tests/test_target.py."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n'
            "Why invalid: if the prompt already showed an exact live anchor such as `src/target.py:12: def build_target(...)`, the scoped file clearly contains the implementation symbol and the blocker contradicts the workspace evidence."
        )

    def _adapter_examples_for_context(self, context: RunnerContext) -> str:
        if self._uses_compact_worker_prompt(context):
            if self._requires_search_replace_only(context):
                return (
                    "Compact local-model JSON reminders:\n"
                    "- Return exactly one or a few surgical search/replace edits inside the allowed file.\n"
                    "- Do not return full-file content for this task.\n"
                    "- Copy the search text exactly from the live workspace snippet.\n"
                    "- If the live scoped file already shows the target function or anchor line, a blocker that says the symbol is missing is invalid."
                )
            return (
                "Compact local-model JSON reminders:\n"
                "- Do not reuse any placeholder filenames, commands, or summaries from generic examples.\n"
                "- For implementation tasks, return concrete edits[] or exact scoped blocker evidence from the allowed file.\n"
                "- Treat task-provided `path:line:symbol` anchors as approximate locators; if the live scoped file shows the same function at a different line, patch that live definition.\n"
                "- If the live scoped file already shows the target function or anchor line, a blocker that says the symbol is missing is invalid."
            )
        return self._adapter_examples()

    def _response_schema_for_context(self, context: RunnerContext) -> dict[str, Any]:
        if self._requires_search_replace_only(context):
            return COMPACT_ADAPTER_SEARCH_REPLACE_RESPONSE_SCHEMA
        if self._uses_compact_worker_prompt(context):
            return COMPACT_ADAPTER_EDIT_RESPONSE_SCHEMA
        return ADAPTER_EDIT_RESPONSE_SCHEMA

    @classmethod
    def _requires_search_replace_only(cls, context: RunnerContext) -> bool:
        if not cls._uses_compact_worker_prompt(context) or not cls._editing_expected_for_context(context):
            return False
        task = context.task
        if task is None:
            return False
        allowed = [str(path).strip().replace("\\", "/") for path in list(task.allowed_paths_json or []) if str(path).strip()]
        if len(allowed) != 1:
            return False
        workspace_root = Path(cls.effective_workspace_path(context)).resolve()
        target = (workspace_root / allowed[0]).resolve()
        try:
            target.relative_to(workspace_root)
        except ValueError:
            return False
        if not target.exists() or not target.is_file():
            return False
        try:
            line_count = len(target.read_text(encoding="utf-8").splitlines())
        except OSError:
            return False
        return line_count >= 120

    @staticmethod
    def _editing_expected(task: Any | None) -> bool:
        if task is None:
            return False
        task_text = " ".join(
            filter(
                None,
                [
                    str(getattr(task, "title", "") or ""),
                    str(getattr(task, "goal", "") or ""),
                    str(getattr(task, "scope", "") or ""),
                ],
            )
        ).lower()
        return any(word in task_text for word in ("fix", "implement", "correct", "update", "change"))

    @classmethod
    def _editing_expected_for_context(cls, context: RunnerContext) -> bool:
        task = context.task
        role_text = " ".join(
            filter(
                None,
                [
                    str(context.agent.role or ""),
                    str(task.agent_role or "") if task is not None else "",
                ],
            )
        ).lower()
        if "validation specialist" in role_text:
            return False
        return cls._editing_expected(task)

    @staticmethod
    def _is_executable_validation_step(step: str) -> bool:
        normalized = str(step or "").strip()
        if not normalized:
            return False
        lowered = normalized.lower()
        command_prefixes = (
            "python ",
            "python3 ",
            "pytest",
            "py.test",
            "tox ",
            "nox ",
            "npm ",
            "pnpm ",
            "yarn ",
            "make ",
            "cmake ",
            "cargo ",
            "go ",
            "node ",
            "bash ",
            "sh ",
            "pwsh ",
            "powershell ",
            "./",
            ".\\",
            "php ",
            "ruby ",
            "bundle ",
            "rake ",
            "poetry ",
            "pipenv ",
        )
        if lowered.startswith(command_prefixes):
            return True
        return False

    @classmethod
    def _extract_embedded_command(cls, step: str) -> str | None:
        normalized = str(step or "").strip()
        if not normalized:
            return None
        if cls._is_executable_validation_step(normalized):
            return normalized
        patterns = (
            r"((?:python|python3)\s+[^\r\n`]+)",
            r"((?:pytest|py\.test)\s+[^\r\n`]+)",
            r"((?:npm|pnpm|yarn|tox|nox|make|cargo|go|node|bash|sh|pwsh|powershell)\s+[^\r\n`]+)",
            r"((?:tests/runtests\.py)\s+[^\r\n`]+)",
            r"((?:manage\.py\s+test)\s+[^\r\n`]+)",
            r"((?:\./|\.\\)[^\r\n`]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = str(match.group(1) or "").strip().strip("`").strip()
            candidate = re.sub(
                r"(?is)^(.*?)(?:\.\s+(?:rerun|re-run|run|do not|if|record|before|after|when)\b.*)$",
                r"\1",
                candidate,
            ).strip()
            if candidate and cls._is_executable_validation_step(candidate):
                return candidate
        return None

    @classmethod
    def _required_validation_commands(cls, task: Any | None) -> list[str]:
        if task is None:
            return []
        commands: list[str] = []
        candidate_texts: list[str] = [
            *[str(step or "") for step in list(getattr(task, "validation_steps_json", []) or [])],
            str(getattr(task, "goal", "") or ""),
            str(getattr(task, "scope", "") or ""),
            *[str(item or "") for item in list(getattr(task, "success_criteria_json", []) or [])],
        ]
        for step in candidate_texts:
            candidate = cls._extract_embedded_command(step)
            if candidate:
                commands.append(candidate)
        return cls._dedupe_ordered(commands)

    @classmethod
    def _requires_command_execution(cls, context: RunnerContext) -> bool:
        task = context.task
        if task is None:
            return False
        required_commands = cls._required_validation_commands(task)
        if not required_commands:
            return False
        if cls._uses_authoritative_benchmark_validation(context) and cls._editing_expected_for_context(context):
            return False
        task_text = " ".join(
            filter(
                None,
                [
                    str(context.agent.role or ""),
                    str(task.agent_role or ""),
                    str(task.title or ""),
                    str(task.goal or ""),
                    str(task.scope or ""),
                ],
            )
        ).lower()
        if cls._editing_expected_for_context(context):
            implementation_validation_markers = (
                "rerun focused validation",
                "re-run focused validation",
                "run focused validation",
                "run the focused validation command",
                "clear the failing validation command",
                "before calling this done",
                "before calling this complete",
                "do not report success unless",
                "run available validation",
            )
            return any(marker in task_text for marker in implementation_validation_markers)
        validation_markers = (
            "validation specialist",
            "validate",
            "validation",
            "reproduce",
            "regression",
            "verify",
            "confirm",
            "test",
        )
        return any(marker in task_text for marker in validation_markers)

    @classmethod
    def _uses_authoritative_benchmark_validation(cls, context: RunnerContext) -> bool:
        task = context.task
        if task is None:
            return False
        candidate_texts = [
            str(getattr(context.project, "idea", "") or ""),
            str(getattr(task, "goal", "") or ""),
            str(getattr(task, "scope", "") or ""),
            *[str(item or "") for item in list(getattr(task, "validation_steps_json", []) or [])],
            *[str(item or "") for item in list(getattr(task, "success_criteria_json", []) or [])],
        ]
        normalized = " ".join(text for text in candidate_texts if text).lower()
        benchmark_markers = (
            "swe-bench",
            "fail_to_pass",
            "pass_to_pass",
            "authoritative validation",
            "authoritative evaluator",
            "prepared local swe-bench-style coding task",
        )
        return any(marker in normalized for marker in benchmark_markers)

    @classmethod
    def _validation_execution_contract_markdown(cls, context: RunnerContext) -> str:
        required_commands = cls._required_validation_commands(context.task)
        if cls._uses_authoritative_benchmark_validation(context):
            commands_block = "\n".join(f"- `{command}`" for command in required_commands) if required_commands else "- None declared"
            if cls._editing_expected_for_context(context):
                return (
                    "Validation execution contract:\n"
                    "- This is an implementation task under authoritative benchmark evaluation.\n"
                    "- Inspect the allowed implementation files first and return at least one concrete edit in `edits[]` unless you can prove the scoped path is wrong.\n"
                    "- Treat the focused command below as the post-patch target, not as a pre-edit gate.\n"
                    "- Mission Control will rerun authoritative benchmark validation after your patch; do not spend the turn only rerunning a local command if the staged workspace hits import/build noise.\n"
                    "- Do not return `blocked`, `done`, or `needs_review` with empty `edits[]` merely because a local rerun fails before reaching the real regression assertions.\n"
                    "- If you mention a local command failure, name the concrete import/build blocker and still return the best justified scoped patch you can support from the live code.\n"
                    "- Required commands:\n"
                    f"{commands_block}"
                )
            return (
                "Validation execution contract:\n"
                "- This benchmark task uses authoritative validation outside the staged worker workspace.\n"
                "- Run the focused command below when the staged workspace supports it, and copy the executed command into both `report.tests_run` and `commands_attempted`.\n"
                "- If the staged workspace hits import/build noise first, do not burn the turn only rerunning it locally if the staged workspace hits import/build noise first.\n"
                "- If the command fails, report the real failure output instead of claiming the issue is not reproducible.\n"
                "- If the command is blocked by the environment, sandbox, or missing dependencies, set `report.status` to `blocked` and name the concrete blocker.\n"
                "- Do not claim the benchmark already passes or is not reproducible unless the command actually ran and passed in this workspace.\n"
                "- Required commands:\n"
                f"{commands_block}"
            )
        if not cls._requires_command_execution(context):
            return ""
        commands_block = "\n".join(f"- `{command}`" for command in required_commands)
        if cls._editing_expected_for_context(context):
            return (
                "Validation execution contract:\n"
                "- This is an implementation task. Inspect the allowed implementation files first and return at least one concrete edit in `edits[]` unless you can prove the scoped path is wrong.\n"
                "- A failing assertion line inside a benchmark test file is evidence about source behavior, not automatic permission to retarget the fix into the test.\n"
                "- Treat a known failing focused command as starting-state evidence, not as the whole job.\n"
                "- Use the required command below as post-edit validation or as contradictory evidence after inspecting the scoped file; do not spend the whole turn only rerunning an already-failing command.\n"
                "- Do not return `needs_review`, `done`, or `blocked` with empty `edits[]` merely because the listed command still fails.\n"
                "- If you truly cannot patch the scoped file, cite the exact file, line, or command output that proves the allowed path is wrong.\n"
                "- A supporting class or helper being defined elsewhere does not prove the scoped implementation file is wrong when that scoped file already defines the failing function or exact live edit anchors.\n"
                "- If the prompt already shows an exact live anchor inside the allowed file for the named function or behavior, do not claim the symbol only exists in a test or other file unless you cite contradictory live repo evidence from another allowed implementation file.\n"
                "- When you do change code, copy the executed command into both `report.tests_run` and `commands_attempted`.\n"
                "- Required commands:\n"
                f"{commands_block}"
            )
        return (
            "Validation execution contract:\n"
            "- This task is command-first. Execute at least one required validation command before you answer.\n"
            "- Copy the executed command into both `report.tests_run` and `commands_attempted`.\n"
            "- If the command is blocked by the environment, sandbox, or missing dependencies, set `report.status` to `blocked` and name the concrete blocker.\n"
            "- Do not return `needs_review` or ask for more evidence when the required command is already listed below.\n"
            "- Required commands:\n"
            f"{commands_block}"
        )

    @classmethod
    def _compact_validation_execution_contract_markdown(cls, context: RunnerContext, task_like: Any | None) -> str:
        if cls._uses_authoritative_benchmark_validation(context):
            if cls._editing_expected_for_context(context):
                return (
                    "Validation execution contract:\n"
                    "- This is an implementation task under authoritative benchmark evaluation.\n"
                    "- Inspect the allowed implementation files first and return at least one concrete edit in `edits[]` unless you can prove the scoped path is wrong.\n"
                    "- Treat the focused command below as the post-patch target, not as a pre-edit gate.\n"
                    "- Mission Control will rerun authoritative benchmark validation after your patch; do not spend the turn only rerunning a local command if the staged workspace hits import/build noise.\n"
                    "- A failing assertion line inside a benchmark test file is evidence about source behavior, not permission to retarget the fix into the test.\n"
                    "- Treat a known failing focused command as starting-state evidence, and do not spend the whole turn only rerunning an already-failing command.\n"
                    "- Do not return `needs_review`, `done`, or `blocked` with empty `edits[]` merely because the focused command still fails.\n"
                    "- A supporting class or helper being defined elsewhere does not prove the scoped implementation file is wrong.\n"
                    "- If the prompt already anchors the live symbol in the allowed file, do not claim the symbol only exists in a test or other file unless you cite contradictory live repo evidence."
                )
            return (
                "Validation execution contract:\n"
                "- This benchmark task uses authoritative validation outside the staged worker workspace.\n"
                "- You must execute the required command below inside the staged workspace before you answer.\n"
                "- Run the focused command below when the staged workspace supports it, and copy the executed command into both `report.tests_run` and `commands_attempted`.\n"
                "- If the staged workspace hits import/build noise first, do not burn the turn only rerunning it locally if the staged workspace hits import/build noise first.\n"
                "- If the command fails, report the real failure output instead of claiming the issue is not reproducible.\n"
                "- Do not claim the benchmark already passes or is not reproducible unless the command actually ran and passed in this workspace.\n"
                "- Copy the executed command into both `report.tests_run` and `commands_attempted`."
            )
        if not cls._requires_command_execution(context):
            return ""
        if cls._editing_expected_for_context(context):
            return (
                "Validation execution contract:\n"
                "- This is an implementation task. Inspect the allowed implementation files first and return at least one concrete edit in `edits[]` unless you can prove the scoped path is wrong.\n"
                "- A failing assertion line inside a benchmark test file is evidence about source behavior, not automatic permission to retarget the fix into the test.\n"
                "- Treat a known failing focused command as starting-state evidence, and do not spend the whole turn only rerunning an already-failing command.\n"
                "- Do not return `needs_review`, `done`, or `blocked` with empty `edits[]` merely because the listed command still fails.\n"
                "- A supporting class or helper being defined elsewhere does not prove the scoped implementation file is wrong.\n"
                "- If the prompt already anchors the live symbol in the allowed file, do not claim the symbol only exists in a test or other file unless you cite contradictory live repo evidence.\n"
                "- Use the required command below as post-edit validation or as contradictory evidence after inspecting the scoped file."
            )
        return (
            "Validation execution contract:\n"
            "- This task is command-first. Execute at least one required validation command before you answer.\n"
            "- Copy the executed command into both `report.tests_run` and `commands_attempted`.\n"
            "- Do not return `needs_review` or ask for more evidence when the required command is already listed below."
        )

    @staticmethod
    def _normalize_command_text(command: str) -> str:
        return re.sub(r"\s+", " ", str(command or "").strip()).lower()

    @classmethod
    def _command_satisfies_requirement(cls, attempted: str, required: str) -> bool:
        attempted_normalized = cls._normalize_command_text(attempted)
        required_normalized = cls._normalize_command_text(required)
        if not attempted_normalized or not required_normalized:
            return False
        return (
            attempted_normalized == required_normalized
            or required_normalized in attempted_normalized
            or attempted_normalized in required_normalized
        )

    @classmethod
    def _enforce_required_command_execution(
        cls,
        state: ExternalAdapterRunState,
        envelope_payload: dict[str, Any],
        report_payload: dict[str, Any],
    ) -> None:
        if not state.enforce_command_execution or not state.required_validation_commands:
            return
        executed = cls._execute_required_validation_command(state, envelope_payload, report_payload)
        if executed:
            return
        tests_run = cls._dedupe_ordered([str(item).strip() for item in list(report_payload.get("tests_run") or []) if str(item).strip()])
        commands_attempted = cls._dedupe_ordered(
            [
                *tests_run,
                *[
                    str(item).strip()
                    for item in list(envelope_payload.get("commands_attempted") or [])
                    if str(item).strip()
                ],
            ]
        )
        report_payload["tests_run"] = tests_run
        envelope_payload["tests_run"] = list(tests_run)
        envelope_payload["commands_attempted"] = list(commands_attempted)
        matched_command = any(
            cls._command_satisfies_requirement(attempted, required)
            for attempted in commands_attempted
            for required in state.required_validation_commands
        )
        if matched_command:
            return
        blocker = (
            "Mission Control required this validation task to execute and report at least one explicit validation command, "
            "but the adapter returned without command evidence."
        )
        risk = (
            "Validation handoff rejected: no required validation command was reported in report.tests_run or commands_attempted."
        )
        blockers = cls._dedupe_ordered([*list(report_payload.get("blockers") or []), blocker])
        risks = cls._dedupe_ordered([*list(report_payload.get("risks") or []), risk])
        report_payload["blockers"] = blockers
        report_payload["risks"] = risks
        report_payload["status"] = "blocked"
        report_payload["summary"] = (
            f"{str(report_payload.get('summary') or 'Adapter run completed.').strip()} "
            "Mission Control rejected the result because the required validation command was not executed or not reported."
        ).strip()
        envelope_payload["status"] = "blocked"
        envelope_payload["summary"] = str(report_payload["summary"])
        envelope_payload["blockers"] = list(blockers)
        envelope_payload["risks"] = list(risks)
        envelope_payload["failure_classification"] = envelope_payload.get("failure_classification") or "validation_not_run"

    @staticmethod
    def _command_output_excerpt(text: str | None, *, max_chars: int = 600) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 24].rstrip() + " ... [truncated]"

    @classmethod
    def _execute_required_validation_command(
        cls,
        state: ExternalAdapterRunState,
        envelope_payload: dict[str, Any],
        report_payload: dict[str, Any],
    ) -> bool:
        command = str((state.required_validation_commands or [None])[0] or "").strip()
        workspace_root = Path(state.workspace_path or "").resolve()
        if not command or not workspace_root.exists() or not workspace_root.is_dir():
            return False
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(workspace_root)
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace_root),
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
                env=environment,
            )
            timed_out = False
            returncode = int(completed.returncode)
            stdout_text = str(completed.stdout or "")
            stderr_text = str(completed.stderr or "")
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = -1
            stdout_text = str(exc.stdout or "")
            stderr_text = str(exc.stderr or "")
        tests_run = cls._dedupe_ordered([command, *[str(item).strip() for item in list(report_payload.get("tests_run") or []) if str(item).strip()]])
        commands_attempted = cls._dedupe_ordered(
            [
                command,
                *tests_run,
                *[
                    str(item).strip()
                    for item in list(envelope_payload.get("commands_attempted") or [])
                    if str(item).strip()
                ],
            ]
        )
        evidence = list(envelope_payload.get("evidence") or [])
        stdout_excerpt = cls._command_output_excerpt(stdout_text)
        stderr_excerpt = cls._command_output_excerpt(stderr_text)
        command_passed = not timed_out and returncode == 0
        evidence.append(
            {
                "kind": "command_output",
                "summary": (
                    "Mission Control executed the required validation command locally and it passed."
                    if command_passed
                    else f"Mission Control executed the required validation command locally and it failed with exit code {returncode}."
                ),
                "status": "passed" if command_passed else "failed",
                "source_path": None,
                "command": command,
                "metadata_json": {
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "stdout_excerpt": stdout_excerpt,
                    "stderr_excerpt": stderr_excerpt,
                },
            }
        )
        report_payload["tests_run"] = tests_run
        envelope_payload["tests_run"] = list(tests_run)
        envelope_payload["commands_attempted"] = list(commands_attempted)
        envelope_payload["evidence"] = evidence
        if command_passed:
            if not state.editing_expected:
                report_payload["status"] = "done"
                report_payload["summary"] = "Mission Control executed the required validation command locally and it passed."
                report_payload["blockers"] = []
                report_payload["recommended_next_task"] = "Prepare the final operator handoff."
                report_payload["risks"] = [
                    item
                    for item in list(report_payload.get("risks") or [])
                    if "explicit validation command" not in str(item).lower()
                ]
                envelope_payload["status"] = "completed"
                envelope_payload["summary"] = str(report_payload["summary"])
                envelope_payload["blockers"] = []
                envelope_payload["risks"] = list(report_payload.get("risks") or [])
                envelope_payload["failure_classification"] = None
            return True
        blocker = (
            f"Required validation command timed out after 180s: {command}"
            if timed_out
            else f"Required validation command failed with exit code {returncode}: {command}"
        )
        diagnostics: list[str] = []
        if stderr_excerpt:
            diagnostics.append(stderr_excerpt)
        elif stdout_excerpt:
            diagnostics.append(stdout_excerpt)
        blockers = cls._dedupe_ordered([blocker])
        risks = cls._dedupe_ordered(
            [
                *[str(item).strip() for item in list(report_payload.get("risks") or []) if str(item).strip()],
                "Mission Control ignored the adapter's command claim and recorded the actual local validation result.",
            ]
        )
        failure_excerpt = cls._clip_middle(stderr_excerpt or stdout_excerpt, 260) if (stderr_excerpt or stdout_excerpt) else ""
        report_payload["status"] = "blocked"
        report_payload["summary"] = (
            f"Mission Control executed the required validation command locally and it failed. {blocker}"
        )
        if failure_excerpt:
            report_payload["summary"] = f"{report_payload['summary']} Observed failure excerpt: {failure_excerpt}"
        report_payload["blockers"] = blockers
        if not timed_out:
            report_payload["recommended_next_task"] = (
                "Inspect the failed validation output, repair the implementation, and rerun the focused validation command."
            )
        report_payload["risks"] = risks
        envelope_payload["status"] = "blocked"
        envelope_payload["summary"] = str(report_payload["summary"])
        envelope_payload["blockers"] = list(blockers)
        envelope_payload["risks"] = list(risks)
        envelope_payload["diagnostics"] = cls._dedupe_ordered(
            [
                *[str(item).strip() for item in list(envelope_payload.get("diagnostics") or []) if str(item).strip()],
                *diagnostics,
            ]
        )
        envelope_payload["failure_classification"] = "validation_failed"
        return True

    def _enforce_live_symbol_presence_contract(
        self,
        state: ExternalAdapterRunState,
        envelope_payload: dict[str, Any],
        report_payload: dict[str, Any],
    ) -> None:
        combined = "\n".join(
            [
                str(report_payload.get("summary") or "").strip(),
                *[str(item).strip() for item in list(report_payload.get("blockers") or []) if str(item).strip()],
            ]
        ).strip()
        lowered = combined.lower()
        if not lowered:
            return
        missing_phrases = (
            "missing from the specified path",
            "missing from the specified file",
            "missing from the allowed file",
            "does not exist in the allowed file",
            "is not found in the specified file",
            "is not found in ",
            "is missing from ",
        )
        if not any(phrase in lowered for phrase in missing_phrases):
            return
        workspace_root = Path(state.workspace_path or "").resolve()
        records = self._live_symbol_presence_records(
            workspace_root,
            list(state.allowed_paths or []),
            state.task_query_text,
        )
        if not records:
            return
        mentioned_symbols = [record for record in records if record[1].lower() in lowered]
        rel_path, symbol, symbol_line, header = (mentioned_symbols[0] if mentioned_symbols else records[0])
        blocker = (
            "Invalid missing-symbol blocker: "
            f"Mission Control verified that `{rel_path}` already contains `{header}` at line {symbol_line}. "
            f"Patch `{symbol}` in that live file and return concrete edits[] instead of claiming the symbol is absent."
        )
        blockers = self._dedupe_ordered(
            [
                *[str(item).strip() for item in list(report_payload.get("blockers") or []) if str(item).strip()],
                blocker,
            ]
        )
        risks = self._dedupe_ordered(
            [
                *[str(item).strip() for item in list(report_payload.get("risks") or []) if str(item).strip()],
                "Adapter reported a missing-symbol blocker that contradicts authoritative live workspace evidence.",
            ]
        )
        report_payload["status"] = "blocked"
        report_payload["blockers"] = blockers
        report_payload["risks"] = risks
        report_payload["recommended_next_task"] = (
            "Patch the verified live definition in the allowed file and return authoritative edits[] for that change."
        )
        summary = str(report_payload.get("summary") or "Adapter run completed.").strip()
        if blocker not in summary:
            summary = f"{summary} {blocker}".strip()
        report_payload["summary"] = summary
        envelope_payload["status"] = "blocked"
        envelope_payload["summary"] = summary
        envelope_payload["blockers"] = list(blockers)
        envelope_payload["risks"] = list(risks)
        envelope_payload["report"] = report_payload
        envelope_payload["failure_classification"] = envelope_payload.get("failure_classification") or "invalid_worker_claim"

    def _build_adapter_prompt(self, context: RunnerContext) -> str:
        prompt_project, prompt_task, prompt_context_pack = self._worker_prompt_inputs(context)
        workspace_snapshot = self._workspace_snapshot_markdown(context)
        exact_edit_anchors = self._exact_live_edit_anchor_markdown(context)
        live_symbol_presence = self._live_symbol_presence_markdown(context)
        issue_fix_clue = self._issue_fix_clue_markdown(context)
        issue_named_symbols = self._issue_named_symbol_markdown(context)
        same_file_anchors = self._same_file_anchor_markdown(context)
        model_note = self._model_specific_adapter_note(context.settings.model)
        editing_expected = "yes" if self._editing_expected_for_context(context) else "no"
        remote_execution_context = self._remote_execution_context_markdown(context)
        previous_attempt_context = self._recent_attempt_context_markdown(context)
        scoped_live_file_focus = self._scoped_live_file_focus_markdown(context)
        validation_contract = (
            self._compact_validation_execution_contract_markdown(context, prompt_task)
            if self._uses_compact_worker_prompt(context)
            else self._validation_execution_contract_markdown(context)
        )
        validation_block = f"{validation_contract}\n\n" if validation_contract else ""
        previous_attempt_block = f"{previous_attempt_context}\n\n" if previous_attempt_context else ""
        exact_edit_anchor_block = f"{exact_edit_anchors}\n\n" if exact_edit_anchors else ""
        live_symbol_presence_block = f"{live_symbol_presence}\n\n" if live_symbol_presence else ""
        issue_fix_clue_block = f"{issue_fix_clue}\n\n" if issue_fix_clue else ""
        issue_named_symbol_block = f"{issue_named_symbols}\n\n" if issue_named_symbols else ""
        same_file_anchor_block = f"{same_file_anchors}\n\n" if same_file_anchors else ""
        scoped_live_file_focus_block = f"{scoped_live_file_focus}\n\n" if scoped_live_file_focus else ""
        if self._uses_compact_worker_prompt(context):
            return self._build_compact_local_adapter_prompt(
                context,
                prompt_project=prompt_project,
                prompt_task=prompt_task,
                prompt_context_pack=prompt_context_pack,
                workspace_snapshot=workspace_snapshot,
                exact_edit_anchor_block=exact_edit_anchor_block,
                live_symbol_presence_block=live_symbol_presence_block,
                issue_fix_clue_block=issue_fix_clue_block,
                issue_named_symbol_block=issue_named_symbol_block,
                same_file_anchor_block=same_file_anchor_block,
                scoped_live_file_focus_block=scoped_live_file_focus_block,
                previous_attempt_block=previous_attempt_block,
                validation_block=validation_block,
                remote_execution_context=remote_execution_context,
                model_note=model_note,
                editing_expected=editing_expected,
            )
        prompt = worker_task_prompt(
            prompt_project,
            context.agent,
            prompt_task,
            context.docs_path,
            context.plan_markdown,
            prompt_context_pack,
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        if exact_edit_anchors:
            scoped_symbol_rule = (
                "- If the exact live anchors below already show the named function or target behavior inside the allowed file, "
                "a blocker that says the symbol only exists in a test file is invalid unless you cite contradictory live repo evidence from another allowed implementation file.\n"
            )
        else:
            scoped_symbol_rule = (
                "- If the scoped live file focus below already shows the named function or target behavior inside the allowed file, "
                "a blocker that says the symbol is missing is invalid unless you cite contradictory live repo evidence from another allowed implementation file.\n"
            )
        return (
            f"{prompt}\n\n"
            "External adapter execution rules:\n"
            "- You may propose file edits only inside the allowed files/areas.\n"
            "- For small or self-contained files, return the full updated file contents.\n"
            "- For large files, prefer a surgical edit with edit.path + edit.search + edit.replace instead of rewriting the whole file.\n"
            "- When using search/replace, copy the search text exactly from the workspace and make it unique within that file.\n"
            "- Never abbreviate live code inside search/replace strings. Do not shorten code into partial identifiers like `self.o`.\n"
            "- If a short search string would match multiple locations, expand it with surrounding lines until it identifies exactly one edit site.\n"
            "- If the current workspace snapshot no longer contains a previous search string, do not repeat that stale patch; adapt to the current file text.\n"
            "- If the snapshot already appears to include your last attempted fix, do not resubmit the same edit; explain the remaining blocker or produce a different concrete change.\n"
            "- If you claim any file in report.files_changed, include authoritative edits[] entries that reproduce those exact file changes.\n"
            "- If you tried a patch and reran validation but it still failed, still return the exact attempted edits[] plus the failed validation evidence. Do not erase the attempted patch from edits[] just because the rerun failed.\n"
            "- Never rewrite a large framework file from scratch for a narrow bugfix unless the prompt includes the exact complete file and your replacement is exact.\n"
            "- Never use placeholders, ellipses, or 'rest of file' summaries inside edit content.\n"
            "- If you cannot make a safe edit, return no edits and explain why in the report.\n"
            "- Do not claim a code fix unless your edits actually implement it.\n\n"
            f"Editing expected for this task: {editing_expected}\n"
            "- If editing expected is no, do not modify files and keep files_changed empty.\n"
            "- If editing expected is yes, assume the allowed implementation file is the default edit target unless live repo evidence proves otherwise.\n"
            "- If editing expected is yes and the scoped file already contains the named function from the issue, the scoped live file focus below, or the exact live edit anchors below, do not claim that file lacks the implementation symbol just because related classes live elsewhere.\n"
            f"{scoped_symbol_rule}"
            "- Treat task-provided `path:line:symbol` anchors as approximate locators. If the same function or class appears in the live scoped file at a different line, use that live definition as the edit anchor instead of blocking on the stale line number.\n"
            "- If editing expected is yes and the anchored function already exists in the allowed file, 'the function already exists' or 'no changes are needed' is not an acceptable blocker while the focused validation command still fails.\n"
            "- If editing expected is yes and the live anchor points to an existing function body, patch inside that body. Do not prepend a replacement implementation block ahead of an existing docstring or turn the function into a stub.\n"
            "- Do not introduce a recursive self-call in the anchored function unless the live file already uses that recursion pattern and the failure evidence specifically requires it.\n"
            "- Do not replace an existing core expression with a newly invented internal helper-call chain unless the live file already shows that exact helper signature and argument count.\n"
            "- If the scoped implementation ends by coercing an already computed intermediate into booleans with patterns like `np.where(...)`, `.astype(bool)`, `== 1`, or `!= 0`, treat that final normalization as a downstream symptom by default. Inspect and patch the upstream calculation or helper that produced the intermediate unless the failing evidence proves only the final coercion is wrong.\n"
            "- If retry evidence says a prior patch only changed final boolean coercion or widened a threshold check and it still failed, do not make another output-normalization tweak on that same variable. Move upstream to the calculation that produces it.\n"
            "- If retry evidence or the task goal explicitly names a same-file sibling helper or upstream function as the likely culprit, inspect and patch that named helper before changing the downstream wrapper or final normalization step again.\n"
            "- If editing expected is yes, do not retarget the fix into a failing test file just because the assertion or import line appears in the traceback.\n"
            "- If editing expected is yes, do not treat a pre-edit validation rerun stack trace as stronger evidence than the scoped implementation hint unless that stack trace points inside an allowed implementation file.\n"
            "- If editing expected is yes, do not spend the entire turn on validation-only output; inspect the scoped files and return concrete edits[] or exact blocker evidence tied to those files.\n"
            "- If the prior run already reproduced the failure, treat this turn as patch-first, then rerun focused validation.\n"
            f"{model_note}\n\n"
            f"{previous_attempt_block}"
            f"{validation_block}"
            f"{live_symbol_presence_block}"
            f"{issue_fix_clue_block}"
            f"{issue_named_symbol_block}"
            f"{same_file_anchor_block}"
            f"{exact_edit_anchor_block}"
            f"{scoped_live_file_focus_block}"
            "Return only valid JSON matching this schema exactly:\n"
            f"{json.dumps(self._response_schema_for_context(context), indent=2)}\n\n"
            f"{self._adapter_examples_for_context(context)}\n\n"
            f"{remote_execution_context}\n\n"
            f"{workspace_snapshot}"
        )

    def _build_compact_local_adapter_prompt(
        self,
        context: RunnerContext,
        *,
        prompt_project: Any,
        prompt_task: Any,
        prompt_context_pack: str | None,
        workspace_snapshot: str,
        exact_edit_anchor_block: str,
        live_symbol_presence_block: str,
        issue_fix_clue_block: str,
        issue_named_symbol_block: str,
        same_file_anchor_block: str,
        scoped_live_file_focus_block: str,
        previous_attempt_block: str,
        validation_block: str,
        remote_execution_context: str,
        model_note: str,
        editing_expected: str,
    ) -> str:
        allowed_paths = [str(path).strip().replace("\\", "/") for path in list(getattr(prompt_task, "allowed_paths_json", None) or []) if str(path).strip()]
        forbidden_paths = [str(path).strip().replace("\\", "/") for path in list(getattr(prompt_task, "forbidden_paths_json", None) or []) if str(path).strip()]
        required_commands = self._required_validation_commands(prompt_task)
        search_replace_only = self._requires_search_replace_only(context)
        search_replace_rule = (
            "- Return search/replace edits only for this task. Do not return full-file content.\n"
            if search_replace_only
            else "- Prefer exact search/replace edits for large files; only return full-file content when the file is small and the replacement is exact.\n"
        )
        context_pack_block = f"Relevant context pack:\n{prompt_context_pack}\n\n" if prompt_context_pack else ""
        exact_anchor_rule = (
            "- If the exact live anchors below already show the target function inside the allowed file, a blocker that says the symbol is missing is invalid.\n"
            if exact_edit_anchor_block
            else "- If the scoped live file focus below already shows the target function inside the allowed file, a blocker that says the symbol is missing is invalid.\n"
        )
        compact_validation_steps = [
            str(step).strip()
            for step in list(getattr(prompt_task, "validation_steps_json", None) or [])
            if str(step).strip()
        ]
        commands_block = "\n".join(f"- `{command}`" for command in required_commands) if required_commands else "- None declared"
        compact_validation_block = (
            "\n".join(f"- {step}" for step in compact_validation_steps)
            if compact_validation_steps
            else "- None declared"
        )
        allowed_block = "\n".join(f"- `{path}`" for path in allowed_paths) if allowed_paths else "- None declared"
        forbidden_block = "\n".join(f"- `{path}`" for path in forbidden_paths) if forbidden_paths else "- None declared"
        return (
            "Compact local worker task:\n"
            f"- Agent: {context.agent.name} ({context.agent.role})\n"
            f"- Task ID: {prompt_task.id}\n"
            f"- Editing expected for this task: {editing_expected}\n"
            f"- Title: {prompt_task.title}\n"
            f"- Goal: {prompt_task.goal}\n"
            f"- Scope: {prompt_task.scope}\n\n"
            f"Benchmark task brief:\n{prompt_project.idea}\n\n"
            f"{context_pack_block}"
            "Allowed paths:\n"
            f"{allowed_block}\n\n"
            "Forbidden paths:\n"
            f"{forbidden_block}\n\n"
            "Required validation commands:\n"
            f"{commands_block}\n\n"
            "Focused validation plan (compact):\n"
            f"{compact_validation_block}\n\n"
            "External adapter execution rules:\n"
            "- Stay inside the allowed paths.\n"
            "- If editing expected is yes, assume the allowed implementation file is the default edit target unless exact live repo evidence proves otherwise.\n"
            "- If editing expected is yes, do not claim that file lacks the implementation symbol just because related classes live elsewhere.\n"
            "- If editing expected is yes, a blocker that says the symbol only exists in a test file is invalid unless you cite contradictory live repo evidence from another allowed implementation file.\n"
            "- Treat task-provided `path:line:symbol` anchors as approximate locators. If the same function or class appears in the live scoped file at a different line, use that live definition as the edit anchor instead of blocking on the stale line number.\n"
            "- If editing expected is yes and the anchored function already exists in the allowed file, 'the function already exists' or 'no changes are needed' is not an acceptable blocker while the focused validation command still fails.\n"
            "- If editing expected is yes and the live anchor points to an existing function body, patch inside that body. Do not prepend a replacement implementation block ahead of an existing docstring or turn the function into a stub.\n"
            "- Do not introduce a recursive self-call in the anchored function unless the live file already uses that recursion pattern and the failure evidence specifically requires it.\n"
            "- Do not replace an existing core expression with a newly invented internal helper-call chain unless the live file already shows that exact helper signature and argument count.\n"
            "- If the scoped implementation ends by coercing an already computed intermediate into booleans with patterns like `np.where(...)`, `.astype(bool)`, `== 1`, or `!= 0`, treat that final normalization as a downstream symptom by default. Inspect and patch the upstream calculation or helper that produced the intermediate unless the failing evidence proves only the final coercion is wrong.\n"
            "- If retry evidence says a prior patch only changed final boolean coercion or widened a threshold check and it still failed, do not make another output-normalization tweak on that same variable. Move upstream to the calculation that produces it.\n"
            "- If retry evidence or the task goal explicitly names a same-file sibling helper or upstream function as the likely culprit, inspect and patch that named helper before changing the downstream wrapper or final normalization step again.\n"
            "- Return only valid JSON matching the schema below.\n"
            "- Do not wrap JSON in markdown fences.\n"
            "- Do not reuse placeholder paths, commands, or summaries.\n"
            "- If editing expected is yes, do not retarget the fix into a failing test file.\n"
            "- If editing expected is yes, do not treat a pre-edit validation rerun stack trace as stronger evidence than the scoped implementation hint unless that stack trace points inside an allowed implementation file.\n"
            "- If the prior run already reproduced the failure, treat this turn as patch-first, then rerun focused validation.\n"
            "- If editing expected is yes, do not spend the entire turn on validation-only output; inspect the scoped files and return concrete edits[] or exact blocker evidence tied to those files.\n"
            "- Treat an already reproduced failing command as patch-first evidence, not the whole job.\n"
            "- If report.files_changed is non-empty, edits[] must include the exact attempted patch for those files.\n"
            "- If you tried a patch and validation still failed, keep that attempted patch in edits[] and explain the remaining failure instead of returning files_changed with edits[].\n"
            f"{search_replace_rule}"
            "- Copy search text exactly from the live workspace snippet.\n"
            "- When using search/replace, make it unique within that file by copying the exact live search text.\n"
            "- If a short search string would match multiple locations, expand it with surrounding lines until it identifies exactly one edit site.\n"
            "- Never invent or abbreviate live code.\n"
            "- Never use placeholders, ellipses, or 'rest of file' summaries inside edits.\n"
            "- If you cannot make a safe edit, return blocked with exact scoped file evidence.\n"
            "- Do not claim the current failing benchmark behavior is already correct, expected, or needs no action while the focused validation command still fails.\n"
            f"{exact_anchor_rule}"
            f"{model_note}\n\n"
            f"{previous_attempt_block}"
            f"{validation_block}"
            f"{live_symbol_presence_block}"
            f"{issue_fix_clue_block}"
            f"{issue_named_symbol_block}"
            f"{same_file_anchor_block}"
            f"{exact_edit_anchor_block}"
            f"{scoped_live_file_focus_block}"
            "Return only valid JSON matching this schema exactly:\n"
            f"{json.dumps(self._response_schema_for_context(context), indent=2)}\n\n"
            f"{self._adapter_examples_for_context(context)}\n\n"
            f"{remote_execution_context}\n\n"
            f"{workspace_snapshot}"
        )

    @staticmethod
    def _clip_tail(text: str | None, max_chars: int) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= max_chars:
            return normalized
        marker = "\n...[truncated for compact local worker prompt]"
        keep = max(0, max_chars - len(marker))
        return normalized[:keep].rstrip() + marker

    @staticmethod
    def _clip_middle(text: str | None, max_chars: int) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= max_chars:
            return normalized
        marker = " ...[truncated]... "
        remaining = max_chars - len(marker)
        if remaining <= 32:
            return normalized[:max_chars]
        head = remaining // 2
        tail = remaining - head
        return f"{normalized[:head].rstrip()}{marker}{normalized[-tail:].lstrip()}"

    @staticmethod
    def _extract_labeled_section(text: str, label: str, labels: list[str]) -> str | None:
        start = text.find(label)
        if start < 0:
            return None
        section_start = start
        search_from = start + len(label)
        end_candidates = [
            candidate
            for candidate in (text.find(other, search_from) for other in labels if other != label)
            if candidate >= 0
        ]
        end = min(end_candidates) if end_candidates else len(text)
        section = re.sub(r"\s+", " ", text[section_start:end]).strip()
        return section or None

    @classmethod
    def _compact_project_idea(cls, text: str | None) -> str:
        normalized = str(text or "").strip()
        if len(normalized) <= 2400:
            return normalized
        flattened = re.sub(r"\s+", " ", normalized)
        labels = [
            "Instance ID:",
            "Repository:",
            "Base commit:",
            "Issue:",
            "Hints:",
            "Description",
            "Workspace clues:",
            "Files to inspect first:",
            "Likely related implementation files:",
            "Implementation anchors:",
            "Exact repo matches for issue snippets:",
            "Focused reproduction commands:",
            "FAIL_TO_PASS targets:",
            "PASS_TO_PASS targets:",
            "Required behavior:",
        ]
        selected_sections: list[str] = []
        for label, budget in [
            ("Instance ID:", 120),
            ("Repository:", 120),
            ("Base commit:", 120),
            ("Issue:", 240),
            ("Hints:", 700),
            ("Description", 800),
            ("Files to inspect first:", 260),
            ("Likely related implementation files:", 320),
            ("Implementation anchors:", 420),
            ("Exact repo matches for issue snippets:", 420),
            ("Focused reproduction commands:", 360),
            ("FAIL_TO_PASS targets:", 220),
            ("Required behavior:", 320),
        ]:
            section = cls._extract_labeled_section(flattened, label, labels)
            if not section:
                continue
            selected_sections.append(cls._clip_middle(section, budget))
        if not selected_sections:
            return cls._clip_middle(flattened, 2200)
        compact = "Benchmark task brief:\n" + "\n".join(f"- {section}" for section in selected_sections)
        return cls._clip_tail(compact, 2200)

    @classmethod
    def _compact_validation_steps(cls, steps: list[str] | None, *, exact_commands: bool) -> list[str]:
        ordered = [str(step).strip() for step in list(steps or []) if str(step).strip()]
        if not ordered:
            return []
        max_entries = 3 if exact_commands else 2
        max_chars = 480 if exact_commands else 260
        compact = [cls._clip_middle(step, max_chars) for step in ordered[:max_entries]]
        remaining = len(ordered) - len(compact)
        if remaining > 0:
            compact.append(f"... {remaining} more validation step(s) omitted for compact local worker context.")
        return compact

    @classmethod
    def _compact_context_pack_markdown(cls, markdown: str | None) -> str | None:
        normalized = str(markdown or "").strip()
        if not normalized:
            return None
        return cls._clip_tail(normalized, 1200)

    @staticmethod
    def _task_is_validation_or_repro(context: RunnerContext) -> bool:
        task = context.task
        agent = context.agent
        combined = " ".join(
            filter(
                None,
                [
                    str(getattr(agent, "role", "") or ""),
                    str(getattr(task, "title", "") or ""),
                    str(getattr(task, "goal", "") or ""),
                    str(getattr(task, "scope", "") or ""),
                ],
            )
        ).lower()
        return any(token in combined for token in ("validate", "validation", "reproduce", "test", "handoff", "inspect"))

    @staticmethod
    def _uses_compact_worker_prompt(context: RunnerContext) -> bool:
        profile = build_prompt_profile(
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        return profile.tier == "weak_local"

    def _worker_prompt_inputs(self, context: RunnerContext) -> tuple[Any, Any, str | None]:
        if not self._uses_compact_worker_prompt(context):
            return context.project, context.task, context.context_pack_markdown
        prompt_project = copy.copy(context.project)
        prompt_task = copy.copy(context.task)
        prompt_project.idea = self._compact_project_idea(getattr(prompt_project, "idea", None))
        prompt_task.goal = self._clip_middle(getattr(prompt_task, "goal", None), 700)
        prompt_task.scope = self._clip_middle(getattr(prompt_task, "scope", None), 520)
        prompt_task.validation_steps_json = self._compact_validation_steps(
            list(getattr(prompt_task, "validation_steps_json", None) or []),
            exact_commands=self._task_is_validation_or_repro(context),
        )
        prompt_context_pack = self._compact_context_pack_markdown(context.context_pack_markdown)
        return prompt_project, prompt_task, prompt_context_pack

    @staticmethod
    def _recent_attempt_context_markdown(context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return ""
        last_report_summary = str(getattr(context.agent, "last_report_summary", "") or "").strip()
        current_action = str(getattr(context.agent, "current_action", "") or "").strip()
        if not last_report_summary and not current_action:
            return ""
        lines = ["Previous attempt signals:"]
        if last_report_summary:
            lines.append(f"- Last report summary: {last_report_summary}")
        if current_action and current_action != last_report_summary:
            lines.append(f"- Current action handoff: {current_action}")
        lowered = " ".join(filter(None, [last_report_summary, current_action])).lower()
        if "search text was not found" in lowered:
            lines.append(
                "- The previous edit failed because its search text did not match the live workspace. Re-read the snapshot and do not repeat the same stale search/replace patch."
            )
        if "could not verify any workspace file changes" in lowered:
            lines.append(
                "- The previous attempt did not produce a verifiable workspace edit. This run must either return an exact applicable edit or return blocked with concrete evidence."
            )
        if "rejected or could not apply one or more proposed edits" in lowered:
            lines.append(
                "- Mission Control already rejected at least one edit payload. Favor exact search/replace against the current workspace over another broad rewrite."
            )
            lines.append(
                "- Never rewrite a large framework file from scratch for a narrow bugfix."
            )
        if "required validation command failed with exit code" in lowered or "executed the required validation command locally and it failed" in lowered:
            lines.append(
                "- The failure has already been reproduced. Do not spend this retry proving it again; inspect the scoped implementation file and return the smallest credible patch or exact scoped blocker evidence."
            )
        if (
            "expected behavior" in lowered
            or "no action needed" in lowered
            or "implementation is correct" in lowered
            or "no changes are needed" in lowered
            or "already defined in the allowed file" in lowered
        ):
            lines.append(
                "- The previous attempt tried to dismiss the benchmark regression as already correct. That is invalid while the focused validation command still fails; either patch the scoped implementation or prove the scoped path is wrong with exact contradictory repo evidence."
            )
        return "\n".join(lines)

    @staticmethod
    def _task_query_text(context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return str(context.project.idea or "")
        parts = [
            str(context.project.idea or ""),
            str(task.title or ""),
            str(task.goal or ""),
            str(task.scope or ""),
            *[str(step) for step in list(task.validation_steps_json or [])],
        ]
        return "\n".join(part for part in parts if part)

    def _remote_execution_context_markdown(self, context: RunnerContext) -> str:
        remote_execution = dict(getattr(context.settings, "remote_execution", None) or {})
        if not remote_execution:
            return "Remote execution context:\n- Not using a remote execution target for this run."
        policy = dict(remote_execution.get("policy") or {})
        selection = dict(remote_execution.get("selection") or {})
        selected_target = dict(remote_execution.get("selected_target") or {})
        artifact_contract = dict(remote_execution.get("artifact_contract") or {})
        connector_contract = dict(remote_execution.get("connector_contract") or {})
        broker_contract = dict(remote_execution.get("broker_contract") or {})
        execution_request = dict(remote_execution.get("execution_request") or {})
        blocking_reasons = list(selection.get("blocking_reasons") or [])
        if "enabled" in policy:
            remote_execution_enabled = bool(policy.get("enabled"))
        else:
            remote_execution_enabled = bool(
                selected_target or execution_request or broker_contract or artifact_contract or connector_contract
            )
        if not remote_execution_enabled:
            return (
                "Remote execution context:\n"
                "- Remote execution is disabled for this run.\n"
                "- Use the local workspace and local commands only."
            )
        if not selected_target:
            blocking_summary = ", ".join(str(item) for item in blocking_reasons) if blocking_reasons else "no selected target"
            return (
                "Remote execution context:\n"
                "- Remote execution policy is present, but no target is ready for this run.\n"
                f"- Blocking reasons: {blocking_summary}"
            )
        target_label = str(selected_target.get("label") or selected_target.get("id") or "remote-target")
        target_host = str(selected_target.get("host") or "unknown-host")
        target_transport = str(selected_target.get("transport") or "ssh")
        workspace_root = str(selected_target.get("workspace_root") or "").strip()
        artifact_paths = list(artifact_contract.get("local_artifact_paths") or [])
        connector_families = list(connector_contract.get("available_families") or [])
        broker_command_families = list(broker_contract.get("target_command_families") or [])
        broker_toolchains = list(broker_contract.get("target_toolchains") or [])
        broker_path_prefixes = list(broker_contract.get("target_path_prefixes") or [])
        broker_repo_roots = list(broker_contract.get("target_repo_roots") or [])
        lines = [
            "Remote execution context:",
            f"- Target: {target_label} ({target_transport} -> {target_host})",
            f"- Remote workspace root: {workspace_root or 'not declared'}",
            f"- Artifact sync enabled: {'yes' if artifact_contract.get('sync_enabled') else 'no'}",
            f"- Artifact paths discovered locally: {', '.join(str(item) for item in artifact_paths[:6]) if artifact_paths else 'none'}",
            f"- Connector families usable in this lane: {', '.join(str(item) for item in connector_families[:6]) if connector_families else 'none'}",
            f"- Broker command families: {', '.join(str(item) for item in broker_command_families[:6]) if broker_command_families else 'none declared'}",
            f"- Broker toolchains: {', '.join(str(item) for item in broker_toolchains[:6]) if broker_toolchains else 'none declared'}",
            f"- Allowed repo roots: {', '.join(str(item) for item in broker_repo_roots[:6]) if broker_repo_roots else 'none declared'}",
            f"- Allowed path prefixes: {', '.join(str(item) for item in broker_path_prefixes[:6]) if broker_path_prefixes else 'none declared'}",
            f"- Session recording required/enabled: {'yes' if broker_contract.get('require_session_recording') else 'no'}/{'yes' if broker_contract.get('session_recording_enabled') else 'no'}",
        ]
        if execution_request:
            lines.extend(
                [
                    (
                        f"- Brokered execution request: {execution_request.get('request_id') or 'unknown'} "
                        f"({execution_request.get('request_status') or 'unknown'})"
                    ),
                    (
                        f"- Execution request manifest: "
                        f"{execution_request.get('execution_request_path') or 'not declared'}"
                    ),
                ]
            )
        artifact_blockers = list(artifact_contract.get("blocking_reasons") or [])
        connector_blockers = list(connector_contract.get("blocking_reasons") or [])
        broker_blockers = list(broker_contract.get("blocking_reasons") or [])
        if artifact_blockers:
            lines.append(f"- Artifact blockers: {', '.join(str(item) for item in artifact_blockers)}")
        if connector_blockers:
            lines.append(f"- Connector blockers: {', '.join(str(item) for item in connector_blockers)}")
        if broker_blockers:
            lines.append(f"- Broker blockers: {', '.join(str(item) for item in broker_blockers)}")
        lines.append("- Honor the remote target contract. Do not assume extra artifact roots or connector access beyond what is listed here.")
        return "\n".join(lines)

    @staticmethod
    def _workspace_snapshot_budget(context: RunnerContext) -> tuple[int, int]:
        provider = str(getattr(context.settings, "provider", "") or "").strip().lower()
        model = str(getattr(context.settings, "model", "") or "").strip().lower()
        if provider == "ollama":
            if "7b" in model and ExternalAdapterRunner._editing_expected_for_context(context):
                return (2, 2600)
            if "7b" in model:
                return (2, 3200)
            return (6, 12000)
        return (12, 32000)

    def _workspace_snapshot_markdown(self, context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return "Editable workspace snapshot:\n- No task file context was provided."
        root = Path(self.effective_workspace_path(context)).resolve()
        allowed = list(task.allowed_paths_json or [])
        if not allowed:
            allowed = ["."]
        query_text = self._task_query_text(context)
        reference_paths = self._dedupe_ordered(
            [
                *self._extract_reference_paths(task.scope),
                *[
                    path
                    for step in list(task.validation_steps_json or [])
                    for path in self._extract_reference_paths(str(step))
                ],
                *self._extract_reference_paths(query_text),
                *self._module_reference_candidates(root, query_text),
            ]
        )
        lines = ["Editable workspace snapshot:"]
        file_count = 0
        total_chars = 0
        max_files, max_chars = self._workspace_snapshot_budget(context)
        included_paths: set[str] = set()
        full_single_file_paths: set[str] = set()
        if self._uses_compact_worker_prompt(context) and self._editing_expected_for_context(context) and len(allowed) == 1:
            single_candidates = self._expand_workspace_candidates(root, allowed[0])
            if len(single_candidates) == 1 and single_candidates[0].is_file():
                candidate = single_candidates[0]
                try:
                    raw = candidate.read_bytes()
                except OSError:
                    raw = b""
                if raw and b"\x00" not in raw:
                    text = raw.decode("utf-8", errors="ignore")
                    if text.strip() and len(text) <= 12000:
                        rel_path = candidate.relative_to(root).as_posix()
                        full_single_file_paths.add(rel_path)
                        max_files = max(max_files, 1)
                        max_chars = max(max_chars, len(text) + 1200)

        def append_paths(path_candidates: list[str], *, read_only: bool) -> bool:
            nonlocal file_count, total_chars
            for relative in path_candidates:
                candidates = self._expand_workspace_candidates(root, relative)
                if not candidates:
                    continue
                files: list[Path] = []
                for candidate in candidates:
                    if candidate.is_file():
                        files.append(candidate)
                    else:
                        files.extend(sorted(path for path in candidate.rglob("*") if path.is_file()))
                for file_path in files:
                    if any(part in {"__pycache__", ".git", "node_modules", ".venv", "venv", "mission-control"} for part in file_path.parts):
                        continue
                    try:
                        raw = file_path.read_bytes()
                    except OSError:
                        continue
                    if b"\x00" in raw:
                        continue
                    text = raw.decode("utf-8", errors="ignore")
                    if not text.strip():
                        continue
                    rel_path = file_path.relative_to(root).as_posix()
                    if rel_path in included_paths:
                        continue
                    if rel_path in full_single_file_paths:
                        snippet = text
                        used_targeted_excerpt = False
                    else:
                        snippet, used_targeted_excerpt = self._targeted_file_excerpt(
                            text,
                            query_text=query_text,
                            rel_path=rel_path,
                            max_chars=4000,
                        )
                    projected = total_chars + len(snippet)
                    if file_count >= max_files or projected > max_chars:
                        lines.append("- Additional workspace files omitted for brevity.")
                        return True
                    if used_targeted_excerpt:
                        suffix = "\n... [targeted excerpt selected from a larger file] ..."
                    else:
                        suffix = ""
                    heading = "REFERENCE FILE (read-only)" if read_only else "FILE"
                    lines.append(f"\n{heading}: {rel_path}\n```text\n{snippet}{suffix}\n```")
                    file_count += 1
                    total_chars = projected
                    included_paths.add(rel_path)
            return False

        prioritized_allowed = self._dedupe_ordered(
            [
                *[
                    path
                    for path in reference_paths
                    if self._path_is_allowed(path, allowed, list(task.forbidden_paths_json or []))
                ],
                *self._prioritized_workspace_paths(root, allowed, query_text),
            ]
        )
        if prioritized_allowed and append_paths(prioritized_allowed, read_only=False):
            return "\n".join(lines)
        if append_paths(list(allowed), read_only=False):
            return "\n".join(lines)
        if self._uses_compact_worker_prompt(context) and self._editing_expected_for_context(context):
            if file_count == 0:
                lines.append("- No readable files were found in the allowed paths.")
            return "\n".join(lines)
        support_only_paths = [path for path in reference_paths if path not in allowed]
        if support_only_paths:
            lines.append("\nRead-only support context:")
            if append_paths(support_only_paths, read_only=True):
                return "\n".join(lines)
        if file_count == 0:
            lines.append("- No readable files were found in the allowed paths.")
        return "\n".join(lines)

    @staticmethod
    def _is_worker_report_payload(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        return "status" in payload and "summary" in payload

    @staticmethod
    def _unwrap_nested_payload(payload: dict[str, Any] | None, *, max_depth: int = 3) -> tuple[dict[str, Any] | None, bool]:
        if not isinstance(payload, dict):
            return None, False
        repaired = False
        candidate = dict(payload)
        for _ in range(max_depth):
            next_candidate: dict[str, Any] | None = None
            result_text = candidate.get("result")
            if isinstance(result_text, str):
                parsed, parsed_repaired = BaseCodexRunner.try_parse_json_payload(result_text)
                if isinstance(parsed, dict):
                    next_candidate = parsed
                    repaired = repaired or parsed_repaired
            report_text = candidate.get("report")
            if next_candidate is None and isinstance(report_text, str):
                parsed, parsed_repaired = BaseCodexRunner.try_parse_json_payload(report_text)
                if isinstance(parsed, dict):
                    next_candidate = dict(candidate)
                    next_candidate["report"] = parsed
                    repaired = repaired or parsed_repaired
            if next_candidate is None:
                break
            candidate = next_candidate
        return candidate, repaired

    @staticmethod
    def _normalize_legacy_adapter_payload(candidate: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(candidate, dict):
            return None
        report = candidate.get("report")
        if not isinstance(report, dict):
            return None
        report_status = str(report.get("status") or "").strip().lower()
        report_summary = str(report.get("summary") or report.get("message") or "").strip()
        raw_edits = candidate.get("edits")
        if not isinstance(raw_edits, list):
            raw_edits = report.get("edits")
        edits: list[dict[str, Any]] = []
        for item in list(raw_edits or []):
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or item.get("file_path") or "").strip()
            content = item.get("content")
            search = item.get("search")
            replace = item.get("replace")
            if not path:
                continue
            normalized_edit = {"path": path}
            if isinstance(content, str):
                normalized_edit["content"] = content
            elif isinstance(search, str) and isinstance(replace, str):
                normalized_edit["search"] = search
                normalized_edit["replace"] = replace
            else:
                continue
            summary = item.get("summary")
            if isinstance(summary, str) and summary.strip():
                normalized_edit["summary"] = summary.strip()
            edits.append(normalized_edit)
        files_changed = list(report.get("files_changed") or candidate.get("files_changed") or [])
        if not files_changed and edits:
            files_changed = [str(item.get("path") or "").strip() for item in edits if str(item.get("path") or "").strip()]
        tests_run = list(report.get("tests_run") or candidate.get("tests_run") or candidate.get("validation_commands") or [])
        blockers = list(report.get("blockers") or candidate.get("blockers") or [])
        risks = list(report.get("risks") or candidate.get("risks") or [])
        if not report_status and not report_summary and not edits and not files_changed:
            return None
        envelope_status = "completed" if report_status == "done" else report_status or "failed"
        return {
            "status": envelope_status,
            "runner_type": ExternalAdapterRunner.runner_type,
            "lane": str(candidate.get("lane") or "implementation"),
            "summary": report_summary or "Adapter completed.",
            "report": {
                "agent": str(report.get("agent") or candidate.get("agent") or "adapter"),
                "task_id": str(report.get("task_id") or candidate.get("task_id") or ""),
                "status": report_status or "needs_review",
                "summary": report_summary or "Adapter completed.",
                "files_changed": files_changed,
                "tests_run": tests_run,
                "blockers": blockers,
                "risks": risks,
                "recommended_next_task": str(report.get("recommended_next_task") or candidate.get("recommended_next_task") or ""),
            },
            "files_changed": files_changed,
            "tests_run": tests_run,
            "commands_attempted": list(candidate.get("commands_attempted") or tests_run),
            "evidence": list(candidate.get("evidence") or []),
            "risks": risks,
            "blockers": blockers,
            "diagnostics": list(candidate.get("diagnostics") or []),
            "approvals_requested": list(candidate.get("approvals_requested") or []),
            "recovery_plan": list(candidate.get("recovery_plan") or []),
            "edits": edits,
            "failure_classification": candidate.get("failure_classification"),
            "needs_approval": bool(candidate.get("needs_approval")),
            "metadata_json": dict(candidate.get("metadata_json") or {}),
        }

    def _normalize_adapter_payload(self, stdout_text: str) -> tuple[dict[str, Any] | None, bool]:
        outer, repaired = self.try_parse_json_payload(stdout_text)
        if outer is None:
            return None, repaired
        candidate, repaired_nested = self._unwrap_nested_payload(outer)
        if candidate is None:
            return None, repaired
        repaired = repaired or repaired_nested
        if isinstance(candidate, dict) and self._is_worker_report_payload(candidate.get("report")):
            edits = candidate.get("edits")
            if not isinstance(edits, list):
                edits = []
            normalized = dict(candidate)
            normalized["edits"] = edits
            normalized.setdefault("runner_type", self.runner_type)
            normalized.setdefault("lane", "implementation")
            normalized.setdefault("summary", str(candidate["report"].get("summary") or "Adapter completed."))
            normalized.setdefault("status", "completed" if candidate["report"].get("status") == "done" else "failed")
            normalized.setdefault("files_changed", list(candidate["report"].get("files_changed") or []))
            normalized.setdefault("tests_run", list(candidate["report"].get("tests_run") or []))
            normalized.setdefault("commands_attempted", list(normalized.get("tests_run") or []))
            normalized.setdefault("evidence", [])
            normalized.setdefault("risks", list(candidate["report"].get("risks") or []))
            normalized.setdefault("blockers", list(candidate["report"].get("blockers") or []))
            normalized.setdefault("diagnostics", [])
            normalized.setdefault("approvals_requested", [])
            normalized.setdefault("recovery_plan", [])
            normalized.setdefault("needs_approval", False)
            normalized.setdefault("metadata_json", {})
            return normalized, repaired
        if self._is_worker_report_payload(candidate):
            return {
                "status": "completed" if candidate.get("status") == "done" else "failed",
                "runner_type": self.runner_type,
                "lane": "implementation",
                "summary": str(candidate.get("summary") or "Adapter completed."),
                "report": candidate,
                "files_changed": list(candidate.get("files_changed") or []),
                "tests_run": list(candidate.get("tests_run") or []),
                "commands_attempted": list(candidate.get("tests_run") or []),
                "evidence": [],
                "risks": list(candidate.get("risks") or []),
                "blockers": list(candidate.get("blockers") or []),
                "diagnostics": [],
                "approvals_requested": [],
                "recovery_plan": [],
                "edits": [],
                "failure_classification": None,
                "needs_approval": False,
                "metadata_json": {},
            }, repaired
        legacy_payload = self._normalize_legacy_adapter_payload(candidate)
        if legacy_payload is not None:
            return legacy_payload, repaired
        error_text = str(candidate.get("error") or "").strip() if isinstance(candidate, dict) else ""
        if error_text:
            failure_classification = "timeout" if "timed out" in error_text.lower() else "runner_failed"
            report = {
                "agent": "adapter",
                "task_id": "",
                "status": "blocked",
                "summary": error_text,
                "files_changed": [],
                "tests_run": [],
                "blockers": [error_text],
                "risks": ["The adapter returned an error before producing a valid Mission Control report."],
                "recommended_next_task": "Retry with a smaller scope or investigate the adapter/runtime failure.",
            }
            return {
                "status": "blocked",
                "runner_type": self.runner_type,
                "lane": "implementation",
                "summary": error_text,
                "report": report,
                "files_changed": [],
                "tests_run": [],
                "commands_attempted": [],
                "evidence": [],
                "risks": list(report["risks"]),
                "blockers": list(report["blockers"]),
                "diagnostics": [],
                "approvals_requested": [],
                "recovery_plan": [report["recommended_next_task"]],
                "edits": [],
                "failure_classification": failure_classification,
                "needs_approval": False,
                "metadata_json": {"adapter_error": error_text},
            }, repaired
        return None, repaired

    @staticmethod
    def _path_is_allowed(path: str, allowed_paths: list[str], forbidden_paths: list[str]) -> bool:
        normalized = path.strip("/").lower()
        if not normalized:
            return False
        allowed = [item.strip("/").lower() for item in allowed_paths if item.strip()]
        forbidden = [item.strip("/").lower() for item in forbidden_paths if item.strip()]
        if forbidden and any(ExternalAdapterRunner._path_matches_pattern(normalized, item) for item in forbidden):
            return False
        if not allowed:
            return True
        return any(ExternalAdapterRunner._path_matches_pattern(normalized, item) for item in allowed)

    @staticmethod
    def _contains_placeholder_edit_content(content: str) -> bool:
        lowered = content.lower()
        if "rest of the file content" in lowered:
            return True
        placeholder_phrases = (
            "full updated file contents go here",
            "updated file contents go here",
            "rest of file",
            "remaining code",
            "unchanged code",
            "existing code",
            "other settings",
        )
        if any(phrase in lowered for phrase in placeholder_phrases):
            return True
        if "..." in content and any(phrase in lowered for phrase in placeholder_phrases):
            return True
        return bool(re.search(r"(?m)^\s*(?:#|//|/\*)?\s*\.\.\.\s*(?:\*/)?\s*$", content))

    @staticmethod
    def _query_same_file_helper_anchor_names(query_text: str | None, relative_path: str) -> list[str]:
        normalized_path = str(relative_path or "").strip().replace("\\", "/").lower()
        if not normalized_path:
            return []
        found: list[str] = []
        seen: set[str] = set()
        for raw_line in str(query_text or "").splitlines():
            stripped = raw_line.strip().lstrip("-").strip()
            segments = [segment.strip().rstrip(".") for segment in stripped.split(";") if segment.strip()]
            for segment in segments:
                lowered = segment.lower()
                if "same-file helper anchors:" in lowered:
                    segment = segment.split(":", 1)[1].strip()
                    lowered = segment.lower()
                if not lowered.startswith(f"{normalized_path}:"):
                    continue
                match = re.search(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", segment)
                if not match:
                    continue
                name = str(match.group(1) or "").strip()
                lowered_name = name.lower()
                if not name or lowered_name in seen:
                    continue
                seen.add(lowered_name)
                found.append(name)
        return found

    @staticmethod
    def _query_has_explicit_same_file_helper_anchors(query_text: str | None, relative_path: str) -> bool:
        normalized_path = str(relative_path or "").strip().replace("\\", "/").lower()
        if not normalized_path:
            return False
        for raw_line in str(query_text or "").splitlines():
            lowered = raw_line.strip().lower()
            if "same-file helper anchors:" in lowered and normalized_path in lowered:
                return True
        return False

    @staticmethod
    def _looks_like_boolean_normalization_text(text: str | None) -> bool:
        lowered = str(text or "").lower()
        if any(marker in lowered for marker in ("np.where(", ".astype(bool)", " true", " false")):
            return True
        return bool(
            re.search(
                r"(?:return|=)\s*\(?[a-z0-9_.\[\]]+\s*(?:==|!=)\s*[01]\)?(?:\s*\.(?:all|any)\(|\s*$)",
                lowered,
            )
        )

    @classmethod
    def _same_file_helper_bypass_normalization_helpers(
        cls,
        *,
        relative_path: str,
        existing_text: str | None,
        query_text: str | None,
    ) -> list[str]:
        helper_names = cls._query_same_file_helper_anchor_names(query_text, relative_path)
        if existing_text:
            normalized_path = str(relative_path or "").strip().replace("\\", "/")
            query_anchors = [anchor for anchor in cls._query_line_anchors(query_text) if anchor[0] == normalized_path]
            if query_anchors:
                anchor_name = cls._definition_name_from_snippet(query_anchors[0][2])
                anchor_line = cls._find_symbol_definition_line(existing_text, anchor_name or "")
                if anchor_line is not None:
                    live_helper_names = [symbol for symbol, _line in cls._same_file_helper_callee_symbols(existing_text, anchor_line)]
                    if live_helper_names:
                        helper_names = cls._dedupe_ordered([*live_helper_names, *helper_names])
        return helper_names

    @classmethod
    def _search_replace_touches_anchored_symbol(
        cls,
        *,
        relative_path: str,
        existing_text: str | None,
        search: str | None,
        query_text: str | None,
    ) -> bool:
        if not existing_text or not search:
            return False
        normalized_path = str(relative_path or "").strip().replace("\\", "/")
        anchored_symbols = cls._dedupe_ordered(
            [
                *cls._query_same_file_helper_anchor_names(query_text, normalized_path),
                *sorted(cls._anchored_symbol_names(query_text, normalized_path)),
            ]
        )
        for symbol in anchored_symbols:
            definition_block = cls._definition_block_for_symbol(existing_text, symbol, max_chars=3200, max_lines=100)
            if definition_block and search in definition_block:
                return True
        return False

    @classmethod
    def _is_same_file_helper_bypass_normalization_edit(
        cls,
        *,
        relative_path: str,
        existing_text: str | None,
        search: str | None,
        replace: str | None,
        content: str | None,
        query_text: str | None,
    ) -> bool:
        explicit_query_helper_anchors = cls._query_has_explicit_same_file_helper_anchors(query_text, relative_path)
        helper_names = cls._same_file_helper_bypass_normalization_helpers(
            relative_path=relative_path,
            existing_text=existing_text,
            query_text=query_text,
        )
        if not helper_names:
            return False
        normalization_targets = [text for text in (search, replace, content) if cls._looks_like_boolean_normalization_text(text)]
        if not normalization_targets:
            return False
        combined_text = "\n".join(str(item or "") for item in (search, replace, content))
        lowered_combined = combined_text.lower()
        lowered_query = str(query_text or "").lower()
        touched_helper_name = any(helper.lower() in "\n".join(str(item or "") for item in (search, replace)).lower() for helper in helper_names)
        helper_definition_changed = False
        if content is not None and existing_text:
            for helper in helper_names:
                existing_helper_block = cls._definition_block_for_symbol(existing_text, helper, max_chars=3200, max_lines=100)
                updated_helper_block = cls._definition_block_for_symbol(content, helper, max_chars=3200, max_lines=100)
                if existing_helper_block and updated_helper_block and existing_helper_block != updated_helper_block:
                    helper_definition_changed = True
                    break
        touched_helper_name = touched_helper_name or helper_definition_changed
        strict_anchor_retry = any(
            marker in lowered_query
            for marker in (
                "same-file helper callees",
                "upstream return path",
            )
        )
        if not touched_helper_name and cls._search_replace_touches_anchored_symbol(
            relative_path=relative_path,
            existing_text=existing_text,
            search=search,
            query_text=query_text,
        ):
            if explicit_query_helper_anchors and not strict_anchor_retry:
                return False
            return True
        return not touched_helper_name

    @staticmethod
    def _is_suspicious_full_file_rewrite(existing_text: str, content: str) -> bool:
        existing_lines = existing_text.splitlines()
        new_lines = content.splitlines()
        if len(existing_lines) < 80:
            return False
        if len(existing_lines) - len(new_lines) < 80:
            return False
        return len(new_lines) <= max(20, int(len(existing_lines) * 0.35))

    @staticmethod
    def _python_syntax_issue(relative_path: str, content: str) -> str | None:
        normalized_path = str(relative_path or "").strip().replace("\\", "/").lower()
        if not normalized_path.endswith(".py"):
            return None
        try:
            compile(content, normalized_path, "exec")
        except SyntaxError as exc:
            line_number = int(getattr(exc, "lineno", 0) or 0)
            details = str(exc.msg or "invalid syntax").strip() or "invalid syntax"
            if line_number > 0:
                return (
                    f"Rejected edit for {relative_path} because it introduces a Python syntax error "
                    f"at line {line_number}: {details}"
                )
            return f"Rejected edit for {relative_path} because it introduces a Python syntax error: {details}"
        return None

    @staticmethod
    def _normalize_search_replace_replacement(existing_text: str, replace: str, position: int) -> str:
        if "\n" not in replace:
            return replace
        line_start = existing_text.rfind("\n", 0, position)
        line_start = 0 if line_start < 0 else line_start + 1
        indent_prefix = existing_text[line_start:position]
        if not indent_prefix or indent_prefix.strip():
            return replace
        return ExternalAdapterRunner._indent_multiline_replacement(replace, indent_prefix)

    @staticmethod
    def _indent_multiline_replacement(replace: str, indent_prefix: str, *, include_first_line: bool = False) -> str:
        lines = replace.splitlines(keepends=True)
        if len(lines) < 2:
            return replace
        follow_up_indents = [
            len(line) - len(line.lstrip(" \t"))
            for line in lines[1:]
            if line.strip()
        ]
        common_follow_up_indent = min(follow_up_indents) if follow_up_indents else 0
        adjusted: list[str] = []
        for index, line in enumerate(lines):
            working_line = line
            if index > 0 and common_follow_up_indent > 0 and working_line.strip():
                trimmed = 0
                while trimmed < common_follow_up_indent and working_line.startswith((" ", "\t")):
                    working_line = working_line[1:]
                    trimmed += 1
            if index == 0 and not include_first_line:
                adjusted.append(working_line)
                continue
            if index > 0 and working_line.strip():
                adjusted.append(indent_prefix + working_line)
            elif working_line.strip() and not working_line.startswith((" ", "\t")):
                adjusted.append(indent_prefix + working_line)
            else:
                adjusted.append(working_line)
        return "".join(adjusted)

    @classmethod
    def _splice_search_replace(
        cls,
        existing_text: str,
        *,
        search: str,
        replace: str,
        position: int,
    ) -> str:
        if "\n" in replace and "\n" not in search:
            line_start = existing_text.rfind("\n", 0, position)
            line_start = 0 if line_start < 0 else line_start + 1
            line_end = existing_text.find("\n", position + len(search))
            line_end = len(existing_text) if line_end < 0 else line_end
            line_prefix = existing_text[line_start:position]
            line_suffix = existing_text[position + len(search) : line_end]
            if line_prefix.strip() or line_suffix.strip():
                indent_prefix = line_prefix[: len(line_prefix) - len(line_prefix.lstrip(" \t"))]
                replacement_block = cls._indent_multiline_replacement(
                    replace,
                    indent_prefix,
                    include_first_line=True,
                )
                return existing_text[:line_start] + replacement_block + existing_text[line_end:]
        normalized_replace = cls._normalize_search_replace_replacement(existing_text, replace, position)
        return existing_text[:position] + normalized_replace + existing_text[position + len(search) :]

    @staticmethod
    def _search_positions(existing_text: str, search: str) -> list[int]:
        positions: list[int] = []
        start = 0
        while True:
            index = existing_text.find(search, start)
            if index < 0:
                break
            positions.append(index)
            start = index + 1
        return positions

    @classmethod
    def _search_multiline_positions_relaxed(cls, existing_text: str, search: str) -> list[tuple[int, str]]:
        if "\n" not in search:
            return []
        search_lines = search.splitlines()
        if len(search_lines) < 2:
            return []
        existing_lines = existing_text.splitlines(keepends=True)
        if len(existing_lines) < len(search_lines):
            return []
        line_offsets: list[int] = []
        cursor = 0
        for line in existing_lines:
            line_offsets.append(cursor)
            cursor += len(line)
        matches: list[tuple[int, str]] = []
        first_search_line = search_lines[0]
        stripped_first_search_line = first_search_line.lstrip(" \t")
        for start_index in range(len(existing_lines) - len(search_lines) + 1):
            first_existing_line = existing_lines[start_index].rstrip("\r\n")
            anchor_column = first_existing_line.find(first_search_line)
            matched_first_line = first_search_line
            if anchor_column < 0 and stripped_first_search_line != first_search_line:
                anchor_column = first_existing_line.find(stripped_first_search_line)
                matched_first_line = stripped_first_search_line
            if anchor_column < 0:
                anchor_column = first_existing_line.find(stripped_first_search_line)
                matched_first_line = stripped_first_search_line
            if anchor_column < 0 or first_existing_line[anchor_column:] != matched_first_line:
                continue
            match_ok = True
            search_offset = 1
            existing_offset = 1
            last_matched_existing_index = start_index
            allow_extra_blank_lines = False
            while search_offset < len(search_lines):
                existing_index = start_index + existing_offset
                if existing_index >= len(existing_lines):
                    match_ok = False
                    break
                search_line = search_lines[search_offset]
                existing_line = existing_lines[existing_index].rstrip("\r\n")
                normalized_search_line = search_line.lstrip(" \t")
                normalized_existing_line = existing_line.lstrip(" \t")
                if normalized_existing_line == normalized_search_line:
                    last_matched_existing_index = existing_index
                    allow_extra_blank_lines = normalized_search_line == ""
                    search_offset += 1
                    existing_offset += 1
                    continue
                if allow_extra_blank_lines and normalized_existing_line == "":
                    last_matched_existing_index = existing_index
                    existing_offset += 1
                    continue
                match_ok = False
                break
            if not match_ok:
                continue
            start_position = line_offsets[start_index] + anchor_column
            last_line = existing_lines[last_matched_existing_index].rstrip("\r\n")
            end_position = line_offsets[last_matched_existing_index] + len(last_line)
            matches.append((start_position, existing_text[start_position:end_position]))
        return matches

    @classmethod
    def _can_apply_search_replace_to_all_matches(
        cls,
        existing_text: str,
        search: str,
        positions: list[int],
        matched_search_texts: dict[int, str] | None = None,
    ) -> bool:
        if len(positions) <= 1 or len(positions) > 8:
            return False
        normalized_matches = {
            cls._normalize_exact_repo_match_snippet(
                (matched_search_texts or {}).get(position, existing_text[position : position + len(search)])
            )
            for position in positions
        }
        return len(normalized_matches) == 1

    @classmethod
    def _apply_search_replace_to_all_matches(
        cls,
        existing_text: str,
        *,
        replace: str,
        positions: list[int],
        matched_search_texts: dict[int, str] | None = None,
        search: str,
    ) -> str:
        updated_text = existing_text
        for position in sorted(positions, reverse=True):
            matched_search = (matched_search_texts or {}).get(position, search)
            updated_text = cls._splice_search_replace(updated_text, search=matched_search, replace=replace, position=position)
        return updated_text

    @staticmethod
    def _strip_list_prefix(text: str) -> str:
        return re.sub(r"^(?:[-*+]\s+|\d+\.\s+)", "", str(text or "").strip())

    @classmethod
    def _normalize_exact_repo_match_line(cls, text: str) -> str:
        return " ".join(cls._strip_list_prefix(text).split())

    @staticmethod
    def _normalize_exact_repo_match_snippet(text: str) -> str:
        return " ".join(str(text or "").strip().split())

    @classmethod
    def _count_query_exact_match_mentions(cls, query_text: str | None, relative_path: str, search: str) -> int:
        normalized_path = str(relative_path or "").strip().replace("\\", "/").lower()
        normalized_search = cls._normalize_exact_repo_match_snippet(search)
        if not normalized_path or not normalized_search:
            return 0
        count = 0
        for raw_line in str(query_text or "").splitlines():
            line = cls._normalize_exact_repo_match_line(raw_line)
            if not line.lower().startswith(f"{normalized_path}:"):
                continue
            if normalized_search in line:
                count += 1
        return count

    @classmethod
    def _exact_repo_match_positions(
        cls,
        query_text: str | None,
        relative_path: str,
        search: str,
    ) -> set[int]:
        normalized_path = str(relative_path or "").strip().replace("\\", "/").lower()
        normalized_search = cls._normalize_exact_repo_match_snippet(search)
        if not normalized_path or not normalized_search:
            return set()
        positions: set[int] = set()
        for raw_line in str(query_text or "").splitlines():
            line = cls._normalize_exact_repo_match_line(raw_line)
            if not line.lower().startswith(f"{normalized_path}:"):
                continue
            marker = line[len(normalized_path) + 1 :]
            line_number_text, separator, remainder = marker.partition(":")
            if not separator or normalized_search not in remainder.strip():
                continue
            try:
                line_number = int(line_number_text.strip())
            except ValueError:
                continue
            if line_number > 0:
                positions.add(line_number)
        return positions

    @classmethod
    def _search_positions_from_exact_repo_matches(
        cls,
        existing_text: str,
        *,
        search: str,
        candidate_positions: list[int],
        query_text: str | None,
        relative_path: str,
    ) -> list[int]:
        line_numbers = cls._exact_repo_match_positions(query_text, relative_path, search)
        if not line_numbers:
            return []
        matched_positions: list[int] = []
        for position in candidate_positions:
            line_number = existing_text.count("\n", 0, position) + 1
            if line_number in line_numbers:
                matched_positions.append(position)
        return matched_positions

    @classmethod
    def _disambiguate_search_replace_edit(
        cls,
        existing_text: str,
        *,
        relative_path: str,
        search: str,
        replace: str,
        query_text: str | None,
    ) -> str | None:
        positions = cls._search_positions(existing_text, search)
        if len(positions) <= 1:
            return existing_text.replace(search, replace, 1) if positions else None

        ranked_terms = cls._ranked_excerpt_terms(str(query_text or ""), relative_path)
        symbol_terms = [term.lower() for term in ranked_terms if "_" in term or any(char.isupper() for char in term)]
        if not symbol_terms:
            return None

        scored_positions: list[tuple[int, int]] = []
        for position in positions:
            prefix = existing_text[:position]
            enclosing_matches = list(re.finditer(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", prefix, flags=re.MULTILINE))
            enclosing_symbol = enclosing_matches[-1].group(1).lower() if enclosing_matches else ""
            line_start = existing_text.rfind("\n", 0, position)
            line_end = existing_text.find("\n", position)
            line_text = existing_text[(line_start + 1 if line_start >= 0 else 0) : (line_end if line_end >= 0 else len(existing_text))].lower()
            score = 0
            for index, term in enumerate(symbol_terms[:8]):
                bonus = max(20, 140 - (index * 12))
                if term and term in enclosing_symbol:
                    score += bonus + 120
                if term and term in line_text:
                    score += bonus
            scored_positions.append((score, position))

        scored_positions.sort(key=lambda item: (-item[0], item[1]))
        if not scored_positions or scored_positions[0][0] <= 0:
            return None
        if len(scored_positions) > 1 and scored_positions[0][0] == scored_positions[1][0]:
            return None
        best_position = scored_positions[0][1]
        return cls._splice_search_replace(existing_text, search=search, replace=replace, position=best_position)

    def _apply_adapter_edits(self, state: ExternalAdapterRunState, edits: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
        workspace_root = Path(state.workspace_path or "").resolve()
        applied: list[str] = []
        issues: list[str] = []
        for edit in edits:
            if not isinstance(edit, dict):
                issues.append("Encountered a non-object edit entry.")
                continue
            relative_path = str(edit.get("path") or "").strip().replace("\\", "/")
            content = edit.get("content")
            search = edit.get("search")
            replace = edit.get("replace")
            has_full_content = isinstance(content, str)
            has_search_replace = isinstance(search, str) and isinstance(replace, str) and bool(search)
            if not relative_path or (not has_full_content and not has_search_replace):
                issues.append("Edit entries must include a string path and either full content or search/replace values.")
                continue
            if self._path_is_benchmark_protected(relative_path, state.protected_paths):
                issues.append(f"Rejected edit to benchmark-protected path: {relative_path}")
                continue
            if not self._path_is_allowed(relative_path, state.allowed_paths, state.forbidden_paths):
                issues.append(f"Rejected edit outside allowed paths: {relative_path}")
                continue
            target = (workspace_root / relative_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                issues.append(f"Rejected edit outside workspace root: {relative_path}")
                continue
            existing_text: str | None = None
            if target.exists():
                try:
                    existing_text = target.read_text(encoding="utf-8")
                except OSError as exc:
                    issues.append(f"Failed to read existing content for {relative_path}: {exc}")
                    continue
            if has_search_replace:
                if existing_text is None:
                    issues.append(f"Rejected search/replace edit for missing file: {relative_path}")
                    continue
                if not search:
                    issues.append(f"Rejected search/replace edit with empty search text: {relative_path}")
                    continue
                positions = self._search_positions(existing_text, search)
                matched_search_texts = {position: search for position in positions}
                if not positions and "\n" in search:
                    relaxed_matches = self._search_multiline_positions_relaxed(existing_text, search)
                    positions = [position for position, _matched_search in relaxed_matches]
                    matched_search_texts = {
                        position: matched_search
                        for position, matched_search in relaxed_matches
                    }
                match_count = len(positions)
                if match_count == 0:
                    issues.append(f"Rejected search/replace edit because the search text was not found in {relative_path}")
                    continue
                if self._contains_placeholder_edit_content(replace):
                    issues.append(
                        f"Rejected placeholder or truncated replacement text for {relative_path}; "
                        "Mission Control requires exact patch text."
                    )
                    continue
                if self._is_same_file_helper_bypass_normalization_edit(
                    relative_path=relative_path,
                    existing_text=existing_text,
                    search=search,
                    replace=replace,
                    content=None,
                    query_text=state.task_query_text,
                ):
                    helper_names = self._same_file_helper_bypass_normalization_helpers(
                        relative_path=relative_path,
                        existing_text=existing_text,
                        query_text=state.task_query_text,
                    )
                    helper_hint = (
                        f" Patch the live same-file helper(s) first: {', '.join(f'`{name}`' for name in helper_names[:3])}."
                        if helper_names
                        else ""
                    )
                    issues.append(
                        f"Rejected downstream boolean-normalization-only edit for {relative_path}; "
                        "same-file helper anchors are present in task context and this edit does not patch them."
                        f"{helper_hint}"
                    )
                    continue
                if match_count > 1:
                    exact_match_mentions = self._count_query_exact_match_mentions(state.task_query_text, relative_path, search)
                    if exact_match_mentions >= 2 and self._can_apply_search_replace_to_all_matches(
                        existing_text,
                        search,
                        positions,
                        matched_search_texts,
                    ):
                        updated_text = self._apply_search_replace_to_all_matches(
                            existing_text,
                            replace=replace,
                            positions=positions,
                            matched_search_texts=matched_search_texts,
                            search=search,
                        )
                    else:
                        exact_repo_positions = self._search_positions_from_exact_repo_matches(
                            existing_text,
                            search=search,
                            candidate_positions=positions,
                            query_text=state.task_query_text,
                            relative_path=relative_path,
                        )
                        if len(exact_repo_positions) == 1:
                            matched_search = matched_search_texts.get(exact_repo_positions[0], search)
                            updated_text = self._splice_search_replace(
                                existing_text,
                                search=matched_search,
                                replace=replace,
                                position=exact_repo_positions[0],
                            )
                        elif (
                            len(exact_repo_positions) >= 2
                            and len(exact_repo_positions) == len(positions)
                            and self._can_apply_search_replace_to_all_matches(
                                existing_text,
                                search,
                                positions,
                                matched_search_texts,
                            )
                        ):
                            updated_text = self._apply_search_replace_to_all_matches(
                                existing_text,
                                replace=replace,
                                positions=positions,
                                matched_search_texts=matched_search_texts,
                                search=search,
                            )
                        else:
                            updated_text = self._disambiguate_search_replace_edit(
                                existing_text,
                                relative_path=relative_path,
                                search=search,
                                replace=replace,
                                query_text=state.task_query_text,
                            )
                            if updated_text is None:
                                issues.append(
                                    f"Rejected search/replace edit because the search text matched {match_count} locations in {relative_path}"
                                )
                                continue
                else:
                    match_position = positions[0]
                    matched_search = matched_search_texts.get(match_position, search)
                    updated_text = self._splice_search_replace(
                        existing_text,
                        search=matched_search,
                        replace=replace,
                        position=match_position,
                    )
                if updated_text == existing_text:
                    issues.append(f"Rejected no-op search/replace edit with unchanged content: {relative_path}")
                    continue
                content_to_write = updated_text
            else:
                assert isinstance(content, str)
                if self._contains_placeholder_edit_content(content):
                    issues.append(
                        f"Rejected placeholder or truncated full-file edit for {relative_path}; "
                        "Mission Control requires exact final file contents."
                    )
                    continue
                if self._is_same_file_helper_bypass_normalization_edit(
                    relative_path=relative_path,
                    existing_text=existing_text,
                    search=None,
                    replace=None,
                    content=content,
                    query_text=state.task_query_text,
                ):
                    helper_names = self._same_file_helper_bypass_normalization_helpers(
                        relative_path=relative_path,
                        existing_text=existing_text,
                        query_text=state.task_query_text,
                    )
                    helper_hint = (
                        f" Patch the live same-file helper(s) first: {', '.join(f'`{name}`' for name in helper_names[:3])}."
                        if helper_names
                        else ""
                    )
                    issues.append(
                        f"Rejected downstream boolean-normalization-only edit for {relative_path}; "
                        "same-file helper anchors are present in task context and this edit does not patch them."
                        f"{helper_hint}"
                    )
                    continue
                if existing_text is not None:
                    if self._is_suspicious_full_file_rewrite(existing_text, content):
                        issues.append(
                            f"Rejected suspiciously destructive full-file rewrite for {relative_path}; "
                            "the proposed replacement shrank the file far beyond a plausible narrow fix."
                        )
                        continue
                    if existing_text == content:
                        issues.append(f"Rejected no-op edit with unchanged content: {relative_path}")
                        continue
                content_to_write = content
            if existing_text is not None:
                renamed_definition, rename_issue = self._renames_protected_definition(
                    relative_path=relative_path,
                    existing_text=existing_text,
                    updated_text=content_to_write,
                    query_text=state.task_query_text,
                )
                if renamed_definition and rename_issue:
                    issues.append(rename_issue)
                    continue
                bypassed_helper, bypass_issue = self._bypasses_anchored_same_file_helper(
                    relative_path=relative_path,
                    existing_text=existing_text,
                    updated_text=content_to_write,
                    query_text=state.task_query_text,
                )
                if bypassed_helper and bypass_issue:
                    issues.append(bypass_issue)
                    continue
            syntax_issue = self._python_syntax_issue(relative_path, content_to_write)
            if syntax_issue:
                issues.append(syntax_issue)
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content_to_write, encoding="utf-8")
                applied.append(relative_path)
            except OSError as exc:
                issues.append(f"Failed to write {relative_path}: {exc}")
        return applied, issues

    def _persist_runtime_manifest(
        self,
        state: ExternalAdapterRunState,
        *,
        envelope_payload: dict[str, Any] | None = None,
        report_payload: dict[str, Any] | None = None,
    ) -> None:
        manifest_path = str(state.runtime_manifest_path or "").strip()
        if not manifest_path:
            return
        payload = dict(state.runtime_manifest_payload or {})
        payload.update(
            {
                "runner_type": self.runner_type,
                "status": state.status,
                "exit_code": state.exit_code,
                "applied_edit_count": len(state.applied_edits),
                "applied_edits": list(state.applied_edits),
                "edit_issue_count": len(state.edit_issues),
                "edit_issues": list(state.edit_issues),
                "process_timeout_seconds": state.process_timeout_seconds,
                "quota_contract": dict(state.quota_contract or {}),
                "quota_enforcement_status": state.quota_enforcement_status,
                "quota_blocking_reasons": list(state.quota_blocking_reasons or []),
            }
        )
        if isinstance(report_payload, dict):
            payload["report"] = {
                "status": report_payload.get("status"),
                "summary": report_payload.get("summary"),
                "files_changed": list(report_payload.get("files_changed") or []),
                "tests_run": list(report_payload.get("tests_run") or []),
                "blockers": list(report_payload.get("blockers") or []),
                "risks": list(report_payload.get("risks") or []),
            }
        if isinstance(envelope_payload, dict):
            payload["result_envelope"] = {
                "status": envelope_payload.get("status"),
                "summary": envelope_payload.get("summary"),
                "lane": envelope_payload.get("lane"),
                "failure_classification": envelope_payload.get("failure_classification"),
                "needs_approval": bool(envelope_payload.get("needs_approval")),
                "evidence_count": len(list(envelope_payload.get("evidence") or [])),
                "commands_attempted": list(envelope_payload.get("commands_attempted") or []),
                "diagnostics": list(envelope_payload.get("diagnostics") or []),
            }
        target = Path(manifest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _build_timeout_envelope(self, state: ExternalAdapterRunState) -> tuple[dict[str, Any], dict[str, Any]]:
        timeout_seconds = float(state.process_timeout_seconds or 0)
        timeout_summary = (
            str(state.timeout_summary or "").strip()
            or f"Adapter exceeded the enforced runtime ceiling of {timeout_seconds:.0f}s and Mission Control terminated it."
        )
        report_payload = {
            "agent": str((state.runtime_manifest_payload or {}).get("target_id") or "adapter"),
            "task_id": "",
            "status": "blocked",
            "summary": timeout_summary,
            "files_changed": [],
            "tests_run": [],
            "blockers": [
                f"Mission Control terminated the adapter after {timeout_seconds:.2f}s because the governed runtime ceiling was exceeded."
            ],
            "risks": [
                "Remote execution runtime exceeded the governed target ceiling.",
            ],
            "recommended_next_task": "Reduce the remote workload or increase the target runtime quota before retrying.",
        }
        envelope_payload = {
            "status": "blocked",
            "runner_type": self.runner_type,
            "lane": "implementation",
            "summary": timeout_summary,
            "report": report_payload,
            "files_changed": [],
            "tests_run": [],
            "commands_attempted": [],
            "evidence": [],
            "risks": list(report_payload["risks"]),
            "blockers": list(report_payload["blockers"]),
            "diagnostics": [],
            "approvals_requested": [],
            "recovery_plan": ["Reduce requested remote work or raise the governed runtime ceiling before dispatch."],
            "edits": [],
            "failure_classification": "user_action_required",
            "needs_approval": False,
            "metadata_json": {
                "quota_enforcement_status": state.quota_enforcement_status,
                "quota_blocking_reasons": list(state.quota_blocking_reasons or []),
                "process_timeout_seconds": timeout_seconds,
            },
        }
        return envelope_payload, report_payload

    async def _start_process(self, context: RunnerContext, prompt: str) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("The external adapter command is not configured or is not available on PATH.")
        command = context.settings.adapter_command or ""
        args = [command, *(context.settings.adapter_args or [])]
        run_id = f"adapter-{uuid.uuid4().hex}"
        initial_usage = build_prompt_usage_estimate(prompt)
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        effective_label = default_label(context.settings.provider)
        workdir = self.effective_workspace_path(context)
        state = ExternalAdapterRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            workspace_path=workdir,
            allowed_paths=list(context.task.allowed_paths_json or []) if context.task else [],
            forbidden_paths=list(context.task.forbidden_paths_json or []) if context.task else [],
            task_query_text=self._task_query_text(context),
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or effective_label,
                "reasoning_effort": context.settings.reasoning_effort or effective_label,
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
                "provider_endpoint": context.settings.provider_endpoint,
                "adapter_command": command,
            },
            required_validation_commands=self._required_validation_commands(context.task),
            enforce_command_execution=self._requires_command_execution(context),
            editing_expected=self._editing_expected_for_context(context),
        )
        workspace_root = Path(workdir).resolve()
        if workspace_root.exists() and workspace_root.is_dir():
            state.protected_paths = self._load_benchmark_protected_paths(workspace_root)
        if workspace_root.exists() and workspace_root.is_dir() and state.allowed_paths:
            state.scoped_workspace_baseline = self._capture_scoped_workspace_baseline(
                workspace_root,
                state.allowed_paths,
                protected_paths=state.protected_paths,
            )
        self.runs[run_id] = state
        state.events.append({"type": "thread.started", "thread_id": run_id})
        state.events.append({"type": "turn.started", "effective_settings": state.effective_settings})
        env = {
            **os.environ.copy(),
            "MISSION_CONTROL_MODEL": context.settings.model or "",
            "MISSION_CONTROL_REASONING_EFFORT": context.settings.reasoning_effort or "",
            "MISSION_CONTROL_SANDBOX_MODE": context.settings.sandbox_mode,
            "MISSION_CONTROL_APPROVAL_POLICY": context.settings.approval_policy,
            "MISSION_CONTROL_PROVIDER": context.settings.provider,
            "MISSION_CONTROL_PROVIDER_ENDPOINT": context.settings.provider_endpoint or "",
            "MISSION_CONTROL_OLLAMA_ENDPOINT": context.settings.provider_endpoint or "",
            "MISSION_CONTROL_DOCS_PATH": context.docs_path,
            "MISSION_CONTROL_PROJECT_NAME": context.project.name,
            "MISSION_CONTROL_PROJECT_WORKSPACE": context.project.workspace_path,
            "MISSION_CONTROL_AGENT_NAME": context.agent.name,
            "MISSION_CONTROL_AGENT_ROLE": context.agent.role,
            "MISSION_CONTROL_TASK_ID": str(context.task.id if context.task else ""),
        }
        state.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=env,
            **self.quiet_subprocess_kwargs(),
        )
        assert state.process.stdin is not None
        state.stdin_writer_task = asyncio.create_task(self._write_prompt_to_process(run_id, prompt))
        state.reader_task = asyncio.create_task(self._consume_process(run_id, args))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            initial_usage=initial_usage,
        )

    async def _write_prompt_to_process(self, run_id: str, prompt: str) -> None:
        state = self.runs.get(run_id)
        if state is None or state.process is None or state.process.stdin is None:
            return
        try:
            state.process.stdin.write(prompt.encode("utf-8"))
            await state.process.stdin.drain()
        except (asyncio.CancelledError, BrokenPipeError, ConnectionResetError):
            return
        finally:
            try:
                state.process.stdin.close()
            except Exception:
                pass

    async def _consume_process(self, run_id: str, args: list[str]) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        stdout_text = ""
        stderr_text = ""
        repaired = False
        envelope_payload: dict[str, Any] | None = None
        report_payload: dict[str, Any] | None = None
        try:
            timeout_seconds = float(state.process_timeout_seconds or 0)
            timed_out = False
            stdout_bytes = b""
            stderr_bytes = b""
            try:
                if timeout_seconds > 0:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(state.process.communicate(), timeout=timeout_seconds)
                else:
                    stdout_bytes, stderr_bytes = await state.process.communicate()
            except asyncio.TimeoutError:
                timed_out = True
                if state.quota_enforcement_status in {None, "", "armed"}:
                    state.quota_enforcement_status = "blocked"
                if "remote_command_runtime_exceeded" not in state.quota_blocking_reasons:
                    state.quota_blocking_reasons.append("remote_command_runtime_exceeded")
                try:
                    state.process.terminate()
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(state.process.wait(), timeout=1.0)
                except Exception:
                    kill = getattr(state.process, "kill", None)
                    if callable(kill):
                        try:
                            kill()
                        except Exception:
                            pass
                    try:
                        await asyncio.wait_for(state.process.wait(), timeout=1.0)
                    except Exception:
                        pass
            state.exit_code = state.process.returncode
            stdout_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
            parsed, repaired = self._normalize_adapter_payload(stdout_text)
            if timed_out:
                envelope_payload, report_payload = self._build_timeout_envelope(state)
                state.status = "blocked"
                state.final_text = json.dumps(envelope_payload)
                state.events.append(
                    {
                        "type": "quota.enforced",
                        "enforcement": "runtime_timeout",
                        "timeout_seconds": timeout_seconds,
                        "blocking_reasons": list(state.quota_blocking_reasons or []),
                    }
                )
            elif parsed:
                envelope_payload = dict(parsed)
                report_payload = dict(envelope_payload.get("report") or {})
                claimed_files_changed = [
                    str(path).strip().replace("\\", "/")
                    for path in list(report_payload.get("files_changed") or [])
                    if str(path).strip()
                ]
                edits = [item for item in (envelope_payload.get("edits") or []) if isinstance(item, dict)]
                synthesized_edits, synthesized_edit_issues = self._synthesize_scoped_workspace_edits(state)
                synthesized_edit_paths = self._edit_path_set(synthesized_edits)
                discarded_changes = self._restore_scoped_workspace_baseline(state)
                state.discarded_workspace_changes = list(discarded_changes)
                effective_edits = edits or synthesized_edits
                applied, issues = self._apply_adapter_edits(state, effective_edits)
                used_synthesized_recovery = False
                synthesized_recovery_reason: str | None = None
                recovered_edit_contract_issues: list[str] = []
                if edits and not applied and synthesized_edits:
                    fallback_applied, fallback_issues = self._apply_adapter_edits(state, synthesized_edits)
                    if fallback_applied:
                        recovered_edit_contract_issues = list(issues)
                        applied = fallback_applied
                        issues = list(fallback_issues)
                        used_synthesized_recovery = True
                        synthesized_recovery_reason = (
                            "because the adapter returned unusable accepted edits[]."
                        )
                    elif fallback_issues:
                        issues = [*issues, *fallback_issues]
                if (
                    edits
                    and synthesized_edits
                    and applied
                    and not used_synthesized_recovery
                    and synthesized_edit_paths
                    and set(applied) == synthesized_edit_paths
                    and not state.enforce_command_execution
                ):
                    drift_paths = self._synthesized_workspace_drift_paths(state, synthesized_edits)
                    if drift_paths:
                        self._restore_scoped_workspace_baseline(state)
                        drift_replay_applied, drift_replay_issues = self._apply_adapter_edits(state, synthesized_edits)
                        if set(drift_replay_applied) == synthesized_edit_paths:
                            applied = drift_replay_applied
                            issues = [*issues, *drift_replay_issues]
                            used_synthesized_recovery = True
                            synthesized_recovery_reason = (
                                "because the accepted edits[] did not reproduce the adapter's final scoped workspace content."
                            )
                        elif drift_replay_issues:
                            issues = [*issues, *drift_replay_issues]
                if synthesized_edit_issues:
                    issues = [*issues, *synthesized_edit_issues]
                state.applied_edits = applied
                state.edit_issues = issues
                if synthesized_edits and (not edits or used_synthesized_recovery):
                    report_payload["risks"] = list(report_payload.get("risks") or [])
                    recovery_reason = synthesized_recovery_reason or (
                        "because the adapter omitted accepted edits[]."
                        if not edits
                        else "because the adapter returned unusable accepted edits[]."
                    )
                    recovered_note = (
                        f"Mission Control recovered {len(synthesized_edits)} scoped workspace change(s) into "
                        f"authoritative edits {recovery_reason}"
                    )
                    if recovered_note not in report_payload["risks"]:
                        report_payload["risks"].append(recovered_note)
                    for recovered_issue in recovered_edit_contract_issues:
                        if recovered_issue not in report_payload["risks"]:
                            report_payload["risks"].append(recovered_issue)
                elif discarded_changes and not edits:
                    report_payload["files_changed"] = []
                    if report_payload.get("status") == "done":
                        report_payload["status"] = "needs_review"
                    direct_edit_note = (
                        "Mission Control discarded unvetted direct workspace edits because the adapter did not provide "
                        "accepted edits[]."
                    )
                    report_payload["risks"] = list(report_payload.get("risks") or [])
                    if direct_edit_note not in report_payload["risks"]:
                        report_payload["risks"].append(direct_edit_note)
                    if claimed_files_changed:
                        claimed_files_note = (
                            "Adapter claimed files_changed for "
                            f"{', '.join(claimed_files_changed[:6])} but did not return authoritative accepted edits[]."
                        )
                        if claimed_files_note not in report_payload["risks"]:
                            report_payload["risks"].append(claimed_files_note)
                    report_payload["summary"] = (
                        f"{report_payload.get('summary') or 'Adapter run completed.'} {direct_edit_note}"
                    ).strip()
                report_payload["files_changed"] = (
                    applied if applied or effective_edits else list(report_payload.get("files_changed") or [])
                )
                envelope_payload["files_changed"] = list(report_payload.get("files_changed") or [])
                if issues:
                    report_payload["risks"] = list(report_payload.get("risks") or []) + issues
                    if report_payload.get("status") == "done":
                        report_payload["status"] = "needs_review"
                    if envelope_payload.get("status") == "completed":
                        envelope_payload["status"] = "needs_review"
                    report_payload["summary"] = (
                        f"{report_payload.get('summary') or 'Adapter run completed.'} "
                        "Mission Control rejected or could not apply one or more proposed edits."
                    ).strip()
                if discarded_changes and effective_edits and not used_synthesized_recovery:
                    discard_note = (
                        f"Mission Control discarded {len(discarded_changes)} unvetted direct workspace change(s) "
                        "before replaying the accepted edits payload."
                    )
                    report_payload["risks"] = list(report_payload.get("risks") or [])
                    if discard_note not in report_payload["risks"]:
                            report_payload["risks"].append(discard_note)
                self._enforce_required_command_execution(state, envelope_payload, report_payload)
                self._enforce_live_symbol_presence_contract(state, envelope_payload, report_payload)
                envelope_payload["summary"] = str(report_payload.get("summary") or envelope_payload.get("summary") or "Adapter run completed.")
                envelope_payload["report"] = report_payload
                envelope_payload["risks"] = list(report_payload.get("risks") or [])
                envelope_payload["blockers"] = list(report_payload.get("blockers") or [])
                envelope_payload["tests_run"] = list(report_payload.get("tests_run") or [])
                state.final_text = json.dumps(envelope_payload)
            else:
                state.final_text = stdout_text or stderr_text or "External adapter returned no output."
            if not timed_out:
                state.status = "done" if state.exit_code == 0 else "error"
            if report_payload and report_payload.get("status") in {"blocked", "needs_review", "error"}:
                state.status = str(report_payload.get("status"))
            if state.quota_contract:
                if state.status == "done" and state.quota_enforcement_status in {None, "", "armed"}:
                    state.quota_enforcement_status = "satisfied"
                elif state.status != "done" and state.quota_enforcement_status in {None, "", "armed"}:
                    state.quota_enforcement_status = "failed"
            self._persist_runtime_manifest(
                state,
                envelope_payload=envelope_payload,
                report_payload=report_payload,
            )
            state.events.append(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": state.final_text},
                    "effective_settings": state.effective_settings,
                    "repaired_json": repaired,
                }
            )
            state.events.append({"type": "turn.completed" if state.status == "done" else "turn.failed"})
            Path(state.logs_path or "").write_text(
                "\n".join(
                    [
                        f"command: {' '.join(args)}",
                        "",
                        stdout_text,
                        "",
                        stderr_text,
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            Path(state.stdout_path or "").write_text(stdout_text, encoding="utf-8")
            Path(state.stderr_path or "").write_text(stderr_text, encoding="utf-8")
            Path(state.event_log_path or "").write_text("\n".join(json.dumps(event) for event in state.events), encoding="utf-8")
        except Exception as exc:
            failure_text = (
                "Mission Control adapter runner failed before it could reconcile the worker result: "
                f"{type(exc).__name__}: {exc}"
            )
            diagnostics_text = traceback.format_exc().strip()
            if diagnostics_text:
                stderr_text = "\n\n".join(part for part in (stderr_text, diagnostics_text) if part)
            state.exit_code = state.exit_code if state.exit_code is not None else 1
            report_payload = {
                "agent": "adapter",
                "task_id": "",
                "status": "error",
                "summary": failure_text,
                "files_changed": [],
                "tests_run": [],
                "blockers": [failure_text],
                "risks": ["Mission Control hit an internal runner error while processing the adapter output."],
                "recommended_next_task": "Retry with a smaller scope or investigate the adapter/runtime failure.",
            }
            envelope_payload = {
                "status": "error",
                "runner_type": self.runner_type,
                "lane": "implementation",
                "summary": failure_text,
                "report": report_payload,
                "files_changed": [],
                "tests_run": [],
                "commands_attempted": [],
                "evidence": [],
                "risks": list(report_payload["risks"]),
                "blockers": list(report_payload["blockers"]),
                "diagnostics": [diagnostics_text] if diagnostics_text else [],
                "approvals_requested": [],
                "recovery_plan": [report_payload["recommended_next_task"]],
                "edits": [],
                "failure_classification": "runner_bug",
                "needs_approval": False,
                "metadata_json": {"runner_exception": f"{type(exc).__name__}: {exc}"},
            }
            state.status = "error"
            state.final_text = json.dumps(envelope_payload)
            self._persist_runtime_manifest(
                state,
                envelope_payload=envelope_payload,
                report_payload=report_payload,
            )
            if not any(event.get("type") == "item.completed" for event in state.events):
                state.events.append(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": state.final_text},
                        "effective_settings": state.effective_settings,
                        "repaired_json": repaired,
                    }
                )
            if not any(event.get("type") in {"turn.completed", "turn.failed"} for event in state.events):
                state.events.append({"type": "turn.failed"})
            Path(state.logs_path or "").write_text(
                "\n".join(
                    [
                        f"command: {' '.join(args)}",
                        "",
                        stdout_text,
                        "",
                        stderr_text,
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            Path(state.stdout_path or "").write_text(stdout_text, encoding="utf-8")
            Path(state.stderr_path or "").write_text(stderr_text, encoding="utf-8")
            Path(state.event_log_path or "").write_text("\n".join(json.dumps(event) for event in state.events), encoding="utf-8")
        finally:
            self.finalize_subprocess_state(state)
