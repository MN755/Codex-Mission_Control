from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from chat_markdown import bullet_lines, compact_reason, compact_text, join_markdown, option_lines, section
from diagnostic_formatter import build_diagnostic_summary_markdown
from event_digest_formatter import build_event_digest_markdown
from handoff_formatter import build_handoff_markdown
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


def _decision_header_lines(
    *,
    decision_type: str,
    risk: str,
    reason: str,
    payload: dict[str, Any],
    requesting_agent: str | None,
) -> list[str]:
    lines = [f"**Risk / impact:** {risk}"]
    if requesting_agent:
        lines.append(f"**Requesting agent:** {requesting_agent}")
    if decision_type == "command_approval":
        command = compact_text(str(payload.get("command") or ""), fallback="No command was recorded.")
        cwd = compact_text(str(payload.get("cwd") or ""), fallback="No working directory was recorded.")
        scope = payload.get("scope") or []
        lines.extend(
            [
                f"**Command:** `{command}`",
                f"**Working directory:** `{cwd}`",
            ]
        )
        if scope:
            lines.append(f"**Scope:** {', '.join(str(item) for item in scope if str(item).strip())}")
        lines.append(f"**Reason:** {compact_reason(reason, max_sentences=2) or 'No short reason was recorded.'}")
    elif decision_type == "tool_approval":
        tool_name = compact_text(str(payload.get('tool_name') or payload.get('requested_access') or ""), fallback="Unknown tool")
        scope = payload.get("scope") or []
        lines.append(f"**Tool:** {tool_name}")
        if scope:
            lines.append(f"**Scope:** {', '.join(str(item) for item in scope if str(item).strip())}")
        lines.append(f"**Reason:** {compact_reason(reason, max_sentences=2) or 'No short reason was recorded.'}")
    elif decision_type == "manager_question":
        lines.append(f"**Question:** {compact_text(str(payload.get('question') or reason), fallback='No question text was recorded.')}")
        lines.append(f"**Impact:** {compact_text(str(payload.get('impact') or risk), fallback='medium')}")
        auto_decide_at = payload.get("auto_decide_at")
        if auto_decide_at:
            lines.append(f"**Auto-decide:** {auto_decide_at}")
    elif decision_type == "handoff_review":
        lines.append(f"**Review request:** {compact_text(reason, fallback='Mission Control needs a handoff decision.')}")
    elif decision_type == "recovery_decision":
        lines.append(f"**Recovery reason:** {compact_text(reason, fallback='Mission Control proposed recovery options.')}")
    elif decision_type == "write_permission":
        lines.append(f"**Write scope:** {compact_text(str(payload.get('scope') or reason), fallback='Mission Control needs write permission details.')}")
    elif decision_type == "swarm_approval":
        lines.append(f"**Swarm change:** {compact_text(reason, fallback='Mission Control wants to change swarm strategy.')}")
    elif decision_type == "subagent_burst_approval":
        lines.append(f"**Purpose:** {compact_text(str(payload.get('purpose') or reason), fallback='Mission Control proposed a bounded subagent burst.')}")
        lines.append(f"**Subagents:** {compact_text(str(payload.get('subagent_count') or 0), fallback='0')}")
        lines.append(f"**Estimated intensity:** {compact_text(str(payload.get('estimated_intensity') or 'medium'), fallback='medium')}")
        lines.append(f"**Reason:** {compact_reason(reason, max_sentences=2) or 'Mission Control believes the work is parallelizable.'}")
    elif decision_type == "snapshot_approval":
        lines.append(f"**Snapshot request:** {compact_text(reason, fallback='Mission Control wants snapshot approval.')}")
    else:
        lines.append(f"**Reason:** {compact_text(reason, fallback='Mission Control needs a decision.')}")
    return [line for line in lines if line]


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
    payload.setdefault("recommended_option", decision.get("recommended_option"))

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
    elif decision_type in {"swarm_approval"}:
        source_type = "manager"
        message_type = "swarm_update"
    elif decision_type == "subagent_burst_approval":
        source_type = "manager"
        message_type = "subagent_burst_recommendation"

    reason = compact_text(str(decision.get("message") or ""), fallback=str(decision["title"]))
    risk = compact_text(str(decision.get("risk_level") or "medium"), fallback="medium")
    if decision_type == "subagent_burst_approval":
        subagents = [str(item) for item in list(payload.get("subagents") or []) if str(item).strip()]
        lines = [
            "## Mission Control recommends a Codex subagent burst",
            "",
            f"**Purpose:** {compact_text(str(payload.get('purpose') or reason), fallback='Read-only burst')}",
            f"**Subagents:** {compact_text(str(payload.get('subagent_count') or len(subagents)), fallback=str(len(subagents)))}",
            f"**Risk:** {risk.title()}",
            f"**Estimated intensity:** {compact_text(str(payload.get('estimated_intensity') or 'medium'), fallback='medium').title()}",
            "",
            "### Why",
            compact_reason(reason, max_sentences=3) or "Mission Control believes the work can be explored in parallel.",
            "",
            "### Proposed subagents",
        ]
        lines.extend(bullet_lines(subagents, empty_message="No subagents were listed."))
        lines.extend(section("Options", option_lines(options)))
    else:
        lines = [f"## {decision['title']}", ""]
        lines.extend(_decision_header_lines(decision_type=decision_type, risk=risk, reason=reason, payload=payload, requesting_agent=requesting_agent))
        if decision.get("recommended_option"):
            lines.extend(["", f"**Recommended option:** `{decision['recommended_option']}`"])
        lines.extend(section("Options", option_lines(options)))

    return _make_bridge_message(
        message_id=f"decision-{decision['id']}",
        project_id=decision.get("project_id"),
        orchestration_id=decision.get("orchestration_id"),
        source_type=source_type,
        message_type=message_type,
        title=str(decision["title"]),
        summary=compact_reason(reason, max_sentences=2, max_chars=220) or str(decision["title"]),
        user_action_required=decision.get("status") == "pending",
        risk_level=decision.get("risk_level"),
        options_json=options,
        machine_payload_json={
            "decision_id": decision["id"],
            "decision_type": decision_type,
            **payload,
        },
        fallback_markdown=join_markdown(lines),
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
    orchestration_status: str | None = None,
    current_blockers: list[str] | None = None,
    handoff_readiness: str | None = None,
    active_agent_count: int | None = None,
) -> dict[str, Any]:
    blockers = [compact_text(item, fallback="") for item in list(current_blockers or []) if compact_text(item, fallback="")]
    work_lines = bullet_lines(current_work, empty_message="No active work is recorded right now.")
    if blockers:
        work_lines.extend([f"- Blocker: {item}" for item in blockers[:3]])
    lines = [
        "## Mission Control Status",
        "",
        f"**Project:** {project_name}",
        f"**Manager:** {compact_text(manager_status)}",
        f"**Mode:** {mode}",
        f"**Swarm:** {swarm}",
        f"**User action needed:** {user_action_needed}",
    ]
    if orchestration_status:
        lines.append(f"**Orchestration:** {orchestration_status}")
    if handoff_readiness:
        lines.append(f"**Handoff:** {handoff_readiness}")
    if active_agent_count is not None:
        lines.append(f"**Active agents:** {active_agent_count}")
    lines.extend(section("Current work", work_lines))
    lines.extend(section("Waiting on you", bullet_lines(waiting_on_you, empty_message="Nothing pending from the user right now.")))
    lines.extend(["", "### Next expected step", compact_text(next_expected_step)])

    message_type = "status_update"
    if orchestration_status == "failed":
        message_type = "failed"
    elif waiting_on_you or blockers:
        message_type = "blocked"

    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=orchestration_id,
        source_type="manager",
        message_type=message_type,
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
            "current_blockers": blockers,
            "handoff_readiness": handoff_readiness,
            "active_agent_count": active_agent_count,
            "orchestration_status": orchestration_status,
        },
        fallback_markdown=join_markdown(lines),
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
        fallback_markdown=build_event_digest_markdown(title=title, grouped_items=grouped_items),
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
    missing_evidence: list[str] | None = None,
) -> dict[str, Any]:
    missing = [compact_text(item, fallback="") for item in list(missing_evidence or []) if compact_text(item, fallback="")]
    title = "Mission Control handoff ready" if handoff_status in {"ready", "needs_review"} else "Mission Control handoff status"
    return _make_bridge_message(
        message_id=message_id,
        project_id=project_id,
        orchestration_id=orchestration_id,
        source_type="handoff",
        message_type="handoff_ready" if handoff_status in {"ready", "needs_review"} else "warning",
        title=title,
        summary=f"Handoff status: {handoff_status}. Evidence level: {evidence_level}.",
        user_action_required=handoff_status == "needs_review",
        risk_level="medium" if handoff_status == "needs_review" or missing else None,
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
            "missing_evidence": missing,
        },
        fallback_markdown=build_handoff_markdown(
            title=title,
            handoff_status=handoff_status,
            confidence_level=confidence_level,
            evidence_level=evidence_level,
            what_changed=what_changed,
            how_to_run=how_to_run,
            validation_items=validation_items,
            known_limitations=known_limitations,
            next_tasks=next_tasks,
            important_files=important_files,
            missing_evidence=missing,
            dry_run=dry_run,
        ),
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


def format_diagnostic_summary_message(
    *,
    message_id: str,
    status: str,
    what_works: list[str],
    needs_attention: list[str],
    recommended_fixes: list[str],
    safe_commands: list[str],
    notes: list[str],
    created_at: datetime,
) -> dict[str, Any]:
    summary = f"Mission Control diagnostics are {status}."
    return _make_bridge_message(
        message_id=message_id,
        project_id=None,
        orchestration_id=None,
        source_type="diagnostics",
        message_type="diagnostic_summary",
        title="Mission Control diagnostics",
        summary=summary,
        user_action_required=status in {"degraded", "broken"},
        risk_level="high" if status == "broken" else ("medium" if status == "degraded" else None),
        options_json=None,
        machine_payload_json={
            "status": status,
            "what_works": what_works,
            "needs_attention": needs_attention,
            "recommended_fixes": recommended_fixes,
            "safe_commands": safe_commands,
            "notes": notes,
            "dashboard_optional": True,
        },
        fallback_markdown=build_diagnostic_summary_markdown(
            status=status,
            what_works=what_works,
            needs_attention=needs_attention,
            recommended_fixes=recommended_fixes,
            safe_commands=safe_commands,
            notes=notes,
        ),
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
        fallback_markdown=join_markdown(lines),
        created_at=created_at,
    )
