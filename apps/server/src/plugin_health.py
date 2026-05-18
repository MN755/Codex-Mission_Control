from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from sqlalchemy import text

from config import REPO_ROOT, RUNTIME_ROOT, get_codex_home
from daemon_state import daemon_dashboard_url, read_daemon_metadata
from db import engine
from manager import service
from system_status import detect_codex_status


PLUGIN_ROOT = REPO_ROOT / "plugins" / "mission-control"
LOCAL_SKILLS_ROOT = REPO_ROOT / ".codex" / "skills"
REQUIRED_PLUGIN_FILES = [
    PLUGIN_ROOT / "plugin.json",
    PLUGIN_ROOT / "README.md",
    PLUGIN_ROOT / "mcp" / "mission-control-mcp.example.json",
]
REQUIRED_PLUGIN_SKILLS = [
    PLUGIN_ROOT / "skills" / "mission-control-orchestrate" / "SKILL.md",
    PLUGIN_ROOT / "skills" / "mission-control-import-codebase" / "SKILL.md",
    PLUGIN_ROOT / "skills" / "mission-control-review-handoff" / "SKILL.md",
]
REQUIRED_LOCAL_SKILLS = [
    LOCAL_SKILLS_ROOT / "mission-control-orchestrate" / "SKILL.md",
    LOCAL_SKILLS_ROOT / "mission-control-import-codebase" / "SKILL.md",
    LOCAL_SKILLS_ROOT / "mission-control-review-handoff" / "SKILL.md",
]
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
PASSING_MCP_STATUSES = {"connected", "running", "healthy", "ok", "ready"}
FAILING_MCP_STATUSES = {"error", "disconnected", "failed", "broken", "unreachable"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _probe_url(url: str, *, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 400, f"HTTP {response.status}"
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, OSError, TimeoutError) as exc:
        return False, type(exc).__name__


def _check(
    *,
    check_id: str,
    label: str,
    status: str,
    summary: str,
    critical: bool,
    fix: str | None = None,
    commands: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": check_id,
        "label": label,
        "status": status,
        "summary": summary,
        "recommended_fix": fix,
        "details_json": dict(details or {}),
        "checked_at": _utc_now(),
        "critical": critical,
        "commands": list(commands or []),
    }


def _is_local_host(host: str | None) -> bool:
    return bool(host and host.strip().lower() in LOCAL_HOSTS)


def _find_mission_control_mcp_server(servers: list[dict[str, Any]]) -> dict[str, Any] | None:
    for server in servers:
        haystacks = [
            str(server.get("name") or ""),
            str(server.get("id") or ""),
            str(server.get("command") or ""),
            str(server.get("display_name") or ""),
            str(server.get("server") or ""),
        ]
        if any("mission-control" in value.lower() or "mission_control" in value.lower() for value in haystacks):
            return server
    return None


async def mission_control_plugin_health() -> dict[str, Any]:
    codex = detect_codex_status()
    metadata = read_daemon_metadata()
    dashboard_url = daemon_dashboard_url()
    daemon_host = str(metadata.get("host") or "")
    daemon_port = int(metadata.get("port") or 0)
    daemon_mode = str(metadata.get("mode") or "unknown")
    daemon_url = f"http://{daemon_host}:{daemon_port}/api/health" if daemon_host and daemon_port else ""
    daemon_ok, daemon_probe = _probe_url(daemon_url) if daemon_url else (False, "no_target")
    dashboard_ok, dashboard_probe = _probe_url(dashboard_url)

    checks: list[dict[str, Any]] = []

    checks.append(
        _check(
            check_id="mission_control_daemon_reachable",
            label="Mission Control daemon reachable",
            status="ready" if daemon_ok and daemon_mode == "daemon" else ("degraded" if daemon_ok else "broken"),
            summary=(
                "Mission Control daemon health endpoint responded successfully."
                if daemon_ok and daemon_mode == "daemon"
                else (
                    "Mission Control backend is reachable, but daemon mode is not confirmed."
                    if daemon_ok
                    else f"Mission Control daemon health probe failed at {daemon_url or 'unknown target'} ({daemon_probe})."
                )
            ),
            critical=True,
            fix=None if daemon_ok and daemon_mode == "daemon" else "Start Mission Control locally and verify the backend health endpoint responds.",
            commands=[".\\scripts\\start-mission-control.ps1", "Invoke-WebRequest http://127.0.0.1:8000/api/health"],
            details={"host": daemon_host, "port": daemon_port, "mode": daemon_mode},
        )
    )

    mcp_servers = list(codex.get("mcp_servers", []))
    mission_server = _find_mission_control_mcp_server(mcp_servers)
    if mission_server is None:
        checks.append(
            _check(
                check_id="mcp_server_reachable",
                label="MCP server reachable",
                status="broken",
                summary="No Mission Control MCP server entry was detected in Codex MCP configuration.",
                critical=True,
                fix="Add the Mission Control MCP server to Codex and reload the MCP config.",
                commands=["codex mcp list --json", "Get-Content plugins\\mission-control\\mcp\\mission-control-mcp.example.json"],
            )
        )
    else:
        raw_status = str(mission_server.get("status") or mission_server.get("connection_status") or "").strip().lower()
        if raw_status in PASSING_MCP_STATUSES:
            state = "ready"
            summary = "Mission Control MCP server is configured and reports a healthy connection state."
        elif raw_status in FAILING_MCP_STATUSES:
            state = "broken"
            summary = f"Mission Control MCP server is configured but reports '{raw_status}'."
        else:
            state = "unknown"
            summary = "Mission Control MCP server is configured, but Codex does not expose a definitive live reachability state."
        checks.append(
            _check(
                check_id="mcp_server_reachable",
                label="MCP server reachable",
                status=state,
                summary=summary,
                critical=True,
                fix=None if state == "ready" else "Verify the MCP bridge command and reload Codex MCP configuration.",
                commands=["codex mcp list --json"],
                details={"server": mission_server},
            )
        )
        for key, label in [
            ("tools", "MCP tools registered"),
            ("resources", "MCP resources registered"),
            ("prompts", "MCP prompts registered"),
        ]:
            raw_value = mission_server.get(key)
            count: int | None = None
            if isinstance(raw_value, list):
                count = len(raw_value)
            elif isinstance(raw_value, int):
                count = raw_value
            elif isinstance(raw_value, dict):
                count = len(raw_value)
            state = "unknown"
            summary = f"Codex did not expose {label.lower()} metadata for the Mission Control MCP server."
            if count is not None:
                state = "ready" if count > 0 else "degraded"
                summary = f"Mission Control MCP server reports {count} {key}."
            checks.append(
                _check(
                    check_id=f"mcp_{key}_registered",
                    label=label,
                    status=state,
                    summary=summary,
                    critical=False,
                    fix=None if count is None or count > 0 else f"Expose at least one {key[:-1]} from the Mission Control MCP bridge.",
                    commands=["codex mcp list --json"],
                    details={"count": count},
                )
            )

    missing_plugin_files = [str(path.relative_to(REPO_ROOT)) for path in REQUIRED_PLUGIN_FILES if not path.exists()]
    checks.append(
        _check(
            check_id="plugin_package_exists",
            label="Plugin package exists",
            status="ready" if not missing_plugin_files else "broken",
            summary="Mission Control plugin package files are present." if not missing_plugin_files else "Mission Control plugin package is incomplete.",
            critical=True,
            fix=None if not missing_plugin_files else "Restore the Mission Control plugin package under plugins/mission-control.",
            commands=["Get-ChildItem plugins\\mission-control -Recurse"],
            details={"missing_files": missing_plugin_files},
        )
    )

    missing_skill_files = [str(path.relative_to(REPO_ROOT)) for path in [*REQUIRED_PLUGIN_SKILLS, *REQUIRED_LOCAL_SKILLS] if not path.exists()]
    checks.append(
        _check(
            check_id="skill_files_exist",
            label="Skill files exist",
            status="ready" if not missing_skill_files else "broken",
            summary="Mission Control skill files are present in both plugin and repo-local Codex skill folders."
            if not missing_skill_files
            else "One or more Mission Control skill files are missing.",
            critical=True,
            fix=None if not missing_skill_files else "Restore the Mission Control skill files and reload Codex skill discovery.",
            commands=["Get-ChildItem .codex\\skills", "Get-ChildItem plugins\\mission-control\\skills -Recurse"],
            details={"missing_files": missing_skill_files},
        )
    )

    checks.append(
        _check(
            check_id="codex_cli_detected",
            label="Codex CLI detected",
            status="ready" if bool(codex.get("cli_detected")) else "broken",
            summary="Codex CLI is available." if codex.get("cli_detected") else "Codex CLI is not available on the current PATH.",
            critical=True,
            fix=None if codex.get("cli_detected") else "Install Codex CLI or fix the PATH.",
            commands=["codex --version"],
            details={"cli_version": codex.get("cli_version")},
        )
    )

    login_status = str(codex.get("login_status") or "").strip()
    login_detectable = bool(codex.get("auth_status_detectable")) and login_status not in {"", "Unavailable"}
    checks.append(
        _check(
            check_id="codex_login_status_detectable",
            label="Codex login status detectable",
            status="ready" if login_detectable else "degraded",
            summary="Codex login status can be queried safely." if login_detectable else "Codex login status could not be confirmed cleanly.",
            critical=False,
            fix=None if login_detectable else "Run `codex login status` and sign in again if needed.",
            commands=["codex login status"],
            details={"auth_mode": codex.get("auth_mode"), "authenticated": bool(codex.get("authenticated"))},
        )
    )

    try:
        runner_inventory = await service.runners.inventory()
        checks.append(
            _check(
                check_id="runner_registry_available",
                label="Runner registry available",
                status="ready" if runner_inventory else "broken",
                summary="Runner registry responded with available runner inventory." if runner_inventory else "Runner registry returned no runner entries.",
                critical=True,
                fix=None if runner_inventory else "Inspect Mission Control runner registration before trying plugin-driven execution.",
                commands=["python -m pytest apps/server/tests/test_runners.py"],
                details={"runner_types": [item.get("runner_type") for item in runner_inventory]},
            )
        )
    except Exception as exc:
        checks.append(
            _check(
                check_id="runner_registry_available",
                label="Runner registry available",
                status="broken",
                summary=f"Runner registry lookup failed: {type(exc).__name__}.",
                critical=True,
                fix="Inspect Mission Control runner registration and startup logs.",
                commands=["python -m pytest apps/server/tests/test_runners.py"],
            )
        )

    runtime_root = RUNTIME_ROOT
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_probe = runtime_root / ".plugin-health.tmp"
    try:
        runtime_probe.write_text("ok", encoding="utf-8")
        runtime_probe.unlink(missing_ok=True)
        runtime_writable = True
    except OSError:
        runtime_writable = False
    checks.append(
        _check(
            check_id="runtime_directory_writable",
            label="Runtime directory writable",
            status="ready" if runtime_writable else "broken",
            summary="Mission Control runtime directory is writable." if runtime_writable else "Mission Control runtime directory is not writable.",
            critical=True,
            fix=None if runtime_writable else "Fix filesystem permissions for the Mission Control runtime directory.",
            commands=["Get-ChildItem .runtime"],
            details={"runtime_root": str(runtime_root)},
        )
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False
    checks.append(
        _check(
            check_id="sqlite_db_reachable",
            label="SQLite DB reachable",
            status="ready" if db_ready else "broken",
            summary="Mission Control SQLite database responded to a simple query." if db_ready else "Mission Control SQLite database could not be queried.",
            critical=True,
            fix=None if db_ready else "Inspect the runtime SQLite file and backend startup logs.",
            commands=["python -m pytest apps/server/tests/test_api_smoke.py"],
        )
    )

    checks.append(
        _check(
            check_id="dashboard_optional_status",
            label="Dashboard optional status",
            status="ready" if dashboard_ok else "unknown",
            summary="Mission Control dashboard URL responded successfully." if dashboard_ok else f"Mission Control dashboard URL did not respond cleanly ({dashboard_probe}), but dashboard reachability is optional for headless bridge mode.",
            critical=False,
            fix=None if dashboard_ok else "Start the standalone dashboard only if you specifically need it.",
            commands=["Invoke-WebRequest http://127.0.0.1:8000/dashboard"],
            details={"dashboard_url": dashboard_url},
        )
    )

    dashboard_host = urlparse(dashboard_url).hostname
    checks.append(
        _check(
            check_id="localhost_only_binding",
            label="Localhost-only binding",
            status="ready" if _is_local_host(daemon_host) and _is_local_host(dashboard_host) else "degraded",
            summary="Mission Control appears to be bound to localhost-only addresses."
            if _is_local_host(daemon_host) and _is_local_host(dashboard_host)
            else "Mission Control binding is not clearly localhost-only.",
            critical=False,
            fix=None if _is_local_host(daemon_host) and _is_local_host(dashboard_host) else "Bind Mission Control to 127.0.0.1 or localhost for plugin mode.",
            commands=["Get-Content scripts\\mission-control.config.json"],
            details={"daemon_host": daemon_host, "dashboard_host": dashboard_host},
        )
    )

    if any(check["status"] == "broken" and check["critical"] for check in checks):
        overall = "broken"
    elif any(check["status"] == "degraded" for check in checks):
        overall = "degraded"
    else:
        overall = "ready"

    recommended_next_steps = list(
        dict.fromkeys(check["recommended_fix"] for check in checks if check.get("recommended_fix") and check["status"] in {"broken", "degraded"})
    )
    safe_commands = list(
        dict.fromkeys(command for check in checks if check["status"] in {"broken", "degraded", "unknown"} for command in check.get("commands", []))
    )
    markdown_lines = [
        "## Plugin Health Doctor",
        "",
        f"**Overall status:** {overall}",
        "",
        "### Checks",
    ]
    for check in checks:
        markdown_lines.append(f"- **{check['label']}** [{check['status']}]: {check['summary']}")
    if recommended_next_steps:
        markdown_lines.extend(["", "### Recommended next steps", *[f"- {item}" for item in recommended_next_steps]])
    if safe_commands:
        markdown_lines.extend(["", "### Safe troubleshooting commands", *[f"- `{item}`" for item in safe_commands]])

    return {
        "status": overall,
        "checks": checks,
        "recommended_next_steps": recommended_next_steps,
        "safe_troubleshooting_commands": safe_commands,
        "codex_chat_markdown": "\n".join(markdown_lines),
        "checked_at": _utc_now(),
        "notes": [
            "Plugin health checks are read-only and never return daemon tokens, API keys, or secret file contents.",
            f"Detected Codex home: {get_codex_home()}",
        ],
    }
