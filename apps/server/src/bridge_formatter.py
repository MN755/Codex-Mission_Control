from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from security.redaction import redact_text, redact_value


def _redaction_status(*, original: dict[str, Any], redacted: dict[str, Any]) -> str:
    return "redacted" if json.dumps(original, default=str, sort_keys=True) != json.dumps(redacted, default=str, sort_keys=True) else "clean"


def _make_bridge_message(
    *,
    message_id: str,
    project_id: int | None,
    orchestration_id: int | None,
    source_type: str,
    message_type: str,
    title: str,
    summary: str,
    user_action_required: bool,
    risk_level: str | None,
    options_json: list[dict[str, Any]] | None,
    machine_payload_json: dict[str, Any] | None,
    fallback_markdown: str,
    created_at: datetime,
    expires_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> dict[str, Any]:
    original = {
        "title": title,
        "summary": summary,
        "options_json": options_json,
        "machine_payload_json": machine_payload_json,
        "fallback_markdown": fallback_markdown,
    }
    redacted = {
        "title": redact_text(title),
        "summary": redact_text(summary),
        "options_json": redact_value(options_json),
        "machine_payload_json": redact_value(machine_payload_json or {}),
        "fallback_markdown": redact_text(fallback_markdown),
    }
    return {
        "id": message_id,
        "project_id": project_id,
        "orchestration_id": orchestration_id,
        "source_type": source_type,
        "message_type": message_type,
        "title": redacted["title"],
        "summary": redacted["summary"],
        "user_action_required": user_action_required,
        "risk_level": risk_level,
        "options_json": redacted["options_json"],
        "machine_payload_json": redacted["machine_payload_json"],
        "fallback_markdown": redacted["fallback_markdown"],
        "redaction_status": _redaction_status(original=original, redacted=redacted),
        "created_at": created_at,
        "expires_at": expires_at,
        "resolved_at": resolved_at,
    }


def _options_markdown(options: list[dict[str, Any]] | None) -> str:
    if not options:
        return ""
    lines = ["", "Options:"]
    for option in options:
        label = str(option.get("label") or option.get("id") or "option")
        description = str(option.get("description") or "").strip()
        lines.append(f"- `{option.get('id', label)}`: {label}{f' - {description}' if description else ''}")
    return "\n".join(lines)


def format_pending_decision_message(
    *,
    decision: dict[str, Any],
    requesting_agent: str | None = None,
) -> dict[str, Any]:
    decision_type = str(decision["decision_type"])
    options = list(decision.get("options_json") or decision.get("options") or [])
    payload = dict(decision.get("presentation_json") or decision.get("presentation") or {})
    payload.setdefault("card_type", decision_type)
    payload.setdefault("title", decision["title"])
    payload.setdefault("risk_level", decision.get("risk_level"))
    payload.setdefault("requesting_agent", requesting_agent)
    payload.setdefault("options", options)

    source_type = "manager"
    message_type = "manager_question"
    if decision_type in {"command_approval", "tool_approval", "write_permission", "snapshot_approval", "safe_mode_confirmation"}:
        source_type = "security"
        message_type = "approval_request"
    elif decision_type in {"handoff_review"}:
        source_type = "handoff"
        message_type = "handoff_ready"
    elif decision_type in {"recovery_decision"}:
        source_type = "system"
        message_type = "recovery_options"
    elif decision_type in {"swarm_approval", "scope_change_decision"}:
        source_type = "manager"
        message_type = "swarm_update" if decision_type == "swarm_approval" else "manager_question"

    reason = str(decision.get("message") or "")
    risk = str(decision.get("risk_level") or "medium")
    command = payload.get("command")
    cwd = payload.get("cwd")
    question = payload.get("question")

    body_lines = [f"## {decision['title']}", "", reason]
    if question:
        body_lines.extend(["", f"Question: {question}"])
    if command:
        body_lines.extend(["", f"Command: `{command}`"])
    if cwd:
        body_lines.extend([f"Working directory: `{cwd}`"])
    body_lines.extend(["", f"Risk: **{risk}**"])
    body_lines.append(_options_markdown(options))

    return _make_bridge_message(
        message_id=f"decision-{decision['id']}",
        project_id=decision.get("project_id"),
        orchestration_id=decision.get("orchestration_id"),
        source_type=source_type,
        message_type=message_type,
        title=str(decision["title"]),
        summary=reason[:220] if reason else str(decision["title"]),
        user_action_required=decision.get("status") == "pending",
        risk_level=decision.get("risk_level"),
        options_json=options,
        machine_payload_json={
            "decision_id": decision["id"],
            "decision_type": decision_type,
            **payload,
        },
        fallback_markdown="\n".join(line for line in body_lines if line is not None),
        created_at=decision["created_at"],
        expires_at=decision.get("expires_at"),
        resolved_at=decision.get("answered_at") or decision.get("resolved_at"),
    )


def format_status_summary_message(
    *,
    message_id: str,
    project_id: int,
    orchestration_id: int | None,
    title: str,
    summary: str,
    project_name: str,
    manager_status: str,
    mode: str,
    swarm: str,
    user_action_needed: str,
    current_work: list[str],
    waiting_on_you: list[str],
    next_expected_step: str,
    risk_level: str | None,
    created_at: datetime,
) -> dict[str, Any]:
    lines = [
        "## Mission Control Status",
        "",
        f"**Project:** {project_name}",
        f"**Manager:** {manager_status}",
        f"**Mode:** {mode}",
        f"**Swarm:** {swarm}",
        f"**User action needed:** {user_action_needed}",
        "",
        "### Current work",
    ]
    lines.extend([f"- {item}" for item in current_work] if current_work else ["- No active work is recorded right now."])
    lines.extend(["", "### Waiting on you"])
    lines.extend([f"- {item}" for item in waiting_on_you] if waiting_on_you else ["- Nothing pending from the user right now."])
    lines.extend(["", "### Next expected step", next_expected_step])
    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=orchestration_id,
        source_type="manager",
        message_type="blocked" if waiting_on_you else "status_update",
        title=title,
        summary=summary,
        user_action_required=bool(waiting_on_you),
        risk_level=risk_level,
        options_json=None,
        machine_payload_json={
            "project_name": project_name,
            "manager_status": manager_status,
            "mode": mode,
            "swarm": swarm,
            "current_work": current_work,
            "waiting_on_you": waiting_on_you,
            "next_expected_step": next_expected_step,
        },
        fallback_markdown="\n".join(lines),
        created_at=created_at,
    )


def format_event_digest_message(
    *,
    message_id: str,
    project_id: int,
    orchestration_id: int | None,
    title: str,
    summary: str,
    grouped_items: dict[str, list[str]],
    created_at: datetime,
) -> dict[str, Any]:
    lines = [f"## {title}", ""]
    if not any(grouped_items.values()):
        lines.append("No significant orchestration events were recorded in this window.")
    else:
        for category, items in grouped_items.items():
            if not items:
                continue
            lines.extend([f"### {category}", *(f"- {item}" for item in items), ""])
    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=orchestration_id,
        source_type="system",
        message_type="event_digest",
        title=title,
        summary=summary,
        user_action_required=False,
        risk_level=None,
        options_json=None,
        machine_payload_json={"groups": grouped_items},
        fallback_markdown="\n".join(lines).strip(),
        created_at=created_at,
    )


def format_handoff_message(
    *,
    message_id: str,
    project_id: int,
    orchestration_id: int | None,
    handoff_status: str,
    confidence_level: str,
    evidence_level: str,
    what_changed: list[str],
    how_to_run: list[str],
    validation_items: list[str],
    known_limitations: list[str],
    next_tasks: list[str],
    important_files: list[str],
    dry_run: bool,
    created_at: datetime,
) -> dict[str, Any]:
    title = "Mission Control handoff ready" if handoff_status in {"ready", "needs_review"} else "Mission Control handoff status"
    status_label = f"{handoff_status}{' (dry-run)' if dry_run else ''}"
    lines = [
        f"## {title}",
        "",
        f"**Status:** {status_label}",
        f"**Confidence / evidence:** {confidence_level} / {evidence_level}",
        "",
        "### What changed",
    ]
    lines.extend([f"- {item}" for item in what_changed] if what_changed else ["- No detailed change list was recorded."])
    lines.extend(["", "### How to run"])
    lines.extend([f"- {item}" for item in how_to_run] if how_to_run else ["- No run instructions were recorded."])
    lines.extend(["", "### Validation / evidence"])
    lines.extend([f"- {item}" for item in validation_items] if validation_items else ["- Validation not run."])
    lines.extend(["", "### Known limitations"])
    lines.extend([f"- {item}" for item in known_limitations] if known_limitations else ["- No limitations were recorded."])
    lines.extend(["", "### Next recommended tasks"])
    lines.extend([f"- {item}" for item in next_tasks] if next_tasks else ["- No explicit follow-up tasks were recorded."])
    lines.extend(["", "### Important files / artifacts"])
    lines.extend([f"- {item}" for item in important_files] if important_files else ["- No artifact paths were recorded."])
    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=orchestration_id,
        source_type="handoff",
        message_type="handoff_ready" if handoff_status in {"ready", "needs_review"} else "warning",
        title=title,
        summary=f"Handoff status: {handoff_status}. Evidence level: {evidence_level}.",
        user_action_required=handoff_status == "needs_review",
        risk_level="medium" if handoff_status == "needs_review" else None,
        options_json=None,
        machine_payload_json={
            "status": handoff_status,
            "confidence_level": confidence_level,
            "evidence_level": evidence_level,
            "what_changed": what_changed,
            "how_to_run": how_to_run,
            "validation_items": validation_items,
            "known_limitations": known_limitations,
            "next_tasks": next_tasks,
            "important_files": important_files,
            "dry_run": dry_run,
        },
        fallback_markdown="\n".join(lines),
        created_at=created_at,
    )


def format_diagnostic_message(
    *,
    message_id: str,
    title: str,
    summary: str,
    markdown: str,
    machine_payload_json: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    return _make_bridge_message(
        message_id=message_id,
        project_id=None,
        orchestration_id=None,
        source_type="diagnostics",
        message_type="diagnostic_summary",
        title=title,
        summary=summary,
        user_action_required=False,
        risk_level=None,
        options_json=None,
        machine_payload_json=machine_payload_json,
        fallback_markdown=markdown,
        created_at=created_at,
    )


def format_safe_mode_message(
    *,
    message_id: str,
    project_id: int,
    enabled: bool,
    details: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    title = "Safe mode enabled" if enabled else "Safe mode status"
    lines = [
        f"## {title}",
        "",
        "Mission Control is using stricter bridge-safe controls for this project.",
        "",
        f"- Require all command approvals: {'yes' if details.get('require_all_command_approvals') else 'no'}",
        f"- Destructive actions blocked: {'yes' if details.get('destructive_actions_blocked') else 'no'}",
        f"- Deployment tools blocked: {'yes' if details.get('deployment_tools_blocked') else 'no'}",
        f"- External account tools require approval: {'yes' if details.get('external_account_tools_require_approval') else 'no'}",
        f"- Dynamic spawning paused: {'yes' if details.get('dynamic_spawning_paused') else 'no'}",
        f"- Imported codebases require read-only scan: {'yes' if details.get('require_read_only_scan_for_imported_codebases') else 'no'}",
    ]
    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=None,
        source_type="security",
        message_type="safe_mode_update",
        title=title,
        summary="Safe mode enabled." if enabled else "Safe mode status fetched.",
        user_action_required=False,
        risk_level="medium" if enabled else None,
        options_json=None,
        machine_payload_json=details,
        fallback_markdown="\n".join(lines),
        created_at=created_at,
    )
