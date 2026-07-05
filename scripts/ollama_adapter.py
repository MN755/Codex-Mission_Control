from __future__ import annotations

import json
import os
import re
import sys
import urllib.request


DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
MODEL_PREFERENCE_ORDER = [
    "gpt-oss:20b",
    "codestral",
    "qwen2.5-coder:14b",
    "qwen2.5-coder:7b",
    "deepseek-coder-v2",
    "deepseek-coder",
    "codellama:13b",
    "codellama",
    "deepseek-r1:8b",
    "deepseek-r1:latest",
    "gemma3:12b",
    "qwen2.5:14b",
    "llama3:latest",
    "gemma3:latest",
    "qwen2.5:7b",
]
WEAKER_EDIT_MODELS = ("qwen2.5:7b", "llama3", "gemma3", "deepseek-r1")


def _base_url() -> str:
    return (os.environ.get("MISSION_CONTROL_OLLAMA_ENDPOINT") or DEFAULT_BASE_URL).rstrip("/")


def _request_json(path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{_base_url()}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _strict_requested_model() -> bool:
    return str(os.environ.get("MISSION_CONTROL_STRICT_MODEL") or "").strip().lower() in {"1", "true", "yes", "on"}


def _list_models() -> list[str]:
    try:
        payload = _request_json("/api/tags")
    except Exception:  # noqa: BLE001
        return []
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    return [str(item.get("name") or "").strip() for item in models if str(item.get("name") or "").strip()]


def _model_preference_score(model_name: str) -> tuple[int, int]:
    lowered = model_name.lower()
    for index, preferred in enumerate(MODEL_PREFERENCE_ORDER):
        if preferred in lowered:
            return (1000 - index, len(lowered))
    if "coder" in lowered or "code" in lowered:
        return (700, len(lowered))
    if "gpt-oss" in lowered:
        return (690, len(lowered))
    if "deepseek" in lowered or "qwen" in lowered or "llama" in lowered or "gemma" in lowered:
        return (500, len(lowered))
    return (0, len(lowered))


def _select_model(requested_model: str | None) -> str:
    requested = (requested_model or "").strip()
    if _strict_requested_model() and requested:
        return requested
    available = _list_models()
    if not available:
        return requested or DEFAULT_MODEL
    if requested and requested != DEFAULT_MODEL:
        return requested
    strongest = max(available, key=_model_preference_score)
    if requested == DEFAULT_MODEL and _model_preference_score(strongest) <= _model_preference_score(DEFAULT_MODEL):
        return DEFAULT_MODEL
    return strongest or requested or DEFAULT_MODEL


def _candidate_models(requested_model: str | None) -> list[str]:
    requested = (requested_model or "").strip()
    if _strict_requested_model() and requested:
        return [requested]
    available = _list_models()
    if not available:
        return [requested or DEFAULT_MODEL]
    ranked = [name for name, _score in sorted(((name, _model_preference_score(name)) for name in available), key=lambda item: item[1], reverse=True)]
    candidates: list[str] = []
    preferred = _select_model(requested_model)
    for name in [preferred, requested, DEFAULT_MODEL, *ranked]:
        normalized = (name or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _adapter_system_prompt(model: str) -> str:
    prompt = [
        "You are an adapter for Mission Control. Follow the prompt exactly.",
        "If the prompt asks for JSON or provides a schema, return only valid JSON with no preamble.",
        "If the schema includes edits, return either full updated file contents or an exact search/replace patch for every changed file.",
        "Never describe a file edit in prose instead of returning it in edits[].",
    ]
    lowered = model.lower()
    if any(marker in lowered for marker in WEAKER_EDIT_MODELS):
        prompt.extend(
            [
                "This model often drifts into explanations, so stay extremely literal.",
                "If report.status is done for an implementation task, edits must contain at least one changed file.",
                "For large existing files, prefer an exact search/replace edit over inventing a full file rewrite.",
                "If the search text from a previous attempt is not present in the current workspace snippet, do not repeat that stale search/replace patch.",
                "If the workspace already appears to contain your earlier change, do not propose the same edit again; inspect the current failure evidence and adjust the patch.",
                "Never rewrite a large framework file from scratch for a narrow bugfix unless the prompt includes the complete file and your replacement is exact.",
                "If you cannot produce a safe file edit, set report.status to needs_review or blocked and return edits as [].",
            ]
        )
    return " ".join(prompt)


def _generate(model: str, prompt: str) -> str:
    payload = {
        "model": model,
        "stream": False,
        "prompt": (
            f"{_adapter_system_prompt(model)}\n\n"
            f"{prompt}"
        ),
    }
    try:
        body = _request_json("/api/generate", payload)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"{type(exc).__name__}: {exc}") from exc

    return str(body.get("response") or "").strip()


def _parse_json_object(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except Exception:  # noqa: BLE001
        cleaned = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        candidate = match.group(0) if match else cleaned
        candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
        try:
            payload = json.loads(candidate)
        except Exception:  # noqa: BLE001
            return None
    if not isinstance(payload, dict):
        return None
    return _normalize_payload_contract(payload)


def _first_string(mapping: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _normalize_edit_entry(edit: object, report_files_changed: list[str]) -> dict | None:
    if not isinstance(edit, dict):
        return None
    normalized = dict(edit)
    path = _first_string(normalized, ("path", "file", "filepath", "filename"))
    if not path and len(report_files_changed) == 1:
        path = report_files_changed[0]
    content = _first_string(
        normalized,
        ("content", "full_content", "updated_content", "new_content", "file_content", "text"),
    )
    search = _first_string(
        normalized,
        ("search", "find", "old", "before", "original", "old_text"),
    )
    replace = _first_string(
        normalized,
        ("replace", "replacement", "new", "after", "updated", "new_text"),
    )
    if path:
        normalized["path"] = path
    if content is not None:
        normalized["content"] = content
    if search is not None:
        normalized["search"] = search
    if replace is not None:
        normalized["replace"] = replace
    return normalized


def _normalize_payload_contract(payload: dict) -> dict:
    normalized = dict(payload)
    report = normalized.get("report")
    if not isinstance(report, dict):
        return normalized
    files_changed = [
        str(item).strip()
        for item in list(report.get("files_changed") or [])
        if str(item).strip()
    ]
    edits = normalized.get("edits")
    if not isinstance(edits, list):
        return normalized
    normalized["edits"] = [
        candidate
        for candidate in (_normalize_edit_entry(edit, files_changed) for edit in edits)
        if candidate is not None
    ]
    return normalized


def _editing_expected(prompt: str) -> bool | None:
    match = re.search(r"Editing expected for this task:\s*(yes|no)", prompt, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip().lower() == "yes"


def _report_claims_code_change(report: dict) -> bool:
    combined = " ".join(
        str(report.get(key) or "")
        for key in ("summary", "recommended_next_task")
    ).lower()
    phrases = (
        "fixed",
        "fix",
        "corrected",
        "correctly add",
        "updated",
        "implemented",
        "changed",
        "modified",
        "patched",
    )
    return any(phrase in combined for phrase in phrases)


def _edit_has_supported_payload(edit: dict) -> bool:
    if not isinstance(edit.get("path"), str):
        return False
    if isinstance(edit.get("content"), str):
        return True
    return isinstance(edit.get("search"), str) and bool(edit.get("search")) and isinstance(edit.get("replace"), str)


def _contains_placeholder_edit_content(content: str) -> bool:
    lowered = content.lower()
    placeholder_phrases = (
        "full updated file contents go here",
        "updated file contents go here",
        "rest of the file content",
        "rest of file",
        "remaining code",
        "unchanged code",
        "existing code",
        "other code omitted",
        "code omitted",
        "other settings",
    )
    if any(phrase in lowered for phrase in placeholder_phrases):
        return True
    if "..." in content and any(
        token in lowered for token in ("omitted", "placeholder", "rest of file", "remaining code", "unchanged code")
    ):
        return True
    return bool(re.search(r"(?m)^\s*(?:#|//|/\*)?\s*\.\.\.\s*(?:\*/)?\s*$", content))


def _repair_reason(prompt: str, text: str) -> str | None:
    if '"edits"' not in prompt:
        payload = _parse_json_object(text)
        return None if payload is not None else "Return only valid JSON matching the requested schema."
    payload = _parse_json_object(text)
    if payload is None:
        return "Return only valid JSON with both report and edits keys."
    report = payload.get("report")
    edits = payload.get("edits")
    if not isinstance(report, dict):
        return "Return a top-level report object matching the required schema."
    if not isinstance(edits, list):
        return "Return edits as a JSON array, even if it is empty."
    status = str(report.get("status") or "").strip().lower()
    editing_expected = _editing_expected(prompt)
    files_changed = report.get("files_changed")
    if not isinstance(files_changed, list):
        files_changed = []
    claimed_change = _report_claims_code_change(report) or bool(files_changed)
    if editing_expected is False:
        if edits:
            return "This task was marked as non-editing, so edits must be an empty array."
        if files_changed:
            return "This task was marked as non-editing, so files_changed must be empty."
        if status == "done" and _report_claims_code_change(report):
            return "This task was marked as non-editing, so do not claim to have changed code."
    if status == "done" and claimed_change and not edits:
        return "You claimed a finished code change but returned no edits. Either include edits[] with full file contents or exact search/replace patches, or change report.status to needs_review/blocked."
    for edit in edits:
        if not isinstance(edit, dict):
            return "Every entry in edits must be an object with path plus either content or search/replace fields."
        if not _edit_has_supported_payload(edit):
            return "Every edit must include a string path and either full file content or exact search/replace values."
        content = edit.get("content")
        if isinstance(content, str) and _contains_placeholder_edit_content(content):
            return (
                "Do not use placeholders, ellipses, or omitted-code summaries inside full-file edits. "
                "Return the exact final file contents or an exact search/replace patch."
            )
        replace = edit.get("replace")
        if isinstance(replace, str) and _contains_placeholder_edit_content(replace):
            return (
                "Do not use placeholders, ellipses, or omitted-code summaries inside replacement text. "
                "Return the exact replacement block copied from the current workspace context."
            )
    return None


def _repair_prompt(prompt: str, previous_answer: str, reason: str, attempt_number: int) -> str:
    return (
        f"Your previous answer did not satisfy the required Mission Control contract on repair attempt {attempt_number}.\n"
        f"Reason: {reason}\n"
        "Return only valid JSON matching the exact schema from the prompt.\n"
        "Rules:\n"
        "- Do not include markdown fences.\n"
        "- Do not explain the edit outside JSON.\n"
        "- If a code fix is complete, include at least one edits entry with either the full updated file content or an exact search/replace patch.\n"
        "- Prefer exact search/replace edits for large existing files instead of rewriting the whole file.\n"
        "- Do not use placeholders, ellipses, or omitted-code summaries inside edits.\n"
        "- If the current workspace no longer contains your previous search text, reread the prompt snapshot and produce a fresh exact patch instead of repeating the stale one.\n"
        "- If you cannot make a safe edit, set report.status to needs_review or blocked and return edits as [].\n\n"
        "Example valid answer:\n"
        '{\n'
        '  "report": {\n'
        '    "agent": "Service Flow Builder",\n'
        '    "task_id": "2",\n'
        '    "status": "done",\n'
        '    "summary": "Fixed the add function and kept the change scoped.",\n'
        '    "files_changed": ["src/math_utils.py"],\n'
        '    "tests_run": ["pytest tests/test_math_utils.py"],\n'
        '    "blockers": [],\n'
        '    "risks": [],\n'
        '    "recommended_next_task": "Re-run focused validation."\n'
        '  },\n'
        '  "edits": [\n'
        '    {\n'
        '      "path": "src/math_utils.py",\n'
        '      "content": "def add(a, b):\\n    return a + b\\n"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "Another valid answer for a targeted patch in a large file:\n"
        '{\n'
        '  "report": {\n'
        '    "agent": "Service Flow Builder",\n'
        '    "task_id": "2",\n'
        '    "status": "done",\n'
        '    "summary": "Adjusted the ordering logic with a surgical patch.",\n'
        '    "files_changed": ["django/db/models/sql/compiler.py"],\n'
        '    "tests_run": [],\n'
        '    "blockers": [],\n'
        '    "risks": [],\n'
        '    "recommended_next_task": "Re-run focused validation."\n'
        '  },\n'
        '  "edits": [\n'
        '    {\n'
        '      "path": "django/db/models/sql/compiler.py",\n'
        '      "search": "without_ordering = self.ordering_parts.search(sql).group(1)",\n'
        '      "replace": "sql_oneline = \' \'.join(sql.split(\'\\\\n\'))\\nwithout_ordering = self.ordering_parts.search(sql_oneline).group(1)"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        f"Original prompt:\n{prompt}\n\n"
        f"Previous answer:\n{previous_answer}\n"
    )


def _coerce_non_editing_contract_violation(prompt: str, text: str, reason: str) -> dict | None:
    if _editing_expected(prompt) is not False:
        return None
    payload = _parse_json_object(text)
    if not isinstance(payload, dict):
        return None
    report = payload.get("report")
    if not isinstance(report, dict):
        return None
    normalized_report = dict(report)
    original_summary = str(normalized_report.get("summary") or "").strip()
    tests_run = [str(item) for item in list(normalized_report.get("tests_run") or []) if str(item).strip()]
    blockers = [str(item) for item in list(normalized_report.get("blockers") or []) if str(item).strip()]
    risks = [str(item) for item in list(normalized_report.get("risks") or []) if str(item).strip()]
    if reason not in blockers:
        blockers.append(reason)
    if tests_run:
        normalized_report["status"] = "done"
        normalized_report["summary"] = (
            "Captured non-editing task evidence and ignored a stray code-change claim from the model."
        )
        if original_summary:
            risks.append(f"Original model summary before coercion: {original_summary}")
    else:
        normalized_report["status"] = "blocked"
        normalized_report["summary"] = (
            "Mission Control rejected a non-editing response that claimed code changes without durable command evidence."
        )
    normalized_report["files_changed"] = []
    normalized_report["blockers"] = blockers
    normalized_report["risks"] = risks
    coerced = dict(payload)
    coerced["report"] = normalized_report
    coerced["edits"] = []
    return coerced


def main() -> int:
    prompt = sys.stdin.read()
    if not prompt.strip():
        print(json.dumps({"result": ""}))
        return 0

    last_error: RuntimeError | None = None
    text = ""
    for model in _candidate_models(os.environ.get("MISSION_CONTROL_MODEL")):
        try:
            text = _generate(model, prompt)
            unresolved_reason: str | None = None
            for attempt in range(1, 4):
                unresolved_reason = _repair_reason(prompt, text)
                if unresolved_reason is None:
                    break
                text = _generate(model, _repair_prompt(prompt, text, unresolved_reason, attempt))
            if unresolved_reason is not None:
                coerced = _coerce_non_editing_contract_violation(prompt, text, unresolved_reason)
                if coerced is not None:
                    text = json.dumps(coerced)
                    last_error = None
                    break
                last_error = RuntimeError(f"Schema repair failed for model {model}: {unresolved_reason}")
                continue
            last_error = None
            break
        except RuntimeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        print(json.dumps({"result": "", "error": str(last_error)}))
        return 1

    print(json.dumps({"result": text}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
