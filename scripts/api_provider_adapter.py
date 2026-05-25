from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


DEFAULT_MODELS = {
    "openai_api": "gpt-4o-mini",
    "anthropic_api": "claude-3-5-sonnet-latest",
    "xai_api": "grok-code-fast-1",
}

DEFAULT_ENDPOINTS = {
    "openai_api": "https://api.openai.com/v1/chat/completions",
    "anthropic_api": "https://api.anthropic.com/v1/messages",
    "xai_api": "https://api.x.ai/v1/chat/completions",
}


def _provider() -> str:
    return (os.environ.get("MISSION_CONTROL_PROVIDER") or "openai_api").strip().lower()


def _model() -> str:
    provider = _provider()
    requested = (os.environ.get("MISSION_CONTROL_MODEL") or "").strip()
    return requested or DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def _endpoint() -> str:
    provider = _provider()
    explicit = (os.environ.get("MISSION_CONTROL_PROVIDER_ENDPOINT") or "").strip()
    if not explicit:
        return DEFAULT_ENDPOINTS[provider]
    normalized = explicit.rstrip("/")
    if provider == "anthropic_api" and not normalized.endswith("/v1/messages"):
        return f"{normalized}/messages" if normalized.endswith("/v1") else f"{normalized}/v1/messages"
    if provider != "anthropic_api" and "/chat/completions" not in normalized:
        return f"{normalized}/chat/completions" if normalized.endswith("/v1") else f"{normalized}/v1/chat/completions"
    return normalized


def _api_key() -> tuple[str, str]:
    provider = _provider()
    key_name = {
        "openai_api": "OPENAI_API_KEY",
        "anthropic_api": "ANTHROPIC_API_KEY",
        "xai_api": "XAI_API_KEY",
    }[provider]
    key_value = (os.environ.get(key_name) or "").strip()
    if not key_value:
        raise RuntimeError(f"{key_name} is not configured.")
    return key_name, key_value


def _request_json(url: str, *, headers: dict[str, str], payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8", errors="ignore")
    loaded = json.loads(body)
    if not isinstance(loaded, dict):
        raise RuntimeError("Provider returned a non-object JSON payload.")
    return loaded


def _system_prompt() -> str:
    return (
        "You are an adapter for Mission Control. Follow the prompt exactly. "
        "If the prompt asks for JSON or provides a schema, return only valid JSON with no preamble. "
        "Never replace required JSON with prose. If you cannot safely complete the task, return JSON that says so."
    )


def _extract_openai_text(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [str(item.get("text") or "").strip() for item in content if isinstance(item, dict)]
        return "\n".join(part for part in text_parts if part).strip()
    return ""


def _extract_anthropic_text(payload: dict) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    text_parts = [str(item.get("text") or "").strip() for item in content if isinstance(item, dict)]
    return "\n".join(part for part in text_parts if part).strip()


def _generate(prompt: str) -> str:
    provider = _provider()
    _key_name, api_key = _api_key()
    url = _endpoint()
    if provider == "anthropic_api":
        payload = {
            "model": _model(),
            "max_tokens": 4096,
            "system": _system_prompt(),
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        response = _request_json(url, headers=headers, payload=payload)
        return _extract_anthropic_text(response)
    payload = {
        "model": _model(),
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    response = _request_json(url, headers=headers, payload=payload)
    return _extract_openai_text(response)


def _parse_json_object(text: str) -> dict | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except Exception:
        cleaned = stripped.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            payload = json.loads(re.sub(r",(\s*[}\]])", r"\1", match.group(0)))
        except Exception:
            return None
    return payload if isinstance(payload, dict) else None


def _repair_reason(prompt: str, text: str) -> str | None:
    payload = _parse_json_object(text)
    if payload is None:
        return "Return only valid JSON matching the requested schema."
    if '"edits"' not in prompt:
        return None
    report = payload.get("report")
    edits = payload.get("edits")
    if not isinstance(report, dict):
        return "Return a top-level report object."
    if not isinstance(edits, list):
        return "Return edits as a JSON array."
    return None


def _repair_prompt(prompt: str, previous_answer: str, reason: str, attempt_number: int) -> str:
    return (
        f"Your previous answer failed Mission Control schema validation on repair attempt {attempt_number}.\n"
        f"Reason: {reason}\n"
        "Return only valid JSON matching the exact schema from the prompt. "
        "Do not include markdown fences or any prose outside the JSON object.\n\n"
        f"Original prompt:\n{prompt}\n\n"
        f"Previous answer:\n{previous_answer}\n"
    )


def main() -> int:
    prompt = sys.stdin.read()
    if not prompt.strip():
        print(json.dumps({"result": ""}))
        return 0
    try:
        text = _generate(prompt)
        unresolved_reason: str | None = None
        for attempt in range(1, 4):
            unresolved_reason = _repair_reason(prompt, text)
            if unresolved_reason is None:
                break
            text = _generate(_repair_prompt(prompt, text, unresolved_reason, attempt))
        if unresolved_reason is not None:
            raise RuntimeError(unresolved_reason)
        print(json.dumps({"result": text}))
        return 0
    except (RuntimeError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"result": "", "error": f"{type(exc).__name__}: {exc}"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
