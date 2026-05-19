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


def choose_next_codex_prompt(configured_runners: list[str]) -> str:
    normalized = {item.lower() for item in configured_runners}
    if normalized <= {"dry-run"}:
        return "Use Mission Control for this repo in dry-run mode and tell me the next safe step."
    return "Use Mission Control for this repo and fix the failing tests."


def compose_install_markdown(report: dict[str, Any]) -> str:
    ready_runners = ", ".join(report.get("configured_runners", [])) or "None"
    unavailable_runners = ", ".join(report.get("unavailable_runners", [])) or "None"
    lines = [
        "## Mission Control Headless Setup",
        "",
        f"**Status:** {_status_text(str(report['status']))}",
        f"**Daemon:** {_component_text(str(report['daemon_status']))}",
        f"**MCP bridge:** {_component_text(str(report['mcp_status']))}",
        f"**Ready runners:** {ready_runners}",
        f"**Needs setup:** {unavailable_runners}",
        "**API providers:** Not auto-enabled unless already configured outside Mission Control.",
        "",
        "### You can now say",
        f"\"{report['next_codex_prompt']}\"",
    ]
    if report.get("user_actions_required"):
        lines.extend(["", "### User actions required"])
        lines.extend(f"- {item}" for item in report["user_actions_required"])
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
    daemon_status = _component_status(health, "mission_control_daemon_reachable")
    mcp_status = _component_status(health, "mcp_server_reachable")
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
        "daemon_status": daemon_status,
        "mcp_status": mcp_status,
        "configured_runners": configured_runners,
        "unavailable_runners": unavailable_runners,
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
    }
    report["codex_chat_markdown"] = compose_install_markdown(report)
    return redact_bootstrap_value(report)
