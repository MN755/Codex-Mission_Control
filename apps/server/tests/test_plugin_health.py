from __future__ import annotations

import asyncio
import os
from pathlib import Path

from daemon_state import ensure_daemon_token


def _daemon_identity(*, repo_root: str, runtime_root: str, launcher_root: str, mode: str = "daemon") -> dict[str, str]:
    return {
        "status": "ok",
        "mode": mode,
        "host": "127.0.0.1",
        "port": 8000,
        "repo_root": repo_root,
        "runtime_root": runtime_root,
        "launcher_root": launcher_root,
    }


def _bridge_headers() -> dict[str, str]:
    token_path = Path(os.environ["MISSION_CONTROL_RUNTIME_ROOT"]) / "daemon.token"
    return {"X-Mission-Control-Token": token_path.read_text(encoding="utf-8").strip()}


def test_plugin_health_ready(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [
                "mission-control-orchestrate",
                "mission-control-import-codebase",
            ],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        "plugin_health.detect_project_nvidia_gpu_diagnostics",
        lambda workspace_path: {
            "available": False,
            "status": "ready",
            "summary": "GPU cluster health lane is idle.",
            "workspace_relevant": False,
            "telemetry_status": "idle",
            "workspace_summary_status": "idle",
            "repo_mode_enabled": False,
            "repo_mode": None,
            "cluster_usable": None,
            "pending_pod_count": None,
            "gpu_memory_saturated": False,
            "gpu_memory_saturation_pct": None,
            "likely_failure_source": "unknown",
            "blocking_reasons": [],
            "observability_sources": [],
            "summary_files": [],
            "recommended_fixes": [],
            "safe_commands": [],
        },
    )

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "ready"
    assert not any(check["status"] == "broken" and check["critical"] for check in payload["checks"])
    assert any(check["key"] == "mission_control_daemon_reachable" and check["status"] == "ready" for check in payload["checks"])
    assert any(check["key"] == "mcp_server_reachable" and check["status"] == "ready" for check in payload["checks"])
    assert payload["platform_profile"]["platform_label"]
    assert payload["performance_profile"]["recommended_swarm_max_agents"] >= 1
    assert payload["device_debug_commands"]
    assert "## Plugin Health Doctor" in payload["codex_chat_markdown"]


def test_plugin_health_treats_live_loaded_mcp_as_ready_without_count_metadata(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "enabled": True}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "mcp_state": {
                "mission_control": {
                    "configured": True,
                    "app_loaded": True,
                }
            },
            "local_skills": [
                "mission-control-orchestrate",
                "mission-control-import-codebase",
            ],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    by_key = {check["key"]: check for check in payload["checks"]}
    assert by_key["mcp_server_reachable"]["status"] == "ready"
    assert by_key["mcp_tools_registered"]["status"] == "ready"
    assert "live-loaded" in by_key["mcp_tools_registered"]["summary"]


def test_plugin_health_warns_when_only_dry_run_runner_available(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    by_key = {check["key"]: check for check in payload["checks"]}
    assert by_key["runner_execution_quality"]["status"] == "degraded"
    assert "real code edits" in by_key["runner_execution_quality"]["summary"]


def test_plugin_health_uses_resolved_backend_port_in_commands(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "status": "stale", "pid_running": False})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8010, "mode": "daemon", "source": "launcher_config"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8010/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    daemon_check = next(check for check in payload["checks"] if check["key"] == "mission_control_daemon_reachable")
    assert any("8010/api/health" in command for command in daemon_check["commands"])


def test_plugin_health_degraded_when_noncritical_checks_warn(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Unavailable",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr(
        "plugin_health._probe_url",
        lambda url, timeout=2.0: (False, "URLError") if url.endswith("/dashboard") else (True, "HTTP 200"),
    )
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "degraded"
    assert any(check["key"] == "dashboard_optional_status" and check["status"] == "unknown" for check in payload["checks"])
    assert any(check["key"] == "codex_login_status_detectable" and check["status"] == "degraded" for check in payload["checks"])
    assert "dashboard reachability is optional" in payload["codex_chat_markdown"].lower()


def test_plugin_health_marks_codex_host_not_ready_when_unauthenticated(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Not authenticated",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr(
        "plugin_health._probe_url",
        lambda url, timeout=2.0: (False, "URLError") if url.endswith("/dashboard") else (True, "HTTP 200"),
    )
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    checks = {check["key"]: check for check in payload["checks"]}

    assert checks["codex_authenticated"]["status"] == "degraded"
    assert "**Codex host ready:** degraded" in payload["codex_chat_markdown"]


def test_plugin_health_degrades_when_login_status_could_not_be_queried(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "CLI path found, but login status could not be queried from this runtime.",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr(
        "plugin_health._probe_url",
        lambda url, timeout=2.0: (False, "URLError") if url.endswith("/dashboard") else (True, "HTTP 200"),
    )
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    checks = {check["key"]: check for check in payload["checks"]}

    assert checks["codex_login_status_detectable"]["status"] == "degraded"


def test_plugin_health_broken_when_critical_checks_fail(monkeypatch, client, tmp_path) -> None:
    ensure_daemon_token()

    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": False,
            "cli_execution_available": False,
            "cli_version": None,
            "login_status": "Unavailable",
            "auth_mode": None,
            "authenticated": False,
            "auth_status_detectable": True,
            "mcp_servers": [],
            "configured_mcp_servers": [],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(tmp_path / "other-repo"),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
            mode="web",
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "web"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "web", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (False, "URLError"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    assert payload["status"] == "broken"
    assert any(check["key"] == "mcp_server_reachable" and check["status"] == "broken" for check in payload["checks"])
    assert any(check["key"] == "codex_cli_detected" and check["status"] == "broken" for check in payload["checks"])
    assert payload["safe_troubleshooting_commands"]

    response = client.get("/api/plugin/health", headers=_bridge_headers())
    assert response.status_code == 200
    assert response.json()["status"] == "broken"


def test_plugin_health_surfaces_gpu_cluster_lane(monkeypatch, tmp_path) -> None:
    async def fake_inventory() -> list[dict]:
        return [{"runner_type": "dry_run", "availability": True}]

    runtime_root = tmp_path / "runtime"
    launcher_root = tmp_path / "launcher"
    monkeypatch.setattr(
        "plugin_health.detect_codex_status",
        lambda: {
            "cli_detected": True,
            "cli_execution_available": True,
            "cli_version": "codex 1.0.0",
            "login_status": "Logged in using ChatGPT",
            "auth_mode": "chatgpt",
            "authenticated": True,
            "auth_status_detectable": True,
            "mcp_servers": [{"name": "mission-control", "status": "connected"}],
            "configured_mcp_servers": [{"name": "mission-control"}],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "plugin_health.daemon_identity_snapshot",
        lambda: _daemon_identity(
            repo_root=str(__import__("plugin_health").REPO_ROOT),
            runtime_root=str(runtime_root),
            launcher_root=str(launcher_root),
        ),
    )
    monkeypatch.setattr("plugin_health.read_daemon_metadata", lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon"})
    monkeypatch.setattr(
        "plugin_health.resolve_backend_binding",
        lambda: {"host": "127.0.0.1", "port": 8000, "mode": "daemon", "source": "daemon_metadata"},
    )
    monkeypatch.setattr("plugin_health.daemon_dashboard_url", lambda project_id=None: "http://127.0.0.1:8000/dashboard")
    monkeypatch.setattr("plugin_health._probe_url", lambda url, timeout=2.0: (True, "HTTP 200"))
    monkeypatch.setattr("plugin_health.service.runners.inventory", fake_inventory)
    monkeypatch.setattr("plugin_health.RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(
        "plugin_health.detect_project_nvidia_gpu_diagnostics",
        lambda workspace_path: {
            "available": True,
            "status": "degraded",
            "summary": "GPU cluster summaries show pending pods.",
            "prometheus_url": "http://prometheus:9090",
            "workspace_relevant": True,
            "telemetry_status": "warning",
            "workspace_summary_status": "degraded",
            "repo_mode_enabled": True,
            "repo_mode": "cuda_cpp",
            "cluster_usable": False,
            "pending_pod_count": 2,
            "gpu_memory_saturated": False,
            "gpu_memory_saturation_pct": None,
            "likely_failure_source": "infrastructure",
            "blocking_reasons": ["2 GPU pod(s) are pending."],
            "observability_sources": ["Prometheus", "DCGM"],
            "summary_files": ["obs/gpu.json"],
            "recommended_fixes": ["Clear pending GPU pods before retrying the run."],
            "safe_commands": ["kubectl get pods -A --field-selector=status.phase=Pending"],
            "metrics": {},
            "alerts": [],
            "queries": {},
        },
    )

    payload = asyncio.run(__import__("plugin_health").mission_control_plugin_health())
    checks = {check["key"]: check for check in payload["checks"]}

    assert payload["status"] == "degraded"
    assert checks["gpu_cluster_health"]["status"] == "degraded"
    assert "pending pods" in checks["gpu_cluster_health"]["summary"].lower()
