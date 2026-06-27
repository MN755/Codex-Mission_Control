from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVIDENCE_CATEGORY_RULES: dict[str, dict[str, tuple[str, ...] | set[str]]] = {
    "logs": {
        "tokens": ("log", "console", "stdout", "stderr"),
        "extensions": set(),
    },
    "screenshots": {
        "tokens": ("screenshot", "screen", "frame", "snapshot"),
        "extensions": {".png", ".jpg", ".jpeg"},
    },
    "traces": {
        "tokens": ("trace", "playwright", "timeline"),
        "extensions": {".zip", ".trace"},
    },
    "crashes": {
        "tokens": ("crash", "dump", "stacktrace", "exception"),
        "extensions": {".dmp", ".crash"},
    },
    "coverage": {
        "tokens": ("coverage", "lcov", "jacoco", "xcresult"),
        "extensions": set(),
    },
    "performance": {
        "tokens": ("perf", "benchmark", "latency", "throughput", "fps", "profile"),
        "extensions": set(),
    },
}


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _dedupe_strings(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def classify_evidence_artifacts(signal_sources: list[str], *, limit_per_category: int = 10) -> dict[str, Any]:
    deduped_sources = _dedupe_strings(signal_sources)
    categories: dict[str, list[str]] = {}
    for category, rule in EVIDENCE_CATEGORY_RULES.items():
        tokens = tuple(str(item) for item in rule.get("tokens", ()))
        extensions = {str(item) for item in rule.get("extensions", set())}
        matched = [
            path
            for path in deduped_sources
            if any(token in path.lower() for token in tokens) or Path(path).suffix.lower() in extensions
        ]
        categories[category] = _dedupe_strings(matched)[:limit_per_category]
    return {
        "categories": categories,
        "categories_present": [category for category, paths in categories.items() if paths],
        "all_evidence_paths": _dedupe_strings([path for paths in categories.values() for path in paths]),
    }


def build_normalized_result_rollup(
    *,
    summaries: list[dict[str, Any]],
    blocking_statuses: list[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_blocking_statuses = sorted({str(item).strip() for item in blocking_statuses if str(item).strip()})
    return {
        **dict(metadata or {}),
        "summary_count": len(summaries),
        "passed_count": len([summary for summary in summaries if str(summary.get("status") or "") == "passed"]),
        "failed_count": len([summary for summary in summaries if str(summary.get("status") or "") == "failed"]),
        "missing_count": len([summary for summary in summaries if str(summary.get("status") or "") == "missing"]),
        "parse_error_count": len([summary for summary in summaries if str(summary.get("status") or "") == "parse_error"]),
        "warning_count": sum(_coerce_int(summary.get("warning_count")) for summary in summaries),
        "publish_ready": not any(str(summary.get("status") or "") in normalized_blocking_statuses for summary in summaries),
        "blocking_statuses": normalized_blocking_statuses,
        "blocking_summary_ids": [
            str(summary.get("output_artifact") or summary.get("source_path") or "")
            for summary in summaries
            if str(summary.get("status") or "") in normalized_blocking_statuses
        ],
        "summaries": summaries,
    }


def write_normalized_result_rollup(workspace_root: Path, rollup_artifact: str, rollup: dict[str, Any]) -> Path:
    rollup_path = _resolve_workspace_artifact_path(workspace_root, rollup_artifact)
    rollup_path.parent.mkdir(parents=True, exist_ok=True)
    rollup_path.write_text(json.dumps(rollup, indent=2), encoding="utf-8")
    return rollup_path


def load_normalized_result_rollup(workspace_root: Path, rollup_artifact: str) -> dict[str, Any] | None:
    rollup_path = _resolve_workspace_artifact_path(workspace_root, rollup_artifact)
    if not rollup_path.exists() or not rollup_path.is_file():
        return None
    try:
        payload = json.loads(rollup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def load_normalized_result_rollup_summary(workspace_root: Path, rollup_artifact: str) -> dict[str, Any]:
    rollup_path = _resolve_workspace_artifact_path(workspace_root, rollup_artifact)
    if not rollup_path.exists() or not rollup_path.is_file():
        return {
            "normalized_results_summary_path": None,
            "normalized_summary_count": 0,
            "normalized_passed_count": 0,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": False,
        }
    try:
        payload = json.loads(rollup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "normalized_results_summary_path": rollup_path.relative_to(workspace_root).as_posix(),
            "normalized_summary_count": 0,
            "normalized_passed_count": 0,
            "normalized_failed_count": 0,
            "normalized_missing_count": 0,
            "normalized_publish_ready": False,
        }
    return {
        "normalized_results_summary_path": rollup_path.relative_to(workspace_root).as_posix(),
        "normalized_summary_count": _coerce_int(payload.get("summary_count")),
        "normalized_passed_count": _coerce_int(payload.get("passed_count")),
        "normalized_failed_count": _coerce_int(payload.get("failed_count")),
        "normalized_missing_count": _coerce_int(payload.get("missing_count")),
        "normalized_publish_ready": bool(payload.get("publish_ready")),
    }


def _resolve_workspace_artifact_path(workspace_root: Path, relative_path: str) -> Path:
    normalized = str(relative_path or "").strip().replace("\\", "/")
    if not normalized:
        return workspace_root
    return workspace_root / Path(normalized)
