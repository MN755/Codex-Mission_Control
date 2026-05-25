from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from sqlalchemy import text

from config import REPO_ROOT, RUNTIME_ROOT, get_codex_home
from daemon_state import daemon_dashboard_url, daemon_identity_snapshot, read_daemon_metadata, resolve_backend_binding
from db import engine
from device_profile import detect_device_profile, detect_performance_profile, platform_debug_commands
from errors import MissionControlError, derive_health_status, format_health_check_item
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
OVERALL_DEGRADED_CHECK_KEYS = {
    "daemon_identity_confirmed",
    "codex_login_status_detectable",
    "localhost_only_binding",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _backend_url(host: str, port: int, path: str) -> str:
    return f"http://{_url_host(host)}:{port}{path}"


def _http_probe_command(url: str) -> str:
    return f"Invoke-WebRequest {url}" if os.name == "nt" else f"curl -fsS {url}"


def _start_daemon_command(port: int) -> str:
    return f".\\scripts\\start-mission-control-daemon.ps1 -BackendPort {port}" if os.name == "nt" else f"./scripts/start-mission-control-daemon.sh"


def _list_command(path: str, *, recursive: bool = False) -> str:
    if os.name == "nt":
        return f"Get-ChildItem {path}{' -Recurse' if recursive else ''}"
    return f"find {path} -maxdepth 3 -type f" if recursive else f"ls -la {path}"


def _read_command(path: str) -> str:
    return f"Get-Content {path}" if os.name == "nt" else f"cat {path}"


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
    error: MissionControlError | None = None,
) -> dict[str, Any]:
    return format_health_check_item(
        check_id=check_id,
        label=label,
        status=status,
        summary=summary,
        critical=critical,
        error=error,
        fix=fix,
        commands=commands,
        details=details,
    )


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


def _component_state(checks: list[dict[str, Any]], keys: list[str]) -> str:
    relevant = [check for check in checks if check.get("key") in keys]
    if any(check.get("status") == "broken" and check.get("critical") for check in relevant):
        return "broken"
    if any(check.get("status") in {"degraded", "unknown"} for check in relevant):
        return "degraded"
    return "ready"


async def mission_control_plugin_health() -> dict[str, Any]:
    codex = detect_codex_status()
    device_profile = detect_device_profile()
    performance_profile = detect_performance_profile()
    identity = daemon_identity_snapshot()
    metadata = read_daemon_metadata()
    backend_binding = resolve_backend_binding()
    dashboard_url = daemon_dashboard_url()
    daemon_host = str(backend_binding.get("host") or identity.get("host") or "")
    daemon_port = int(backend_binding.get("port") or identity.get("port") or 0)
    device_debug_commands = platform_debug_commands(backend_port=daemon_port or 8010)
    identity_mode = str(identity.get("mode") or "unknown")
    daemon_mode = str(backend_binding.get("mode") or identity_mode or "unknown")
    daemon_url = _backend_url(daemon_host, daemon_port, "/api/health") if daemon_host and daemon_port else ""
    identity_url = _backend_url(daemon_host, daemon_port, "/api/diagnostics/identity") if daemon_host and daemon_port else ""
    in_process_daemon = (
        os.environ.get("MISSION_CONTROL_SERVER_MODE") == "daemon"
        and identity_mode == "daemon"
        and str(identity.get("repo_root") or "") == str(REPO_ROOT)
    )
    daemon_ok, daemon_probe = (
        (True, "in_process_daemon")
        if in_process_daemon
        else (_probe_url(daemon_url) if daemon_url else (False, "no_target"))
    )
    dashboard_ok, dashboard_probe = _probe_url(dashboard_url)

    checks: list[dict[str, Any]] = []

    daemon_error: MissionControlError | None = None
    daemon_status = "ready"
    daemon_summary = "Mission Control daemon health endpoint responded successfully."
    if not daemon_ok:
        daemon_error = MissionControlError(
            code="MC-DAEMON-NOT-RUNNING-001",
            breakpoint="daemon.health_check",
            safe_details={"host": daemon_host or None, "port": daemon_port or None, "probe": daemon_probe},
        )
        daemon_status = derive_health_status(daemon_error, critical=True)
        daemon_summary = daemon_error.detail or f"Mission Control daemon health probe failed at {daemon_url or 'unknown target'} ({daemon_probe})."
    elif daemon_mode != "daemon":
        daemon_error = MissionControlError(
            code="MC-DAEMON-HEALTH-FAILED-001",
            detail="Mission Control backend is reachable, but daemon mode is not confirmed.",
            severity="warning",
            breakpoint="daemon.health_check",
            retryable=True,
            user_action_required=False,
            safe_details={"host": daemon_host or None, "port": daemon_port or None, "mode": daemon_mode},
        )
        daemon_status = "degraded"
        daemon_summary = daemon_error.detail or daemon_summary
    elif str(metadata.get("status") or "") == "stale":
        daemon_status = "degraded"
        daemon_summary = "Mission Control daemon is reachable, but daemon metadata is stale and should be refreshed."
    checks.append(
        _check(
            check_id="mission_control_daemon_reachable",
            label="Mission Control daemon reachable",
            status=daemon_status,
            summary=daemon_summary,
            critical=True,
            fix=None if daemon_error is None else daemon_error.recommended_fix,
            commands=[
                _start_daemon_command(daemon_port),
                _http_probe_command(daemon_url),
                _http_probe_command(identity_url),
            ],
            details={
                "host": daemon_host,
                "port": daemon_port,
                "mode": daemon_mode,
                "identity_mode": identity_mode,
                "binding_source": backend_binding.get("source"),
                "metadata_status": metadata.get("status"),
                "stored_metadata_status": metadata.get("stored_status"),
                "repo_root": identity.get("repo_root"),
                "runtime_root": identity.get("runtime_root"),
                "launcher_root": identity.get("launcher_root"),
            },
            error=daemon_error,
        )
    )

    identity_status = "ready"
    identity_summary = "Daemon identity matches the current Mission Control checkout and runtime roots."
    if str(identity.get("repo_root") or "") != str(REPO_ROOT):
        identity_status = "broken"
        identity_summary = "The reachable daemon belongs to a different Mission Control checkout than the current repository."
    elif str(metadata.get("status") or "") in {"missing", "stale"}:
        identity_status = "degraded"
        identity_summary = "The daemon is reachable, but persisted daemon metadata is missing or stale."
    checks.append(
        _check(
            check_id="daemon_identity_confirmed",
            label="Daemon identity confirmed",
            status=identity_status,
            summary=identity_summary,
            critical=True,
            fix=None if identity_status == "ready" else "Restart the daemon from this repository checkout so runtime metadata matches the live backend.",
            commands=[_http_probe_command(identity_url)],
            details=identity,
        )
    )

    live_mcp_servers = list(codex.get("mcp_servers", []))
    configured_mcp_servers = list(codex.get("configured_mcp_servers", []))
    mission_server = _find_mission_control_mcp_server(live_mcp_servers)
    configured_server = _find_mission_control_mcp_server(configured_mcp_servers)
    codex_cli_detected = bool(codex.get("cli_detected"))
    cli_execution_available = bool(codex.get("cli_execution_available"))
    if mission_server is None and configured_server is None:
        bridge_error = MissionControlError(
            code="MC-MCP-BRIDGE-MISSING-001",
            breakpoint="mcp.start",
            safe_details={"mcp_server_count": len(live_mcp_servers)},
        )
        checks.append(
            _check(
                check_id="mcp_server_reachable",
                label="MCP server reachable",
                status=derive_health_status(bridge_error, critical=True),
                summary=bridge_error.detail,
                critical=True,
                fix=bridge_error.recommended_fix,
                commands=["codex mcp list --json", _read_command("plugins/mission-control/mcp/mission-control-mcp.example.json")],
                details={"configured_mcp_servers": configured_mcp_servers, "live_mcp_servers": live_mcp_servers},
                error=bridge_error,
            )
        )
    else:
        bridge_status = "ready"
        bridge_summary = "Mission Control MCP server is configured and reports a healthy connection state."
        bridge_fix: str | None = None
        bridge_error = None
        mcp_state = (codex.get("mcp_state") or {}).get("mission_control") or {}
        app_loaded = mcp_state.get("app_loaded")
        if mission_server is not None:
            raw_status = str(mission_server.get("status") or mission_server.get("connection_status") or "").strip().lower()
            if raw_status in FAILING_MCP_STATUSES:
                bridge_error = MissionControlError(
                    code="MC-MCP-HANDSHAKE-FAILED-001",
                    detail=f"Mission Control MCP server is configured but reports '{raw_status}'.",
                    breakpoint="mcp.handshake",
                    safe_details={"reported_status": raw_status},
                )
                bridge_status = derive_health_status(bridge_error, critical=True)
                bridge_summary = bridge_error.detail or bridge_summary
                bridge_fix = bridge_error.recommended_fix
            elif app_loaded is True:
                bridge_status = "ready"
                bridge_summary = "Mission Control MCP server is configured and was discovered in the live Codex MCP server list."
                bridge_fix = None
            elif raw_status not in PASSING_MCP_STATUSES:
                bridge_status = "unknown"
                bridge_summary = "Mission Control MCP server is configured, but Codex did not expose a definitive live reachability state."
                bridge_fix = "Verify the MCP bridge command and reload Codex MCP configuration."
        elif app_loaded is True:
            bridge_status = "ready"
            bridge_summary = "Mission Control MCP server is configured and was discovered in the live Codex MCP server list."
            bridge_fix = None
        elif configured_server is not None and not cli_execution_available and codex_cli_detected:
            bridge_status = "degraded"
            bridge_summary = "Mission Control is configured in Codex config, but this runtime could not inspect live MCP loading."
            bridge_fix = "Reload Codex and verify the Mission Control MCP server from the app host, or use a runtime that can execute the Codex CLI."
        else:
            bridge_status = "degraded"
            bridge_summary = "Mission Control is configured in Codex config, but it was not discovered in the live Codex MCP server list."
            bridge_fix = "Reload Codex so it loads the updated Mission Control MCP registration, then verify the live MCP server list again."
        checks.append(
            _check(
                check_id="mcp_server_reachable",
                label="MCP server reachable",
                status=bridge_status,
                summary=bridge_summary,
                critical=True,
                fix=bridge_fix,
                commands=["codex mcp list --json"],
                details={
                    "configured_server": configured_server,
                    "live_server": mission_server,
                    "mcp_state": codex.get("mcp_state"),
                },
                error=bridge_error,
            )
        )
        server_for_counts = mission_server or configured_server or {}
        for key, label in [
            ("tools", "MCP tools registered"),
            ("resources", "MCP resources registered"),
            ("prompts", "MCP prompts registered"),
        ]:
            raw_value = server_for_counts.get(key)
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
            elif app_loaded is True:
                state = "ready"
                summary = f"Mission Control MCP server is live-loaded, but Codex did not expose {label.lower()} counts."
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
    package_error = (
        MissionControlError(
            code="MC-PLUGIN-PACKAGE-INVALID-001",
            breakpoint="plugin.package_validate",
            safe_details={"missing_files": missing_plugin_files},
        )
        if missing_plugin_files
        else None
    )
    checks.append(
        _check(
            check_id="plugin_package_exists",
            label="Plugin package exists",
            status="ready" if package_error is None else derive_health_status(package_error, critical=True),
            summary="Mission Control plugin package files are present." if package_error is None else package_error.detail,
            critical=True,
            fix=None if package_error is None else package_error.recommended_fix,
            commands=[_list_command("plugins/mission-control", recursive=True)],
            details={"missing_files": missing_plugin_files},
            error=package_error,
        )
    )

    missing_skill_files = [str(path.relative_to(REPO_ROOT)) for path in [*REQUIRED_PLUGIN_SKILLS, *REQUIRED_LOCAL_SKILLS] if not path.exists()]
    skill_error = (
        MissionControlError(
            code="MC-PLUGIN-SKILL-MISSING-001",
            breakpoint="plugin.skill_discovery",
            safe_details={"missing_files": missing_skill_files},
        )
        if missing_skill_files
        else None
    )
    checks.append(
        _check(
            check_id="skill_files_exist",
            label="Skill files exist",
            status="ready" if skill_error is None else derive_health_status(skill_error, critical=True),
            summary="Mission Control skill files are present in both plugin and repo-local Codex skill folders."
            if skill_error is None
            else skill_error.detail,
            critical=True,
            fix=None if skill_error is None else skill_error.recommended_fix,
            commands=[_list_command(".codex/skills"), _list_command("plugins/mission-control/skills", recursive=True)],
            details={"missing_files": missing_skill_files},
            error=skill_error,
        )
    )

    codex_cli_error = None
    codex_cli_status = "ready"
    codex_cli_summary = "Codex CLI path is available."
    if not codex_cli_detected:
        codex_cli_error = MissionControlError(
            code="MC-CODEX-CLI-MISSING-001",
            breakpoint="codex_cli.detect",
            safe_details={"cli_version": codex.get("cli_version"), "cli_path": codex.get("cli_path")},
        )
        codex_cli_status = derive_health_status(codex_cli_error, critical=True)
        codex_cli_summary = codex_cli_error.detail or codex_cli_summary
    checks.append(
        _check(
            check_id="codex_cli_detected",
            label="Codex CLI detected",
            status=codex_cli_status,
            summary=codex_cli_summary,
            critical=True,
            fix=None if codex_cli_error is None else codex_cli_error.recommended_fix,
            commands=["codex --version"],
            details={"cli_version": codex.get("cli_version"), "cli_path": codex.get("cli_path")},
            error=codex_cli_error,
        )
    )

    execution_status = "ready" if cli_execution_available else ("unknown" if codex_cli_detected else "broken")
    execution_summary = "Codex CLI can be executed from the current runtime." if cli_execution_available else (
        "Codex CLI path exists, but direct execution is unavailable from the current runtime."
        if codex_cli_detected
        else "Codex CLI is not available from the current runtime."
    )
    checks.append(
        _check(
            check_id="codex_cli_execution_available",
            label="Codex CLI execution available",
            status=execution_status,
            summary=execution_summary,
            critical=False,
            fix=None if cli_execution_available else "Use config-based and backend-based validation when the current runtime cannot execute codex.exe directly.",
            commands=["codex --version", "codex login status", "codex mcp list --json"],
            details={"cli_path": codex.get("cli_path"), "cli_path_exists": codex.get("cli_path_exists")},
        )
    )

    login_status = str(codex.get("login_status") or "").strip()
    login_status_lower = login_status.lower()
    login_query_unavailable = (
        login_status in {"", "Unavailable"}
        or "could not be queried" in login_status_lower
        or "unavailable from this runtime" in login_status_lower
    )
    login_detectable = bool(codex.get("auth_status_detectable")) and not login_query_unavailable
    login_error = None if login_detectable else MissionControlError(
        code="MC-CODEX-LOGIN-UNKNOWN-001",
        breakpoint="codex_cli.login_status",
        severity="warning",
        safe_details={"auth_mode": codex.get("auth_mode"), "authenticated": bool(codex.get("authenticated"))},
    )
    checks.append(
        _check(
            check_id="codex_login_status_detectable",
            label="Codex login status detectable",
            status="ready" if login_error is None else derive_health_status(login_error, critical=False),
            summary="Codex login status can be queried safely." if login_error is None else login_error.detail,
            critical=False,
            fix=None if login_error is None else login_error.recommended_fix,
            commands=["codex login status"],
            details={"auth_mode": codex.get("auth_mode"), "authenticated": bool(codex.get("authenticated"))},
            error=login_error,
        )
    )

    try:
        runner_inventory = await service.runners.inventory()
        runner_error = None if runner_inventory else MissionControlError(
            code="MC-RUNNER-NONE-AVAILABLE-001",
            breakpoint="runner.registry_load",
            severity="warning",
            safe_details={"runner_types": []},
        )
        non_dry_runners = [item for item in runner_inventory if item.get("runner_type") != "dry_run" and item.get("availability")]
        checks.append(
            _check(
                check_id="runner_registry_available",
                label="Runner registry available",
                status="ready" if runner_error is None else derive_health_status(runner_error, critical=True),
                summary="Runner registry responded with available runner inventory." if runner_error is None else runner_error.detail,
                critical=True,
                fix=None if runner_error is None else runner_error.recommended_fix,
                commands=["python -m pytest apps/server/tests/test_runners.py"],
                details={"runner_types": [item.get("runner_type") for item in runner_inventory]},
                error=runner_error,
            )
        )
        checks.append(
            _check(
                check_id="runner_execution_quality",
                label="Runner execution quality",
                status="ready" if non_dry_runners else "degraded",
                summary=(
                    "At least one real coding runner is available for worker execution."
                    if non_dry_runners
                    else "Only dry-run execution is currently available; Mission Control can plan, but real code edits need Codex CLI, Claude CLI, Ollama, or an API runner."
                ),
                critical=False,
                fix=None if non_dry_runners else "Configure at least one real runner before expecting autonomous edits.",
                commands=["python scripts/mission-control-manage.py status --json"],
                details={"ready_runner_types": [item.get("runner_type") for item in non_dry_runners]},
            )
        )
    except Exception as exc:
        runner_error = MissionControlError(
            code="MC-RUNNER-SELECTION-FAILED-001",
            detail=f"Runner registry lookup failed: {type(exc).__name__}.",
            breakpoint="runner.registry_load",
            safe_details={"exception_type": type(exc).__name__},
            caused_by=exc,
        )
        checks.append(
            _check(
                check_id="runner_registry_available",
                label="Runner registry available",
                status=derive_health_status(runner_error, critical=True),
                summary=runner_error.detail or "Runner registry lookup failed.",
                critical=True,
                fix=runner_error.recommended_fix,
                commands=["python -m pytest apps/server/tests/test_runners.py"],
                error=runner_error,
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
    runtime_error = None if runtime_writable else MissionControlError(
        code="MC-STORAGE-RUNTIME-WRITE-FAILED-001",
        breakpoint="diagnostics.write_report",
        safe_details={"runtime_root": str(runtime_root)},
    )
    checks.append(
        _check(
            check_id="runtime_directory_writable",
            label="Runtime directory writable",
            status="ready" if runtime_error is None else derive_health_status(runtime_error, critical=True),
            summary="Mission Control runtime directory is writable." if runtime_error is None else runtime_error.detail,
            critical=True,
            fix=None if runtime_error is None else runtime_error.recommended_fix,
            commands=[_list_command(".runtime")],
            details={"runtime_root": str(runtime_root)},
            error=runtime_error,
        )
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ready = True
    except Exception:
        db_ready = False
    db_error = None if db_ready else MissionControlError(
        code="MC-STORAGE-DB-UNAVAILABLE-001",
        breakpoint="bootstrap.health_check",
    )
    checks.append(
        _check(
            check_id="sqlite_db_reachable",
            label="SQLite DB reachable",
            status="ready" if db_error is None else derive_health_status(db_error, critical=True),
            summary="Mission Control SQLite database responded to a simple query." if db_error is None else db_error.detail,
            critical=True,
            fix=None if db_error is None else db_error.recommended_fix,
            commands=["python -m pytest apps/server/tests/test_api_smoke.py"],
            error=db_error,
        )
    )

    dashboard_error = None if dashboard_ok else MissionControlError(
        code="MC-DAEMON-HEALTH-FAILED-001",
        detail=f"Mission Control dashboard URL did not respond cleanly ({dashboard_probe}), but dashboard reachability is optional for background bridge mode.",
        severity="debug",
        breakpoint="daemon.health_check",
        retryable=True,
        user_action_required=False,
        safe_details={"dashboard_url": dashboard_url},
    )
    checks.append(
        _check(
            check_id="dashboard_optional_status",
            label="Dashboard optional status",
            status="ready" if dashboard_ok else "unknown",
            summary="Mission Control dashboard URL responded successfully." if dashboard_ok else dashboard_error.detail,
            critical=False,
            fix=None if dashboard_ok else "Start the standalone dashboard only if you specifically need it.",
            commands=[_http_probe_command(dashboard_url)],
            details={"dashboard_url": dashboard_url},
            error=dashboard_error,
        )
    )

    dashboard_host = urlparse(dashboard_url).hostname
    binding_error = None if _is_local_host(daemon_host) and _is_local_host(dashboard_host) else MissionControlError(
        code="MC-NETWORK-LOCALHOST-UNREACHABLE-001",
        detail="Mission Control binding is not clearly localhost-only.",
        severity="warning",
        breakpoint="daemon.port_bind",
        retryable=True,
        user_action_required=True,
        safe_details={"daemon_host": daemon_host, "dashboard_host": dashboard_host},
    )
    checks.append(
        _check(
            check_id="localhost_only_binding",
            label="Localhost-only binding",
            status="ready" if binding_error is None else derive_health_status(binding_error, critical=False),
            summary="Mission Control appears to be bound to localhost-only addresses." if binding_error is None else binding_error.detail,
            critical=False,
            fix=None if binding_error is None else binding_error.recommended_fix,
            commands=[_read_command("scripts/mission-control.config.json")],
            details={"daemon_host": daemon_host, "dashboard_host": dashboard_host},
            error=binding_error,
        )
    )

    authenticated = bool(codex.get("authenticated"))
    login_ready_error = None if authenticated else MissionControlError(
        code="MC-CODEX-LOGIN-UNKNOWN-001",
        breakpoint="codex_cli.auth_required",
        severity="warning",
        safe_details={"auth_mode": codex.get("auth_mode"), "login_status": login_status},
    )
    checks.append(
        _check(
            check_id="codex_authenticated",
            label="Codex authenticated",
            status="ready" if login_ready_error is None else derive_health_status(login_ready_error, critical=False),
            summary="Codex CLI is authenticated and usable for host-backed Mission Control flows." if login_ready_error is None else login_ready_error.detail,
            critical=False,
            fix=None if login_ready_error is None else login_ready_error.recommended_fix,
            commands=["codex login status", "codex login"],
            details={"auth_mode": codex.get("auth_mode"), "authenticated": authenticated},
            error=login_ready_error,
        )
    )

    device_budget_status = "degraded" if performance_profile.get("lag_risk") == "high" else "ready"
    device_budget_summary = (
        f"{device_profile.get('platform_label')} detected. Mission Control should keep live swarm activity at or below "
        f"{performance_profile.get('recommended_swarm_max_agents')} agent(s) here to avoid turning local execution into a space heater."
    )
    checks.append(
        _check(
            check_id="device_runtime_budget",
            label="Device runtime budget",
            status=device_budget_status,
            summary=device_budget_summary,
            critical=False,
            fix=(
                "Reduce swarm aggressiveness, prefer compact plans, or use a stronger remote runner when this device starts to lag."
                if device_budget_status == "degraded"
                else None
            ),
            commands=device_debug_commands[:3],
            details={"platform_profile": device_profile, "performance_profile": performance_profile},
        )
    )

    overall_degraded = any(check["status"] == "broken" and check["critical"] for check in checks)
    if overall_degraded:
        overall = "broken"
    elif any(check["status"] in {"degraded", "unknown"} and check["critical"] for check in checks):
        overall = "degraded"
    elif any(check["key"] in OVERALL_DEGRADED_CHECK_KEYS and check["status"] in {"degraded", "unknown"} for check in checks):
        overall = "degraded"
    else:
        overall = "ready"

    recommended_next_steps = list(
        dict.fromkeys(check["recommended_fix"] for check in checks if check.get("recommended_fix") and check["status"] in {"broken", "degraded", "unknown"})
    )
    safe_commands = list(
        dict.fromkeys(command for check in checks if check["status"] in {"broken", "degraded", "unknown"} for command in check.get("commands", []))
    )
    safe_commands = list(dict.fromkeys([*device_debug_commands, *safe_commands]))

    backend_ready = _component_state(
        checks,
        ["mission_control_daemon_reachable", "daemon_identity_confirmed", "runtime_directory_writable", "sqlite_db_reachable", "runner_registry_available"],
    )
    bridge_ready = _component_state(checks, ["mcp_server_reachable", "plugin_package_exists", "skill_files_exist"])
    codex_ready = _component_state(checks, ["codex_cli_detected", "codex_cli_execution_available", "codex_login_status_detectable", "codex_authenticated"])
    optional_ui_ready = _component_state(checks, ["dashboard_optional_status"])

    markdown_lines = [
        "## Plugin Health Doctor",
        "",
        f"**Overall status:** {overall}",
        f"**Backend ready:** {backend_ready}",
        f"**Bridge ready:** {bridge_ready}",
        f"**Codex host ready:** {codex_ready}",
        f"**Optional UI:** {optional_ui_ready}",
        f"**Device:** {device_profile.get('platform_label')}",
        f"**Lag guardrail:** keep live swarm at or below {performance_profile.get('recommended_swarm_max_agents')} agent(s)",
        "",
        "### Checks",
    ]
    for check in checks:
        suffix = f" ({check['code']})" if check.get("code") else ""
        markdown_lines.append(f"- **{check['label']}** [{check['status']}]{suffix}: {check['summary']}")
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
        "platform_profile": device_profile,
        "performance_profile": performance_profile,
        "device_debug_commands": device_debug_commands,
        "notes": [
            "Plugin health checks are read-only and never return daemon tokens, API keys, or secret file contents.",
            f"Detected Codex home: {get_codex_home()}",
            f"Active repo root: {identity.get('repo_root')}",
            f"Launcher root: {identity.get('launcher_root')}",
            f"Runtime root: {identity.get('runtime_root')}",
        ],
    }
