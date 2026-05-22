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
        "If the schema includes edits, include the full updated file contents for every changed file.",
        "Never describe a file edit in prose instead of returning it in edits[].",
    ]
    lowered = model.lower()
    if any(marker in lowered for marker in WEAKER_EDIT_MODELS):
        prompt.extend(
            [
                "This model often drifts into explanations, so stay extremely literal.",
                "If report.status is done for an implementation task, edits must contain at least one changed file.",
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
    return payload if isinstance(payload, dict) else None


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
        return "You claimed a finished code change but returned no edits. Either include edits[] with full file contents or change report.status to needs_review/blocked."
    for edit in edits:
        if not isinstance(edit, dict):
            return "Every entry in edits must be an object with path and content fields."
        if not isinstance(edit.get("path"), str) or not isinstance(edit.get("content"), str):
            return "Every edit must include string path and full file content values."
    return None


def _repair_prompt(prompt: str, previous_answer: str, reason: str, attempt_number: int) -> str:
    return (
        f"Your previous answer did not satisfy the required Mission Control contract on repair attempt {attempt_number}.\n"
        f"Reason: {reason}\n"
        "Return only valid JSON matching the exact schema from the prompt.\n"
        "Rules:\n"
        "- Do not include markdown fences.\n"
        "- Do not explain the edit outside JSON.\n"
        "- If a code fix is complete, include at least one edits entry with the full updated file content.\n"
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
        f"Original prompt:\n{prompt}\n\n"
        f"Previous answer:\n{previous_answer}\n"
    )


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
