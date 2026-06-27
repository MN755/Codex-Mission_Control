from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _nested_value(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def estimate_text_tokens(text: str | None) -> int | None:
    if text is None:
        return None
    length = len(text.strip())
    if length <= 0:
        return 0
    return max(1, (length + 3) // 4)


def build_prompt_usage_estimate(prompt: str | None) -> dict[str, Any]:
    estimated_tokens = estimate_text_tokens(prompt)
    return {
        "source": "prompt_estimate",
        "estimated": True,
        "sample_count": 1,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "cached_input_tokens": None,
        "reasoning_tokens": None,
        "context_tokens": None,
        "peak_context_tokens": None,
        "context_window_tokens": None,
        "context_utilization": None,
        "peak_context_utilization": None,
        "estimated_input_tokens": estimated_tokens,
        "estimated_context_tokens": estimated_tokens,
        "prompt_char_count": len(prompt or ""),
        "raw_usage": {},
        "updated_at": utc_now_iso(),
    }


def extract_usage_payload(event: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    candidates: list[tuple[str, Any]] = [
        ("usage", event.get("usage")),
        ("usage_metadata", event.get("usage_metadata")),
        ("metrics.usage", _nested_value(event, ("metrics", "usage"))),
        ("data.usage", _nested_value(event, ("data", "usage"))),
        ("response.usage", _nested_value(event, ("response", "usage"))),
        ("turn.usage", _nested_value(event, ("turn", "usage"))),
        ("params.usage", _nested_value(event, ("params", "usage"))),
        ("params.turn.usage", _nested_value(event, ("params", "turn", "usage"))),
        ("result.usage", _nested_value(event, ("result", "usage"))),
        ("result.turn.usage", _nested_value(event, ("result", "turn", "usage"))),
        ("item.usage", _nested_value(event, ("item", "usage"))),
        ("item.result.usage", _nested_value(event, ("item", "result", "usage"))),
    ]
    for source, payload in candidates:
        if isinstance(payload, dict) and payload:
            return payload, source
    return None, None


def normalize_usage_snapshot(raw_usage: dict[str, Any], *, source: str) -> dict[str, Any]:
    input_tokens = _coerce_int(
        _first_value(
            raw_usage,
            "input_tokens",
            "inputTokens",
            "prompt_tokens",
            "promptTokens",
        )
    )
    output_tokens = _coerce_int(
        _first_value(
            raw_usage,
            "output_tokens",
            "outputTokens",
            "completion_tokens",
            "completionTokens",
        )
    )
    total_tokens = _coerce_int(_first_value(raw_usage, "total_tokens", "totalTokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    cached_input_tokens = _coerce_int(
        _first_value(
            raw_usage,
            "cached_input_tokens",
            "cachedInputTokens",
            "cache_read_input_tokens",
            "cacheReadInputTokens",
        )
    )
    if cached_input_tokens is None:
        cached_input_tokens = _coerce_int(
            _nested_value(raw_usage, ("input_token_details", "cached_tokens"))
        )
    if cached_input_tokens is None:
        cached_input_tokens = _coerce_int(
            _nested_value(raw_usage, ("input_token_details", "cache_read_tokens"))
        )
    reasoning_tokens = _coerce_int(
        _first_value(raw_usage, "reasoning_tokens", "reasoningTokens")
    )
    if reasoning_tokens is None:
        reasoning_tokens = _coerce_int(
            _nested_value(raw_usage, ("output_token_details", "reasoning_tokens"))
        )
    if reasoning_tokens is None:
        reasoning_tokens = _coerce_int(
            _nested_value(raw_usage, ("output_token_details", "reasoning"))
        )
    context_tokens = _coerce_int(
        _first_value(raw_usage, "context_tokens", "contextTokens")
    )
    if context_tokens is None:
        context_tokens = (
            _coerce_int(_nested_value(raw_usage, ("input_token_details", "total_tokens")))
            or _coerce_int(_nested_value(raw_usage, ("prompt_token_details", "total_tokens")))
            or input_tokens
        )
    context_window_tokens = _coerce_int(
        _first_value(
            raw_usage,
            "context_window_tokens",
            "contextWindowTokens",
            "max_input_tokens",
            "maxInputTokens",
            "max_prompt_tokens",
            "maxPromptTokens",
            "max_context_tokens",
            "maxContextTokens",
            "context_limit_tokens",
            "contextLimitTokens",
        )
    )
    context_utilization = None
    if context_tokens is not None and context_window_tokens and context_window_tokens > 0:
        context_utilization = round(context_tokens / context_window_tokens, 6)
    return {
        "source": source,
        "estimated": False,
        "sample_count": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_tokens": reasoning_tokens,
        "context_tokens": context_tokens,
        "peak_context_tokens": context_tokens,
        "context_window_tokens": context_window_tokens,
        "context_utilization": context_utilization,
        "peak_context_utilization": context_utilization,
        "estimated_input_tokens": None,
        "estimated_context_tokens": None,
        "prompt_char_count": None,
        "raw_usage": dict(raw_usage),
        "updated_at": utc_now_iso(),
    }


def usage_snapshot_from_event(event: dict[str, Any]) -> dict[str, Any] | None:
    raw_usage, source = extract_usage_payload(event)
    if not raw_usage or not source:
        return None
    return normalize_usage_snapshot(raw_usage, source=source)


def merge_usage_snapshots(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    if not existing:
        return dict(incoming or {})
    if not incoming:
        return dict(existing)
    merged = dict(existing)
    merged["source"] = incoming.get("source") or existing.get("source")
    merged["estimated"] = bool(incoming.get("estimated")) and not any(
        incoming.get(key) is not None
        for key in ("input_tokens", "output_tokens", "total_tokens", "context_tokens")
    )
    merged["sample_count"] = int(existing.get("sample_count") or 0) + int(incoming.get("sample_count") or 1)
    merged["updated_at"] = incoming.get("updated_at") or existing.get("updated_at") or utc_now_iso()
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "context_tokens",
        "context_window_tokens",
        "context_utilization",
        "estimated_input_tokens",
        "estimated_context_tokens",
        "prompt_char_count",
    ):
        if incoming.get(key) is not None:
            merged[key] = incoming.get(key)
    existing_peak_context = (
        _coerce_int(existing.get("peak_context_tokens"))
        or _coerce_int(existing.get("context_tokens"))
        or _coerce_int(existing.get("estimated_context_tokens"))
        or 0
    )
    incoming_peak_context = _coerce_int(incoming.get("peak_context_tokens")) or _coerce_int(incoming.get("context_tokens")) or _coerce_int(incoming.get("estimated_context_tokens")) or 0
    peak_context = max(existing_peak_context, incoming_peak_context)
    merged["peak_context_tokens"] = peak_context if peak_context > 0 else None
    existing_peak_util = _coerce_float(existing.get("peak_context_utilization")) or _coerce_float(existing.get("context_utilization")) or 0.0
    incoming_peak_util = _coerce_float(incoming.get("peak_context_utilization")) or _coerce_float(incoming.get("context_utilization")) or 0.0
    peak_util = max(existing_peak_util, incoming_peak_util)
    merged["peak_context_utilization"] = round(peak_util, 6) if peak_util > 0 else None
    if incoming.get("raw_usage"):
        merged["raw_usage"] = dict(incoming["raw_usage"])
    return merged


def empty_usage_rollup() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "context_tokens": 0,
        "estimated_input_tokens": 0,
        "estimated_context_tokens": 0,
        "peak_context_tokens": 0,
        "context_window_tokens": None,
        "peak_context_utilization": None,
        "sample_count": 0,
        "estimated_source_count": 0,
    }


def accumulate_usage_rollup(rollup: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return rollup
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "context_tokens",
        "estimated_input_tokens",
        "estimated_context_tokens",
    ):
        value = _coerce_int(snapshot.get(key))
        if value is not None:
            rollup[key] = int(rollup.get(key) or 0) + value
    sample_count = _coerce_int(snapshot.get("sample_count")) or 1
    rollup["sample_count"] = int(rollup.get("sample_count") or 0) + sample_count
    if snapshot.get("estimated"):
        rollup["estimated_source_count"] = int(rollup.get("estimated_source_count") or 0) + 1
    peak_context = _coerce_int(snapshot.get("peak_context_tokens")) or _coerce_int(snapshot.get("context_tokens")) or _coerce_int(snapshot.get("estimated_context_tokens")) or 0
    if peak_context > int(rollup.get("peak_context_tokens") or 0):
        rollup["peak_context_tokens"] = peak_context
    window_tokens = _coerce_int(snapshot.get("context_window_tokens"))
    if window_tokens is not None:
        current_window = _coerce_int(rollup.get("context_window_tokens"))
        rollup["context_window_tokens"] = max(current_window or 0, window_tokens) if current_window is not None else window_tokens
    peak_util = _coerce_float(snapshot.get("peak_context_utilization")) or _coerce_float(snapshot.get("context_utilization"))
    if peak_util is not None:
        current_peak = _coerce_float(rollup.get("peak_context_utilization")) or 0.0
        if peak_util > current_peak:
            rollup["peak_context_utilization"] = round(peak_util, 6)
    return rollup
