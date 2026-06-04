from __future__ import annotations

import importlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from platformdirs import user_data_dir

DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8010
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _base_url(host: str, port: int) -> str:
    return f"http://{_url_host(host)}:{port}"


def _is_local_host(host: str | None) -> bool:
    return bool(host and host.strip().lower() in LOCAL_HOSTS)


class MissionControlDaemonClient:
    def __init__(self, *, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.repo_root = self._discover_repo_root()
        self.config = self._load_launcher_config()
        host = os.environ.get("MISSION_CONTROL_BACKEND_HOST", str(self.config.get("host", DEFAULT_BACKEND_HOST)))
        port = int(os.environ.get("MISSION_CONTROL_BACKEND_PORT", int(self.config.get("backendPort", DEFAULT_BACKEND_PORT))))
        self._configured_host = host
        self._configured_port = port
        self.base_url = base_url or _base_url(host, port)
        self.timeout = timeout
        self._orchestration_project_ids: dict[int, int] = {}

    def _discover_repo_root(self) -> Path | None:
        explicit = os.environ.get("MISSION_CONTROL_REPO_ROOT")
        if explicit:
            candidate = Path(explicit).expanduser().resolve()
            if (candidate / "apps" / "server" / "src" / "main.py").exists() and (candidate / "README.md").exists():
                return candidate
            return None
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "apps" / "server" / "src" / "main.py").exists() and (parent / "README.md").exists():
                return parent
        return None

    def _default_app_support_root(self) -> Path:
        explicit = os.environ.get("MISSION_CONTROL_APP_HOME")
        if explicit:
            return Path(explicit).expanduser().resolve()
        return Path(user_data_dir("Codex Mission Control", "OpenAI")).resolve()

    def _load_launcher_config(self) -> dict[str, Any]:
        server_src = (self.repo_root / "apps" / "server" / "src") if self.repo_root is not None else None
        if server_src is not None and server_src.exists() and str(server_src) not in sys.path:
            sys.path.insert(0, str(server_src))
        try:
            load_launcher_config = importlib.import_module("config").load_launcher_config

            return load_launcher_config()
        except Exception:
            if self.repo_root is None:
                return {"host": DEFAULT_BACKEND_HOST, "backendPort": DEFAULT_BACKEND_PORT}
            config_path = self.repo_root / "scripts" / "mission-control.config.json"
            if not config_path.exists():
                return {"host": DEFAULT_BACKEND_HOST, "backendPort": DEFAULT_BACKEND_PORT}
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"host": DEFAULT_BACKEND_HOST, "backendPort": DEFAULT_BACKEND_PORT}

    def _validate_localhost_binding(self) -> None:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or self._configured_host
        if not _is_local_host(host):
            raise RuntimeError(
                "Mission Control daemon startup is restricted to localhost bindings. "
                f"Refusing non-local host: {host}."
            )

    @property
    def _runtime_root(self) -> Path:
        explicit = os.environ.get("MISSION_CONTROL_RUNTIME_ROOT")
        if explicit:
            return Path(explicit).expanduser().resolve()
        if self.repo_root is not None:
            return (self.repo_root / "apps" / "server" / ".runtime").resolve()
        return (self._default_app_support_root() / "runtime").resolve()

    @property
    def _launcher_root(self) -> Path:
        explicit = os.environ.get("MISSION_CONTROL_LAUNCHER_DIR")
        if explicit:
            return Path(explicit).expanduser().resolve()
        launcher_dir = str(self.config.get("launcherLogDir", ".runtime/launcher"))
        launcher_path = Path(launcher_dir)
        if launcher_path.is_absolute():
            return launcher_path.resolve()
        if self.repo_root is not None:
            return (self.repo_root / launcher_dir).resolve()
        return (self._default_app_support_root() / launcher_dir).resolve()

    @property
    def _daemon_token_path(self) -> Path:
        return self._runtime_root / "daemon.token"

    @property
    def _server_script(self) -> Path | None:
        if self.repo_root is None:
            return None
        script_path = (self.repo_root / "apps" / "server" / "src" / "mission_control_daemon.py").resolve()
        return script_path if script_path.exists() else None

    def _daemon_launch_command(self) -> list[str]:
        if self._server_script is not None:
            return [sys.executable, str(self._server_script)]
        if importlib.util.find_spec("mission_control_daemon") is not None:
            return [sys.executable, "-m", "mission_control_daemon"]
        raise RuntimeError(
            "Mission Control daemon startup requires the source checkout or the installed "
            "`codex-mission-control-server` package."
        )

    def _daemon_working_dir(self) -> str:
        if self.repo_root is not None:
            return str(self.repo_root)
        return str(self._default_app_support_root())

    def _read_daemon_token(self) -> str | None:
        if not self._daemon_token_path.exists():
            return None
        token = self._daemon_token_path.read_text(encoding="utf-8").strip()
        return token or None

    def _headers(self, *, requires_token: bool) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if requires_token:
            token = self._read_daemon_token()
            if token:
                headers["X-Mission-Control-Token"] = token
        return headers

    def _port_in_use(self) -> bool:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or self._configured_host
        port = parsed.port or self._configured_port
        try:
            with socket.create_connection((host, port), timeout=0.75):
                return True
        except OSError:
            return False

    def _healthcheck(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/api/health")
                return response.status_code == 200 and response.json().get("status") == "ok"
        except Exception:
            return False

    def _daemon_identity(self) -> dict[str, Any] | None:
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/api/diagnostics/identity", headers=self._headers(requires_token=True))
            if response.status_code >= 400:
                return None
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _validate_running_daemon_identity(self) -> None:
        identity = self._daemon_identity()
        if not identity:
            return
        expected_repo = str(self.repo_root) if self.repo_root is not None else ""
        actual_repo = str(identity.get("repo_root") or "")
        actual_port = int(identity.get("port") or 0)
        actual_mode = str(identity.get("mode") or "unknown")
        if expected_repo and actual_repo and actual_repo != expected_repo:
            raise RuntimeError(
                "Mission Control daemon is healthy, but the current port belongs to a different repository checkout. "
                f"expected_repo_root={expected_repo} actual_repo_root={actual_repo} configured_base_url={self.base_url}."
            )
        if actual_port and actual_port != self._configured_port:
            raise RuntimeError(
                "Mission Control daemon is healthy, but it reported a different effective port than the current launcher config. "
                f"configured_port={self._configured_port} actual_port={actual_port} configured_base_url={self.base_url}."
            )
        if actual_mode != "daemon":
            raise RuntimeError(
                "Mission Control backend is reachable, but it is not running in daemon mode. "
                f"configured_base_url={self.base_url} actual_mode={actual_mode}."
            )

    def ensure_daemon_running(self) -> None:
        self._validate_localhost_binding()
        if self._healthcheck():
            self._validate_running_daemon_identity()
            return
        if self._port_in_use():
            parsed = urlparse(self.base_url)
            effective_host = parsed.hostname or self._configured_host
            effective_port = parsed.port or self._configured_port
            raise RuntimeError(
                "Mission Control daemon port is already in use but the health check failed. "
                f"configured_base_url={self.base_url} configured_host={effective_host} configured_port={effective_port}. "
                f"expected_repo_root={self.repo_root}. "
                "Likely causes: stale launcher config, another localhost service on the same port, or a dead Mission Control process with stale metadata."
            )
        self._launcher_root.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.setdefault("MISSION_CONTROL_SERVER_MODE", "daemon")
        env.setdefault("MISSION_CONTROL_BACKEND_HOST", urlparse(self.base_url).hostname or self._configured_host)
        env.setdefault("MISSION_CONTROL_BACKEND_PORT", str(urlparse(self.base_url).port or self._configured_port))
        if self.repo_root is not None:
            env.setdefault("MISSION_CONTROL_REPO_ROOT", str(self.repo_root))
        else:
            env.setdefault("MISSION_CONTROL_APP_HOME", str(self._default_app_support_root()))
        stdout_handle = open(self._launcher_root / "daemon.stdout.log", "a", encoding="utf-8")
        stderr_handle = open(self._launcher_root / "daemon.stderr.log", "a", encoding="utf-8")
        kwargs: dict[str, Any] = {"cwd": self._daemon_working_dir(), "env": env, "stdout": stdout_handle, "stderr": stderr_handle}
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(self._daemon_launch_command(), **kwargs)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self._healthcheck():
                self._validate_running_daemon_identity()
                return
            time.sleep(0.5)
        raise RuntimeError("Mission Control daemon did not become healthy in time.")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        requires_token: bool = True,
    ) -> Any:
        self.ensure_daemon_running()
        headers = self._headers(requires_token=requires_token)
        with httpx.Client(timeout=self.timeout) as client:
            response = client.request(method, f"{self.base_url}{path}", json=json_body, params=params, headers=headers)
        if response.status_code >= 400:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"Mission Control daemon request failed ({response.status_code}): {detail}")
        return response.json() if response.content else None

    def _safe_short(self, value: Any, *, fallback: str = "") -> str:
        text = str(value or fallback).strip()
        return text[:240] if text else fallback

    def _maybe_orchestration_id(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> int | None:
        if orchestration_id is not None:
            return orchestration_id
        if project_id is None:
            return None
        session = self.active_project_orchestration(project_id)
        return int(session["id"]) if session else None

    def _remember_orchestration_project(self, orchestration_id: int | None, project_id: int | None) -> None:
        if orchestration_id is None or project_id is None:
            return
        self._orchestration_project_ids[int(orchestration_id)] = int(project_id)

    def _project_id_for_orchestration(self, orchestration_id: int, project_id: int | None = None) -> int:
        if project_id is not None:
            self._remember_orchestration_project(orchestration_id, project_id)
            return int(project_id)
        cached = self._orchestration_project_ids.get(int(orchestration_id))
        if cached is not None:
            return cached
        raise RuntimeError(
            "Mission Control requires a project_id for uncached orchestration lookups. "
            "Start or fetch the orchestration through a project-scoped flow first."
        )

    def daemon_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/daemon/status", requires_token=True)

    def plugin_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/plugin/health", requires_token=True)

    def plugin_health_summary(self) -> dict[str, Any]:
        return self.plugin_health()

    def get_auth_state(self) -> dict[str, Any]:
        return self._request("GET", "/api/system/auth-state")

    def get_runners_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/runners/status")

    def get_headless_config(self) -> dict[str, Any]:
        return self._request("GET", "/api/headless/config")

    def get_codex_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/system/codex-status")

    def attach_workspace(
        self,
        *,
        workspace_path: str,
        project_name: str | None = None,
        mode: str = "auto",
        read_only_first: bool = True,
        attach_policy: str = "reuse_existing",
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/headless/attach-workspace",
            json_body={
                "workspace_path": workspace_path,
                "project_name": project_name,
                "mode": mode,
                "read_only_first": read_only_first,
                "attach_policy": attach_policy,
            },
        )
        project = payload.get("project") if isinstance(payload, dict) else None
        orchestration = payload.get("orchestration") if isinstance(payload, dict) else None
        if isinstance(project, dict) and isinstance(orchestration, dict):
            self._remember_orchestration_project(orchestration.get("id"), project.get("id"))
        return payload

    def start_task(self, *, project_id: int, user_request: str, source: str = "codex_plugin", orchestration_id: int | None = None) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/orchestrations",
            json_body={"project_id": project_id, "user_request": user_request, "source": source, "orchestration_id": orchestration_id},
        )
        if isinstance(payload, dict):
            self._remember_orchestration_project(payload.get("id"), project_id)
        return payload

    def list_projects(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/projects")

    def get_project(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}")

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/health", requires_token=False)

    def get_diagnostics_identity(self) -> dict[str, Any]:
        return self._request("GET", "/api/diagnostics/identity")

    def get_auth_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/system/auth-jobs/{job_id}")

    def get_headless_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/headless/health")

    def get_profile(self) -> dict[str, Any]:
        return self._request("GET", "/api/profile")

    def get_headless_diagnostic_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/headless/diagnostic-summary")

    def get_orchestration(self, orchestration_id: int, *, project_id: int | None = None) -> dict[str, Any]:
        resolved_project_id = self._project_id_for_orchestration(orchestration_id, project_id)
        payload = self._request("GET", f"/api/projects/{resolved_project_id}/orchestrations/{orchestration_id}")
        if isinstance(payload, dict):
            self._remember_orchestration_project(payload.get("id"), payload.get("project_id") or resolved_project_id)
        return payload

    def active_project_orchestration(self, project_id: int) -> dict[str, Any] | None:
        payload = self._request("GET", f"/api/projects/{project_id}/orchestrations/active")
        if isinstance(payload, dict):
            self._remember_orchestration_project(payload.get("id"), payload.get("project_id") or project_id)
        return payload

    def _resolve_orchestration_id(self, *, orchestration_id: int | None = None, project_id: int | None = None, action: str) -> int:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is None:
            raise RuntimeError(f"{action} requires an orchestration_id or a project with an active orchestration.")
        return resolved_id

    def get_status(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._resolve_orchestration_id(
            orchestration_id=orchestration_id,
            project_id=project_id,
            action="Mission Control status",
        )
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        payload = self._request("GET", f"/api/projects/{resolved_project_id}/orchestrations/{resolved_id}/status")
        if isinstance(payload, dict):
            self._remember_orchestration_project(payload.get("orchestration_id") or resolved_id, payload.get("project_id") or resolved_project_id)
        return payload

    def get_status_summary(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is not None:
            resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
            return self._request("GET", f"/api/orchestrations/{resolved_id}/status-summary", params={"project_id": resolved_project_id})
        if project_id is None:
            raise RuntimeError("Mission Control status summary requires an orchestration_id or project_id.")
        return self._request("GET", f"/api/projects/{project_id}/status-summary")

    def get_pending_decisions(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> list[dict[str, Any]]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is None:
            if project_id is None:
                return []
            return self._request("GET", f"/api/projects/{project_id}/pending-decisions")
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("GET", f"/api/projects/{resolved_project_id}/orchestrations/{resolved_id}/pending-decisions")

    def get_decision_bridge_message(self, decision_id: int, *, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/decisions/{decision_id}/bridge-message")

    def answer_decision(self, *, decision_id: int, project_id: int, option_id: str, selected_text: str, free_text: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/decisions/{decision_id}/answer",
            params={"project_id": project_id},
            json_body={"option_id": option_id, "selected_text": selected_text, "free_text": free_text},
        )

    def pause(self, orchestration_id: int | None = None, *, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._resolve_orchestration_id(
            orchestration_id=orchestration_id,
            project_id=project_id,
            action="Pause",
        )
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("POST", f"/api/orchestrations/{resolved_id}/pause", params={"project_id": resolved_project_id}, json_body={})

    def resume(self, orchestration_id: int | None = None, *, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._resolve_orchestration_id(
            orchestration_id=orchestration_id,
            project_id=project_id,
            action="Resume",
        )
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("POST", f"/api/orchestrations/{resolved_id}/resume", params={"project_id": resolved_project_id}, json_body={})

    def get_handoff(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._resolve_orchestration_id(
            orchestration_id=orchestration_id,
            project_id=project_id,
            action="Mission Control handoff lookup",
        )
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("GET", f"/api/projects/{resolved_project_id}/orchestrations/{resolved_id}/handoff")

    def get_event_digest(
        self,
        *,
        orchestration_id: int | None = None,
        project_id: int | None = None,
        window: str = "last_15_minutes",
    ) -> dict[str, Any]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is not None:
            resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
            return self._request("GET", f"/api/orchestrations/{resolved_id}/event-digest", params={"window": window, "project_id": resolved_project_id})
        if project_id is None:
            raise RuntimeError("Event digest requires an orchestration_id or project_id.")
        return self._request("GET", f"/api/projects/{project_id}/event-digest", params={"window": window})

    def get_handoff_summary(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is not None:
            resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
            return self._request("GET", f"/api/orchestrations/{resolved_id}/handoff-summary", params={"project_id": resolved_project_id})
        if project_id is None:
            raise RuntimeError("Handoff summary requires an orchestration_id or project_id.")
        return self._request("GET", f"/api/projects/{project_id}/handoff-summary")

    def get_orchestration_events(self, orchestration_id: int | None = None, *, project_id: int | None = None) -> list[dict[str, Any]]:
        resolved_id = self._resolve_orchestration_id(
            orchestration_id=orchestration_id,
            project_id=project_id,
            action="Orchestration events",
        )
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("GET", f"/api/projects/{resolved_project_id}/orchestrations/{resolved_id}/events")

    def get_agents(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/agents")

    def get_agent_logs(self, project_id: int, agent_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/agents/{agent_id}/logs")

    def get_agent_contracts(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/agent-contracts")

    def get_pending_questions(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/questions/pending")

    def get_pending_approvals(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/approvals/pending")

    def get_project_handoff(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/handoff", requires_token=True)

    def get_handoff_evidence(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/handoff/evidence")

    def get_handoff_evidence_preview(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/handoff/evidence/preview")

    def get_decision_ledger(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/decision-ledger")

    def get_path_locks(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/path-locks")

    def get_operator_snapshot(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/operator-snapshot")

    def get_instincts_preview(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/instincts/preview")

    def get_verification_brief(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/verification-brief")

    def get_capability_report(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/capability-report")

    def get_capability_section(self, project_id: int, section_key: str) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/capability-report/{section_key}")

    def get_workspace_tooling(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/workspace-tooling")

    def get_project_workspace(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/workspace")

    def get_project_action(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/action")

    def list_project_actions(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/actions")

    def get_manager_messages(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/manager/messages")

    def get_manager_queue(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/manager/queue")

    def get_project_tasks(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/tasks")

    def get_project_events(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/events")

    def list_handoffs(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/handoffs")

    def list_diagnostic_reports(self, project_id: int | None = None) -> list[dict[str, Any]]:
        params = {"project_id": project_id} if project_id is not None else None
        return self._request("GET", "/api/diagnostics/reports", params=params)

    def get_profile_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/profile/summary")

    def get_subagent_policy(self) -> dict[str, Any]:
        return self._request("GET", "/api/subagent-policy")

    def get_subagent_policy_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/subagent-policy/summary")

    def get_preferences(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/preferences")

    def get_global_preference_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/preferences/summary")

    def get_project_preferences(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/preferences")

    def get_project_preference_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/preferences/summary")

    def get_effective_preferences(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/preferences/effective")

    def list_playbooks(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/playbooks")

    def get_playbook_catalog_entry(self, playbook_key: str) -> dict[str, Any]:
        return self._request("GET", f"/api/playbooks/{playbook_key}")

    def get_runbook(self, project_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/projects/{project_id}/runbook")

    def get_runbook_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/runbook/summary")

    def get_recovery_plans(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/recovery-plans")

    def get_recovery_plans_preview(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/recovery-plans/preview")

    def get_playbook(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/playbook")

    def get_playbook_recommendations(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/playbook/recommendations")

    def get_latest_swarm_simulation(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/swarm/simulations/latest")

    def get_execution_policy_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/execution-policy/summary")

    def get_coordination_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/coordination/summary")

    def get_integrations_catalog(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/integrations/catalog")

    def get_integration_connections(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/integrations/connections")

    def get_integration_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/integrations/health")

    def get_system_status(self, project_id: int | None = None) -> dict[str, Any]:
        if project_id is None:
            return self._request("GET", "/api/system/status")
        return self._request("GET", "/api/system/status", params={"project_id": project_id})

    def get_startup_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/startup/status")

    def get_dashboard_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/dashboard/summary")

    def get_widget_catalog(self, scope: str | None = None) -> list[dict[str, Any]]:
        if scope is not None:
            return self._request("GET", f"/api/widgets/catalog/{scope}")
        return self._request("GET", "/api/widgets/catalog")

    def list_widget_instances(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/widgets/instances")

    def get_project_widget_instances(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/widgets/instances")

    def get_widget_instance_data(self, instance_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/widgets/instances/{instance_id}/data")

    def get_project_widget_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/widgets/summary")

    def get_agent_archetypes(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/agent-archetypes")

    def get_capability_benchmarks(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/capabilities/benchmarks")

    def get_capability_matrix(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/capabilities/matrix")

    def get_agent_reputation(self, project_id: int | None = None) -> list[dict[str, Any]]:
        if project_id is None:
            return self._request("GET", "/api/agents/reputation")
        return self._request("GET", f"/api/projects/{project_id}/agents/reputation")

    def import_host_integrations(self) -> dict[str, Any]:
        return self._request("POST", "/api/integrations/import-host-state")

    def get_project_integrations(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/integrations")

    def get_project_integration_family(self, project_id: int, family: str) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/integrations/{family}")

    def get_context_packs(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/context-packs")

    def get_context_pack(self, context_pack_id: int, *, project_id: int | None = None) -> dict[str, Any]:
        params = {"project_id": project_id} if project_id is not None else None
        return self._request("GET", f"/api/context-packs/{context_pack_id}", params=params)

    def preview_project_integration_action(self, project_id: int, family: str, action_id: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/integrations/{family}/actions/{action_id}/preview",
            json_body={"params": params or {}, "confirmed": False},
        )

    def execute_project_integration_action(
        self,
        project_id: int,
        family: str,
        action_id: str,
        *,
        params: dict[str, Any] | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/integrations/{family}/actions/{action_id}/execute",
            json_body={"params": params or {}, "confirmed": confirmed},
        )

    def get_tensorflow_feature_catalog(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/tensorflow/features")

    def get_tensorflow_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
        params = {"variant": variant} if variant else None
        return self._request("GET", f"/api/projects/{project_id}/tensorflow/features/{feature_id}", params=params)

    def get_pytorch_feature_catalog(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/pytorch/features")

    def get_pytorch_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
        params = {"variant": variant} if variant else None
        return self._request("GET", f"/api/projects/{project_id}/pytorch/features/{feature_id}", params=params)

    def get_spatial_feature_catalog(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/spatial/features")

    def get_spatial_feature_bundle(self, project_id: int, feature_id: str, *, variant: str | None = None) -> dict[str, Any]:
        params = {"variant": variant} if variant else None
        return self._request("GET", f"/api/projects/{project_id}/spatial/features/{feature_id}", params=params)

    def search_codebase(
        self,
        project_id: int,
        *,
        pattern: str,
        glob: str | None = None,
        max_matches: int = 40,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/codebase/search",
            json_body={"pattern": pattern, "glob": glob, "max_matches": max_matches},
        )

    def get_webwright_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/webwright")

    def get_nvidia_dynamo_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/dynamo")

    def get_nvidia_nim_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/nim")

    def get_nvidia_aiq_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/aiq")

    def run_nvidia_aiq_research(
        self,
        project_id: int,
        *,
        query: str,
        agent_type: str = "deep_researcher",
        timeout_seconds: int = 90,
        poll_interval_seconds: float = 2.0,
        expiry_seconds: int = 3600,
        endpoint_override: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/nvidia/aiq/research",
            json_body={
                "query": query,
                "agent_type": agent_type,
                "timeout_seconds": timeout_seconds,
                "poll_interval_seconds": poll_interval_seconds,
                "expiry_seconds": expiry_seconds,
                "endpoint_override": endpoint_override,
            },
        )

    def get_nvidia_gpu_diagnostics(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/gpu-diagnostics")

    def get_nvidia_local_runtime_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/local-runtime")

    def get_nvidia_validation_plan(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/nvidia/validation-plan")

    def get_codebase_map(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/codebase-map", requires_token=True)

    def get_codebase_understanding(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/codebase-understanding", requires_token=True)

    def set_import_interview_choice(self, project_id: int, choice: str) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/import/interview-choice", json_body={"choice": choice})

    def get_import_safety(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/import-safety")

    def update_import_safety(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/projects/{project_id}/import-safety", json_body=payload)

    def get_project_settings(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/settings")

    def update_project_settings(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/api/projects/{project_id}/settings", json_body=payload)

    def get_tool_catalog(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/tools")

    def get_skills(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/skills")

    def set_tool_permission(self, tool_id: str, permission_policy: str) -> dict[str, Any]:
        return self._request("PUT", f"/api/tools/{tool_id}/permission", json_body={"permission_policy": permission_policy})

    def get_project_understanding(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/understanding")

    def get_interview(self, project_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/projects/{project_id}/interview")

    def get_plan(self, project_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/projects/{project_id}/plan")

    def get_reservations(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/reservations")

    def get_project_subagent_batches(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/subagent-batches")

    def get_subagent_batch(self, project_id: int, batch_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/subagent-batches/{batch_id}")

    def get_swarm_preferences(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/swarm/preferences")

    def update_swarm_preferences(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get_swarm_preferences(project_id)
        merged = {
            "optimization_mode": payload.get("optimization_mode", current.get("optimization_mode")),
            "swarm_aggressiveness": payload.get("swarm_aggressiveness", current.get("swarm_aggressiveness")),
            "max_agents": payload.get("max_agents", current.get("max_agents")),
            "require_approval_above_agent_count": payload.get(
                "require_approval_above_agent_count", current.get("require_approval_above_agent_count")
            ),
            "allow_dynamic_spawning": payload.get("allow_dynamic_spawning", current.get("allow_dynamic_spawning")),
            "allow_dynamic_retirement": payload.get("allow_dynamic_retirement", current.get("allow_dynamic_retirement")),
            "docs_depth": payload.get("docs_depth", current.get("docs_depth")),
            "testing_depth": payload.get("testing_depth", current.get("testing_depth")),
        }
        return self._request("PUT", f"/api/projects/{project_id}/swarm/preferences", json_body=merged)

    def generate_swarm_plan(self, project_id: int, *, goal: str | None = None, milestone_id: int | None = None) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/swarm/plan", json_body={"goal": goal, "milestone_id": milestone_id})

    def get_swarm_plan(self, project_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/projects/{project_id}/swarm/plan")

    def get_swarm_events(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/swarm/events")

    def approve_swarm_plan(self, project_id: int, swarm_plan_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/approve", json_body={})

    def get_risks(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/risks")

    def get_risk_summary(self, project_id: int | None = None) -> dict[str, Any]:
        if project_id is None:
            return self._request("GET", "/api/risks/summary")
        return self._request("GET", f"/api/projects/{project_id}/risks/summary")

    def get_common_risks(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/risks/common")

    def get_scope_creep(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/scope-creep")

    def get_validation_coverage(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/validation-coverage")

    def get_validation_coverage_summary(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/validation-coverage/summary")

    def get_validation_summary(self, project_id: int) -> dict[str, Any]:
        return self.get_validation_coverage_summary(project_id)

    def get_agents_md_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/agents-md/status")

    def get_security_policy(self, project_id: int | None = None) -> dict[str, Any]:
        if project_id is None:
            return self._request("GET", "/api/security/policy")
        return self._request("GET", f"/api/projects/{project_id}/security/policy")

    def get_security_audit_log(self, project_id: int | None = None) -> list[dict[str, Any]]:
        if project_id is None:
            return self._request("GET", "/api/security/audit-log")
        return self._request("GET", f"/api/projects/{project_id}/security/audit-log")

    def propose_agents_md(self, project_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/agents-md/propose", json_body={})

    def send_manager_message(self, project_id: int, message: str) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/manager/messages", json_body={"message": message})

    def get_safe_mode(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/safe-mode")

    def enable_safe_mode(self, project_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/safe-mode", json_body={})

    def list_snapshots(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/snapshots")

    def list_swarm_simulations(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/swarm/simulations")

    def create_snapshot(
        self,
        project_id: int,
        *,
        label: str,
        description: str,
        created_before_task_id: int | None = None,
        created_before_agent_id: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/snapshots",
            json_body={
                "label": label,
                "description": description,
                "created_before_task_id": created_before_task_id,
                "created_before_agent_id": created_before_agent_id,
            },
        )

    def get_snapshot_restore_plan(self, project_id: int, snapshot_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/snapshots/{snapshot_id}/restore-plan")

    def list_recovery_plans(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/recovery-plans")

    def create_recovery_plan(
        self,
        project_id: int,
        *,
        trigger_type: str,
        trigger_summary: str,
        related_agent_id: int | None = None,
        related_task_id: int | None = None,
        suggested_actions_json: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/projects/{project_id}/recovery-plans",
            json_body={
                "trigger_type": trigger_type,
                "trigger_summary": trigger_summary,
                "related_agent_id": related_agent_id,
                "related_task_id": related_task_id,
                "suggested_actions_json": suggested_actions_json or [],
            },
        )

    def get_diagnostics(self, *, project_id: int | None = None, orchestration_id: int | None = None) -> dict[str, Any]:
        plugin_health = self.plugin_health()
        resolved_project_id = project_id
        if resolved_project_id is None and orchestration_id is not None:
            session = self.get_orchestration(orchestration_id, project_id=project_id)
            resolved_project_id = int(session["project_id"])
        reports = self.list_diagnostic_reports(project_id=resolved_project_id)
        latest_report = reports[0] if reports else None
        status = None
        if resolved_project_id is not None:
            try:
                status = self.get_status(project_id=resolved_project_id)
            except Exception:
                status = None
        return {
            "project_id": resolved_project_id,
            "plugin_health": plugin_health.get("status"),
            "health_checks": plugin_health.get("checks", []),
            "recommended_fixes": plugin_health.get("recommended_fixes", plugin_health.get("recommended_next_steps", [])),
            "recent_reports": reports[:5],
            "platform_profile": latest_report.get("platform_profile", {}) if isinstance(latest_report, dict) else {},
            "performance_profile": latest_report.get("performance_profile", {}) if isinstance(latest_report, dict) else {},
            "gpu_cluster_health": plugin_health.get("gpu_cluster_health", {}),
            "safe_debug_commands": latest_report.get("safe_debug_commands", []) if isinstance(latest_report, dict) else [],
            "bundle_path": latest_report.get("bundle_path") if isinstance(latest_report, dict) else None,
            "orchestration_status": status.get("orchestration_status") if status else None,
            "manager_status": status.get("manager_status") if status else None,
            "nvidia_gpu_diagnostics": self.get_nvidia_gpu_diagnostics(resolved_project_id) if resolved_project_id is not None else None,
        }

    def import_existing_codebase(
        self,
        *,
        workspace_path: str,
        project_name: str | None = None,
        attach_policy: str = "reuse_existing",
        read_only_first: bool = True,
    ) -> dict[str, Any]:
        attached = self.attach_workspace(
            workspace_path=workspace_path,
            project_name=project_name,
            mode="existing_codebase",
            read_only_first=read_only_first,
            attach_policy=attach_policy,
        )
        project = attached.get("project") or {}
        project_id = project.get("id")
        codebase_map = self.get_codebase_map(int(project_id)) if project_id is not None else None
        understanding = self.get_codebase_understanding(int(project_id)) if project_id is not None else None
        return {
            "attach": attached,
            "project_id": project_id,
            "codebase_map": codebase_map,
            "codebase_understanding": understanding,
        }

    def request_recovery_options(
        self, *, project_id: int | None = None, orchestration_id: int | None = None, user_context: str | None = None
    ) -> dict[str, Any]:
        resolved_project_id = project_id
        if resolved_project_id is None and orchestration_id is not None:
            session = self.get_orchestration(orchestration_id, project_id=project_id)
            resolved_project_id = int(session["project_id"])
        if resolved_project_id is None:
            raise RuntimeError("Recovery options require a project_id or orchestration_id.")
        message = "Mission Control bridge request: summarize the current blocker and safest recovery options for Codex chat."
        if user_context:
            message = f"{message} Context: {user_context}"
        response = self.send_manager_message(resolved_project_id, message)
        return {
            "project_id": resolved_project_id,
            "status": "requested",
            "manager_message_id": response.get("id"),
            "content_markdown": response.get("content_markdown", ""),
        }

    def request_recovery_plan(
        self,
        *,
        project_id: int | None = None,
        orchestration_id: int | None = None,
        trigger_type: str = "bridge_request",
        trigger_summary: str,
        related_agent_id: int | None = None,
        related_task_id: int | None = None,
        suggested_actions_json: list[str] | None = None,
    ) -> dict[str, Any]:
        resolved_project_id = project_id
        if resolved_project_id is None and orchestration_id is not None:
            session = self.get_orchestration(orchestration_id, project_id=project_id)
            resolved_project_id = int(session["project_id"])
        if resolved_project_id is None:
            raise RuntimeError("Recovery plan requests require a project_id or orchestration_id.")
        return self.create_recovery_plan(
            resolved_project_id,
            trigger_type=trigger_type,
            trigger_summary=trigger_summary,
            related_agent_id=related_agent_id,
            related_task_id=related_task_id,
            suggested_actions_json=suggested_actions_json,
        )

    def _summarize_status(self, status: dict[str, Any]) -> dict[str, Any]:
        agents = []
        for agent in status.get("active_agents", [])[:8]:
            agents.append(
                {
                    "name": agent.get("name"),
                    "status": agent.get("status"),
                    "role": agent.get("role"),
                    "current_action": agent.get("current_action"),
                }
            )
        recent_events = []
        for event in status.get("recent_events", [])[:6]:
            recent_events.append(
                {
                    "event_type": event.get("event_type"),
                    "summary": self._safe_short(event.get("message") or event.get("summary") or event.get("payload_json")),
                }
            )
        return {
            "orchestration_id": status.get("orchestration_id"),
            "project_id": status.get("project_id"),
            "project_name": status.get("project_name"),
            "orchestration_status": status.get("orchestration_status"),
            "current_phase": status.get("current_phase"),
            "manager_status": status.get("manager_status"),
            "active_agents": agents,
            "pending_decisions_count": status.get("pending_decisions_count", 0),
            "current_blockers": status.get("current_blockers", []),
            "next_expected_action": status.get("next_expected_action"),
            "user_action_required": status.get("user_action_required", False),
            "handoff_readiness": status.get("handoff_readiness"),
            "recent_events": recent_events,
        }

    def _summarize_events(self, orchestration_id: int, events: list[dict[str, Any]]) -> dict[str, Any]:
        summarized = []
        for event in events[:10]:
            summarized.append(
                {
                    "event_type": event.get("event_type"),
                    "created_at": event.get("created_at"),
                    "summary": self._safe_short(event.get("payload_json")),
                }
            )
        return {
            "orchestration_id": orchestration_id,
            "event_count": len(events),
            "latest_event_at": events[0].get("created_at") if events else None,
            "recent_events": summarized,
        }

    def _summarize_project_status(self, project: dict[str, Any], status: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "project_id": project.get("id"),
            "project_name": project.get("name"),
            "project_status": project.get("status"),
            "workspace_path": project.get("workspace_path"),
            "handoff_status": project.get("handoff_status"),
            "orchestration_status": status.get("orchestration_status") if status else "not_running",
            "current_phase": status.get("current_phase") if status else None,
            "manager_status": status.get("manager_status") if status else project.get("latest_activity"),
            "next_expected_action": status.get("next_expected_action") if status else "Attach or start a Mission Control task.",
            "handoff_readiness": status.get("handoff_readiness") if status else project.get("handoff_status"),
        }

    def _summarize_projects(self, projects: list[dict[str, Any]]) -> dict[str, Any]:
        active = [project for project in projects if project.get("archived_at") is None]
        pinned = [project for project in projects if project.get("pinned")]
        return {
            "project_count": len(projects),
            "active_project_count": len(active),
            "pinned_project_count": len(pinned),
            "projects": [
                {
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "status": project.get("status"),
                    "display_status": project.get("display_status"),
                    "runner_mode": project.get("runner_mode"),
                    "manager_mode": project.get("manager_mode"),
                    "pinned": project.get("pinned", False),
                    "handoff_status": project.get("handoff_status"),
                    "latest_milestone": project.get("latest_milestone"),
                    "latest_activity": project.get("latest_activity"),
                    "last_opened_at": project.get("last_opened_at"),
                    "updated_at": project.get("updated_at"),
                }
                for project in projects[:20]
            ],
        }

    def _summarize_project_details(self, project: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project.get("id"),
            "project_name": project.get("name"),
            "slug": project.get("slug"),
            "idea": project.get("idea"),
            "workspace_path": project.get("workspace_path"),
            "status": project.get("status"),
            "display_status": project.get("display_status"),
            "runner_mode": project.get("runner_mode"),
            "manager_mode": project.get("manager_mode"),
            "source_type": project.get("source_type"),
            "source_path": project.get("source_path"),
            "import_mode": project.get("import_mode"),
            "scan_status": project.get("scan_status"),
            "write_permission_status": project.get("write_permission_status"),
            "pinned": project.get("pinned", False),
            "archived_at": project.get("archived_at"),
            "handoff_status": project.get("handoff_status"),
            "latest_milestone": project.get("latest_milestone"),
            "latest_activity": project.get("latest_activity"),
            "docs_path": project.get("docs_path"),
            "created_at": project.get("created_at"),
            "updated_at": project.get("updated_at"),
            "last_opened_at": project.get("last_opened_at"),
        }

    def _summarize_agents(self, project_id: int, agents: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "agent_count": len(agents),
            "agents": [
                {
                    "id": agent.get("id"),
                    "name": agent.get("name"),
                    "kind": agent.get("kind"),
                    "status": agent.get("status"),
                    "role": agent.get("role"),
                    "current_action": agent.get("current_action"),
                    "locked_paths": agent.get("locked_paths_json") or [],
                }
                for agent in agents[:12]
            ],
        }

    def _summarize_agent_logs(self, project_id: int, agent_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        content = str(payload.get("content") or "")
        lines = content.splitlines()
        tail_lines = lines[-20:]
        return {
            "project_id": project_id,
            "agent_id": agent_id,
            "logs_path": payload.get("logs_path"),
            "line_count": len(lines),
            "character_count": len(content),
            "has_content": bool(content.strip()),
            "tail_lines": tail_lines,
            "tail_preview": "\n".join(tail_lines),
        }

    def _summarize_agent_contracts(self, project_id: int, contracts: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "contract_count": len(contracts),
            "contracts": [
                {
                    "id": contract.get("id"),
                    "agent_name": contract.get("agent_name"),
                    "archetype": contract.get("archetype"),
                    "status": contract.get("status"),
                    "mission": self._safe_short(contract.get("mission")),
                    "allowed_paths": (contract.get("allowed_paths_json") or [])[:8],
                    "allowed_tools": (contract.get("allowed_tools_json") or [])[:8],
                    "validation_required": (contract.get("validation_required_json") or [])[:8],
                }
                for contract in contracts[:12]
            ],
        }

    def _summarize_pending_decisions(self, project_id: int, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "decision_count": len(decisions),
            "decisions": [
                {
                    "id": decision.get("id"),
                    "decision_type": decision.get("decision_type"),
                    "title": decision.get("title"),
                    "message": self._safe_short(decision.get("message")),
                    "risk_level": decision.get("risk_level"),
                    "recommended_option": decision.get("recommended_option"),
                    "options": decision.get("options", [])[:4],
                    "status": decision.get("status"),
                }
                for decision in decisions[:12]
            ],
        }

    def _summarize_pending_questions(self, project_id: int, questions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "question_count": len(questions),
            "questions": [
                {
                    "id": question.get("id"),
                    "category": question.get("category"),
                    "question": self._safe_short(question.get("question")),
                    "impact": self._safe_short(question.get("impact")),
                    "status": question.get("status"),
                    "options": list(question.get("options") or [])[:4],
                }
                for question in questions[:12]
            ],
        }

    def _summarize_pending_approvals(self, project_id: int, approvals: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "approval_count": len(approvals),
            "approvals": [
                {
                    "id": approval.get("id"),
                    "kind": approval.get("kind"),
                    "summary": self._safe_short(approval.get("summary")),
                    "risk_level": approval.get("risk_level"),
                    "status": approval.get("status"),
                }
                for approval in approvals[:12]
            ],
        }

    def _summarize_decision_ledger(self, project_id: int, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "decision_count": len(decisions),
            "recent_decisions": [
                {
                    "id": decision.get("id"),
                    "decision_type": decision.get("decision_type"),
                    "title": decision.get("title"),
                    "decision": self._safe_short(decision.get("decision")),
                    "reason": self._safe_short(decision.get("reason")),
                    "made_by": decision.get("made_by"),
                    "reversible": decision.get("reversible", False),
                    "created_at": decision.get("created_at"),
                }
                for decision in decisions[:15]
            ],
        }

    def _summarize_path_locks(self, project_id: int, locks: list[dict[str, Any]]) -> dict[str, Any]:
        active = [entry for entry in locks if entry.get("status") == "active"]
        waiting = [entry for entry in locks if entry.get("status") == "waiting"]
        return {
            "project_id": project_id,
            "lock_count": len(locks),
            "active_lock_count": len(active),
            "waiting_lock_count": len(waiting),
            "locks": [
                {
                    "id": entry.get("id"),
                    "path_pattern": entry.get("path_pattern"),
                    "owner_agent_id": entry.get("owner_agent_id"),
                    "owner_task_id": entry.get("owner_task_id"),
                    "status": entry.get("status"),
                    "reason": self._safe_short(entry.get("reason")),
                }
                for entry in locks[:20]
            ],
        }

    def _summarize_operator_snapshot(self, project_id: int, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": snapshot.get("project_name"),
            "project_status": snapshot.get("project_status"),
            "overall_status": snapshot.get("overall_status"),
            "orchestration_status": snapshot.get("orchestration_status"),
            "handoff_status": snapshot.get("handoff_status"),
            "current_action": snapshot.get("current_action"),
            "pending_approvals_count": snapshot.get("pending_approvals_count", 0),
            "pending_questions_count": snapshot.get("pending_questions_count", 0),
            "active_agent_count": snapshot.get("active_agent_count", 0),
            "current_focus": list(snapshot.get("current_focus") or [])[:6],
            "top_risks": list(snapshot.get("top_risks") or [])[:6],
            "recent_events": list(snapshot.get("recent_events") or [])[:6],
            "validation_gap_count": snapshot.get("validation_gap_count", 0),
            "swarm_mode": snapshot.get("swarm_mode"),
            "recommended_next_action": snapshot.get("recommended_next_action"),
            "performance_note": snapshot.get("performance_note"),
            "generated_at": snapshot.get("generated_at"),
        }

    def _summarize_instincts_preview(self, project_id: int, preview: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "instinct_count": preview.get("instinct_count", 0),
            "instincts": [
                {
                    "key": instinct.get("key"),
                    "title": instinct.get("title"),
                    "trigger": self._safe_short(instinct.get("trigger")),
                    "rule": self._safe_short(instinct.get("rule")),
                    "confidence": instinct.get("confidence"),
                    "tags": list(instinct.get("tags") or [])[:6],
                    "evidence": list(instinct.get("evidence") or [])[:4],
                }
                for instinct in list(preview.get("instincts") or [])[:6]
            ],
            "generated_at": preview.get("generated_at"),
        }

    def _summarize_verification_brief(self, project_id: int, brief: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "readiness": brief.get("readiness"),
            "required_checks": list(brief.get("required_checks") or [])[:8],
            "recommended_checks": list(brief.get("recommended_checks") or [])[:8],
            "evidence_gaps": list(brief.get("evidence_gaps") or [])[:8],
            "release_blockers": list(brief.get("release_blockers") or [])[:8],
            "handoff_warnings": list(brief.get("handoff_warnings") or [])[:8],
            "loop_strategy": list(brief.get("loop_strategy") or [])[:6],
            "generated_at": brief.get("generated_at"),
        }

    def _summarize_workspace_tooling(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "workspace_path": payload.get("workspace_path"),
            "available": bool(payload.get("available")),
            "summary": payload.get("summary"),
            "repo_profile": dict(payload.get("repo_profile") or {}),
            "packs": list(payload.get("packs") or [])[:6],
            "intake_commands": list(payload.get("intake_commands") or [])[:6],
            "validation_commands": list(payload.get("validation_commands") or [])[:8],
            "security_commands": list(payload.get("security_commands") or [])[:8],
            "recommended_next_steps": list(payload.get("recommended_next_steps") or [])[:8],
            "tools": list(payload.get("tools") or [])[:12],
        }

    def _summarize_runbook(self, project_id: int, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {
                "project_id": project_id,
                "exists": False,
                "content_markdown": None,
                "generated_from_handoff_id": None,
                "generated_at": None,
                "updated_at": None,
            }
        return {
            "id": payload.get("id"),
            "project_id": project_id,
            "exists": True,
            "content_markdown": payload.get("content_markdown"),
            "generated_from_handoff_id": payload.get("generated_from_handoff_id"),
            "generated_at": payload.get("generated_at"),
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": payload.get("id"),
            "display_name": payload.get("display_name"),
            "preferred_provider_choice": payload.get("preferred_provider_choice"),
            "preferred_start_mode": payload.get("preferred_start_mode"),
            "selected_provider": payload.get("selected_provider"),
            "auth_mode": payload.get("auth_mode"),
            "first_run_completed": payload.get("first_run_completed"),
            "onboarding_completed": payload.get("onboarding_completed"),
            "default_runner_mode": payload.get("default_runner_mode"),
            "manager_model": payload.get("manager_model"),
            "default_worker_model": payload.get("default_worker_model"),
            "sandbox_mode": payload.get("sandbox_mode"),
            "approval_policy": payload.get("approval_policy"),
            "theme": payload.get("theme"),
            "startup_behavior": payload.get("startup_behavior"),
            "connected_accounts_json": dict(payload.get("connected_accounts_json") or {}),
            "dashboard_widgets_json": list(payload.get("dashboard_widgets_json") or [])[:24],
            "tool_permission_overrides_json": dict(payload.get("tool_permission_overrides_json") or {}),
            "provider_endpoint_configured": bool(payload.get("provider_endpoint")),
            "adapter_command": payload.get("adapter_command"),
            "adapter_args_json": list(payload.get("adapter_args_json") or [])[:12],
            "recent_startup_error_json": payload.get("recent_startup_error_json"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "last_opened_at": payload.get("last_opened_at"),
        }

    def _summarize_active_orchestration(self, project_id: int, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {
                "project_id": project_id,
                "exists": False,
                "orchestration_id": None,
                "status": None,
                "manager_status": None,
                "mode": None,
                "source": None,
                "user_request": None,
                "workspace_path": None,
                "metadata_json": {},
                "created_at": None,
                "updated_at": None,
                "completed_at": None,
            }
        return {
            "project_id": project_id,
            "exists": True,
            "orchestration_id": payload.get("id"),
            "status": payload.get("status"),
            "manager_status": payload.get("manager_status"),
            "mode": payload.get("mode"),
            "source": payload.get("source"),
            "user_request": payload.get("user_request"),
            "workspace_path": payload.get("workspace_path"),
            "metadata_json": dict(payload.get("metadata_json") or {}),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "completed_at": payload.get("completed_at"),
        }

    def _summarize_ml_feature_catalog(self, project_id: int, payload: list[dict[str, Any]]) -> dict[str, Any]:
        features = list(payload or [])
        return {
            "project_id": project_id,
            "feature_count": len(features),
            "features": [
                {
                    "feature_id": item.get("feature_id"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "variants": list(item.get("variants") or [])[:10],
                    "keywords": list(item.get("keywords") or [])[:12],
                }
                for item in features[:32]
            ],
        }

    def _summarize_ml_feature_bundle(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "feature_id": payload.get("feature_id"),
            "variant": payload.get("variant"),
            "summary": payload.get("summary"),
            "files": dict(payload.get("files") or {}),
            "validation_steps": list(payload.get("validation_steps") or [])[:16],
            "dependencies": list(payload.get("dependencies") or [])[:20],
            "evidence_targets": list(payload.get("evidence_targets") or [])[:16],
        }

    def _summarize_spatial_feature_catalog(self, project_id: int, payload: list[dict[str, Any]]) -> dict[str, Any]:
        features = list(payload or [])
        return {
            "project_id": project_id,
            "feature_count": len(features),
            "features": [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "category": item.get("category"),
                    "variants": list(item.get("variants") or [])[:8],
                    "keywords": list(item.get("keywords") or [])[:10],
                }
                for item in features[:32]
            ],
        }

    def _summarize_spatial_feature_bundle(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "feature_id": payload.get("feature_id"),
            "variant": payload.get("variant"),
            "title": payload.get("title"),
            "summary": payload.get("summary"),
            "dependencies": list(payload.get("dependencies") or [])[:20],
            "starter_files": list(payload.get("starter_files") or [])[:24],
            "validation_steps": list(payload.get("validation_steps") or [])[:16],
            "evidence_targets": list(payload.get("evidence_targets") or [])[:16],
            "notes": list(payload.get("notes") or [])[:10],
        }

    def _summarize_capability_report(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        sections = list(payload.get("sections") or [])
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "section_count": int(payload.get("section_count") or len(sections)),
            "sections": sections[:15],
            "report_markdown": payload.get("report_markdown"),
            "generated_at": payload.get("generated_at"),
        }

    def _summarize_capability_section(self, project_id: int, section_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "section_key": section_key,
            "title": payload.get("title"),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "details": list(payload.get("details") or [])[:10],
            "commands": list(payload.get("commands") or [])[:8],
            "artifacts": list(payload.get("artifacts") or [])[:8],
            "metadata_json": dict(payload.get("metadata_json") or {}),
        }

    def _summarize_webwright_status(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "install_status": payload.get("install_status"),
            "summary": payload.get("summary"),
            "launch_command": payload.get("launch_command"),
            "workspace_signals": list(payload.get("workspace_signals") or [])[:8],
            "recommended_fix": payload.get("recommended_fix"),
            "recommended_install_commands": list(payload.get("recommended_install_commands") or [])[:6],
            "use_cases": list(payload.get("use_cases") or [])[:6],
            "notes": list(payload.get("notes") or [])[:6],
            "version": payload.get("version"),
        }

    def _summarize_nvidia_dynamo_status(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "reachable": bool(payload.get("reachable")),
            "endpoint": payload.get("endpoint"),
            "endpoint_configured": bool(payload.get("endpoint_configured")),
            "api_key_configured": bool(payload.get("api_key_configured")),
            "auth_required": bool(payload.get("auth_required")),
            "authenticated": bool(payload.get("authenticated")),
            "available_models": list(payload.get("available_models") or [])[:12],
            "runtime_ready": bool(payload.get("runtime_ready")),
            "runtime_status": payload.get("runtime_status"),
            "runtime_summary": payload.get("runtime_summary"),
            "runtime_blockers": list(payload.get("runtime_blockers") or [])[:8],
            "adapter_command_configured": bool(payload.get("adapter_command_configured")),
            "adapter_command_detected": bool(payload.get("adapter_command_detected")),
            "adapter_command_path": payload.get("adapter_command_path"),
            "adapter_args": list(payload.get("adapter_args") or [])[:8],
            "adapter_recipe_source": payload.get("adapter_recipe_source"),
            "summary": payload.get("summary"),
            "notes": list(payload.get("notes") or [])[:8],
        }

    def _summarize_nvidia_nim_status(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "reachable": bool(payload.get("reachable")),
            "endpoint": payload.get("endpoint"),
            "endpoint_configured": bool(payload.get("endpoint_configured")),
            "api_key_configured": bool(payload.get("api_key_configured")),
            "auth_required": bool(payload.get("auth_required")),
            "authenticated": bool(payload.get("authenticated")),
            "available_models": list(payload.get("available_models") or [])[:12],
            "runtime_ready": bool(payload.get("runtime_ready")),
            "runtime_status": payload.get("runtime_status"),
            "runtime_summary": payload.get("runtime_summary"),
            "runtime_blockers": list(payload.get("runtime_blockers") or [])[:8],
            "adapter_command_configured": bool(payload.get("adapter_command_configured")),
            "adapter_command_detected": bool(payload.get("adapter_command_detected")),
            "adapter_command_path": payload.get("adapter_command_path"),
            "adapter_args": list(payload.get("adapter_args") or [])[:8],
            "adapter_recipe_source": payload.get("adapter_recipe_source"),
            "summary": payload.get("summary"),
            "notes": list(payload.get("notes") or [])[:8],
        }

    def _summarize_nvidia_aiq_status(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "install_status": payload.get("install_status"),
            "summary": payload.get("summary"),
            "endpoint": payload.get("endpoint"),
            "endpoint_configured": bool(payload.get("endpoint_configured")),
            "api_key_configured": bool(payload.get("api_key_configured")),
            "auth_required": bool(payload.get("auth_required")),
            "dask_available": payload.get("dask_available"),
            "agent_types": list(payload.get("agent_types") or [])[:8],
            "data_sources": list(payload.get("data_sources") or [])[:8],
            "recommended_fix": payload.get("recommended_fix"),
            "notes": list(payload.get("notes") or [])[:8],
        }

    def _summarize_nvidia_gpu_diagnostics(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "prometheus_url": payload.get("prometheus_url"),
            "workspace_relevant": bool(payload.get("workspace_relevant")),
            "telemetry_status": payload.get("telemetry_status"),
            "workspace_summary_status": payload.get("workspace_summary_status"),
            "repo_mode": payload.get("repo_mode"),
            "cluster_usable": payload.get("cluster_usable"),
            "pending_pod_count": payload.get("pending_pod_count"),
            "gpu_memory_saturation_pct": payload.get("gpu_memory_saturation_pct"),
            "gpu_memory_saturated": bool(payload.get("gpu_memory_saturated")),
            "likely_failure_source": payload.get("likely_failure_source"),
            "blocking_reasons": list(payload.get("blocking_reasons") or [])[:8],
            "observability_sources": list(payload.get("observability_sources") or [])[:8],
            "summary_files": list(payload.get("summary_files") or [])[:8],
            "safe_commands": list(payload.get("safe_commands") or [])[:8],
            "metrics": dict(payload.get("metrics") or {}),
            "alerts": list(payload.get("alerts") or [])[:8],
            "recommended_fixes": list(payload.get("recommended_fixes") or [])[:8],
        }

    def _summarize_nvidia_local_runtime_status(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "repo_mode_enabled": bool(payload.get("repo_mode_enabled")),
            "repo_mode": payload.get("repo_mode"),
            "detected_tools": list(payload.get("detected_tools") or [])[:12],
            "missing_required_tools": list(payload.get("missing_required_tools") or [])[:8],
            "missing_optional_tools": list(payload.get("missing_optional_tools") or [])[:8],
            "gpu_names": list(payload.get("gpu_names") or [])[:8],
            "driver_version": payload.get("driver_version"),
            "cuda_release": payload.get("cuda_release"),
            "compute_sanitizer_available": bool(payload.get("compute_sanitizer_available")),
            "nsight_systems_available": bool(payload.get("nsight_systems_available")),
            "nsight_compute_available": bool(payload.get("nsight_compute_available")),
            "cuda_gdb_available": bool(payload.get("cuda_gdb_available")),
            "ngc_cli_available": bool(payload.get("ngc_cli_available")),
            "container_runtime_ready": bool(payload.get("container_runtime_ready")),
            "recommended_fixes": list(payload.get("recommended_fixes") or [])[:8],
            "validation_hints": list(payload.get("validation_hints") or [])[:8],
            "notes": list(payload.get("notes") or [])[:6],
        }

    def _summarize_nvidia_validation_plan(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "available": bool(payload.get("available")),
            "status": payload.get("status"),
            "summary": payload.get("summary"),
            "repo_mode_enabled": bool(payload.get("repo_mode_enabled")),
            "repo_mode": payload.get("repo_mode"),
            "local_runtime_status": payload.get("local_runtime_status"),
            "gpu_diagnostics_status": payload.get("gpu_diagnostics_status"),
            "sanitizer_ready": bool(payload.get("sanitizer_ready")),
            "profiler_ready": bool(payload.get("profiler_ready")),
            "container_smoke_ready": bool(payload.get("container_smoke_ready")),
            "ngc_smoke_image": payload.get("ngc_smoke_image"),
            "steps": list(payload.get("steps") or [])[:12],
            "blockers": list(payload.get("blockers") or [])[:8],
            "recommended_fixes": list(payload.get("recommended_fixes") or [])[:8],
            "evidence_targets": list(payload.get("evidence_targets") or [])[:8],
        }

    def _summarize_handoff(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        handoff = payload.get("handoff") if "handoff" in payload else payload
        status = str(payload.get("status", handoff.get("status")) or "not_ready")
        ready = bool(payload["ready"]) if "ready" in payload else status in {"ready", "needs_review", "handoff_ready"}
        return {
            "project_id": project_id,
            "project_name": handoff.get("project_name"),
            "status": status,
            "ready": ready,
            "summary": handoff.get("summary"),
            "run_instructions": handoff.get("run_instructions", []),
            "tests_count": handoff.get("tests_count", 0),
            "confidence_level": handoff.get("confidence_level"),
            "evidence_status": handoff.get("evidence_status"),
            "missing_evidence": handoff.get("missing_evidence", []),
            "known_limitations": handoff.get("known_limitations", []),
            "dry_run": handoff.get("dry_run", False),
        }

    def _summarize_orchestration_session(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "orchestration_id": payload.get("id"),
            "workspace_path": payload.get("workspace_path"),
            "source": payload.get("source"),
            "user_request": payload.get("user_request"),
            "status": payload.get("status"),
            "manager_status": payload.get("manager_status"),
            "mode": payload.get("mode"),
            "metadata_json": dict(payload.get("metadata_json") or {}),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "completed_at": payload.get("completed_at"),
        }

    def _summarize_handoff_evidence(self, project_id: int, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for item in evidence:
            evidence_type = str(item.get("evidence_type") or "unknown")
            status = str(item.get("status") or "unknown")
            type_counts[evidence_type] = type_counts.get(evidence_type, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
        return {
            "project_id": project_id,
            "evidence_count": len(evidence),
            "evidence_types": sorted(type_counts),
            "evidence_type_counts": type_counts,
            "status_counts": status_counts,
            "evidence_items": [
                {
                    "id": item.get("id"),
                    "evidence_type": item.get("evidence_type"),
                    "claim": self._safe_short(item.get("claim")),
                    "summary": self._safe_short(item.get("summary")),
                    "status": item.get("status"),
                    "source_path": item.get("source_path"),
                    "command": item.get("command"),
                    "created_at": item.get("created_at"),
                }
                for item in evidence[:12]
            ],
        }

    def _summarize_codebase_map(self, codebase_map: dict[str, Any], understanding: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "project_id": codebase_map.get("project_id"),
            "source_path": codebase_map.get("source_path"),
            "languages": codebase_map.get("languages_json", []),
            "frameworks": codebase_map.get("frameworks_json", []),
            "entry_points": codebase_map.get("entry_points_json", [])[:8],
            "build_commands": codebase_map.get("build_commands_json", [])[:6],
            "test_commands": codebase_map.get("test_commands_json", [])[:6],
            "important_folders": codebase_map.get("important_folders_json", [])[:12],
            "risk_flags": codebase_map.get("risk_flags_json", [])[:8],
            "understanding_summary": understanding.get("summary") if understanding else None,
            "recommended_interview_mode": understanding.get("recommended_interview_mode") if understanding else None,
        }

    def _summarize_diagnostics(self, project_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
        reports = payload.get("recent_reports", [])
        latest = reports[0] if reports else None
        return {
            "project_id": project_id,
            "plugin_health": payload.get("plugin_health"),
            "report_count": len(reports),
            "latest_report": latest,
            "orchestration_status": payload.get("orchestration_status"),
            "manager_status": payload.get("manager_status"),
            "recommended_fixes": payload.get("recommended_fixes", [])[:6],
            "platform_profile": payload.get("platform_profile", {}),
            "performance_profile": payload.get("performance_profile", {}),
            "safe_debug_commands": payload.get("safe_debug_commands", [])[:6],
            "bundle_path": payload.get("bundle_path"),
            "notes": [check.get("summary") for check in payload.get("health_checks", [])[:6] if check.get("summary")],
        }

    def _summarize_skills(self, skills: list[dict[str, Any]]) -> dict[str, Any]:
        categories = sorted({str(skill.get("category") or "uncategorized") for skill in skills})
        return {
            "skill_count": len(skills),
            "categories": categories,
            "skills": [
                {
                    "name": skill.get("name"),
                    "label": skill.get("label"),
                    "category": skill.get("category"),
                    "status": skill.get("status"),
                    "summary": self._safe_short(skill.get("summary")),
                }
                for skill in skills[:20]
            ],
        }

    def _summarize_project_understanding(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "summary": payload.get("summary"),
            "known_fact_count": len(payload.get("known_facts_json") or {}),
            "unknown_count": len(payload.get("unknowns_json") or {}),
            "assumption_count": len(payload.get("assumptions_json") or []),
            "constraint_count": len(payload.get("constraints_json") or []),
            "confidence_by_category": payload.get("confidence_by_category_json") or {},
            "known_facts": payload.get("known_facts_json") or {},
            "unknowns": payload.get("unknowns_json") or {},
            "assumptions": (payload.get("assumptions_json") or [])[:12],
            "constraints": (payload.get("constraints_json") or [])[:12],
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_interview(self, project_id: int, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {
                "project_id": project_id,
                "exists": False,
                "status": None,
                "question_budget": 0,
                "question_count": 0,
                "questions_answered": 0,
                "pending_questions": 0,
                "manager_mode": None,
                "understanding_summary": None,
                "questions": [],
            }
        return {
            "project_id": project_id,
            "exists": True,
            "id": payload.get("id"),
            "status": payload.get("status"),
            "question_budget": payload.get("question_budget"),
            "question_count": payload.get("question_count"),
            "questions_asked": payload.get("questions_asked"),
            "questions_answered": payload.get("questions_answered"),
            "questions_remaining": payload.get("questions_remaining"),
            "pending_questions": payload.get("pending_questions"),
            "manager_mode": payload.get("manager_mode"),
            "stopped_early": payload.get("stopped_early"),
            "stop_reason": payload.get("stop_reason"),
            "understanding_summary": payload.get("understanding_summary"),
            "assumptions": (payload.get("assumptions") or [])[:12],
            "constraints": (payload.get("constraints") or [])[:12],
            "generation_sources": (payload.get("generation_sources") or [])[:8],
            "questions": [
                {
                    "id": question.get("id"),
                    "index": question.get("index"),
                    "question": self._safe_short(question.get("question")),
                    "category": question.get("category"),
                    "status": question.get("status"),
                    "impact": question.get("impact"),
                    "selected_option_id": question.get("selected_option_id"),
                    "selected_text": question.get("selected_text"),
                }
                for question in (payload.get("questions") or [])[:12]
            ],
        }

    def _summarize_plan(self, project_id: int, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not payload:
            return {
                "project_id": project_id,
                "exists": False,
                "status": None,
                "version": None,
                "summary_json": None,
                "content_markdown": None,
                "updated_at": None,
            }
        return {
            "project_id": project_id,
            "exists": True,
            "id": payload.get("id"),
            "status": payload.get("status"),
            "version": payload.get("version"),
            "summary_json": payload.get("summary_json"),
            "content_markdown": payload.get("content_markdown"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_reservations(self, project_id: int, reservations: list[dict[str, Any]]) -> dict[str, Any]:
        active = [reservation for reservation in reservations if reservation.get("released_at") is None]
        return {
            "project_id": project_id,
            "reservation_count": len(reservations),
            "active_reservation_count": len(active),
            "reservations": [
                {
                    "id": reservation.get("id"),
                    "task_id": reservation.get("task_id"),
                    "agent_id": reservation.get("agent_id"),
                    "path": reservation.get("path"),
                    "created_at": reservation.get("created_at"),
                    "released_at": reservation.get("released_at"),
                }
                for reservation in reservations[:16]
            ],
        }

    def _summarize_swarm_plan(self, project_id: int, plan: dict[str, Any] | None, prefs: dict[str, Any]) -> dict[str, Any]:
        if not plan:
            return {
                "project_id": project_id,
                "support_status": "empty",
                "summary": "No swarm plan is currently available.",
                "preferences": {
                    "optimization_mode": prefs.get("optimization_mode"),
                    "swarm_aggressiveness": prefs.get("swarm_aggressiveness"),
                    "max_agents": prefs.get("max_agents"),
                    "allow_dynamic_spawning": prefs.get("allow_dynamic_spawning"),
                },
            }
        return {
            "project_id": project_id,
            "mode": plan.get("mode"),
            "recommended_agent_count": plan.get("recommended_agent_count"),
            "active_agent_count": plan.get("active_agent_count"),
            "coordination_risk": plan.get("coordination_risk"),
            "path_conflict_risk": plan.get("path_conflict_risk"),
            "approval_required": plan.get("approval_required"),
            "dynamic_spawning_enabled": plan.get("dynamic_spawning_enabled"),
            "dynamic_retirement_enabled": plan.get("dynamic_retirement_enabled"),
            "expected_bottlenecks": plan.get("expected_bottlenecks_json", [])[:8],
            "validation_strategy": plan.get("validation_strategy_json", [])[:8],
            "strategy_summary": plan.get("strategy_summary"),
            "specs": [
                {
                    "name": spec.get("name"),
                    "archetype": spec.get("archetype"),
                    "mission": spec.get("mission"),
                    "status": spec.get("status"),
                }
                for spec in plan.get("specs", [])[:12]
            ],
        }

    def _summarize_risks(self, project_id: int, risks: list[dict[str, Any]]) -> dict[str, Any]:
        open_risks = [risk for risk in risks if risk.get("status") not in {"closed", "mitigated"}]
        mitigated = [risk for risk in risks if risk.get("status") in {"closed", "mitigated"}]
        return {
            "project_id": project_id,
            "risk_count": len(risks),
            "open_risks": [
                {
                    "title": risk.get("title"),
                    "severity": risk.get("severity"),
                    "status": risk.get("status"),
                    "mitigation": risk.get("mitigation"),
                }
                for risk in open_risks[:10]
            ],
            "mitigated_risks": [
                {
                    "title": risk.get("title"),
                    "severity": risk.get("severity"),
                    "status": risk.get("status"),
                }
                for risk in mitigated[:5]
            ],
        }

    def _summarize_snapshots(self, project_id: int, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "snapshot_count": len(snapshots),
            "snapshots": [
                {
                    "id": snapshot.get("id"),
                    "snapshot_type": snapshot.get("snapshot_type"),
                    "label": snapshot.get("label"),
                    "description": self._safe_short(snapshot.get("description")),
                    "status": snapshot.get("status"),
                    "git_ref": snapshot.get("git_ref"),
                    "created_at": snapshot.get("created_at"),
                }
                for snapshot in snapshots[:12]
            ],
        }

    def _summarize_recovery_plans(self, project_id: int, plans: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "recovery_plan_count": len(plans),
            "plans": [
                {
                    "id": plan.get("id"),
                    "trigger_type": plan.get("trigger_type"),
                    "trigger_summary": self._safe_short(plan.get("trigger_summary")),
                    "status": plan.get("status"),
                    "selected_action": plan.get("selected_action"),
                    "suggested_actions": (plan.get("suggested_actions_json") or [])[:8],
                    "created_at": plan.get("created_at"),
                }
                for plan in plans[:12]
            ],
        }

    def _summarize_validation(self, project_id: int, areas: list[dict[str, Any]]) -> dict[str, Any]:
        coverage_counts: dict[str, int] = {}
        for area in areas:
            key = str(area.get("coverage_status") or "unknown")
            coverage_counts[key] = coverage_counts.get(key, 0) + 1
        notable_gaps = [area.get("area") for area in areas if area.get("coverage_status") in {"none", "failed", "skipped"}]
        return {
            "project_id": project_id,
            "coverage_counts": coverage_counts,
            "areas": [
                {
                    "area": area.get("area"),
                    "coverage_status": area.get("coverage_status"),
                    "evidence_summary": area.get("evidence_summary"),
                }
                for area in areas[:16]
            ],
            "notable_gaps": notable_gaps[:10],
        }

    def _summarize_validation_summary(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        areas = list(payload.get("items") or [])
        summary = self._summarize_validation(project_id, areas)
        summary["notable_gaps"] = list(payload.get("gaps") or summary["notable_gaps"])[:10]
        return summary

    def _summarize_effective_preferences(self, project_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "item_count": len(items),
            "editable_count": sum(1 for item in items if item.get("editable")),
            "inherited_count": sum(1 for item in items if item.get("inherited")),
            "items": [
                {
                    "id": item.get("id"),
                    "key": item.get("key"),
                    "value_json": item.get("value_json"),
                    "source": item.get("source"),
                    "scope": item.get("scope"),
                    "project_id": item.get("project_id"),
                    "editable": item.get("editable"),
                    "inherited": item.get("inherited", False),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
                for item in items[:24]
            ],
        }

    def _summarize_preferences(self, items: list[dict[str, Any]], *, project_id: int | None = None) -> dict[str, Any]:
        return {
            "scope": "project" if project_id is not None else "global",
            "project_id": project_id,
            "item_count": len(items),
            "editable_count": sum(1 for item in items if item.get("editable")),
            "items": [
                {
                    "id": item.get("id"),
                    "key": item.get("key"),
                    "value_json": item.get("value_json"),
                    "source": item.get("source"),
                    "scope": item.get("scope"),
                    "project_id": item.get("project_id"),
                    "editable": item.get("editable"),
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                }
                for item in items[:24]
            ],
        }

    def _summarize_subagent_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": payload.get("enabled"),
            "default_mode": payload.get("default_mode"),
            "sandbox_mode": payload.get("sandbox_mode"),
            "max_subagents_per_burst": payload.get("max_subagents_per_burst"),
            "max_runtime_seconds": payload.get("max_runtime_seconds"),
            "allow_file_edits": payload.get("allow_file_edits"),
            "allow_commands": payload.get("allow_commands"),
            "require_user_approval_above_count": payload.get("require_user_approval_above_count"),
            "allowed_task_types_json": (payload.get("allowed_task_types_json") or [])[:12],
            "default_spawn_method": payload.get("default_spawn_method"),
            "writes_allowed": payload.get("writes_allowed"),
            "read_only_default": payload.get("read_only_default"),
            "command_capable": payload.get("command_capable"),
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_validation_coverage(self, project_id: int, items: list[dict[str, Any]]) -> dict[str, Any]:
        gaps = [
            str(item.get("area"))
            for item in items
            if str(item.get("coverage_status") or "").lower() not in {"passed", "ok", "covered"}
            and item.get("area")
        ]
        return {
            "project_id": project_id,
            "item_count": len(items),
            "gap_count": len(gaps),
            "gaps": gaps[:24],
            "coverage_statuses": sorted({str(item.get("coverage_status") or "unknown") for item in items}),
            "items": [
                {
                    "area": item.get("area"),
                    "coverage_status": item.get("coverage_status"),
                    "evidence_summary": item.get("evidence_summary"),
                    "coverage_percent": item.get("coverage_percent"),
                    "last_verified_at": item.get("last_verified_at"),
                }
                for item in items[:24]
            ],
        }

    def _summarize_subagent_batches(self, project_id: int, batches: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "batch_count": len(batches),
            "active_count": sum(1 for batch in batches if str(batch.get("status") or "").lower() not in {"completed", "failed", "cancelled"}),
            "completed_count": sum(1 for batch in batches if str(batch.get("status") or "").lower() == "completed"),
            "statuses": sorted({str(batch.get("status") or "unknown") for batch in batches}),
            "batches": [
                {
                    "id": batch.get("id"),
                    "status": batch.get("status"),
                    "task_type": batch.get("task_type"),
                    "spawn_method": batch.get("spawn_method"),
                    "requested_count": batch.get("requested_count"),
                    "approved_count": batch.get("approved_count"),
                    "completed_count": batch.get("completed_count"),
                    "failure_count": batch.get("failure_count"),
                    "created_at": batch.get("created_at"),
                    "updated_at": batch.get("updated_at"),
                }
                for batch in batches[:20]
            ],
        }

    def _summarize_subagent_batch(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "batch_id": payload.get("id"),
            "id": payload.get("id"),
            "status": payload.get("status"),
            "task_type": payload.get("task_type"),
            "spawn_method": payload.get("spawn_method"),
            "requested_count": payload.get("requested_count"),
            "approved_count": payload.get("approved_count"),
            "completed_count": payload.get("completed_count"),
            "failure_count": payload.get("failure_count"),
            "summary_markdown": payload.get("summary_markdown"),
            "approvals_required": payload.get("approvals_required"),
            "results": (payload.get("results") or [])[:20],
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_widget_instances(self, instances: list[dict[str, Any]], *, project_id: int | None = None) -> dict[str, Any]:
        scope = "project" if project_id is not None else "dashboard"
        return {
            "scope": scope,
            "project_id": project_id,
            "instance_count": len(instances),
            "widget_types": sorted({str(instance.get("widget_type")) for instance in instances if instance.get("widget_type")}),
            "instances": [
                {
                    "id": instance.get("id"),
                    "scope": instance.get("scope"),
                    "project_id": instance.get("project_id"),
                    "widget_type": instance.get("widget_type"),
                    "area": instance.get("area"),
                    "order_index": instance.get("order_index"),
                    "size": instance.get("size"),
                    "collapsed": instance.get("collapsed"),
                    "enabled": instance.get("enabled"),
                    "updated_at": instance.get("updated_at"),
                }
                for instance in instances[:20]
            ],
        }

    def _summarize_widget_instance_data(self, instance_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data_json") or {}
        return {
            "widget_instance_id": instance_id,
            "widget_type": payload.get("widget_type"),
            "title": payload.get("title"),
            "status": payload.get("status"),
            "empty_state": payload.get("empty_state"),
            "warning_count": len(payload.get("warnings_json") or []),
            "warnings": (payload.get("warnings_json") or [])[:8],
            "data_keys": sorted(data.keys())[:20],
            "data_json": data,
            "updated_at": payload.get("updated_at"),
        }

    def _summarize_project_actions(self, project_id: int, actions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "action_count": len(actions),
            "actions": actions[:20],
        }

    def _summarize_manager_messages(self, project_id: int, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "message_count": len(messages),
            "messages": messages[:20],
        }

    def _summarize_tasks(self, project_id: int, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "task_count": len(tasks),
            "tasks": tasks[:24],
        }

    def _summarize_project_events(self, project_id: int, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "event_count": len(events),
            "events": events[:40],
        }

    def _summarize_handoffs(self, handoffs: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "handoff_count": len(handoffs),
            "handoffs": handoffs[:20],
        }

    def _summarize_diagnostic_reports(self, reports: list[dict[str, Any]], *, project_id: int | None = None) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "report_count": len(reports),
            "reports": reports[:20],
        }

    def _summarize_latest_diagnostic_report(self, project_id: int, reports: list[dict[str, Any]]) -> dict[str, Any]:
        latest = reports[0] if reports else None
        return {
            "project_id": project_id,
            "exists": latest is not None,
            "report_count": len(reports),
            "report": latest,
        }

    def _summarize_agent_archetypes(self, archetypes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "archetype_count": len(archetypes),
            "archetypes": archetypes[:20],
        }

    def _summarize_capability_benchmarks(self, benchmarks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "benchmark_count": len(benchmarks),
            "benchmarks": benchmarks[:20],
        }

    def _summarize_capability_matrix(self, matrix: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "entry_count": len(matrix),
            "entries": matrix[:40],
        }

    def _summarize_agent_reputation(self, reputations: list[dict[str, Any]], *, project_id: int | None = None) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "reputation_count": len(reputations),
            "reputations": reputations[:20],
        }

    def _summarize_integration_action_preview(
        self,
        project_id: int,
        family: str,
        action_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "family": family,
            "action_id": action_id,
            "title": payload.get("title"),
            "summary": payload.get("summary"),
            "project_name": payload.get("project_name"),
            "workspace_path": payload.get("workspace_path"),
            "command": payload.get("command"),
            "risk_level": payload.get("risk_level"),
            "permission_policy": payload.get("permission_policy"),
            "preview_supported": payload.get("preview_supported"),
            "mutates_remote_state": payload.get("mutates_remote_state"),
            "requires_confirmation": payload.get("requires_confirmation"),
            "missing_params": list(payload.get("missing_params") or [])[:8],
            "notes": list(payload.get("notes") or [])[:8],
        }

    def _summarize_integration_catalog(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        connected_count = 0
        categories: dict[str, int] = {}
        families = []
        for entry in entries[:30]:
            status = str(entry.get("status") or "unknown")
            category = str(entry.get("category") or "other")
            if status == "connected":
                connected_count += 1
            categories[category] = categories.get(category, 0) + 1
            families.append(
                {
                    "family": entry.get("family"),
                    "name": entry.get("name"),
                    "category": category,
                    "status": status,
                    "provider_count": len(list(entry.get("providers") or [])),
                    "action_count": len(list(entry.get("available_action_ids") or [])),
                    "host_support_count": len(list(entry.get("host_support") or [])),
                    "host_imported": bool(entry.get("host_imported", False)),
                    "connection_source": entry.get("connection_source"),
                }
            )
        return {
            "family_count": len(entries),
            "connected_family_count": connected_count,
            "category_counts": categories,
            "families": families,
        }

    def _summarize_integration_connections(self, connections: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        imported_count = 0
        summarized = []
        for connection in connections[:30]:
            status = str(connection.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            if connection.get("host_imported"):
                imported_count += 1
            summarized.append(
                {
                    "family": connection.get("family"),
                    "status": status,
                    "provider_count": len(list(connection.get("providers") or [])),
                    "host_imported": bool(connection.get("host_imported", False)),
                    "connection_source": connection.get("connection_source"),
                    "approval_policy": connection.get("approval_policy"),
                    "notes": list(connection.get("notes") or [])[:4],
                }
            )
        return {
            "connection_count": len(connections),
            "host_imported_count": imported_count,
            "status_counts": status_counts,
            "connections": summarized,
        }

    def _summarize_integration_health(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "version": payload.get("version"),
            "family_count": payload.get("family_count", 0),
            "connection_count": payload.get("connection_count", 0),
            "authoritative_connection_count": payload.get("authoritative_connection_count", 0),
            "host_imported_count": payload.get("host_imported_count", 0),
            "status_counts": dict(payload.get("status_counts") or {}),
            "recent_action_failures": list(payload.get("recent_action_failures") or [])[:8],
            "host_import_roots": dict(payload.get("host_import_roots") or {}),
        }

    def _summarize_project_integrations(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        families = list(payload.get("families") or [])
        ready_family_count = 0
        connected_family_count = 0
        summarized = []
        for family_payload in families[:30]:
            status = str(family_payload.get("status") or "unknown")
            connection_status = str(family_payload.get("connection_status") or status)
            if status == "ready":
                ready_family_count += 1
            if connection_status == "connected":
                connected_family_count += 1
            summarized.append(
                {
                    "family": family_payload.get("family"),
                    "name": family_payload.get("name"),
                    "status": status,
                    "connection_status": connection_status,
                    "resolved_provider": family_payload.get("resolved_provider"),
                    "action_count": family_payload.get("action_count", len(list(family_payload.get("available_actions") or []))),
                    "blocker_count": family_payload.get("blocker_count", len(list(family_payload.get("blockers") or []))),
                    "host_imported": bool(family_payload.get("host_imported", False)),
                    "connection_source": family_payload.get("connection_source"),
                }
            )
        return {
            "project_id": project_id,
            "project_name": payload.get("project_name"),
            "workspace_path": payload.get("workspace_path"),
            "summary": payload.get("summary"),
            "family_count": payload.get("family_count", len(families)),
            "ready_family_count": ready_family_count,
            "connected_family_count": connected_family_count,
            "status_counts": dict(payload.get("status_counts") or {}),
            "connection_status_counts": dict(payload.get("connection_status_counts") or {}),
            "families": summarized,
        }

    def _summarize_project_integration_family(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        actions = list(payload.get("available_actions") or [])
        return {
            "project_id": project_id,
            "family": payload.get("family"),
            "name": payload.get("name"),
            "summary": payload.get("summary"),
            "category": payload.get("category"),
            "project_name": payload.get("project_name"),
            "workspace_path": payload.get("workspace_path"),
            "status": payload.get("status"),
            "connection_status": payload.get("connection_status"),
            "connection_source": payload.get("connection_source"),
            "host_imported": bool(payload.get("host_imported", False)),
            "resolved_provider": payload.get("resolved_provider"),
            "provider_candidates": list(payload.get("provider_candidates") or [])[:8],
            "required_permissions": list(payload.get("required_permissions") or [])[:8],
            "safe_commands": list(payload.get("safe_commands") or [])[:8],
            "blockers": list(payload.get("blockers") or [])[:8],
            "recommended_fixes": list(payload.get("recommended_fixes") or [])[:8],
            "action_count": payload.get("action_count", len(actions)),
            "available_actions": [
                {
                    "action_id": action.get("action_id"),
                    "title": action.get("title"),
                    "status": action.get("status"),
                    "risk_level": action.get("risk_level"),
                    "permission_policy": action.get("permission_policy"),
                    "provider": action.get("provider"),
                    "requires_confirmation": bool(action.get("requires_confirmation", False)),
                }
                for action in actions[:12]
            ],
        }

    def _summarize_project_integration_actions(self, project_id: int, family: str, payload: dict[str, Any]) -> dict[str, Any]:
        actions = list(payload.get("available_actions") or [])
        risk_level_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        preview_supported_count = 0
        requires_confirmation_count = 0
        summarized = []
        for action in actions[:20]:
            risk_level = str(action.get("risk_level") or "unknown")
            status = str(action.get("status") or "unknown")
            risk_level_counts[risk_level] = risk_level_counts.get(risk_level, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            if action.get("preview_supported"):
                preview_supported_count += 1
            if action.get("requires_confirmation"):
                requires_confirmation_count += 1
            summarized.append(
                {
                    "action_id": action.get("action_id"),
                    "title": action.get("title"),
                    "status": status,
                    "risk_level": risk_level,
                    "permission_policy": action.get("permission_policy"),
                    "provider": action.get("provider"),
                    "preview_supported": bool(action.get("preview_supported", False)),
                    "requires_confirmation": bool(action.get("requires_confirmation", False)),
                    "ready_to_execute": bool(action.get("ready_to_execute", False)),
                    "missing_params": list(action.get("missing_params") or [])[:6],
                }
            )
        return {
            "project_id": project_id,
            "family": family,
            "project_name": payload.get("project_name"),
            "workspace_path": payload.get("workspace_path"),
            "action_count": len(actions),
            "preview_supported_count": preview_supported_count,
            "requires_confirmation_count": requires_confirmation_count,
            "risk_level_counts": risk_level_counts,
            "status_counts": status_counts,
            "actions": summarized,
        }

    def _summarize_context_packs(self, project_id: int, packs: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "context_pack_count": len(packs),
            "context_packs": packs[:20],
        }

    def _summarize_common_risks(self, risks: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "common_risk_count": len(risks),
            "common_risks": risks[:20],
        }

    def _summarize_swarm_simulations(self, project_id: int, simulations: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "simulation_count": len(simulations),
            "simulations": simulations[:20],
        }

    def _summarize_swarm_events(self, project_id: int, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "event_count": len(events),
            "events": events[:30],
        }

    def _summarize_scope_creep(self, project_id: int, signals: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        for signal in signals:
            status = str(signal.get("status") or "unknown")
            severity = str(signal.get("severity") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return {
            "project_id": project_id,
            "signal_count": len(signals),
            "status_counts": status_counts,
            "severity_counts": severity_counts,
            "signals": signals[:20],
        }

    def _summarize_security_audit_log(self, entries: list[dict[str, Any]], *, project_id: int | None = None) -> dict[str, Any]:
        decision_counts: dict[str, int] = {}
        risk_counts: dict[str, int] = {}
        for entry in entries:
            decision = str(entry.get("decision") or "unknown")
            risk = str(entry.get("risk_level") or "unknown")
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        return {
            "project_id": project_id,
            "audit_entry_count": len(entries),
            "decision_counts": decision_counts,
            "risk_level_counts": risk_counts,
            "entries": entries[:20],
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        if not uri.startswith("mission-control://"):
            raise RuntimeError("Unsupported Mission Control resource URI.")
        parts = [segment for segment in uri.removeprefix("mission-control://").split("/") if segment]
        if len(parts) >= 1 and parts[0] == "agent-archetypes":
            return self._summarize_agent_archetypes(self.get_agent_archetypes())
        if len(parts) >= 2 and parts[0] == "capabilities":
            if parts[1] == "benchmarks":
                return self._summarize_capability_benchmarks(self.get_capability_benchmarks())
            if parts[1] == "matrix":
                return self._summarize_capability_matrix(self.get_capability_matrix())
        if len(parts) == 2 and parts[0] == "agents" and parts[1] == "reputation":
            return self._summarize_agent_reputation(self.get_agent_reputation())
        if len(parts) == 2 and parts[0] == "context-packs":
            try:
                context_pack_id = int(parts[1])
            except ValueError as exc:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
            return self.get_context_pack(context_pack_id)
        if len(parts) == 1 and parts[0] == "handoffs":
            return self._summarize_handoffs(self.list_handoffs())
        if len(parts) == 1 and parts[0] == "health":
            return self.get_health()
        if len(parts) == 2 and parts[0] == "headless" and parts[1] == "diagnostic-summary":
            return self.get_headless_diagnostic_summary()
        if len(parts) == 2 and parts[0] == "diagnostics" and parts[1] == "reports":
            return self._summarize_diagnostic_reports(self.list_diagnostic_reports())
        if len(parts) == 2 and parts[0] == "diagnostics" and parts[1] == "identity":
            return self.get_diagnostics_identity()
        if len(parts) == 2 and parts[0] == "headless" and parts[1] == "health":
            return self.get_headless_health()
        if len(parts) == 3 and parts[0] == "system" and parts[1] == "auth-jobs":
            return self.get_auth_job(parts[2])
        if len(parts) == 2 and parts[0] == "integrations":
            kind = parts[1]
            if kind == "catalog":
                return self._summarize_integration_catalog(self.get_integrations_catalog())
            if kind == "connections":
                return self._summarize_integration_connections(self.get_integration_connections())
            if kind == "health":
                return self._summarize_integration_health(self.get_integration_health())
        if len(parts) == 1 and parts[0] == "profile":
            return self._summarize_profile(self.get_profile())
        if len(parts) == 2 and parts[0] == "profile" and parts[1] == "summary":
            return self.get_profile_summary()
        if len(parts) == 1 and parts[0] == "tools":
            tools = self.get_tool_catalog()
            return {"tool_count": len(tools), "tools": tools}
        if len(parts) == 2 and parts[0] == "preferences" and parts[1] == "summary":
            return self.get_global_preference_summary()
        if len(parts) >= 1 and parts[0] == "playbooks":
            if len(parts) == 1:
                return {"playbooks": self.list_playbooks()}
            if len(parts) == 2:
                return self.get_playbook_catalog_entry(parts[1])
        if len(parts) == 2 and parts[0] == "risks" and parts[1] == "summary":
            return self.get_risk_summary()
        if len(parts) == 2 and parts[0] == "risks" and parts[1] == "common":
            return self._summarize_common_risks(self.get_common_risks())
        if len(parts) == 2 and parts[0] == "security" and parts[1] == "policy":
            return self.get_security_policy()
        if len(parts) == 2 and parts[0] == "security" and parts[1] == "audit-log":
            return self._summarize_security_audit_log(self.get_security_audit_log())
        if len(parts) == 2 and parts[0] == "system" and parts[1] == "status":
            return self.get_system_status()
        if len(parts) == 2 and parts[0] == "system" and parts[1] == "auth-state":
            return self.get_auth_state()
        if len(parts) == 2 and parts[0] == "system" and parts[1] == "codex-status":
            return self.get_codex_status()
        if len(parts) == 2 and parts[0] == "startup" and parts[1] == "status":
            return self.get_startup_status()
        if len(parts) == 2 and parts[0] == "daemon" and parts[1] == "status":
            return self.daemon_status()
        if len(parts) == 2 and parts[0] == "runners" and parts[1] == "status":
            return self.get_runners_status()
        if len(parts) == 2 and parts[0] == "plugin" and parts[1] == "health":
            return self.plugin_health_summary()
        if len(parts) == 2 and parts[0] == "headless" and parts[1] == "config":
            return self.get_headless_config()
        if len(parts) == 2 and parts[0] == "dashboard" and parts[1] == "summary":
            return self.get_dashboard_summary()
        if len(parts) >= 2 and parts[0] == "widgets" and parts[1] == "catalog":
            if len(parts) not in (2, 3):
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
            scope = parts[2] if len(parts) == 3 else None
            return {"scope": scope or "all", "catalog": self.get_widget_catalog(scope=scope)}
        if len(parts) >= 2 and parts[0] == "widgets" and parts[1] == "instances":
            if len(parts) == 4 and parts[3] == "data":
                try:
                    instance_id = int(parts[2])
                except ValueError as exc:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                return self._summarize_widget_instance_data(instance_id, self.get_widget_instance_data(instance_id))
            if len(parts) != 2:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
            return self._summarize_widget_instances(self.list_widget_instances())
        if len(parts) == 1 and parts[0] == "preferences":
            return self._summarize_preferences(self.get_preferences())
        if len(parts) >= 1 and parts[0] == "subagent-policy":
            if len(parts) == 2 and parts[1] == "summary":
                return self.get_subagent_policy_summary()
            if len(parts) != 1:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
            return self._summarize_subagent_policy(self.get_subagent_policy())
        if len(parts) == 1 and parts[0] == "skills":
            return self._summarize_skills(self.get_skills())
        if len(parts) == 1 and parts[0] == "projects":
            return self._summarize_projects(self.list_projects())
        if len(parts) == 2 and parts[0] == "projects":
            try:
                project_id = int(parts[1])
            except ValueError as exc:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
            return self._summarize_project_details(self.get_project(project_id))
        if len(parts) >= 3 and parts[0] == "orchestrations":
            try:
                orchestration_id = int(parts[1])
            except ValueError as exc:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
            kind = parts[2]
            if kind == "status":
                raise RuntimeError(
                    "Cold orchestration resource reads require the project-scoped URI "
                    "`mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`."
                )
            if kind == "events":
                raise RuntimeError(
                    "Cold orchestration resource reads require the project-scoped URI "
                    "`mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`."
                )
        if len(parts) >= 3 and parts[0] == "projects":
            try:
                project_id = int(parts[1])
            except ValueError as exc:
                raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
            kind = parts[2]
            if kind == "orchestrations" and len(parts) >= 4 and parts[3] == "active":
                if len(parts) != 4:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_active_orchestration(project_id, self.active_project_orchestration(project_id))
            if kind == "orchestrations" and len(parts) == 4:
                try:
                    orchestration_id = int(parts[3])
                except ValueError as exc:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                return self._summarize_orchestration_session(project_id, self.get_orchestration(orchestration_id, project_id=project_id))
            if kind == "orchestrations" and len(parts) >= 5:
                try:
                    orchestration_id = int(parts[3])
                except ValueError as exc:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                detail_kind = parts[4]
                if detail_kind == "status" and len(parts) == 5:
                    return self._summarize_status(self.get_status(orchestration_id=orchestration_id, project_id=project_id))
                if detail_kind == "events" and len(parts) == 5:
                    return self._summarize_events(orchestration_id, self.get_orchestration_events(orchestration_id, project_id=project_id))
            if kind == "decisions" and len(parts) == 5 and parts[4] == "bridge-message":
                try:
                    decision_id = int(parts[3])
                except ValueError as exc:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                return self.get_decision_bridge_message(decision_id, project_id=project_id)
            if kind == "status-summary" and len(parts) == 3:
                return self.get_status_summary(project_id=project_id)
            if kind == "orchestrations" and len(parts) >= 4:
                if len(parts) == 5 and parts[4] == "status-summary":
                    return self.get_status_summary(orchestration_id=orchestration_id, project_id=project_id)
                if len(parts) == 5 and parts[4] == "event-digest":
                    return self.get_event_digest(orchestration_id=orchestration_id, project_id=project_id)
                if len(parts) == 5 and parts[4] == "handoff-summary":
                    return self.get_handoff_summary(orchestration_id=orchestration_id, project_id=project_id)
                if len(parts) == 5 and parts[4] == "handoff":
                    return self._summarize_handoff(project_id, self.get_handoff(orchestration_id=orchestration_id, project_id=project_id))
                if len(parts) == 5 and parts[4] == "pending-decisions":
                    return self._summarize_pending_decisions(
                        project_id,
                        self.get_pending_decisions(orchestration_id=orchestration_id, project_id=project_id),
                    )
            if kind == "status":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                project = self.get_project(project_id)
                orchestration_id = self._maybe_orchestration_id(project_id=project_id)
                status = self.get_status(orchestration_id=orchestration_id, project_id=project_id) if orchestration_id is not None else None
                return self._summarize_project_status(project, status)
            if kind == "agents" and len(parts) == 5 and parts[4] == "logs":
                try:
                    agent_id = int(parts[3])
                except ValueError as exc:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                return self._summarize_agent_logs(project_id, agent_id, self.get_agent_logs(project_id, agent_id))
            if kind == "agents" and len(parts) == 4 and parts[3] == "reputation":
                return self._summarize_agent_reputation(self.get_agent_reputation(project_id), project_id=project_id)
            if kind == "agents":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_agents(project_id, self.get_agents(project_id))
            if kind == "pending-decisions":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                decisions = self.get_pending_decisions(project_id=project_id)
                return self._summarize_pending_decisions(project_id, decisions)
            if kind == "questions" and len(parts) == 4 and parts[3] == "pending":
                return self._summarize_pending_questions(project_id, self.get_pending_questions(project_id))
            if kind == "approvals" and len(parts) == 4 and parts[3] == "pending":
                return self._summarize_pending_approvals(project_id, self.get_pending_approvals(project_id))
            if kind == "event-digest" and len(parts) == 3:
                return self.get_event_digest(project_id=project_id)
            if kind == "handoff-summary" and len(parts) == 3:
                return self.get_handoff_summary(project_id=project_id)
            if kind == "handoff":
                if len(parts) == 4 and parts[3] == "evidence":
                    return self._summarize_handoff_evidence(project_id, self.get_handoff_evidence(project_id))
                if len(parts) == 5 and parts[3] == "evidence" and parts[4] == "preview":
                    return self.get_handoff_evidence_preview(project_id)
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_handoff(project_id, self.get_project_handoff(project_id))
            if kind == "codebase-map":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                codebase_map = self.get_codebase_map(project_id)
                understanding = self.get_codebase_understanding(project_id)
                return self._summarize_codebase_map(codebase_map, understanding)
            if kind == "context-packs":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_context_packs(project_id, self.get_context_packs(project_id))
            if kind == "scope-creep":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_scope_creep(project_id, self.get_scope_creep(project_id))
            if kind == "codebase-understanding":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_codebase_understanding(project_id)
            if kind == "understanding":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_project_understanding(project_id, self.get_project_understanding(project_id))
            if kind == "interview":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_interview(project_id, self.get_interview(project_id))
            if kind == "plan":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_plan(project_id, self.get_plan(project_id))
            if kind == "reservations":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_reservations(project_id, self.get_reservations(project_id))
            if kind == "import-safety":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_import_safety(project_id)
            if kind == "diagnostics" and len(parts) == 4 and parts[3] == "latest-report":
                return self._summarize_latest_diagnostic_report(project_id, self.list_diagnostic_reports(project_id=project_id))
            if kind == "diagnostics":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_diagnostics(project_id, self.get_diagnostics(project_id=project_id))
            if kind == "settings":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_project_settings(project_id)
            if kind == "details":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_project_details(self.get_project(project_id))
            if kind == "swarm" and len(parts) == 4 and parts[3] == "preferences":
                return self.get_swarm_preferences(project_id)
            if kind == "swarm" and len(parts) == 4 and parts[3] == "plan":
                prefs = self.get_swarm_preferences(project_id)
                plan = self.get_swarm_plan(project_id)
                return self._summarize_swarm_plan(project_id, plan, prefs)
            if kind == "swarm" and len(parts) == 4 and parts[3] == "events":
                return self._summarize_swarm_events(project_id, self.get_swarm_events(project_id))
            if kind == "swarm" and len(parts) == 4 and parts[3] == "simulations":
                return self._summarize_swarm_simulations(project_id, self.list_swarm_simulations(project_id))
            if kind == "swarm-plan":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                prefs = self.get_swarm_preferences(project_id)
                plan = self.get_swarm_plan(project_id)
                return self._summarize_swarm_plan(project_id, plan, prefs)
            if kind == "swarm" and len(parts) == 5 and parts[3] == "simulations" and parts[4] == "latest":
                return self.get_latest_swarm_simulation(project_id)
            if kind == "risk-register":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_risks(project_id, self.get_risks(project_id))
            if kind == "risks" and len(parts) == 3:
                return self._summarize_risks(project_id, self.get_risks(project_id))
            if kind == "risks" and len(parts) == 4 and parts[3] == "summary":
                return self.get_risk_summary(project_id)
            if kind == "agent-contracts":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_agent_contracts(project_id, self.get_agent_contracts(project_id))
            if kind == "validation-summary":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_validation_summary(project_id, self.get_validation_summary(project_id))
            if kind == "validation-coverage" and len(parts) == 4 and parts[3] == "summary":
                return self.get_validation_coverage_summary(project_id)
            if kind == "decision-ledger":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_decision_ledger(project_id, self.get_decision_ledger(project_id))
            if kind == "path-locks":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_path_locks(project_id, self.get_path_locks(project_id))
            if kind == "security" and len(parts) == 4 and parts[3] == "policy":
                return self.get_security_policy(project_id)
            if kind == "security" and len(parts) == 4 and parts[3] == "audit-log":
                return self._summarize_security_audit_log(self.get_security_audit_log(project_id), project_id=project_id)
            if kind == "agents-md" and len(parts) == 4 and parts[3] == "status":
                return self.get_agents_md_status(project_id)
            if kind == "operator-snapshot":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_operator_snapshot(project_id, self.get_operator_snapshot(project_id))
            if kind == "instincts":
                if len(parts) == 4 and parts[3] == "preview":
                    return self._summarize_instincts_preview(project_id, self.get_instincts_preview(project_id))
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_instincts_preview(project_id, self.get_instincts_preview(project_id))
            if kind == "verification-brief":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_verification_brief(project_id, self.get_verification_brief(project_id))
            if kind == "capability-report":
                if len(parts) == 4:
                    section_key = parts[3]
                    return self._summarize_capability_section(
                        project_id,
                        section_key,
                        self.get_capability_section(project_id, section_key),
                    )
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_capability_report(project_id, self.get_capability_report(project_id))
            if kind == "workspace":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_project_workspace(project_id)
            if kind == "workspace-tooling":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_workspace_tooling(project_id, self.get_workspace_tooling(project_id))
            if kind == "action":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_project_action(project_id)
            if kind == "actions":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_project_actions(project_id, self.list_project_actions(project_id))
            if kind == "manager" and len(parts) == 4 and parts[3] == "messages":
                return self._summarize_manager_messages(project_id, self.get_manager_messages(project_id))
            if kind == "manager" and len(parts) == 4 and parts[3] == "queue":
                return self.get_manager_queue(project_id)
            if kind == "widgets" and len(parts) == 4 and parts[3] == "instances":
                return self._summarize_widget_instances(self.get_project_widget_instances(project_id), project_id=project_id)
            if kind == "runbook":
                if len(parts) == 4 and parts[3] == "summary":
                    return self.get_runbook_summary(project_id)
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_runbook(project_id, self.get_runbook(project_id))
            if kind == "safe-mode":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_safe_mode(project_id)
            if kind == "tasks":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_tasks(project_id, self.get_project_tasks(project_id))
            if kind == "recovery-plans":
                if len(parts) == 4 and parts[3] == "preview":
                    return self.get_recovery_plans_preview(project_id)
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_recovery_plans(project_id, self.get_recovery_plans(project_id))
            if kind == "events":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_project_events(project_id, self.get_project_events(project_id))
            if kind == "snapshots":
                if len(parts) == 5 and parts[4] == "restore-plan":
                    try:
                        snapshot_id = int(parts[3])
                    except ValueError as exc:
                        raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                    return self.get_snapshot_restore_plan(project_id, snapshot_id)
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_snapshots(project_id, self.list_snapshots(project_id))
            if kind == "playbook":
                if len(parts) == 4 and parts[3] == "recommendations":
                    return {"project_id": project_id, "recommendations": self.get_playbook_recommendations(project_id)}
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self.get_playbook(project_id)
            if kind == "preferences":
                if len(parts) == 3:
                    return self._summarize_preferences(self.get_project_preferences(project_id), project_id=project_id)
                if len(parts) == 4 and parts[3] == "summary":
                    return self.get_project_preference_summary(project_id)
                if len(parts) == 4 and parts[3] == "effective":
                    return self._summarize_effective_preferences(project_id, self.get_effective_preferences(project_id))
            if kind == "validation-coverage":
                if len(parts) == 3:
                    return self._summarize_validation_coverage(project_id, self.get_validation_coverage(project_id))
                if len(parts) == 4 and parts[3] == "summary":
                    return self.get_validation_coverage_summary(project_id)
            if kind == "widgets" and len(parts) == 4 and parts[3] == "summary":
                return self.get_project_widget_summary(project_id)
            if kind == "subagent-batches":
                if len(parts) == 4:
                    try:
                        batch_id = int(parts[3])
                    except ValueError as exc:
                        raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}") from exc
                    return self._summarize_subagent_batch(project_id, self.get_subagent_batch(project_id, batch_id))
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_subagent_batches(project_id, self.get_project_subagent_batches(project_id))
            if kind == "execution-policy" and len(parts) == 4 and parts[3] == "summary":
                return self.get_execution_policy_summary(project_id)
            if kind == "coordination" and len(parts) == 4 and parts[3] == "summary":
                return self.get_coordination_summary(project_id)
            if kind == "integrations":
                if project_id is None:
                    raise ValueError("Project-scoped integration resources require a project id.")
                if len(parts) == 5 and parts[4] == "actions":
                    family = parts[3]
                    return self._summarize_project_integration_actions(
                        project_id,
                        family,
                        self.get_project_integration_family(project_id, family),
                    )
                if len(parts) == 7 and parts[4] == "actions" and parts[6] == "preview":
                    family = parts[3]
                    action_id = parts[5]
                    return self._summarize_integration_action_preview(
                        project_id,
                        family,
                        action_id,
                        self.preview_project_integration_action(project_id, family, action_id),
                    )
                if len(parts) == 4:
                    return self._summarize_project_integration_family(
                        project_id,
                        self.get_project_integration_family(project_id, parts[3]),
                    )
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_project_integrations(project_id, self.get_project_integrations(project_id))
            if kind == "tensorflow" and len(parts) >= 4 and parts[3] == "features":
                if len(parts) == 4:
                    return self._summarize_ml_feature_catalog(project_id, self.get_tensorflow_feature_catalog(project_id))
                if len(parts) != 5:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                feature_id = parts[4]
                return self._summarize_ml_feature_bundle(project_id, self.get_tensorflow_feature_bundle(project_id, feature_id))
            if kind == "pytorch" and len(parts) >= 4 and parts[3] == "features":
                if len(parts) == 4:
                    return self._summarize_ml_feature_catalog(project_id, self.get_pytorch_feature_catalog(project_id))
                if len(parts) != 5:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                feature_id = parts[4]
                return self._summarize_ml_feature_bundle(project_id, self.get_pytorch_feature_bundle(project_id, feature_id))
            if kind == "spatial" and len(parts) >= 4 and parts[3] == "features":
                if len(parts) == 4:
                    return self._summarize_spatial_feature_catalog(project_id, self.get_spatial_feature_catalog(project_id))
                if len(parts) != 5:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                feature_id = parts[4]
                return self._summarize_spatial_feature_bundle(project_id, self.get_spatial_feature_bundle(project_id, feature_id))
            if kind == "webwright":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_webwright_status(project_id, self.get_webwright_status(project_id))
            if kind == "nvidia" and len(parts) == 4:
                nvidia_kind = parts[3]
                if nvidia_kind == "dynamo":
                    return self._summarize_nvidia_dynamo_status(project_id, self.get_nvidia_dynamo_status(project_id))
                if nvidia_kind == "nim":
                    return self._summarize_nvidia_nim_status(project_id, self.get_nvidia_nim_status(project_id))
                if nvidia_kind == "aiq":
                    return self._summarize_nvidia_aiq_status(project_id, self.get_nvidia_aiq_status(project_id))
                if nvidia_kind == "gpu-diagnostics":
                    return self._summarize_nvidia_gpu_diagnostics(project_id, self.get_nvidia_gpu_diagnostics(project_id))
                if nvidia_kind == "local-runtime":
                    return self._summarize_nvidia_local_runtime_status(project_id, self.get_nvidia_local_runtime_status(project_id))
                if nvidia_kind == "validation-plan":
                    return self._summarize_nvidia_validation_plan(project_id, self.get_nvidia_validation_plan(project_id))
            if kind == "nvidia-dynamo":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_dynamo_status(project_id, self.get_nvidia_dynamo_status(project_id))
            if kind == "nvidia-nim":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_nim_status(project_id, self.get_nvidia_nim_status(project_id))
            if kind == "nvidia-aiq":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_aiq_status(project_id, self.get_nvidia_aiq_status(project_id))
            if kind == "nvidia-gpu-diagnostics":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_gpu_diagnostics(project_id, self.get_nvidia_gpu_diagnostics(project_id))
            if kind == "nvidia-local-runtime":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_local_runtime_status(project_id, self.get_nvidia_local_runtime_status(project_id))
            if kind == "nvidia-validation-plan":
                if len(parts) != 3:
                    raise RuntimeError(f"Unsupported Mission Control resource URI: {uri}")
                return self._summarize_nvidia_validation_plan(project_id, self.get_nvidia_validation_plan(project_id))
        raise RuntimeError("Unsupported Mission Control resource URI.")
