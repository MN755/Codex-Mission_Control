from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = REPO_ROOT / "apps" / "server"
SERVER_SRC = SERVER_ROOT / "src"
if str(SERVER_SRC) not in sys.path:
    sys.path.insert(0, str(SERVER_SRC))

from benchmark_harness import (  # noqa: E402
    ACTIVE_TASK_STATUSES,
    COMPLETED_TASK_FLOW_STATUSES,
    STARTABLE_TASK_STATUSES,
    apply_solver_test_patch,
    analyze_task_execution,
    BenchmarkTaskResult,
    BenchmarkTaskSpec,
    HarnessRunConfig,
    TERMINAL_TASK_STATUSES,
    ValidationCommandResult,
    benchmark_preflight,
    build_manager_issue_prompt,
    build_project_issue_context,
    build_repo_context,
    build_meaningful_workspace_diff,
    build_workspace_diff,
    checkout_workspace_commit,
    classify_failure_category,
    default_output_root,
    detect_python_bootstrap_commands,
    detect_setup_commands,
    detect_validation_commands,
    extract_task_summary,
    filter_benchmark_protected_changed_files,
    load_task_manifest,
    meaningful_patch_paths,
    persist_summary,
    preferred_repo_dirname,
    recover_git_changed_files,
    run_evaluator_validation,
    run_validation_commands,
    recover_timeout_task_result,
    restore_workspace_files_from_snapshot,
    select_tasks,
    snapshot_workspace,
    stage_workspace_snapshot,
    summarize_results,
    task_flow_completed,
    task_flow_terminal,
    write_benchmark_protected_paths_manifest,
)


ADAPTER_PATH = REPO_ROOT / "scripts" / "ollama_adapter.py"
EVALUATOR_SPEC_ENV_VAR = "MISSION_CONTROL_BENCHMARK_EVALUATOR_SPEC"


def _safe_name(value: str) -> str:
    lowered = value.strip().replace("\\", "-").replace("/", "-")
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in lowered).strip("-") or "task"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _finalize_workspace_diff(
    workspace_path: Path,
    before_snapshot: dict[str, str],
    test_patch: str | None,
) -> tuple[str, list[str], list[str], dict[str, list[str]] | None]:
    after_snapshot = snapshot_workspace(workspace_path)
    _raw_diff, raw_changed_files = build_workspace_diff(before_snapshot, after_snapshot)
    _candidate_changed_files, skipped_protected_files = filter_benchmark_protected_changed_files(
        meaningful_patch_paths(raw_changed_files),
        test_patch,
    )
    protected_restore_report: dict[str, list[str]] | None = None
    if skipped_protected_files:
        protected_restore_report = restore_workspace_files_from_snapshot(
            workspace_path,
            before_snapshot,
            skipped_protected_files,
        )
        after_snapshot = snapshot_workspace(workspace_path)
    diff_text, changed_files = build_meaningful_workspace_diff(before_snapshot, after_snapshot)
    return diff_text, changed_files, skipped_protected_files, protected_restore_report


def _trim_text_block(text: str, *, max_chars: int, from_end: bool = False) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    if from_end:
        return normalized[-max_chars:].lstrip()
    return normalized[:max_chars].rstrip()


def _dedupe_ordered_texts(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = str(item).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _read_text_excerpt(path_text: str | None, *, max_chars: int = 1200, max_lines: int = 40) -> str | None:
    path_value = str(path_text or "").strip()
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        raw_text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    lines = [line.rstrip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return None
    excerpt = "\n".join(lines[-max_lines:])
    return _trim_text_block(excerpt, max_chars=max_chars, from_end=True) or None


def _candidate_diff_excerpt(diff_path: str | None, *, max_chars: int = 900) -> str | None:
    path_value = str(diff_path or "").strip()
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        diff_text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    interesting_lines = [
        line
        for line in diff_text.splitlines()
        if line.startswith("diff --git")
        or line.startswith("@@")
        or (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    ]
    if not interesting_lines:
        return None
    excerpt = "\n".join(interesting_lines[:24]).strip()
    return _trim_text_block(excerpt, max_chars=max_chars) or None


def _strip_inline_comment(line: str) -> str:
    return re.sub(r"\s+#.*$", "", str(line or "")).strip()


def _boolean_normalization_target(line: str) -> str | None:
    normalized = _strip_inline_comment(line)
    if not normalized:
        return None
    indexed_match = re.fullmatch(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=)\s*(0|1|True|False)\s*\]\s*=\s*(True|False)",
        normalized,
    )
    if indexed_match and indexed_match.group(1) == indexed_match.group(2):
        return str(indexed_match.group(1) or "").strip() or None
    assignment_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", normalized)
    if not assignment_match:
        return None
    lhs = str(assignment_match.group(1) or "").strip()
    rhs = str(assignment_match.group(2) or "").strip()
    rhs_compact = re.sub(r"\s+", "", rhs)
    if re.fullmatch(rf"\(?{re.escape(lhs)}\)?(?:==|!=)(?:0|1|True|False)", rhs_compact):
        return lhs
    if rhs_compact.endswith(".astype(bool)") or rhs_compact.startswith("np.asarray(") and "dtype=bool" in rhs_compact:
        return lhs
    if rhs_compact.startswith(("np.any(", "np.all(")):
        return lhs
    if (
        rhs_compact.startswith("np.where(")
        and "True" in rhs
        and "False" in rhs
    ):
        return lhs
    return None


def _equivalent_output_normalization_target(diff_path: str | None) -> str | None:
    path_value = str(diff_path or "").strip()
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        diff_text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    targets: list[tuple[str, str]] = []
    for raw_line in diff_text.splitlines():
        if raw_line.startswith(("+++", "---")) or not raw_line.startswith(("+", "-")):
            continue
        normalized = _strip_inline_comment(raw_line[1:])
        if not normalized:
            continue
        target = _boolean_normalization_target(normalized)
        if not target:
            return None
        targets.append((raw_line[0], target))
    if not targets:
        return None
    target_names = {target for _sign, target in targets}
    if len(target_names) != 1:
        return None
    signs = {sign for sign, _target in targets}
    if signs != {"+", "-"}:
        return None
    return next(iter(target_names))


def _validation_error_signature_excerpt(
    validation_results: list[ValidationCommandResult],
    *,
    max_chars: int = 500,
) -> str | None:
    pattern = re.compile(
        r"(Traceback \(most recent call last\):|[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Failure|Exit):.+)"
    )
    collected: list[str] = []
    seen: set[str] = set()
    for result in validation_results:
        if not result.timed_out and result.returncode == 0:
            continue
        for path_text in (result.stderr_path, result.stdout_path):
            candidate = str(path_text or "").strip()
            if not candidate:
                continue
            source = Path(candidate)
            if not source.exists() or not source.is_file():
                continue
            try:
                raw_text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in pattern.finditer(raw_text):
                line = str(match.group(1) or "").strip()
                if not line or line in seen:
                    continue
                seen.add(line)
                collected.append(line)
                if len(collected) >= 6:
                    excerpt = "\n".join(collected)
                    return _trim_text_block(excerpt, max_chars=max_chars) or None
    if not collected:
        return None
    excerpt = "\n".join(collected)
    return _trim_text_block(excerpt, max_chars=max_chars) or None


def _validation_failure_excerpt(validation_results: list[ValidationCommandResult], *, max_chars: int = 1200) -> str | None:
    for result in validation_results:
        if not result.timed_out and result.returncode == 0:
            continue
        blocks: list[str] = [f"Command: {result.command}"]
        if result.timed_out:
            blocks.append("Validation timed out.")
        error_signature_excerpt = _validation_error_signature_excerpt([result], max_chars=max_chars // 3)
        if error_signature_excerpt:
            blocks.append(f"Error signatures:\n{error_signature_excerpt}")
        stderr_excerpt = _read_text_excerpt(result.stderr_path, max_chars=max_chars // 2, max_lines=30)
        stdout_excerpt = _read_text_excerpt(result.stdout_path, max_chars=max_chars // 2, max_lines=30)
        if stderr_excerpt:
            blocks.append(f"stderr:\n{stderr_excerpt}")
        if stdout_excerpt:
            blocks.append(f"stdout:\n{stdout_excerpt}")
        return _trim_text_block("\n\n".join(blocks), max_chars=max_chars)
    return None


def _validation_failure_node_ids(validation_results: list[ValidationCommandResult]) -> list[str]:
    failed_nodes: list[str] = []
    pattern = re.compile(r"^FAILED\s+([^\s]+)", re.MULTILINE)
    for result in validation_results:
        if not result.timed_out and result.returncode == 0:
            continue
        for path_text in (result.stdout_path, result.stderr_path):
            candidate = str(path_text or "").strip()
            if not candidate:
                continue
            source = Path(candidate)
            if not source.exists() or not source.is_file():
                continue
            try:
                raw_text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in pattern.finditer(raw_text):
                node_id = str(match.group(1) or "").strip()
                if node_id:
                    failed_nodes.append(node_id)
    return _dedupe_ordered_texts(failed_nodes)


def _validation_failure_count(validation_results: list[ValidationCommandResult]) -> int:
    node_ids = _validation_failure_node_ids(validation_results)
    if node_ids:
        return len(node_ids)
    summary_pattern = re.compile(r"(?i)\b(\d+)\s+failed\b")
    for result in validation_results:
        if not result.timed_out and result.returncode == 0:
            continue
        for path_text in (result.stdout_path, result.stderr_path):
            candidate = str(path_text or "").strip()
            if not candidate:
                continue
            source = Path(candidate)
            if not source.exists() or not source.is_file():
                continue
            try:
                raw_text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            match = summary_pattern.search(raw_text)
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    continue
    return 0


def _validation_error_signatures(validation_results: list[ValidationCommandResult]) -> list[str]:
    excerpt = _validation_error_signature_excerpt(validation_results, max_chars=1200)
    if not excerpt:
        return []
    return _dedupe_ordered_texts([line.strip() for line in excerpt.splitlines() if line.strip()])


def _validation_assertion_call_symbols(validation_results: list[ValidationCommandResult]) -> list[str]:
    stop_words = {
        "assert",
        "assert_allclose",
        "assert_equal",
        "assert_array_equal",
        "assert_true",
        "assert_false",
        "self",
    }
    collected: list[str] = []
    for result in validation_results:
        if not result.timed_out and result.returncode == 0:
            continue
        for path_text in (result.stdout_path, result.stderr_path):
            candidate = str(path_text or "").strip()
            if not candidate:
                continue
            source = Path(candidate)
            if not source.exists() or not source.is_file():
                continue
            try:
                raw_text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in raw_text.splitlines():
                normalized = line.strip()
                if "assert" not in normalized:
                    continue
                for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", normalized):
                    symbol = str(match.group(1) or "").strip()
                    if not symbol or symbol in stop_words:
                        continue
                    collected.append(symbol)
    return _dedupe_ordered_texts(collected)


def _repo_context_same_file_anchors(repo_context_path: str | None, target_file: str) -> list[tuple[int, str]]:
    path_value = str(repo_context_path or "").strip()
    normalized_target = str(target_file or "").strip().replace("\\", "/")
    if not path_value or not normalized_target:
        return []
    candidate = Path(path_value)
    if not candidate.exists() or not candidate.is_file():
        return []
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    anchors: list[tuple[int, str]] = []
    for raw_item in list(payload.get("implementation_anchors") or []):
        item = str(raw_item or "").strip()
        match = re.match(r"([^:]+):(\d+):\s*(.+)$", item)
        if not match:
            continue
        rel_path = str(match.group(1) or "").strip().replace("\\", "/")
        if rel_path != normalized_target:
            continue
        line_number = int(match.group(2))
        snippet = str(match.group(3) or "").strip()
        anchors.append((line_number, snippet))
    return anchors


def _diff_changed_line_numbers(diff_path: str | None, target_file: str) -> list[int]:
    path_value = str(diff_path or "").strip()
    normalized_target = str(target_file or "").strip().replace("\\", "/")
    if not path_value or not normalized_target:
        return []
    candidate = Path(path_value)
    if not candidate.exists() or not candidate.is_file():
        return []
    try:
        diff_text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    current_file: str | None = None
    line_numbers: list[int] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :].strip().replace("\\", "/")
            continue
        if current_file != normalized_target:
            continue
        match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if not match:
            continue
        line_numbers.append(int(match.group(1)))
    return line_numbers


def _anchor_symbol_from_snippet(snippet: str) -> str | None:
    match = re.search(r"\b(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", str(snippet or ""))
    if not match:
        return None
    symbol = str(match.group(1) or "").strip()
    return symbol or None


def _changed_anchor_symbol(previous_result: BenchmarkTaskResult, changed_file: str) -> str | None:
    line_numbers = _diff_changed_line_numbers(previous_result.artifact_paths.get("diff_path"), changed_file)
    if not line_numbers:
        return None
    anchors = _repo_context_same_file_anchors(previous_result.artifact_paths.get("repo_context_path"), changed_file)
    if not anchors:
        return None
    target_line = line_numbers[0]
    eligible = [(line_number, snippet) for line_number, snippet in anchors if line_number <= target_line]
    chosen = eligible[-1] if eligible else anchors[0]
    return _anchor_symbol_from_snippet(chosen[1])


def _retry_error_signature_guidance(previous_result: BenchmarkTaskResult) -> list[str]:
    signatures = _validation_error_signatures(previous_result.validation_results)
    if not signatures:
        return []
    severe_markers = ("IndentationError", "SyntaxError", "AttributeError", "TypeError", "NameError", "UnboundLocalError")
    severe = [signature for signature in signatures if any(marker in signature for marker in severe_markers)]
    if not severe:
        return []
    preview = ", ".join(severe[:3])
    return [
        f"The previous patch introduced a direct syntax/runtime error during validation: {preview}.",
        "Revert that direction and keep the original control flow and function structure intact while fixing the regression.",
    ]


def _retry_output_coercion_guidance(previous_result: BenchmarkTaskResult) -> list[str]:
    target = _equivalent_output_normalization_target(previous_result.artifact_paths.get("diff_path"))
    if target:
        return [
            f"The previous patch only changed the final boolean coercion for `{target}` after it was already computed.",
            "Inspect the upstream calculation or earlier helper that produces that value instead of trying another equivalent output-normalization tweak.",
        ]
    return []


def _retry_helper_signature_guidance(previous_result: BenchmarkTaskResult) -> list[str]:
    signatures = _validation_error_signatures(previous_result.validation_results)
    missing_arg_signature = next(
        (
            signature
            for signature in signatures
            if "TypeError:" in signature and "missing" in signature and "required positional argument" in signature
        ),
        None,
    )
    if not missing_arg_signature:
        return []
    diff_path = str(previous_result.artifact_paths.get("diff_path") or "").strip()
    if not diff_path:
        return []
    candidate = Path(diff_path)
    if not candidate.exists() or not candidate.is_file():
        return []
    try:
        diff_text = candidate.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    added_calls = [
        line[1:].strip()
        for line in diff_text.splitlines()
        if line.startswith("+")
        and not line.startswith("+++")
        and "=" in line
        and "(" in line
        and ")" in line
    ]
    if not added_calls:
        return []
    return [
        f"The previous patch invented an internal helper-call rewrite that failed at runtime: {missing_arg_signature}.",
        "Do not replace the existing core expression with a new helper-call chain unless the live file already shows that exact helper signature and argument count. Patch the existing logic instead of guessing helper composition.",
    ]


def _retry_same_file_anchor_guidance(previous_result: BenchmarkTaskResult) -> list[str]:
    if len(previous_result.changed_files) != 1:
        return []
    changed_file = previous_result.changed_files[0]
    anchors = _repo_context_same_file_anchors(previous_result.artifact_paths.get("repo_context_path"), changed_file)
    if len(anchors) < 2:
        return []
    changed_anchor_symbol = _changed_anchor_symbol(previous_result, changed_file)
    if not changed_anchor_symbol:
        return []
    assertion_symbols = _validation_assertion_call_symbols(previous_result.validation_results)
    if not assertion_symbols:
        return []
    anchor_symbols = {
        symbol
        for _line_number, snippet in anchors
        for symbol in [ _anchor_symbol_from_snippet(snippet) ]
        if symbol
    }
    sibling_symbols = [
        symbol
        for symbol in assertion_symbols
        if symbol in anchor_symbols and symbol != changed_anchor_symbol
    ]
    if not sibling_symbols:
        return []
    sibling_preview = ", ".join(f"`{symbol}`" for symbol in sibling_symbols[:3])
    return [
        f"The remaining failing assertion still centers on {sibling_preview}, while the previous patch targeted `{changed_anchor_symbol}` in the same file.",
        "Inspect that sibling same-file helper or return path before repeating another equivalent edit in the previously changed anchor.",
    ]


def _retry_regression_feedback(task: BenchmarkTaskSpec, previous_result: BenchmarkTaskResult) -> list[str]:
    expected_failures = _dedupe_ordered_texts([str(item).strip() for item in list(task.fail_to_pass or []) if str(item).strip()])
    observed_failures = _validation_failure_node_ids(previous_result.validation_results)
    if not observed_failures:
        guidance: list[str] = []
        guidance.extend(_retry_error_signature_guidance(previous_result))
        guidance.extend(_retry_helper_signature_guidance(previous_result))
        guidance.extend(_retry_output_coercion_guidance(previous_result))
        guidance.extend(_retry_same_file_anchor_guidance(previous_result))
        return guidance
    expected_set = set(expected_failures)
    observed_set = set(observed_failures)
    extra_failures = [node_id for node_id in observed_failures if node_id not in expected_set]
    guidance: list[str] = []
    if expected_failures and observed_set == expected_set:
        guidance.append(
            "The previous patch did not eliminate the original benchmark failures. Change a different part of the scoped implementation instead of resubmitting the same logic."
        )
    if extra_failures:
        preview = ", ".join(extra_failures[:4])
        guidance.append(
            f"The previous patch introduced additional failing targets outside the original benchmark regression set: {preview}."
        )
        guidance.append(
            "Revert that direction and preserve unrelated behavior while fixing only the original regression."
        )
    guidance.extend(_retry_error_signature_guidance(previous_result))
    guidance.extend(_retry_helper_signature_guidance(previous_result))
    guidance.extend(_retry_output_coercion_guidance(previous_result))
    guidance.extend(_retry_same_file_anchor_guidance(previous_result))
    return guidance


def _build_retry_feedback(task: BenchmarkTaskSpec, previous_result: BenchmarkTaskResult, *, attempt_number: int) -> str:
    regression_guidance = _retry_regression_feedback(task, previous_result)
    lines = [
        f"Retry feedback for attempt {attempt_number}: the previous benchmark attempt applied a candidate patch but failed authoritative validation.",
        "Do not repeat the same patch unchanged. Revise or replace it using the concrete failing evidence below.",
    ]
    if previous_result.changed_files:
        lines.append(f"Previous changed files: {', '.join(previous_result.changed_files[:6])}")
    if regression_guidance:
        lines.append("Highest-priority correction cues:")
        lines.extend(f"- {item}" for item in regression_guidance)
    failure_excerpt = _validation_failure_excerpt(previous_result.validation_results, max_chars=900)
    if failure_excerpt:
        lines.append(f"Validation failure excerpt:\n{failure_excerpt}")
    diff_excerpt = _candidate_diff_excerpt(previous_result.artifact_paths.get('diff_path'), max_chars=700)
    if diff_excerpt:
        lines.append(f"Prior patch excerpt:\n{diff_excerpt}")
    lines.append("You still need a real code edit plus rerun validation. A reproduce-only retry is not enough.")
    retry_feedback = "\n\n".join(lines)
    base_hints = str(task.hints_text or "").strip()
    if not base_hints:
        return _trim_text_block(retry_feedback, max_chars=1800)
    earlier_hints = _trim_text_block(base_hints, max_chars=250)
    combined = retry_feedback
    if earlier_hints:
        combined = (
            f"{retry_feedback}\n\n"
            "Earlier hints (lower priority than the fresh failure evidence above):\n"
            f"{earlier_hints}"
        )
    return _trim_text_block(combined, max_chars=1800)


def _should_retry_failed_attempt(
    result: BenchmarkTaskResult,
    *,
    attempt_number: int,
    max_task_attempts: int,
) -> bool:
    if attempt_number >= max_task_attempts or result.resolved:
        return False
    return bool(result.patch_applied and not result.validation_succeeded and result.failure_category == "validation_failed")


def _retry_basis_result(
    latest_result: BenchmarkTaskResult,
    selected_result: BenchmarkTaskResult | None,
) -> BenchmarkTaskResult:
    if latest_result.patch_applied and latest_result.failure_category == "validation_failed":
        return latest_result
    if (
        selected_result is not None
        and selected_result.patch_applied
        and not selected_result.validation_succeeded
        and selected_result.failure_category == "validation_failed"
    ):
        return selected_result
    return latest_result


def _attempt_selection_score(result: BenchmarkTaskResult) -> tuple[int, int, int, int, int, int, int]:
    equivalent_output_normalization = bool(
        result.patch_applied
        and not result.validation_succeeded
        and not result.resolved
        and _equivalent_output_normalization_target(result.artifact_paths.get("diff_path"))
    )
    failure_count = _validation_failure_count(result.validation_results) if result.validation_results else 10_000
    return (
        1 if result.resolved else 0,
        1 if result.validation_succeeded else 0,
        1 if bool(result.validation_results) else 0,
        -failure_count,
        1 if result.patch_applied else 0,
        0 if equivalent_output_normalization else 1,
        1 if result.completed else 0,
    )


def _build_run_label(prefix: str = "run") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}"


def _benchmark_workspace_root() -> Path:
    override = str(os.environ.get("MISSION_CONTROL_BENCHMARK_WORKSPACE_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    return (REPO_ROOT / "tests" / "_swe_bench_workspaces").resolve()


def _benchmark_workspace_path(task_output_dir: Path) -> Path:
    suffix = hashlib.sha1(task_output_dir.as_posix().encode("utf-8")).hexdigest()[:8]
    workspace_name = f"{_safe_name(task_output_dir.name)[:48]}-{suffix}"
    return _benchmark_workspace_root() / workspace_name


def _evaluator_spec_env(task: BenchmarkTaskSpec) -> dict[str, str]:
    payload = task.sensitive_payload()
    return {EVALUATOR_SPEC_ENV_VAR: json.dumps(payload)} if payload else {}


def _repo_cache_root_from_config(config: HarnessRunConfig) -> Path | None:
    root_text = str(config.repo_cache_root or config.prepared_repos_root or "").strip()
    if not root_text:
        return None
    return Path(root_text).resolve()


def _git_command_for_path(repo_root: Path, *args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={repo_root.resolve().as_posix()}", *args]


def _git_has_commit(repo_root: Path, commit: str) -> bool:
    completed = subprocess.run(
        _git_command_for_path(repo_root, "rev-parse", "--verify", f"{commit}^{{commit}}"),
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed.returncode == 0


def _prepare_repositories(tasks: list[BenchmarkTaskSpec], repo_cache_root: Path, *, refresh_existing: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {
        "repo_cache_root": repo_cache_root.as_posix(),
        "repos": [],
        "prepared_count": 0,
        "reused_count": 0,
        "fetched_count": 0,
        "failed_count": 0,
    }
    repo_cache_root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, set[str]] = {}
    for task in tasks:
        repo_name = str(task.repo_name or "").strip()
        if not repo_name:
            continue
        commits = grouped.setdefault(repo_name, set())
        if task.base_commit:
            commits.add(task.base_commit)
        if task.metadata.get("environment_setup_commit"):
            commits.add(str(task.metadata["environment_setup_commit"]).strip())

    for repo_name in sorted(grouped):
        target = repo_cache_root / preferred_repo_dirname(repo_name)
        commits = sorted(commit for commit in grouped[repo_name] if commit)
        entry = {
            "repo": repo_name,
            "path": target.as_posix(),
            "status": "reused",
            "missing_commits": [],
            "notes": [],
        }
        try:
            if not (target / ".git").exists():
                clone_url = f"https://github.com/{repo_name}.git"
                completed = subprocess.run(
                    ["git", "clone", clone_url, target.as_posix()],
                    cwd=str(repo_cache_root),
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError((completed.stderr or completed.stdout or "").strip() or f"git clone exited {completed.returncode}")
                entry["status"] = "cloned"
                report["prepared_count"] += 1
            else:
                report["reused_count"] += 1

                missing_commits = [commit for commit in commits if not _git_has_commit(target, commit)]
            if missing_commits or refresh_existing:
                completed = subprocess.run(
                    _git_command_for_path(target, "fetch", "--all", "--tags"),
                    cwd=str(target),
                    capture_output=True,
                    text=True,
                    timeout=1800,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError((completed.stderr or completed.stdout or "").strip() or f"git fetch exited {completed.returncode}")
                report["fetched_count"] += 1
                missing_commits = [commit for commit in commits if not _git_has_commit(target, commit)]
            entry["missing_commits"] = missing_commits
            if missing_commits:
                entry["status"] = "missing_commits"
                entry["notes"].append("Some requested commits are still unavailable after fetch.")
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "failed"
            entry["notes"].append(f"{type(exc).__name__}: {exc}")
            report["failed_count"] += 1
        report["repos"].append(entry)
    return report


def _extract_missing_modules(*texts: str) -> list[str]:
    modules: list[str] = []
    for text in texts:
        for match in re.finditer(r"No module named ['\"]([^'\"]+)['\"]", text or ""):
            modules.append(str(match.group(1) or "").strip())
    return sorted({item for item in modules if item})


def _module_to_package_name(module_name: str) -> str:
    mapping = {
        "PIL": "pillow",
        "cv2": "opencv-python",
        "dateutil": "python-dateutil",
        "erfa": "pyerfa",
        "extension_helpers": "extension-helpers",
        "yaml": "pyyaml",
        "sklearn": "scikit-learn",
    }
    return mapping.get(module_name, module_name)


def _extract_pytest_plugin_packages(*texts: str) -> list[str]:
    option_to_package = {
        "--arraydiff": "pytest-arraydiff",
        "--doctest-plus": "pytest-doctestplus",
        "--doctest-rst": "pytest-doctestplus",
        "--mpl": "pytest-mpl",
        "--open-files": "pytest-openfiles",
        "--remote-data": "pytest-remotedata",
        "--text-file-format": "pytest-doctestplus",
    }
    packages: list[str] = []
    for text in texts:
        for match in re.finditer(r"unrecognized arguments:\s+([^\r\n]+)", text or "", flags=re.IGNORECASE):
            for option in re.findall(r"--[A-Za-z0-9][A-Za-z0-9_-]*", str(match.group(1) or "")):
                package_name = option_to_package.get(option.strip().lower())
                if package_name:
                    packages.append(package_name)
    return sorted({item for item in packages if item})


def _find_windows_vcvars64_bat() -> Path | None:
    if os.name != "nt":
        return None
    override = str(os.environ.get("MISSION_CONTROL_VCVARS64_BAT") or "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.exists():
            return candidate.resolve()
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    vswhere_path = program_files_x86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere_path.exists():
        try:
            completed = subprocess.run(
                [
                    str(vswhere_path),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed and completed.returncode == 0:
            install_path = str(completed.stdout or "").strip()
            if install_path:
                candidate = Path(install_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
                if candidate.exists():
                    return candidate.resolve()
    fallback = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat")
    if fallback.exists():
        return fallback.resolve()
    return None


def _command_needs_windows_cpp_toolchain(command: str) -> bool:
    normalized = str(command or "").strip().lower()
    return "python setup.py build_ext" in normalized


def _wrap_command_for_windows_cpp_toolchain(command: str, *, vcvars64_bat: Path | None = None) -> str:
    resolved_vcvars = vcvars64_bat or _find_windows_vcvars64_bat()
    if resolved_vcvars is None or not _command_needs_windows_cpp_toolchain(command):
        return command
    return f'call "{resolved_vcvars}" && {command}'


def _prepare_python_workspace(workspace_path: Path, output_dir: Path, *, timeout_seconds: int) -> dict[str, Any]:
    raw_commands = detect_python_bootstrap_commands(workspace_path)
    vcvars64_bat = _find_windows_vcvars64_bat()
    commands = [
        _wrap_command_for_windows_cpp_toolchain(command, vcvars64_bat=vcvars64_bat)
        for command in raw_commands
    ]
    results = run_validation_commands(
        workspace_path,
        commands,
        output_dir,
        timeout_seconds=timeout_seconds,
    )
    return {
        "commands": raw_commands,
        "executed_commands": commands,
        "results": [item.to_dict() for item in results],
    }


def _read_result_output_text(result: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("stdout_path", "stderr_path"):
        candidate = Path(str(result.get(key) or "").strip())
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            chunks.append(candidate.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _detect_local_setup_blocker(
    python_bootstrap_report: dict[str, Any],
    bootstrap_report: dict[str, Any],
) -> str | None:
    bootstrap_outputs = "\n".join(
        _read_result_output_text(result)
        for result in list(python_bootstrap_report.get("results") or [])
        if isinstance(result, dict)
    ).lower()
    probe_outputs = "\n".join(
        _read_result_output_text(result)
        for result in list(bootstrap_report.get("probe_results") or [])
        if isinstance(result, dict)
    ).lower()
    if not bootstrap_outputs and not probe_outputs:
        return None
    compiler_markers = (
        "command 'cl.exe' failed",
        "unable to find vcvarsall",
        "command 'gcc' failed",
        "no such file or directory: 'gcc'",
    )
    windows_sdk_markers = (
        "fatal error lnk1158",
        "cannot run 'rc.exe'",
    )
    source_checkout_markers = (
        "trying to import astropy from within a source checkout",
        "editable installation without building the extension modules first",
        "build the extension modules first",
    )
    dependency_drift_markers = (
        "numpy.core is deprecated and has been renamed to numpy._core",
        "syntax error in ctypedef statement",
        "is not a type identifier",
    )
    if any(marker in bootstrap_outputs for marker in compiler_markers) and any(
        marker in probe_outputs for marker in source_checkout_markers
    ):
        return (
            "Local setup failed because the staged workspace needs compiled extension modules, "
            "but no supported C compiler is available on this host."
        )
    if any(marker in bootstrap_outputs for marker in windows_sdk_markers) and any(
        marker in probe_outputs for marker in source_checkout_markers
    ):
        return (
            "Local setup failed after bootstrapping the Windows C++ toolchain because extension-module "
            "resource compilation still failed (`rc.exe` / `LNK1158`)."
        )
    if any(marker in bootstrap_outputs for marker in dependency_drift_markers) or any(
        marker in probe_outputs for marker in dependency_drift_markers
    ):
        return (
            "Local setup failed because the host Python dependency stack is incompatible with the staged workspace "
            "(for example NumPy/Cython version drift)."
        )
    return None


def _bootstrap_missing_test_dependencies(workspace_path: Path, validation_commands: list[str], output_dir: Path, *, timeout_seconds: int) -> dict[str, Any]:
    if not validation_commands:
        return {"probe_results": [], "installed_packages": [], "install_results": []}
    probe_results = run_validation_commands(
        workspace_path,
        [validation_commands[0]],
        output_dir / "probe",
        timeout_seconds=timeout_seconds,
    )
    missing_modules: list[str] = []
    plugin_packages: list[str] = []
    for result in probe_results:
        stdout_text = Path(result.stdout_path).read_text(encoding="utf-8") if result.stdout_path else ""
        stderr_text = Path(result.stderr_path).read_text(encoding="utf-8") if result.stderr_path else ""
        missing_modules.extend(_extract_missing_modules(stdout_text, stderr_text))
        plugin_packages.extend(_extract_pytest_plugin_packages(stdout_text, stderr_text))
    packages = sorted(
        {
            *[_module_to_package_name(name) for name in sorted(set(missing_modules))],
            *plugin_packages,
        }
    )
    install_results = run_validation_commands(
        workspace_path,
        [f"python -m pip install {' '.join(packages)}"] if packages else [],
        output_dir / "install",
        timeout_seconds=timeout_seconds,
    )
    install_succeeded = bool(packages) and all(
        not item.timed_out and item.returncode == 0 for item in install_results
    )
    return {
        "probe_results": [item.to_dict() for item in probe_results],
        "attempted_packages": packages,
        "installed_packages": packages if install_succeeded else [],
        "install_results": [item.to_dict() for item in install_results],
    }


def _runtime_imports() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from config import DB_PATH
    from daemon_state import ensure_daemon_token
    from db import engine, init_db
    from main import app
    from startup import startup_service

    return {
        "TestClient": TestClient,
        "DB_PATH": DB_PATH,
        "app": app,
        "engine": engine,
        "ensure_daemon_token": ensure_daemon_token,
        "init_db": init_db,
        "startup_service": startup_service,
    }


def _load_selected_tasks(config: HarnessRunConfig) -> list[BenchmarkTaskSpec]:
    tasks = load_task_manifest(
        config.tasks_path,
        dataset_split=config.dataset_split,
        prepared_repos_root=config.prepared_repos_root or config.repo_cache_root,
        repo_map_path=config.repo_map_path,
    )
    return select_tasks(
        tasks,
        start_index=config.start_index,
        max_tasks=config.max_tasks,
        task_ids=config.task_ids,
    )


def _reset_db(runtime: dict[str, Any]) -> None:
    engine = runtime["engine"]
    db_path = runtime["DB_PATH"]
    init_db = runtime["init_db"]
    startup_service = runtime["startup_service"]
    engine.dispose()
    if db_path.exists():
        db_path.unlink()
    init_db()
    startup_service.last_status = None
    engine.dispose()


def _bridge_headers(runtime: dict[str, Any]) -> dict[str, str]:
    return {"X-Mission-Control-Token": runtime["ensure_daemon_token"]()}


def _call_api(
    client: Any,
    method: str,
    path: str,
    trajectory_path: Path,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
) -> Any:
    started = time.monotonic()
    response = client.request(method, path, params=params, json=json_body)
    entry = {
        "ts": time.time(),
        "method": method,
        "path": path,
        "params": params or {},
        "json": json_body,
        "status_code": response.status_code,
        "runtime_seconds": round(time.monotonic() - started, 3),
    }
    try:
        payload = response.json()
        entry["response_preview"] = payload if isinstance(payload, dict) else payload[:3]
    except Exception:
        payload = None
        entry["response_preview"] = (response.text or "")[:800]
    _append_jsonl(trajectory_path, entry)
    response.raise_for_status()
    return payload if payload is not None else response.json()


def _collect_agent_logs(client: Any, project_id: int, agents: list[dict[str, Any]], output_dir: Path, trajectory_path: Path) -> dict[str, str]:
    log_paths: dict[str, str] = {}
    for agent in agents:
        agent_id = int(agent["id"])
        payload = _call_api(
            client,
            "GET",
            f"/api/projects/{project_id}/agents/{agent_id}/logs",
            trajectory_path,
        )
        target = output_dir / "agent-logs" / f"agent-{agent_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(payload.get("content") or ""), encoding="utf-8")
        log_paths[str(agent_id)] = target.as_posix()
    return log_paths


def _normalize_adapter_arg(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.as_posix()
    repo_candidate = (REPO_ROOT / candidate).resolve()
    if repo_candidate.exists():
        return repo_candidate.as_posix()
    cwd_candidate = candidate.resolve()
    if cwd_candidate.exists():
        return cwd_candidate.as_posix()
    return text


def _resolve_adapter_launch(config: HarnessRunConfig) -> tuple[str, list[str]]:
    adapter_command = str(config.adapter_command or sys.executable).strip() or sys.executable
    adapter_args = list(config.adapter_args or [ADAPTER_PATH.as_posix()])
    return adapter_command, [_normalize_adapter_arg(item) for item in adapter_args]


def _configure_project(
    client: Any,
    config: HarnessRunConfig,
    project_id: int,
    trajectory_path: Path,
) -> dict[str, Any]:
    manager_model, worker_model = config.normalized_models()
    adapter_command, adapter_args = _resolve_adapter_launch(config)
    return _call_api(
        client,
        "PUT",
        "/api/settings",
        trajectory_path,
        params={"project_id": project_id},
        json_body={
            "provider": config.provider,
            "manager_model": manager_model,
            "default_worker_model": worker_model,
            "manager_reasoning_effort": config.manager_reasoning_effort,
            "default_worker_reasoning_effort": config.worker_reasoning_effort,
            "per_role_model_overrides_json": {},
            "per_role_reasoning_overrides_json": {},
            "adapter_command": adapter_command,
            "adapter_args_json": adapter_args,
            "runner_mode": "auto",
            "sandbox_mode": config.sandbox_mode,
            "approval_policy": config.approval_policy,
            "workspace_widgets_json": [],
            "approval_overrides_json": {},
        },
    )


def _ensure_project_write_permission(
    client: Any,
    project: dict[str, Any],
    trajectory_path: Path,
) -> dict[str, Any] | None:
    if str(project.get("source_type") or "").strip() != "existing_folder":
        return None
    if str(project.get("write_permission_status") or "").strip() != "read_only":
        return None
    project_id = int(project["id"])
    return _call_api(
        client,
        "POST",
        f"/api/projects/{project_id}/write-permission",
        trajectory_path,
        json_body={"write_permission_status": "write_allowed"},
    )


def _apply_swarm_preferences(client: Any, project_id: int, config: HarnessRunConfig, trajectory_path: Path) -> None:
    _call_api(
        client,
        "PUT",
        f"/api/projects/{project_id}/swarm/preferences",
        trajectory_path,
        json_body={
            "optimization_mode": "fastest_build",
            "swarm_aggressiveness": "medium",
            "max_agents": config.swarm_max_agents,
            "require_approval_above_agent_count": 50,
            "allow_dynamic_spawning": True,
            "allow_dynamic_retirement": True,
            "docs_depth": "standard",
            "testing_depth": "standard",
        },
    )


def _seed_benchmark_project(
    client: Any,
    project_id: int,
    prompt: str,
    config: HarnessRunConfig,
    trajectory_path: Path,
) -> dict[str, Any]:
    payloads: dict[str, Any] = {
        "change_request": _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/change-requests",
            trajectory_path,
            json_body={"request_text": prompt},
        ),
    }
    if config.enable_swarm_planning:
        swarm_plan = _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/swarm/plan",
            trajectory_path,
            json_body={"goal": "Fix the issue, apply the patch, and validate locally."},
        )
        if swarm_plan.get("approval_required"):
            swarm_plan = _call_api(
                client,
                "POST",
                f"/api/projects/{project_id}/swarm/plan/{swarm_plan['id']}/approve",
                trajectory_path,
            )
        payloads["swarm_plan"] = swarm_plan
        payloads["swarm_spawn"] = _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/swarm/spawn",
            trajectory_path,
        )
    payloads["task_generation"] = _call_api(
        client,
        "POST",
        f"/api/projects/{project_id}/tasks/generate",
        trajectory_path,
    )
    return payloads


def _auto_answer_decisions(client: Any, project_id: int, trajectory_path: Path) -> list[dict[str, Any]]:
    answered: list[dict[str, Any]] = []
    decisions = _call_api(client, "GET", f"/api/projects/{project_id}/pending-decisions", trajectory_path)
    for decision in decisions:
        options = list(decision.get("options") or [])
        if not options:
            continue
        option_by_id = {str(item.get("id")): item for item in options}
        selected = _select_decision_option(decision, option_by_id, options)
        payload = _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/decisions/{decision['id']}/answer",
            trajectory_path,
            json_body={
                "option_id": selected["id"],
                "selected_text": selected.get("label") or selected["id"],
            },
        )
        answered.append(payload)
    return answered


def _select_decision_option(
    decision: dict[str, Any],
    option_by_id: dict[str, dict[str, Any]],
    options: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_type = str(decision.get("decision_type") or "").strip().lower()
    review_text = " ".join(
        filter(
            None,
            [
                str(decision.get("title") or ""),
                str(decision.get("message") or ""),
                str(((decision.get("presentation") or {}) if isinstance(decision.get("presentation"), dict) else {}).get("fallback_markdown") or ""),
            ],
        )
    ).lower()
    if decision_type == "handoff_review" and "request_changes" in option_by_id:
        implementation_markers = ("focused retry", "implement", "fix", "patch", "analysis-only")
        validation_markers = ("validation", "handoff", "final report")
        rejection_markers = (
            "rejected or could not apply",
            "rejected search/replace",
            "no verified workspace file changes",
            "no-change review gate",
            "runner completion envelope validation failed",
            "input should be 'done', 'blocked', 'needs_review' or 'error'",
            "failed to reproduce",
            "reproduction failed",
            "failed validation",
            "validation failed",
            "failed to run",
            "not fully resolved",
            "unable to reproduce",
            "missing dependencies",
            "please check the environment",
            "provide more details",
        )
        success_markers = (
            "validation passed",
            "focused validation passed",
            "all specified tests passed successfully",
            "verified the fix outcome",
            "handoff is ready",
            "issue resolved",
            "fix verified",
        )
        if any(marker in review_text for marker in rejection_markers):
            return option_by_id["request_changes"]
        if any(marker in review_text for marker in implementation_markers) and not any(
            marker in review_text for marker in validation_markers
        ):
            return option_by_id["request_changes"]
        if any(marker in review_text for marker in validation_markers) and not any(
            marker in review_text for marker in success_markers
        ):
            return option_by_id["request_changes"]
    return option_by_id.get(str(decision.get("recommended_option") or "")) or options[0]


def _auto_approve_commands(client: Any, project_id: int, trajectory_path: Path, *, allow_for_project: bool) -> list[dict[str, Any]]:
    approvals = _call_api(client, "GET", f"/api/projects/{project_id}/approvals/pending", trajectory_path)
    resolved: list[dict[str, Any]] = []
    route = "allow-for-project" if allow_for_project else "approve-once"
    for approval in approvals:
        payload = _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/approvals/{approval['id']}/{route}",
            trajectory_path,
        )
        resolved.append(payload)
    return resolved


def _agent_is_busy(agent: dict[str, Any]) -> bool:
    status = str(agent.get("status") or "").strip().lower()
    return status not in {"idle", "waiting", "done", "stopped", "retired"} or agent.get("current_task_id") is not None


def _task_has_live_agent_assignment(task: dict[str, Any], agents: list[dict[str, Any]] | None = None) -> bool:
    task_id = int(task.get("id") or 0)
    assigned_agent_id = int(task.get("assigned_agent_id") or 0)
    if task_id <= 0 or assigned_agent_id <= 0 or not agents:
        return False
    agent = next((item for item in agents if int(item.get("id") or 0) == assigned_agent_id), None)
    if agent is None:
        return False
    return int(agent.get("current_task_id") or 0) == task_id and _agent_is_busy(agent)


def _assigned_task_can_be_relaunched(task: dict[str, Any], agents: list[dict[str, Any]] | None = None) -> bool:
    assigned_agent_id = int(task.get("assigned_agent_id") or 0)
    if assigned_agent_id <= 0:
        return True
    if not agents:
        return False
    agent = next((item for item in agents if int(item.get("id") or 0) == assigned_agent_id), None)
    if agent is None:
        return True
    if _task_has_live_agent_assignment(task, agents):
        return False
    return str(agent.get("status") or "").strip().lower() in {"idle", "waiting", "done", "stopped"}


def _active_execution_tasks(
    tasks: list[dict[str, Any]],
    task_statuses: dict[int, str] | None = None,
    agents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return [
        task
        for task in tasks
        if (
            str(task.get("status") or "") == "working"
            or (
                str(task.get("status") or "") == "assigned"
                and _task_has_live_agent_assignment(task, agents)
                and (
                    task_statuses is None
                    or _task_dependencies_completed(task, task_statuses)
                )
                and "waiting for task dependencies" not in str(task.get("waiting_reason") or "").strip().lower()
            )
        )
    ]


def _task_is_validation_or_handoff_lane(task: dict[str, Any]) -> bool:
    text = " ".join(
        str(task.get(field) or "").strip().lower()
        for field in ("title", "goal", "scope", "agent_role", "milestone")
    )
    if not text:
        return False
    return any(token in text for token in ("validate", "validation", "verify", "handoff"))


def _task_is_fix_implementation_lane(task: dict[str, Any]) -> bool:
    text = " ".join(
        str(task.get(field) or "").strip().lower()
        for field in ("title", "goal", "scope", "agent_role", "milestone")
    )
    if not text:
        return False
    if _task_is_validation_or_handoff_lane(task):
        return False
    return any(
        token in text
        for token in (
            "implement",
            "implementation",
            "patch",
            "code fix",
            "fix the code",
            "smallest safe code fix",
            "service flow builder",
            "backend specialist",
        )
    )


def _task_is_post_validation_retry_lane(task: dict[str, Any]) -> bool:
    text = " ".join(
        str(task.get(field) or "").strip().lower()
        for field in ("title", "goal", "scope", "agent_role", "milestone", "waiting_reason")
    )
    if not text:
        return False
    if "validate" not in text and "handoff" not in text and "blocker" not in text:
        return False
    return any(
        token in text
        for token in (
            "resolve a blocker or error before the main flow can continue",
            "confirm the blocker is removed",
            "rework ",
            "implement a fix",
            "fix for ",
            "last blocker to overcome",
        )
    )


def _should_stop_for_evaluator_convergence(
    tasks: list[dict[str, Any]],
    pending_decisions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
) -> bool:
    if pending_decisions or pending_approvals or not tasks:
        return False
    open_tasks = [
        task
        for task in tasks
        if str(task.get("status") or "").strip() not in COMPLETED_TASK_FLOW_STATUSES
    ]
    if not open_tasks:
        return False
    if not all(
        _task_is_validation_or_handoff_lane(task) or _task_is_post_validation_retry_lane(task)
        for task in open_tasks
    ):
        return False
    return any(
        str(task.get("status") or "").strip() in {"done", "completed"}
        and _task_is_fix_implementation_lane(task)
        for task in tasks
    )


def _task_is_restartable_after_prior_start(task: dict[str, Any], started_task_ids: set[int]) -> bool:
    task_id = int(task.get("id") or 0)
    if task_id <= 0 or task_id not in started_task_ids:
        return True
    status = str(task.get("status") or "").strip()
    assigned_agent_id = int(task.get("assigned_agent_id") or 0)
    if status == "backlog" and assigned_agent_id == 0:
        return True
    if status == "assigned" and assigned_agent_id == 0:
        return True
    if int(task.get("failure_count") or 0) > 0:
        return True
    if status not in STARTABLE_TASK_STATUSES and not (status == "assigned" and assigned_agent_id == 0):
        return False
    waiting_reason = str(task.get("waiting_reason") or "").strip().lower()
    restart_markers = (
        "review requested changes",
        "clean retry",
        "returned it to the runnable backlog",
        "previous assignment",
    )
    return any(marker in waiting_reason for marker in restart_markers)


def _task_launch_was_already_claimed(
    task_id: int,
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> bool:
    task = next((item for item in tasks if int(item.get("id") or 0) == task_id), None)
    if task is None:
        return False
    status = str(task.get("status") or "").strip().lower()
    if status == "working":
        return True
    if status == "assigned" and _task_has_live_agent_assignment(task, agents):
        return True
    assigned_agent_id = int(task.get("assigned_agent_id") or 0)
    if assigned_agent_id <= 0:
        return False
    agent = next((item for item in agents if int(item.get("id") or 0) == assigned_agent_id), None)
    if agent is None:
        return False
    return int(agent.get("current_task_id") or 0) == task_id and _agent_is_busy(agent)


def _should_wait_for_worker_capacity(start_message: str, agents: list[dict[str, Any]]) -> bool:
    normalized = str(start_message or "").strip().lower()
    busy_markers = (
        "no idle worker is available",
        "agent already has an active unfinished run",
        "task already has an active unfinished run",
    )
    return any(marker in normalized for marker in busy_markers) and any(_agent_is_busy(agent) for agent in agents)


def _should_wait_for_transient_launch_block(
    start_message: str,
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    *,
    task_id: int | None = None,
) -> bool:
    normalized = str(start_message or "").strip().lower()
    if not normalized:
        return False
    if task_id is not None and "task is not in a startable state" in normalized:
        return _task_launch_was_already_claimed(task_id, tasks, agents)
    if _should_wait_for_worker_capacity(start_message, agents):
        return True
    if any(marker in normalized for marker in (" owns ", "overlapping paths", "path ownership")):
        return bool(_active_execution_tasks(tasks, agents=agents)) or any(_agent_is_busy(agent) for agent in agents)
    return False


def _task_has_superseded_waiting_reason(task: dict[str, Any]) -> bool:
    return "superseded after" in str(task.get("waiting_reason") or "").strip().lower()


def _startable_task_sort_key(task: dict[str, Any]) -> tuple[int, int, int]:
    status = str(task.get("status") or "").strip().lower()
    if status == "backlog":
        status_rank = 0
    elif status == "assigned":
        status_rank = 1
    elif status == "waiting_on_paths":
        status_rank = 2
    else:
        status_rank = 3
    priority = int(task.get("priority") or 0)
    task_id = int(task.get("id") or 0)
    return (status_rank, priority, task_id)


def _collect_startable_tasks(
    tasks: list[dict[str, Any]],
    current_statuses: dict[int, str],
    started_task_ids: set[int],
    agents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidates = [
        task
        for task in tasks
        if (
            (
                str(task.get("status") or "") in STARTABLE_TASK_STATUSES
                or (
                    str(task.get("status") or "") == "assigned"
                    and _assigned_task_can_be_relaunched(task, agents)
                )
            )
            and _task_is_restartable_after_prior_start(task, started_task_ids)
            and _task_dependencies_completed(task, current_statuses)
            and not _task_has_superseded_waiting_reason(task)
        )
    ]
    candidates.sort(key=_startable_task_sort_key)
    return candidates


def _attempt_auto_start_ready_task(
    client: Any,
    project_id: int,
    config: HarnessRunConfig,
    trajectory_path: Path,
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    candidate_tasks: list[dict[str, Any]],
    started_task_ids: set[int],
    auto_start_count: int,
) -> tuple[int, bool, bool, str | None, bool]:
    started_any_task = False
    waiting_for_worker_capacity = False
    deadlock_reason: str | None = None
    progress_made = False
    for index, next_task in enumerate(candidate_tasks):
        task_id = int(next_task["id"])
        if auto_start_count >= config.max_auto_task_starts and task_id not in started_task_ids:
            deadlock_reason = "Harness exhausted the unique auto-start budget before all runnable tasks could be launched."
            if index < len(candidate_tasks) - 1:
                continue
            break
        start_payload = _call_api(
            client,
            "POST",
            f"/api/projects/{project_id}/tasks/{task_id}/start",
            trajectory_path,
        )
        start_ok = not (isinstance(start_payload, dict) and start_payload.get("ok") is False)
        if start_ok:
            if task_id not in started_task_ids:
                auto_start_count += 1
            started_task_ids.add(task_id)
            started_any_task = True
            progress_made = True
            break
        if isinstance(start_payload, dict):
            deadlock_message = str(start_payload.get("message") or "").strip()
            if "waiting on dependencies" in deadlock_message.lower():
                continue
            if "superseded after" in deadlock_message.lower():
                progress_made = True
                continue
            refreshed_tasks = _call_api(client, "GET", f"/api/projects/{project_id}/tasks", trajectory_path)
            refreshed_agents = _call_api(client, "GET", f"/api/projects/{project_id}/agents", trajectory_path)
            if _should_wait_for_transient_launch_block(
                deadlock_message,
                refreshed_tasks,
                refreshed_agents,
                task_id=task_id,
            ):
                progress_made = True
                if index < len(candidate_tasks) - 1:
                    continue
                waiting_for_worker_capacity = True
                break
            if deadlock_message:
                deadlock_reason = deadlock_message
        if not deadlock_reason:
            deadlock_reason = f"Mission Control could not start task {next_task['id']}."
        break
    return auto_start_count, started_any_task, waiting_for_worker_capacity, deadlock_reason, progress_made


def _persist_poll_snapshots(
    snapshot_dir: Path,
    *,
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    events: list[dict[str, Any]],
    pending_decisions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
    started_task_ids: set[int],
    deadlock_reason: str | None = None,
) -> None:
    _write_json(snapshot_dir / "latest-tasks.json", tasks)
    _write_json(snapshot_dir / "latest-agents.json", agents)
    _write_json(snapshot_dir / "latest-events.json", events)
    _write_json(snapshot_dir / "latest-pending-decisions.json", pending_decisions)
    _write_json(snapshot_dir / "latest-pending-approvals.json", pending_approvals)
    _write_json(
        snapshot_dir / "latest-meta.json",
        {
            "started_task_ids": sorted(started_task_ids),
            "deadlock_reason": deadlock_reason,
            "updated_at": time.time(),
        },
    )


def _fetch_project_state(
    client: Any,
    project_id: int,
    trajectory_path: Path,
    *,
    snapshot_dir: Path | None = None,
    started_task_ids: set[int] | None = None,
    deadlock_reason: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    tasks = _call_api(client, "GET", f"/api/projects/{project_id}/tasks", trajectory_path)
    agents = _call_api(client, "GET", f"/api/projects/{project_id}/agents", trajectory_path)
    events = _call_api(client, "GET", f"/api/projects/{project_id}/events", trajectory_path)
    pending_decisions = _call_api(client, "GET", f"/api/projects/{project_id}/pending-decisions", trajectory_path)
    pending_approvals = _call_api(client, "GET", f"/api/projects/{project_id}/approvals/pending", trajectory_path)
    if snapshot_dir is not None:
        _persist_poll_snapshots(
            snapshot_dir,
            tasks=tasks,
            agents=agents,
            events=events,
            pending_decisions=pending_decisions,
            pending_approvals=pending_approvals,
            started_task_ids=started_task_ids or set(),
            deadlock_reason=deadlock_reason,
        )
    return {
        "tasks": tasks,
        "agents": agents,
        "events": events,
        "pending_decisions": pending_decisions,
        "pending_approvals": pending_approvals,
    }


def _task_dependencies_completed(task: dict[str, Any], task_statuses: dict[int, str]) -> bool:
    dependency_ids = [int(item) for item in list(task.get("dependencies_json") or []) if str(item).strip()]
    if not dependency_ids:
        return True
    return all(task_statuses.get(dependency_id) in {"completed", "done", "superseded"} for dependency_id in dependency_ids)


def _should_request_manager_recovery(
    tasks: list[dict[str, Any]],
    pending_decisions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
    *,
    recovery_attempts_without_progress: int,
    max_recovery_attempts_without_progress: int = 2,
) -> bool:
    if not tasks:
        return False
    if pending_decisions or pending_approvals:
        return False
    if recovery_attempts_without_progress >= max_recovery_attempts_without_progress:
        return False
    return any(
        str(task.get("status") or "").strip() not in TERMINAL_TASK_STATUSES
        for task in tasks
        if str(task.get("status") or "").strip()
    )


def _completion_grace_seconds(config: HarnessRunConfig) -> float:
    idle_bound = max(float(config.idle_timeout_seconds), 30.0)
    task_budget_bound = max(180.0, min(float(config.task_timeout_seconds) * 0.5, 900.0))
    return float(max(30.0, min(idle_bound, task_budget_bound)))


def _should_run_post_poll_validation(*, timed_out: bool, patch_applied: bool) -> bool:
    return not timed_out or patch_applied


def _worker_subprocess_timeout_seconds(config: HarnessRunConfig) -> int:
    # The inner worker owns repo bootstrap, the Mission Control polling loop, timeout recovery,
    # and optional evaluator replay. A fixed 120-second tail slack was too small for large repos.
    return int(config.task_timeout_seconds + config.validation_timeout_seconds + 240)


def _should_enter_completion_grace(
    tasks: list[dict[str, Any]],
    agents: list[dict[str, Any]],
    task_statuses: dict[int, str],
    pending_decisions: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
    *,
    recent_progress_age: float,
    idle_timeout_seconds: float,
) -> bool:
    if pending_decisions or pending_approvals:
        return False
    if recent_progress_age > max(float(idle_timeout_seconds), 30.0):
        return False
    return bool(_active_execution_tasks(tasks, task_statuses, agents)) or any(_agent_is_busy(agent) for agent in agents)


def _poll_run(
    client: Any,
    project_id: int,
    config: HarnessRunConfig,
    trajectory_path: Path,
    *,
    snapshot_dir: Path | None = None,
) -> dict[str, Any]:
    started_task_ids: set[int] = set()
    task_statuses: dict[int, str] = {}
    event_count = 0
    last_progress = time.monotonic()
    loop_started = time.monotonic()
    auto_start_count = 0
    timed_out = False
    deadlock_reason: str | None = None
    early_exit_reason: str | None = None
    recovery_attempts_without_progress = 0

    while time.monotonic() - loop_started < config.task_timeout_seconds:
        if config.auto_answer_pending_decisions:
            answered = _auto_answer_decisions(client, project_id, trajectory_path)
            if answered:
                last_progress = time.monotonic()
        if config.auto_approve_commands:
            approved = _auto_approve_commands(client, project_id, trajectory_path, allow_for_project=True)
            if approved:
                last_progress = time.monotonic()

        project_state = _fetch_project_state(
            client,
            project_id,
            trajectory_path,
            snapshot_dir=snapshot_dir,
            started_task_ids=started_task_ids,
            deadlock_reason=deadlock_reason,
        )
        tasks = project_state["tasks"]
        agents = project_state["agents"]
        events = project_state["events"]
        current_decisions = project_state["pending_decisions"]
        current_approvals = project_state["pending_approvals"]

        current_statuses = {int(task["id"]): str(task.get("status") or "") for task in tasks}
        if current_statuses != task_statuses or len(events) != event_count:
            last_progress = time.monotonic()
            task_statuses = current_statuses
            event_count = len(events)
            recovery_attempts_without_progress = 0
        if _should_stop_for_evaluator_convergence(tasks, current_decisions, current_approvals):
            early_exit_reason = (
                "Harness stopped once implementation converged and only validation/handoff lanes remained open; "
                "the evaluator will decide the benchmark result from the current workspace patch."
            )
            break

        active_execution_tasks = _active_execution_tasks(tasks, current_statuses, agents)
        if not active_execution_tasks:
            candidate_tasks = _collect_startable_tasks(tasks, current_statuses, started_task_ids, agents)
            auto_start_count, started_any_task, waiting_for_worker_capacity, launch_deadlock_reason, progress_made = _attempt_auto_start_ready_task(
                client,
                project_id,
                config,
                trajectory_path,
                tasks,
                agents,
                candidate_tasks,
                started_task_ids,
                auto_start_count,
            )
            if progress_made:
                last_progress = time.monotonic()
            if launch_deadlock_reason:
                deadlock_reason = launch_deadlock_reason
            if started_any_task:
                time.sleep(config.poll_interval_seconds)
                continue
            if waiting_for_worker_capacity:
                time.sleep(config.poll_interval_seconds)
                continue
            if deadlock_reason:
                break
            if tasks and all(str(task.get("status") or "") in TERMINAL_TASK_STATUSES for task in tasks):
                break
            if tasks and candidate_tasks == []:
                if _should_request_manager_recovery(
                    tasks,
                    current_decisions,
                    current_approvals,
                    recovery_attempts_without_progress=recovery_attempts_without_progress,
                ):
                    _call_api(
                        client,
                        "POST",
                        f"/api/projects/{project_id}/manager/next-step",
                        trajectory_path,
                    )
                    recovery_attempts_without_progress += 1
                    last_progress = time.monotonic()
                    time.sleep(config.poll_interval_seconds)
                    continue
                deadlock_reason = "No runnable tasks remained; remaining tasks were waiting on dependencies or routing."
                break

        if time.monotonic() - last_progress >= config.idle_timeout_seconds:
            if active_execution_tasks:
                time.sleep(config.poll_interval_seconds)
                continue
            break
        time.sleep(config.poll_interval_seconds)
    else:
        timed_out = True

    final_state = _fetch_project_state(
        client,
        project_id,
        trajectory_path,
        snapshot_dir=snapshot_dir,
        started_task_ids=started_task_ids,
        deadlock_reason=deadlock_reason,
    )
    final_statuses = {int(task["id"]): str(task.get("status") or "") for task in final_state["tasks"]}
    grace_candidate_tasks = _collect_startable_tasks(
        final_state["tasks"],
        final_statuses,
        started_task_ids,
        final_state["agents"],
    )
    if timed_out and (
        _should_enter_completion_grace(
            final_state["tasks"],
            final_state["agents"],
            final_statuses,
            final_state["pending_decisions"],
            final_state["pending_approvals"],
            recent_progress_age=time.monotonic() - last_progress,
            idle_timeout_seconds=config.idle_timeout_seconds,
        )
        or bool(grace_candidate_tasks)
    ):
        grace_deadline = time.monotonic() + _completion_grace_seconds(config)
        while time.monotonic() < grace_deadline:
            if config.auto_answer_pending_decisions:
                answered = _auto_answer_decisions(client, project_id, trajectory_path)
                if answered:
                    last_progress = time.monotonic()
            if config.auto_approve_commands:
                approved = _auto_approve_commands(client, project_id, trajectory_path, allow_for_project=True)
                if approved:
                    last_progress = time.monotonic()
            time.sleep(config.poll_interval_seconds)
            final_state = _fetch_project_state(
                client,
                project_id,
                trajectory_path,
                snapshot_dir=snapshot_dir,
                started_task_ids=started_task_ids,
                deadlock_reason=deadlock_reason,
            )
            current_statuses = {int(task["id"]): str(task.get("status") or "") for task in final_state["tasks"]}
            if current_statuses != task_statuses or len(final_state["events"]) != event_count:
                last_progress = time.monotonic()
                task_statuses = current_statuses
                event_count = len(final_state["events"])
            active_execution_tasks = _active_execution_tasks(final_state["tasks"], current_statuses, final_state["agents"])
            if not active_execution_tasks:
                grace_candidate_tasks = _collect_startable_tasks(
                    final_state["tasks"],
                    current_statuses,
                    started_task_ids,
                    final_state["agents"],
                )
                auto_start_count, started_any_task, waiting_for_worker_capacity, _grace_deadlock_reason, progress_made = _attempt_auto_start_ready_task(
                    client,
                    project_id,
                    config,
                    trajectory_path,
                    final_state["tasks"],
                    final_state["agents"],
                    grace_candidate_tasks,
                    started_task_ids,
                    auto_start_count,
                )
                if progress_made:
                    last_progress = time.monotonic()
                if started_any_task or waiting_for_worker_capacity:
                    time.sleep(config.poll_interval_seconds)
                    continue
            if final_state["tasks"] and all(
                str(task.get("status") or "") in TERMINAL_TASK_STATUSES for task in final_state["tasks"]
            ):
                timed_out = False
                break
            if not _should_enter_completion_grace(
                final_state["tasks"],
                final_state["agents"],
                current_statuses,
                final_state["pending_decisions"],
                final_state["pending_approvals"],
                recent_progress_age=time.monotonic() - last_progress,
                idle_timeout_seconds=config.idle_timeout_seconds,
            ):
                break

    return {
        "timed_out": timed_out,
        "tasks": final_state["tasks"],
        "agents": final_state["agents"],
        "events": final_state["events"],
        "pending_decisions": final_state["pending_decisions"],
        "pending_approvals": final_state["pending_approvals"],
        "started_task_ids": sorted(started_task_ids),
        "deadlock_reason": deadlock_reason,
        "early_exit_reason": early_exit_reason,
    }


def _run_single_task_attempt(task: BenchmarkTaskSpec, config: HarnessRunConfig, task_output_dir: Path) -> BenchmarkTaskResult:
    runtime_root = task_output_dir / "runtime"
    os.environ["MISSION_CONTROL_APP_HOME"] = str(runtime_root / "app-home")
    os.environ["MISSION_CONTROL_RUNTIME_ROOT"] = str(runtime_root)
    os.environ["MISSION_CONTROL_LAUNCHER_DIR"] = str(runtime_root / "launcher")
    os.environ["MISSION_CONTROL_MODEL"] = config.model
    if config.strict_model:
        os.environ["MISSION_CONTROL_STRICT_MODEL"] = "1"
    else:
        os.environ.pop("MISSION_CONTROL_STRICT_MODEL", None)

    runtime = _runtime_imports()
    _reset_db(runtime)
    TestClient = runtime["TestClient"]

    workspace_path = _benchmark_workspace_path(task_output_dir)
    trajectory_path = task_output_dir / "trajectory.jsonl"
    before_snapshot: dict[str, str] = {}
    validation_results = []
    setup_results = []
    notes: list[str] = []
    start_time = time.monotonic()

    _write_json(task_output_dir / "task-spec.json", task.to_dict())
    _write_json(task_output_dir / "run-config.json", config.to_dict())

    try:
        notes.extend(stage_workspace_snapshot(task.repo_path, workspace_path, base_commit=task.base_commit))
    except Exception as exc:  # noqa: BLE001
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="setup_failed",
            attempted=False,
            completed=False,
            resolved=False,
            patch_applied=False,
            validation_succeeded=False,
            failure_category="setup_failed",
            runtime_seconds=round(time.monotonic() - start_time, 3),
            notes=[f"Workspace staging failed: {type(exc).__name__}: {exc}"],
            model_settings={"provider": config.provider, "model": config.model},
            artifact_paths={"task_output_dir": task_output_dir.as_posix()},
        )

    environment_setup_commit = str(task.metadata.get("environment_setup_commit") or "").strip() or None
    setup_commit = environment_setup_commit or task.base_commit
    if setup_commit and setup_commit != task.base_commit:
        try:
            notes.append(f"Switching staged workspace to environment setup commit {setup_commit} for bootstrap/setup.")
            notes.extend(checkout_workspace_commit(workspace_path, setup_commit))
        except Exception as exc:  # noqa: BLE001
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="setup_failed",
                attempted=False,
                completed=False,
                resolved=False,
                patch_applied=False,
                validation_succeeded=False,
                failure_category="setup_failed",
                runtime_seconds=round(time.monotonic() - start_time, 3),
                notes=notes + [f"Failed to switch staged workspace to environment_setup_commit {setup_commit}: {type(exc).__name__}: {exc}"],
                model_settings={"provider": config.provider, "model": config.model},
                artifact_paths={
                    "task_output_dir": task_output_dir.as_posix(),
                    "workspace_path": workspace_path.as_posix(),
                },
            )

    setup_commands = detect_setup_commands(workspace_path, task.setup_commands)
    setup_was_explicit = bool(task.setup_commands)
    python_bootstrap_report = _prepare_python_workspace(
        workspace_path,
        task_output_dir / "python-bootstrap",
        timeout_seconds=min(config.validation_timeout_seconds, 180),
    )
    _write_json(task_output_dir / "python-bootstrap.json", python_bootstrap_report)
    bootstrap_results = list(python_bootstrap_report.get("results") or [])
    if bootstrap_results and not any(item.get("returncode") == 0 for item in bootstrap_results):
        notes.append("Python workspace bootstrap commands all failed.")
    if setup_commands:
        setup_results = run_validation_commands(
            workspace_path,
            setup_commands,
            task_output_dir / "setup",
            timeout_seconds=config.validation_timeout_seconds,
        )
        _write_json(
            task_output_dir / "setup-results.json",
            [item.to_dict() for item in setup_results],
        )
        if not any(not item.timed_out and item.returncode == 0 for item in setup_results):
            failure_note = "All detected setup commands failed."
            if setup_was_explicit:
                return BenchmarkTaskResult(
                    instance_id=task.instance_id,
                    repo_name=task.repo_name,
                    status="setup_failed",
                    attempted=False,
                    completed=False,
                    resolved=False,
                    patch_applied=False,
                    validation_succeeded=False,
                    failure_category="setup_failed",
                    runtime_seconds=round(time.monotonic() - start_time, 3),
                    validation_commands=setup_commands,
                    validation_results=setup_results,
                    notes=notes + [failure_note],
                    model_settings={"provider": config.provider, "model": config.model},
                    artifact_paths={
                        "task_output_dir": task_output_dir.as_posix(),
                        "workspace_path": workspace_path.as_posix(),
                        "setup_results_path": (task_output_dir / "setup-results.json").as_posix(),
                    },
                )
            notes.append(f"{failure_note} Continuing because setup was heuristic only.")

    if setup_commit and task.base_commit and setup_commit != task.base_commit:
        try:
            notes.extend(checkout_workspace_commit(workspace_path, task.base_commit))
            notes.append(f"Restored staged workspace to base commit {task.base_commit} after setup.")
        except Exception as exc:  # noqa: BLE001
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="setup_failed",
                attempted=False,
                completed=False,
                resolved=False,
                patch_applied=False,
                validation_succeeded=False,
                failure_category="setup_failed",
                runtime_seconds=round(time.monotonic() - start_time, 3),
                notes=notes + [f"Failed to restore staged workspace to base_commit {task.base_commit} after setup: {type(exc).__name__}: {exc}"],
                model_settings={"provider": config.provider, "model": config.model},
                artifact_paths={
                    "task_output_dir": task_output_dir.as_posix(),
                    "workspace_path": workspace_path.as_posix(),
                },
            )

    solver_test_patch_report = apply_solver_test_patch(
        task,
        workspace_path,
        task_output_dir,
        timeout_seconds=min(config.validation_timeout_seconds, 120),
    )
    if solver_test_patch_report is not None:
        _write_json(task_output_dir / "solver-test-patch-apply.json", solver_test_patch_report)
        if solver_test_patch_report.get("applied"):
            notes.append(
                "Applied the SWE-bench test_patch to the solver workspace so focused validation commands can target the benchmark regression."
            )
        else:
            notes.append(
                "Could not apply the SWE-bench test_patch to the solver workspace; Mission Control continued without benchmark-visible regression tests."
            )
    protected_paths_manifest = write_benchmark_protected_paths_manifest(workspace_path, task.test_patch)
    _write_json(task_output_dir / "benchmark-protected-paths.json", protected_paths_manifest)

    before_snapshot = snapshot_workspace(workspace_path)
    validation_commands = detect_validation_commands(
        workspace_path,
        task.validation_commands,
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=task.pass_to_pass,
    )
    bootstrap_report = _bootstrap_missing_test_dependencies(
        workspace_path,
        validation_commands,
        task_output_dir / "bootstrap-deps",
        timeout_seconds=min(config.validation_timeout_seconds, 120),
    )
    _write_json(task_output_dir / "bootstrap-deps.json", bootstrap_report)
    installed_packages = [str(item) for item in list(bootstrap_report.get("installed_packages") or []) if str(item).strip()]
    attempted_packages = [str(item) for item in list(bootstrap_report.get("attempted_packages") or []) if str(item).strip()]
    if installed_packages:
        notes.append(f"Installed missing test dependencies before orchestration: {', '.join(installed_packages)}.")
    elif attempted_packages:
        notes.append(
            "Attempted to install missing test dependencies before orchestration, "
            f"but the install did not succeed: {', '.join(attempted_packages)}."
        )
    setup_blocker = _detect_local_setup_blocker(python_bootstrap_report, bootstrap_report)
    if setup_blocker:
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="setup_failed",
            attempted=False,
            completed=False,
            resolved=False,
            patch_applied=False,
            validation_succeeded=False,
            failure_category="setup_failed",
            runtime_seconds=round(time.monotonic() - start_time, 3),
            validation_commands=validation_commands,
            notes=notes + [setup_blocker],
            model_settings={"provider": config.provider, "model": config.model},
            artifact_paths={
                "task_output_dir": task_output_dir.as_posix(),
                "workspace_path": workspace_path.as_posix(),
                "python_bootstrap_path": (task_output_dir / "python-bootstrap.json").as_posix(),
                "bootstrap_deps_path": (task_output_dir / "bootstrap-deps.json").as_posix(),
            },
        )
    repo_context = build_repo_context(task, workspace_path, validation_commands)
    _write_json(task_output_dir / "repo-context.json", repo_context)
    prompt = build_manager_issue_prompt(task, validation_commands, repo_context)
    (task_output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    with TestClient(runtime["app"]) as client:
        client.headers.update(_bridge_headers(runtime))
        issue_context = build_project_issue_context(task, validation_commands, repo_context)
        project = _call_api(
            client,
            "POST",
            "/api/projects",
            trajectory_path,
            json_body={
                "name": f"SWE-bench {task.instance_id}",
                "idea": issue_context[:4000],
                "workspace_path": workspace_path.as_posix(),
                "provider": config.provider,
                "runner_mode": "auto",
                "manager_mode": "auto",
            },
        )
        project_id = int(project["id"])
        _write_json(task_output_dir / "project.json", project)
        settings_payload = _configure_project(client, config, project_id, trajectory_path)
        _write_json(task_output_dir / "settings.json", settings_payload)
        write_permission_payload = _ensure_project_write_permission(client, project, trajectory_path)
        if write_permission_payload is not None:
            _write_json(task_output_dir / "write-permission.json", write_permission_payload)
        if config.enable_swarm_planning:
            _apply_swarm_preferences(client, project_id, config, trajectory_path)
        seeded_payloads = _seed_benchmark_project(client, project_id, prompt, config, trajectory_path)
        _write_json(task_output_dir / "change-request.json", seeded_payloads["change_request"])
        if "swarm_plan" in seeded_payloads:
            _write_json(task_output_dir / "swarm-plan.json", seeded_payloads["swarm_plan"])
        if "swarm_spawn" in seeded_payloads:
            _write_json(task_output_dir / "swarm-spawn.json", seeded_payloads["swarm_spawn"])
        generation = dict(seeded_payloads["task_generation"])
        _write_json(task_output_dir / "task-generation.json", generation)
        snapshot_dir = task_output_dir / "runtime-snapshots"
        poll_result = _poll_run(
            client,
            project_id,
            config,
            trajectory_path,
            snapshot_dir=snapshot_dir,
        )

        tasks = poll_result["tasks"]
        agents = poll_result["agents"]
        events = poll_result["events"]
        pending_decisions = poll_result["pending_decisions"]
        pending_approvals = poll_result["pending_approvals"]
        deadlock_reason = str(poll_result.get("deadlock_reason") or "").strip()
        early_exit_reason = str(poll_result.get("early_exit_reason") or "").strip()

        _write_json(task_output_dir / "tasks.json", tasks)
        _write_json(task_output_dir / "agents.json", agents)
        _write_json(task_output_dir / "events.json", events)
        _write_json(task_output_dir / "pending-decisions.json", pending_decisions)
        _write_json(task_output_dir / "pending-approvals.json", pending_approvals)
        manager_messages = _call_api(client, "GET", f"/api/projects/{project_id}/manager/messages", trajectory_path)
        _write_json(task_output_dir / "manager-messages.json", manager_messages)
        agent_log_paths = _collect_agent_logs(client, project_id, agents, task_output_dir, trajectory_path)
        _write_json(task_output_dir / "agent-log-paths.json", agent_log_paths)

    refreshed_state = _fetch_project_state(
        client,
        project_id,
        trajectory_path,
        snapshot_dir=snapshot_dir,
        started_task_ids=set(int(item) for item in list(poll_result.get("started_task_ids") or [])),
        deadlock_reason=deadlock_reason,
    )
    tasks = refreshed_state["tasks"]
    agents = refreshed_state["agents"]
    events = refreshed_state["events"]
    pending_decisions = refreshed_state["pending_decisions"]
    pending_approvals = refreshed_state["pending_approvals"]

    if bool(poll_result["timed_out"]):
        changed_files = recover_git_changed_files(workspace_path)
        diff_text = ""
        meaningful_changed_files = meaningful_patch_paths(changed_files)
        candidate_changed_files, skipped_protected_files = filter_benchmark_protected_changed_files(
            meaningful_changed_files,
            task.test_patch,
        )
        protected_restore_report = None
        if skipped_protected_files:
            protected_restore_report = restore_workspace_files_from_snapshot(
                workspace_path,
                before_snapshot,
                skipped_protected_files,
            )
            changed_files = recover_git_changed_files(workspace_path)
            meaningful_changed_files = meaningful_patch_paths(changed_files)
            candidate_changed_files, _ignored_skipped = filter_benchmark_protected_changed_files(
                meaningful_changed_files,
                task.test_patch,
            )
        notes.append(
            "Skipped the full workspace snapshot diff after timeout and used git-status-based changed-file recovery instead."
        )
    else:
        diff_text, changed_files, skipped_protected_files, protected_restore_report = _finalize_workspace_diff(
            workspace_path,
            before_snapshot,
            task.test_patch,
        )
        meaningful_changed_files = meaningful_patch_paths(changed_files)
        candidate_changed_files, _ignored_skipped = filter_benchmark_protected_changed_files(
            meaningful_changed_files,
            task.test_patch,
        )
    diff_path = task_output_dir / "workspace.diff"
    diff_path.write_text(diff_text, encoding="utf-8")
    equivalent_output_normalization_target = (
        _equivalent_output_normalization_target(diff_path.as_posix()) if candidate_changed_files else None
    )
    if equivalent_output_normalization_target:
        notes.append(
            "Candidate diff only rewrote final boolean normalization for "
            f"`{equivalent_output_normalization_target}` without changing the upstream computation that produced it."
        )
    if protected_restore_report is not None:
        _write_json(task_output_dir / "protected-file-restore.json", protected_restore_report)
        restored_count = len(list(protected_restore_report.get("restored_files") or []))
        deleted_count = len(list(protected_restore_report.get("deleted_files") or []))
        notes.append(
            "Restored benchmark-protected workspace files before post-run validation "
            f"({restored_count} restored, {deleted_count} deleted) so solver-side validation stays authoritative."
        )

    worker_validation_results: list[ValidationCommandResult] = []
    if _should_run_post_poll_validation(
        timed_out=bool(poll_result["timed_out"]),
        patch_applied=bool(candidate_changed_files),
    ):
        worker_validation_results = run_validation_commands(
            workspace_path,
            validation_commands,
            task_output_dir / "validation",
            timeout_seconds=config.validation_timeout_seconds,
        )
    else:
        notes.append(
            "Skipped post-run harness validation because Mission Control timed out before producing a candidate patch."
        )
    _write_json(
        task_output_dir / "validation-results.json",
        [item.to_dict() for item in worker_validation_results],
    )

    task_statuses = [str(task_payload.get("status") or "") for task_payload in tasks]
    run_analysis = analyze_task_execution(tasks, events, agents)
    _write_json(task_output_dir / "run-analysis.json", run_analysis)
    notes.extend(str(item) for item in run_analysis.get("notes") or [] if str(item).strip())
    if early_exit_reason:
        notes.append(early_exit_reason)
    summary_text = extract_task_summary(manager_messages) or ""
    runner_failed = any(int(agent.get("failure_count") or 0) > 0 for agent in agents) or "HTTP Error 500" in summary_text
    patch_applied = bool(candidate_changed_files)
    final_validation_commands = list(validation_commands)
    final_validation_results = list(worker_validation_results)
    evaluator_artifact_paths: dict[str, str] = {}
    if task.test_patch and patch_applied:
        evaluator_summary = run_evaluator_validation(
            task,
            workspace_path,
            candidate_changed_files,
            task_output_dir / "evaluator",
            timeout_seconds=config.validation_timeout_seconds,
        )
        final_validation_commands = list(evaluator_summary.commands)
        final_validation_results = list(evaluator_summary.results)
        evaluator_artifact_paths = dict(evaluator_summary.artifact_paths)
        notes.extend(str(item) for item in evaluator_summary.notes if str(item).strip())
    if skipped_protected_files:
        notes.append(
            "Ignored candidate edits that overlapped the authoritative SWE-bench test_patch when counting the candidate patch."
        )
    validation_attempted = bool(final_validation_results)
    validation_succeeded = patch_applied and bool(final_validation_results) and all(
        not item.timed_out and item.returncode == 0 for item in final_validation_results
    )
    setup_failed = False
    effective_timed_out = bool(poll_result["timed_out"])
    if effective_timed_out and task_flow_terminal(task_statuses) and not pending_decisions and not pending_approvals:
        notes.append(
            "Mission Control reached a terminal task state during final reconciliation after the polling timeout threshold."
        )
        effective_timed_out = False
    completed = task_flow_completed(task_statuses, timed_out=effective_timed_out)
    orchestration_deadlocked = bool(deadlock_reason) and not completed
    if deadlock_reason and orchestration_deadlocked:
        notes.append(f"Mission Control deadlocked before task flow completion: {deadlock_reason}")
    failure_category = classify_failure_category(
        timed_out=effective_timed_out,
        setup_failed=setup_failed,
        orchestration_deadlocked=orchestration_deadlocked,
        patch_applied=patch_applied,
        runner_failed=runner_failed,
        validation_attempted=validation_attempted,
        validation_succeeded=validation_succeeded,
        pending_approvals=len(pending_approvals),
        pending_decisions=len(pending_decisions),
        tasks_generated=int(generation.get("count") or len(tasks)),
        task_statuses=task_statuses,
        manager_parse_failures=int(run_analysis.get("manager_parse_failures") or 0),
        retry_count=int(run_analysis.get("retry_count") or 0),
        unblock_task_count=int(run_analysis.get("unblock_task_count") or 0),
    )
    attempted = bool(tasks) or bool(generation.get("count"))
    resolved = patch_applied and validation_succeeded
    if resolved:
        failure_category = None
    if resolved and not completed:
        notes.append("Patch applied and focused validation passed, but Mission Control did not finish its internal task flow before the harness stopped.")
    if validation_attempted and not patch_applied:
        if all(not item.timed_out and item.returncode == 0 for item in final_validation_results):
            notes.append(
                "Validation commands passed, but no accepted candidate workspace edits were recorded, so the run was not counted as validation success."
            )
        else:
            notes.append(
                "Validation commands ran, but no accepted candidate workspace edits were recorded, so the run could not count as validation success."
            )
    status = "resolved_with_open_tasks" if resolved and not completed else ("resolved" if resolved else failure_category or ("completed" if completed else "unresolved"))

    observed_commands = final_validation_commands[:]
    for approval in pending_approvals:
        payload = dict(approval.get("request_payload_json") or {})
        command = str(payload.get("command") or "").strip()
        if command:
            observed_commands.append(command)

    return BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status=status,
        attempted=attempted,
        completed=completed,
        resolved=resolved,
        patch_applied=patch_applied,
        validation_succeeded=validation_succeeded,
        failure_category=failure_category,
        runtime_seconds=round(time.monotonic() - start_time, 3),
        changed_files=candidate_changed_files,
        validation_commands=final_validation_commands,
        validation_results=final_validation_results,
        worker_validation_commands=validation_commands,
        worker_validation_results=worker_validation_results,
        observed_commands=observed_commands,
        notes=notes,
        model_settings={
            "provider": config.provider,
            "manager_model": config.normalized_models()[0],
            "worker_model": config.normalized_models()[1],
            "approval_policy": config.approval_policy,
            "sandbox_mode": config.sandbox_mode,
            "strict_model": config.strict_model,
        },
        artifact_paths={
            "task_output_dir": task_output_dir.as_posix(),
            "trajectory_path": trajectory_path.as_posix(),
            "diff_path": diff_path.as_posix(),
            "workspace_path": workspace_path.as_posix(),
            "agent_logs_dir": (task_output_dir / "agent-logs").as_posix(),
            "agent_log_paths_json": (task_output_dir / "agent-log-paths.json").as_posix(),
            "run_analysis_path": (task_output_dir / "run-analysis.json").as_posix(),
            "repo_context_path": (task_output_dir / "repo-context.json").as_posix(),
            "setup_results_path": (task_output_dir / "setup-results.json").as_posix(),
            "bootstrap_deps_path": (task_output_dir / "bootstrap-deps.json").as_posix(),
            **evaluator_artifact_paths,
        },
        task_summary=summary_text[:500] or None,
        retry_count=int(run_analysis.get("retry_count") or 0),
        unblock_task_count=int(run_analysis.get("unblock_task_count") or 0),
        manager_parse_failures=int(run_analysis.get("manager_parse_failures") or 0),
        event_counts=dict(run_analysis.get("event_counts") or {}),
    )


def _run_single_task(task: BenchmarkTaskSpec, config: HarnessRunConfig, task_output_dir: Path) -> BenchmarkTaskResult:
    task_output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(task_output_dir / "task-spec.json", task.to_dict())
    _write_json(task_output_dir / "run-config.json", config.to_dict())

    original_task = task
    current_task = task
    attempts_payload: list[dict[str, Any]] = []
    final_result: BenchmarkTaskResult | None = None
    selected_attempt_number = 0

    for attempt_number in range(1, max(int(config.max_task_attempts or 1), 1) + 1):
        attempt_output_dir = task_output_dir / f"attempt-{attempt_number:02d}"
        attempt_output_dir.mkdir(parents=True, exist_ok=True)
        result = _run_single_task_attempt(current_task, config, attempt_output_dir)
        _write_json(attempt_output_dir / "task-result.json", result.to_dict())
        attempts_payload.append(
            {
                "attempt_number": attempt_number,
                "status": result.status,
                "resolved": result.resolved,
                "patch_applied": result.patch_applied,
                "validation_succeeded": result.validation_succeeded,
                "failure_category": result.failure_category,
                "changed_files": list(result.changed_files),
                "artifact_paths": dict(result.artifact_paths),
                "notes": list(result.notes),
            }
        )
        if final_result is None:
            final_result = result
            selected_attempt_number = attempt_number
        else:
            current_score = _attempt_selection_score(result)
            selected_score = _attempt_selection_score(final_result)
            if current_score > selected_score or (current_score == selected_score and attempt_number >= selected_attempt_number):
                final_result = result
                selected_attempt_number = attempt_number
        retry_basis = _retry_basis_result(result, final_result)
        if not _should_retry_failed_attempt(
            retry_basis,
            attempt_number=attempt_number,
            max_task_attempts=max(int(config.max_task_attempts or 1), 1),
        ):
            break
        retry_hints = _build_retry_feedback(original_task, retry_basis, attempt_number=attempt_number + 1)
        if retry_basis is not result:
            regression_note = (
                f"Latest retry regression on attempt {attempt_number}: "
                "no verified workspace file changes were produced, so continue iterating from the most recent "
                "authoritative patch-validation attempt instead of resetting to reproduce-only analysis."
            )
            retry_hints = _trim_text_block(f"{retry_hints}\n\n{regression_note}", max_chars=1800)
        current_task = replace(
            original_task,
            hints_text=retry_hints,
        )

    attempts_path = task_output_dir / "attempts.json"
    _write_json(attempts_path, attempts_payload)
    if final_result is None:
        raise RuntimeError("The benchmark harness did not execute any task attempts.")
    aggregate_patch_applied = any(bool(item.get("patch_applied")) for item in attempts_payload)
    aggregate_validation_succeeded = any(bool(item.get("validation_succeeded")) for item in attempts_payload)
    aggregate_changed_files = list(
        dict.fromkeys(
            str(path).strip()
            for item in attempts_payload
            for path in list(item.get("changed_files") or [])
            if str(path).strip()
        )
    )

    total_attempts = len(attempts_payload)
    if total_attempts > 1:
        retry_notes = [
            f"Attempt {item['attempt_number']} ended with status={item['status']} failure_category={item['failure_category'] or 'none'}."
            for item in attempts_payload[:-1]
        ]
        selection_note = None
        if selected_attempt_number and selected_attempt_number != total_attempts:
            selection_note = (
                f"Selected attempt {selected_attempt_number} as the benchmark result because later attempts did not improve over its verified progress."
            )
        final_result.notes = [
            f"Ran {total_attempts} benchmark attempts for this task; later attempts reused local evaluator evidence from earlier failed patches.",
            *retry_notes,
            *([selection_note] if selection_note else []),
            *list(final_result.notes),
        ]
    if aggregate_patch_applied and not final_result.patch_applied:
        final_result.patch_applied = True
        if aggregate_changed_files and not final_result.changed_files:
            final_result.changed_files = list(aggregate_changed_files)
        final_result.notes = [
            "Earlier attempts produced candidate patches even though the selected final attempt did not preserve an accepted patch payload.",
            *list(final_result.notes),
        ]
    if aggregate_validation_succeeded and not final_result.validation_succeeded:
        final_result.validation_succeeded = True
    final_result.model_settings = {
        **dict(final_result.model_settings),
        "max_task_attempts": max(int(config.max_task_attempts or 1), 1),
        "attempt_count": total_attempts,
    }
    final_result.artifact_paths = {
        **dict(final_result.artifact_paths),
        "task_output_dir": task_output_dir.as_posix(),
        "attempts_path": attempts_path.as_posix(),
        "final_attempt_dir": (task_output_dir / f"attempt-{selected_attempt_number:02d}").as_posix(),
        "last_attempt_dir": (task_output_dir / f"attempt-{total_attempts:02d}").as_posix(),
    }
    return final_result


def _run_manifest(config: HarnessRunConfig) -> int:
    tasks = _load_selected_tasks(config)

    output_root = Path(config.output_root)
    run_root = output_root / config.run_label
    run_root.mkdir(parents=True, exist_ok=True)
    _write_json(run_root / "run-config.json", config.to_dict())
    if config.auto_prepare_repos:
        repo_cache_root = _repo_cache_root_from_config(config)
        if repo_cache_root is None:
            raise SystemExit("--auto-prepare-repos requires --repo-cache-root or --prepared-repos-root.")
        prep_report = _prepare_repositories(tasks, repo_cache_root)
        _write_json(run_root / "repo-preparation.json", prep_report)
        tasks = _load_selected_tasks(config)
    preflight = benchmark_preflight(config)
    _write_json(run_root / "preflight.json", preflight)
    if not preflight.get("ready"):
        summary = summarize_results([], run_label=config.run_label)
        summary["preflight"] = preflight
        paths = persist_summary(run_root, summary)
        print(json.dumps({"run_root": run_root.as_posix(), "preflight": preflight, **paths}, indent=2))
        return 2
    _write_json(run_root / "manifest-copy.json", [task.to_dict() for task in tasks])

    results: list[BenchmarkTaskResult] = []
    config_path = run_root / "run-config.json"
    for index, task in enumerate(tasks, start=1):
        task_root = run_root / f"{index:04d}-{_safe_name(task.instance_id)}"
        task_root.mkdir(parents=True, exist_ok=True)
        task_spec_path = task_root / "task-spec.json"
        _write_json(task_spec_path, task.to_dict())
        command = [
            sys.executable,
            __file__,
            "--task-spec",
            task_spec_path.as_posix(),
            "--run-config",
            config_path.as_posix(),
            "--task-output-dir",
            task_root.as_posix(),
        ]
        timeout_seconds = _worker_subprocess_timeout_seconds(config)
        try:
            worker_environment = os.environ.copy()
            worker_environment.update(_evaluator_spec_env(task))
            completed = subprocess.run(
                command,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=worker_environment,
            )
            (task_root / "worker-stdout.txt").write_text(completed.stdout or "", encoding="utf-8")
            (task_root / "worker-stderr.txt").write_text(completed.stderr or "", encoding="utf-8")
            payload = json.loads((completed.stdout or "").strip() or "{}")
        except subprocess.TimeoutExpired:
            recovered_workspace_path = _benchmark_workspace_path(task_root)
            recovery_note: str | None = None
            try:
                recovered = recover_timeout_task_result(
                    task,
                    config,
                    task_root,
                    workspace_path_override=recovered_workspace_path,
                )
            except Exception as recovery_exc:  # noqa: BLE001
                recovered = None
                recovery_note = (
                    "Harness worker subprocess timed out before returning a result. "
                    f"Timeout recovery also failed: {type(recovery_exc).__name__}: {recovery_exc}"
                )
            payload = recovered.to_dict() if recovered is not None else BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="timeout",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=False,
                validation_succeeded=False,
                failure_category="timeout",
                runtime_seconds=float(timeout_seconds),
                model_settings={"provider": config.provider, "model": config.model},
                artifact_paths={"task_output_dir": task_root.as_posix()},
                notes=[recovery_note or "Harness worker subprocess timed out before returning a result."],
            ).to_dict()
        except json.JSONDecodeError:
            payload = BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="setup_failed",
                attempted=False,
                completed=False,
                resolved=False,
                patch_applied=False,
                validation_succeeded=False,
                failure_category="setup_failed",
                runtime_seconds=0.0,
                model_settings={"provider": config.provider, "model": config.model},
                artifact_paths={"task_output_dir": task_root.as_posix()},
                notes=["Harness worker returned invalid JSON."],
            ).to_dict()
        if not (task_root / "worker-stdout.txt").exists():
            (task_root / "worker-stdout.txt").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        result = BenchmarkTaskResult(
            instance_id=str(payload.get("instance_id") or task.instance_id),
            repo_name=payload.get("repo_name"),
            status=str(payload.get("status") or "unresolved"),
            attempted=bool(payload.get("attempted")),
            completed=bool(payload.get("completed")),
            resolved=bool(payload.get("resolved")),
            patch_applied=bool(payload.get("patch_applied")),
            validation_succeeded=bool(payload.get("validation_succeeded")),
            failure_category=payload.get("failure_category"),
            runtime_seconds=float(payload.get("runtime_seconds") or 0.0),
            changed_files=[str(item) for item in list(payload.get("changed_files") or [])],
            validation_commands=[str(item) for item in list(payload.get("validation_commands") or [])],
            validation_results=[
                ValidationCommandResult(
                    command=str(item.get("command") or ""),
                    returncode=item.get("returncode"),
                    timed_out=bool(item.get("timed_out")),
                    runtime_seconds=float(item.get("runtime_seconds") or 0.0),
                    stdout_path=str(item.get("stdout_path") or ""),
                    stderr_path=str(item.get("stderr_path") or ""),
                )
                for item in list(payload.get("validation_results") or [])
                if isinstance(item, dict)
            ],
            observed_commands=[str(item) for item in list(payload.get("observed_commands") or [])],
            notes=[str(item) for item in list(payload.get("notes") or [])],
            model_settings=dict(payload.get("model_settings") or {}),
            artifact_paths=dict(payload.get("artifact_paths") or {}),
            task_summary=str(payload.get("task_summary") or "").strip() or None,
            retry_count=int(payload.get("retry_count") or 0),
            unblock_task_count=int(payload.get("unblock_task_count") or 0),
            manager_parse_failures=int(payload.get("manager_parse_failures") or 0),
            event_counts={
                str(key): int(value)
                for key, value in dict(payload.get("event_counts") or {}).items()
                if str(key).strip()
            },
        )
        results.append(result)
        _write_json(task_root / "task-result.json", payload)

    summary = summarize_results(results, run_label=config.run_label)
    paths = persist_summary(run_root, summary)
    print(json.dumps({"run_root": run_root.as_posix(), **paths}, indent=2))
    return 0


def _run_preflight_only(config: HarnessRunConfig) -> int:
    output_root = Path(config.output_root)
    run_root = output_root / config.run_label
    run_root.mkdir(parents=True, exist_ok=True)
    _write_json(run_root / "run-config.json", config.to_dict())
    if config.auto_prepare_repos:
        repo_cache_root = _repo_cache_root_from_config(config)
        if repo_cache_root is None:
            raise SystemExit("--auto-prepare-repos requires --repo-cache-root or --prepared-repos-root.")
        prep_tasks = _load_selected_tasks(config)
        prep_report = _prepare_repositories(prep_tasks, repo_cache_root)
        _write_json(run_root / "repo-preparation.json", prep_report)
    preflight = benchmark_preflight(config)
    _write_json(run_root / "preflight.json", preflight)

    manifest_copy_path: str | None = None
    try:
        selected_tasks = _load_selected_tasks(config)
        manifest_copy = run_root / "manifest-copy.json"
        _write_json(manifest_copy, [task.to_dict() for task in selected_tasks])
        manifest_copy_path = manifest_copy.as_posix()
    except Exception:
        manifest_copy_path = None

    print(
        json.dumps(
            {
                "run_root": run_root.as_posix(),
                "preflight_path": (run_root / "preflight.json").as_posix(),
                "manifest_copy_path": manifest_copy_path,
                "ready": bool(preflight.get("ready")),
                "blockers": list(preflight.get("blockers") or []),
            },
            indent=2,
        )
    )
    return 0 if preflight.get("ready") else 2


def _run_task_worker(task_spec_path: str, run_config_path: str, task_output_dir: str) -> int:
    try:
        task = BenchmarkTaskSpec.from_record(json.loads(Path(task_spec_path).read_text(encoding="utf-8")))
        hidden_payload = str(os.environ.get(EVALUATOR_SPEC_ENV_VAR) or "").strip()
        if hidden_payload:
            try:
                task = task.with_sensitive_payload(json.loads(hidden_payload))
            except json.JSONDecodeError:
                pass
        config = HarnessRunConfig.from_dict(json.loads(Path(run_config_path).read_text(encoding="utf-8")))
        result = _run_single_task(task, config, Path(task_output_dir))
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        failure = {
            "instance_id": Path(task_spec_path).stem,
            "status": "setup_failed",
            "attempted": False,
            "completed": False,
            "resolved": False,
            "patch_applied": False,
            "validation_succeeded": False,
            "failure_category": "setup_failed",
            "runtime_seconds": 0.0,
            "notes": [f"{type(exc).__name__}: {exc}", traceback.format_exc()],
            "artifact_paths": {"task_output_dir": task_output_dir},
        }
        print(json.dumps(failure, indent=2))
        return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Mission Control against a local SWE-bench-style manifest.")
    parser.add_argument("--tasks", help="Path to a local JSON/JSONL task manifest, parquet file, or SWE-bench dataset directory.")
    parser.add_argument("--output-root", help="Directory for benchmark outputs.")
    parser.add_argument("--run-label", help="Optional run label.")
    parser.add_argument("--dataset-split", default="test", help="Dataset split when --tasks points at a SWE-bench parquet source.")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--manager-model")
    parser.add_argument("--worker-model")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--sandbox-mode", default="workspace-write")
    parser.add_argument("--approval-policy", default="never")
    parser.add_argument("--task-timeout-seconds", type=int, default=900)
    parser.add_argument("--idle-timeout-seconds", type=int, default=90)
    parser.add_argument("--validation-timeout-seconds", type=int, default=300)
    parser.add_argument("--max-task-attempts", type=int, default=2)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--max-auto-task-starts", type=int, default=16)
    parser.add_argument("--swarm-max-agents", type=int, default=4)
    parser.add_argument("--enable-swarm-planning", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--max-tasks", type=int)
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--prepared-repos-root", help="Root directory containing prepared local repos or per-instance workspaces.")
    parser.add_argument("--repo-map", help="JSON file mapping instance ids or repo names to local prepared repo paths.")
    parser.add_argument("--repo-cache-root", help="Root directory for reusable upstream repo clones, usually owner__repo folders.")
    parser.add_argument("--auto-prepare-repos", action="store_true", help="Clone/fetch missing upstream repos into the local repo cache before preflight or execution.")
    parser.add_argument("--preflight-only", action="store_true", help="Audit local model + manifest readiness without running tasks.")
    parser.add_argument("--auto-approve-commands", action="store_true")
    parser.add_argument("--no-auto-answer-decisions", action="store_true")
    parser.add_argument("--no-strict-model", action="store_true")
    parser.add_argument("--adapter-command")
    parser.add_argument("--adapter-arg", action="append", default=[])
    parser.add_argument("--task-spec", help=argparse.SUPPRESS)
    parser.add_argument("--run-config", help=argparse.SUPPRESS)
    parser.add_argument("--task-output-dir", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.task_spec and args.run_config and args.task_output_dir:
        return _run_task_worker(args.task_spec, args.run_config, args.task_output_dir)
    if not args.tasks:
        raise SystemExit("--tasks is required unless running an internal task worker.")

    output_root = Path(args.output_root).resolve() if args.output_root else default_output_root(REPO_ROOT)
    run_label = args.run_label or _build_run_label("swe-bench-lite")
    config = HarnessRunConfig(
        tasks_path=str(Path(args.tasks).resolve()),
        output_root=output_root.as_posix(),
        run_label=run_label,
        dataset_split=str(args.dataset_split or "test").strip() or "test",
        model=args.model,
        manager_model=args.manager_model,
        worker_model=args.worker_model,
        provider=args.provider,
        sandbox_mode=args.sandbox_mode,
        approval_policy=args.approval_policy,
        poll_interval_seconds=args.poll_interval_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        idle_timeout_seconds=args.idle_timeout_seconds,
        validation_timeout_seconds=args.validation_timeout_seconds,
        max_task_attempts=max(int(args.max_task_attempts or 1), 1),
        max_auto_task_starts=args.max_auto_task_starts,
        swarm_max_agents=args.swarm_max_agents,
        enable_swarm_planning=bool(args.enable_swarm_planning),
        auto_answer_pending_decisions=not args.no_auto_answer_decisions,
        auto_approve_commands=bool(args.auto_approve_commands),
        strict_model=not args.no_strict_model,
        start_index=max(int(args.start_index or 0), 0),
        max_tasks=args.max_tasks,
        task_ids=list(args.task_id or []),
        prepared_repos_root=str(Path(args.prepared_repos_root).resolve()) if args.prepared_repos_root else None,
        repo_map_path=str(Path(args.repo_map).resolve()) if args.repo_map else None,
        repo_cache_root=str(Path(args.repo_cache_root).resolve()) if args.repo_cache_root else None,
        auto_prepare_repos=bool(args.auto_prepare_repos),
        adapter_command=args.adapter_command,
        adapter_args=list(args.adapter_arg or []),
    )
    if args.preflight_only:
        return _run_preflight_only(config)
    return _run_manifest(config)


if __name__ == "__main__":
    raise SystemExit(main())
