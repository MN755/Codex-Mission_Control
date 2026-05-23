from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bootstrap.secret_redaction import redact_bootstrap_value, redaction_status


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _component_status(health: dict[str, Any], key: str) -> str:
    for check in health.get("checks", []):
        if check.get("key") == key:
            return str(check.get("status") or "unknown")
    return "unknown"


def _dedupe(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _status_text(status: str) -> str:
    mapping = {
        "ready": "Ready",
        "degraded": "Degraded but usable",
        "failed": "Failed",
    }
    return mapping.get(status, status.replace("_", " ").title())


def _component_text(status: str) -> str:
    mapping = {
        "ready": "Running",
        "degraded": "Degraded",
        "broken": "Unavailable",
        "failed": "Unavailable",
        "unknown": "Unknown",
    }
    return mapping.get(status, status.replace("_", " ").title())


def _lookup_check(health: dict[str, Any], key: str) -> dict[str, Any] | None:
    for check in health.get("checks", []):
        if check.get("key") == key:
            return check
    return None


def _readiness_item(*, key: str, label: str, state: str, summary: str) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "state": state,
        "summary": summary,
    }


def _build_readiness_matrix(
    *,
    health: dict[str, Any],
    daemon_status: str,
    mcp_status: str,
    codex_host_status: str,
    discovered_installs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    daemon_check = _lookup_check(health, "mission_control_daemon_reachable") or {}
    bridge_check = _lookup_check(health, "mcp_server_reachable") or {}
    login_check = _lookup_check(health, "codex_login_status_detectable") or {}
    identity_check = _lookup_check(health, "daemon_identity_confirmed") or {}
    items = [
        _readiness_item(
            key="backend_daemon",
            label="Backend daemon reachable",
            state=daemon_status,
            summary=str(daemon_check.get("summary") or "Mission Control backend reachability was not verified."),
        ),
        _readiness_item(
            key="daemon_identity",
            label="Active checkout owns the daemon",
            state=str(identity_check.get("status") or "unknown"),
            summary=str(identity_check.get("summary") or "Daemon identity was not verified."),
        ),
        _readiness_item(
            key="mcp_bridge",
            label="MCP bridge callable",
            state=mcp_status,
            summary=str(bridge_check.get("summary") or "Mission Control MCP bridge state is unknown."),
        ),
        _readiness_item(
            key="codex_host",
            label="Codex host visibility",
            state=codex_host_status,
            summary=str(login_check.get("summary") or "Codex host observability is limited in this runtime."),
        ),
    ]
    conflicting_installs = [item for item in discovered_installs if (item.get("markers") or {}).get("install_conflict")]
    install_count = len(conflicting_installs)
    if install_count > 1:
        items.append(
            _readiness_item(
                key="multiple_installs",
                label="Multiple installs reconciled",
                state="degraded",
                summary="More than one Mission Control install was detected. Confirm which checkout should own the daemon and Codex registration.",
            )
        )
    else:
        items.append(
            _readiness_item(
                key="multiple_installs",
                label="Multiple installs reconciled",
                state="ready",
                summary="No competing Mission Control install ownership was detected.",
            )
        )
    return items


def choose_next_codex_prompt(configured_runners: list[str]) -> str:
    normalized = {item.lower() for item in configured_runners}
    if normalized <= {"dry-run"}:
        return "Use Mission Control for this repo in dry-run mode and tell me the next safe step."
    return "Use Mission Control for this repo and fix the failing tests."


def _operator_recommendations(report: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    if str(report.get("daemon_status")) != "ready":
        recommendations.append("Start or repair the Mission Control daemon before launching manager-led work.")
    if str(report.get("mcp_status")) != "ready":
        recommendations.append("Reload Codex or Claude Code after install so the MCP bridge and plugin bundle are loaded.")
    configured = {str(item).lower() for item in report.get("configured_runners", [])}
    if configured <= {"dry-run"}:
        recommendations.append("Configure Codex CLI, Claude CLI, Ollama, or an API runner before expecting real file edits.")
    if report.get("warnings"):
        recommendations.append("Review degraded health warnings before starting long-running orchestration.")
    return _dedupe(recommendations)


def compose_install_markdown(report: dict[str, Any]) -> str:
    ready_runners = ", ".join(report.get("configured_runners", [])) or "None"
    unavailable_runners = ", ".join(report.get("unavailable_runners", [])) or "None"
    environment = report.get("environment") or {}
    daemon_status = environment.get("daemon_status") if isinstance(environment, dict) else {}
    subsystem_status = report.get("subsystem_status") or {}
    discovered_installs = list(report.get("discovered_installs") or [])
    conflicting_installs = [item for item in discovered_installs if (item.get("markers") or {}).get("install_conflict")]
    lines = [
        "## Mission Control Headless Setup",
        "",
        f"**Status:** {_status_text(str(report['status']))}",
        f"**Daemon:** {_component_text(str(report['daemon_status']))}",
        f"**MCP bridge:** {_component_text(str(report['mcp_status']))}",
        f"**Active repo root:** {daemon_status.get('repo_root') or report.get('install_path')}",
        f"**Ready runners:** {ready_runners}",
        f"**Needs setup:** {unavailable_runners}",
        "**API providers:** Not auto-enabled unless already configured outside Mission Control.",
        "",
        "### You can now say",
        f"\"{report['next_codex_prompt']}\"",
    ]
    readiness_matrix = list(report.get("readiness_matrix") or [])
    if readiness_matrix:
        lines.extend(["", "### Operational readiness"])
        lines.extend(
            f"- **{item.get('label')}:** {_component_text(str(item.get('state') or 'unknown'))}. {item.get('summary')}"
            for item in readiness_matrix
        )
    if subsystem_status:
        lines.extend(["", "### Subsystem status"])
        lines.extend(f"- **{label}:** {_component_text(str(status))}" for label, status in subsystem_status.items())
    if len(conflicting_installs) > 1:
        lines.extend(["", "### Other installs found"])
        lines.extend(
            f"- `{item.get('kind')}` at `{item.get('path')}`"
            for item in conflicting_installs
            if str(item.get("path") or "") != str(report.get("active_repo_root") or "")
        )
    if report.get("user_actions_required"):
        lines.extend(["", "### User actions required"])
        lines.extend(f"- {item}" for item in report["user_actions_required"])
    if report.get("operator_recommendations"):
        lines.extend(["", "### Operator recommendations"])
        lines.extend(f"- {item}" for item in report["operator_recommendations"])
    if report.get("warnings"):
        lines.extend(["", "### Warnings"])
        lines.extend(f"- {item}" for item in report["warnings"])
    return "\n".join(lines)


def build_install_report(
    *,
    probes: list[dict[str, Any]],
    headless_config: dict[str, Any],
    health: dict[str, Any],
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    configured_runners = [probe["label"] for probe in probes if probe["configured"] or probe["runner_id"] == "dry_run"]
    unavailable_runners = [probe["label"] for probe in probes if probe.get("requires_user_action") or not probe["available"]]
    health_actions = [str(item) for item in health.get("recommended_next_steps", [])]
    probe_actions = [str(probe["recommended_fix"]) for probe in probes if probe.get("recommended_fix") and probe.get("requires_user_action")]
    warnings = [str(probe["billing_warning"]) for probe in probes if probe.get("billing_warning")]
    warnings.extend(
        str(check.get("summary"))
        for check in health.get("checks", [])
        if check.get("status") in {"degraded", "unknown"} and check.get("summary")
    )
    environment = environment or {}
    discovered_installs = list(environment.get("discovered_installs") or [])
    conflicting_installs = [item for item in discovered_installs if (item.get("markers") or {}).get("install_conflict")]
    if len(conflicting_installs) > 1:
        warnings.append("Multiple Mission Control installs were detected. Confirm which checkout should own the active daemon and Codex MCP registration.")
    daemon_status = _component_status(health, "mission_control_daemon_reachable")
    mcp_status = _component_status(health, "mcp_server_reachable")
    codex_host_status = _component_status(health, "codex_login_status_detectable")
    readiness_matrix = _build_readiness_matrix(
        health=health,
        daemon_status=daemon_status,
        mcp_status=mcp_status,
        codex_host_status=codex_host_status,
        discovered_installs=discovered_installs,
    )
    live_runners = [probe for probe in probes if probe["runner_id"] != "dry_run" and probe["configured"]]
    if health.get("status") == "broken" and not live_runners:
        status = "failed"
    elif health.get("status") == "ready" and live_runners:
        status = "ready"
    else:
        status = "degraded"
    report = {
        "status": status,
        "install_path": str(headless_config["install_path"]),
        "runtime_path": str(headless_config["runtime_path"]),
        "active_repo_root": str((environment or {}).get("daemon_status", {}).get("repo_root") or headless_config["install_path"]),
        "daemon_status": daemon_status,
        "mcp_status": mcp_status,
        "subsystem_status": {
            "Backend": daemon_status,
            "Bridge": mcp_status,
            "Codex host": codex_host_status,
            "Optional UI": _component_status(health, "dashboard_optional_status"),
        },
        "readiness_matrix": readiness_matrix,
        "configured_runners": configured_runners,
        "unavailable_runners": unavailable_runners,
        "discovered_installs": discovered_installs,
        "user_actions_required": _dedupe(probe_actions + health_actions),
        "warnings": _dedupe(warnings),
        "next_codex_prompt": choose_next_codex_prompt(configured_runners),
        "redaction_status": "redacted"
        if any(
            status_value == "redacted"
            for status_value in [
                headless_config.get("redaction_status", "clean"),
                redaction_status(health),
                redaction_status(environment or {}),
            ]
        )
        else "clean",
        "created_at": utc_now(),
        "codex_chat_markdown": "",
        "headless_config": headless_config,
        "plugin_health": health,
        "environment": environment or {},
        "problems": [
            {
                "type": f"https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#{str(item.get('code')).lower()}",
                "title": str(item.get("label") or "Mission Control issue"),
                "status": 503 if item.get("status") in {"broken", "failed"} else 409,
                "detail": str(item.get("summary") or ""),
                "instance": "",
                "code": str(item.get("code")),
                "family": str(item.get("family") or ""),
                "severity": str(item.get("severity") or "warning"),
                "breakpoint": str(item.get("breakpoint") or ""),
                "retryable": bool(item.get("retryable")),
                "user_action_required": bool(item.get("user_action_required")),
                "recommended_fix": str(item.get("recommended_fix") or ""),
                "correlation_id": str(item.get("correlation_id") or ""),
                "orchestration_id": None,
                "project_id": None,
                "runner": None,
                "redaction_status": str(item.get("redaction_status") or "clean"),
                "safe_details": dict(item.get("details_json") or {}),
            }
            for item in health.get("checks", [])
            if item.get("code")
        ]
        + [
            {
                "type": f"https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#{str(probe.get('code')).lower()}",
                "title": str(probe.get("label") or "Runner issue"),
                "status": 503 if not probe.get("configured") else 409,
                "detail": str(probe.get("recommended_fix") or probe.get("install_status") or ""),
                "instance": "",
                "code": str(probe.get("code")),
                "family": "MC-RUNNER" if str(probe.get("runner_id")) not in {"codex_cli", "ollama", "claude_cli"} else f"MC-{str(probe.get('runner_id')).split('_')[0].upper()}",
                "severity": str(probe.get("severity") or "warning"),
                "breakpoint": str(probe.get("breakpoint") or ""),
                "retryable": bool(probe.get("retryable")),
                "user_action_required": bool(probe.get("user_action_required")),
                "recommended_fix": str(probe.get("recommended_fix") or ""),
                "correlation_id": "",
                "orchestration_id": None,
                "project_id": None,
                "runner": str(probe.get("runner_id") or ""),
                "redaction_status": "clean",
                "safe_details": dict(probe.get("details_json") or {}),
            }
            for probe in probes
            if probe.get("code")
        ],
    }
    report["operator_recommendations"] = _operator_recommendations(report)
    report["codex_chat_markdown"] = compose_install_markdown(report)
    return redact_bootstrap_value(report)
