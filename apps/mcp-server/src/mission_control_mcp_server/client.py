from __future__ import annotations

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

    def _discover_repo_root(self) -> Path:
        explicit = os.environ.get("MISSION_CONTROL_REPO_ROOT")
        if explicit:
            return Path(explicit).expanduser().resolve()
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "apps" / "server" / "src" / "main.py").exists() and (parent / "README.md").exists():
                return parent
        raise RuntimeError("Could not discover the Codex Mission Control repository root.")

    def _load_launcher_config(self) -> dict[str, Any]:
        server_src = self.repo_root / "apps" / "server" / "src"
        if server_src.exists() and str(server_src) not in sys.path:
            sys.path.insert(0, str(server_src))
        try:
            from config import load_launcher_config

            return load_launcher_config()
        except Exception:
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
        return (self.repo_root / "apps" / "server" / ".runtime").resolve()

    @property
    def _launcher_root(self) -> Path:
        explicit = os.environ.get("MISSION_CONTROL_LAUNCHER_DIR")
        if explicit:
            return Path(explicit).expanduser().resolve()
        launcher_dir = str(self.config.get("launcherLogDir", ".runtime/launcher"))
        return (self.repo_root / launcher_dir).resolve()

    @property
    def _daemon_token_path(self) -> Path:
        return self._runtime_root / "daemon.token"

    @property
    def _server_script(self) -> Path:
        return (self.repo_root / "apps" / "server" / "src" / "mission_control_daemon.py").resolve()

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
                response = client.get(f"{self.base_url}/api/diagnostics/identity")
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
        expected_repo = str(self.repo_root)
        actual_repo = str(identity.get("repo_root") or "")
        actual_port = int(identity.get("port") or 0)
        actual_mode = str(identity.get("mode") or "unknown")
        if actual_repo and actual_repo != expected_repo:
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
        env.setdefault("MISSION_CONTROL_REPO_ROOT", str(self.repo_root))
        stdout_handle = open(self._launcher_root / "daemon.stdout.log", "a", encoding="utf-8")
        stderr_handle = open(self._launcher_root / "daemon.stderr.log", "a", encoding="utf-8")
        kwargs: dict[str, Any] = {"cwd": str(self.repo_root), "env": env, "stdout": stdout_handle, "stderr": stderr_handle}
        if os.name == "nt":
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([sys.executable, str(self._server_script)], **kwargs)
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
        session = self.get_orchestration(orchestration_id)
        resolved_project_id = int(session["project_id"])
        self._remember_orchestration_project(orchestration_id, resolved_project_id)
        return resolved_project_id

    def daemon_status(self) -> dict[str, Any]:
        return self._request("GET", "/api/daemon/status", requires_token=False)

    def plugin_health(self) -> dict[str, Any]:
        return self._request("GET", "/api/orchestrations/plugin-health", requires_token=True)

    def plugin_health_summary(self) -> dict[str, Any]:
        return self.plugin_health()

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

    def get_project(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}")

    def get_orchestration(self, orchestration_id: int) -> dict[str, Any]:
        payload = self._request("GET", f"/api/orchestrations/{orchestration_id}")
        if isinstance(payload, dict):
            self._remember_orchestration_project(payload.get("id"), payload.get("project_id"))
        return payload

    def active_project_orchestration(self, project_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/projects/{project_id}/orchestrations/active")

    def get_status(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is None:
            raise RuntimeError("Mission Control status requires an orchestration_id or a project with an active orchestration.")
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        payload = self._request("GET", f"/api/orchestrations/{resolved_id}/status", params={"project_id": resolved_project_id})
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
        return self._request("GET", f"/api/orchestrations/{resolved_id}/pending-decisions", params={"project_id": resolved_project_id})

    def answer_decision(self, *, decision_id: int, project_id: int, option_id: str, selected_text: str, free_text: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/decisions/{decision_id}/answer",
            params={"project_id": project_id},
            json_body={"option_id": option_id, "selected_text": selected_text, "free_text": free_text},
        )

    def pause(self, orchestration_id: int, *, project_id: int | None = None) -> dict[str, Any]:
        resolved_project_id = self._project_id_for_orchestration(orchestration_id, project_id=project_id)
        return self._request("POST", f"/api/orchestrations/{orchestration_id}/pause", params={"project_id": resolved_project_id}, json_body={})

    def resume(self, orchestration_id: int, *, project_id: int | None = None) -> dict[str, Any]:
        resolved_project_id = self._project_id_for_orchestration(orchestration_id, project_id=project_id)
        return self._request("POST", f"/api/orchestrations/{orchestration_id}/resume", params={"project_id": resolved_project_id}, json_body={})

    def get_handoff(self, *, orchestration_id: int | None = None, project_id: int | None = None) -> dict[str, Any]:
        resolved_id = self._maybe_orchestration_id(orchestration_id=orchestration_id, project_id=project_id)
        if resolved_id is None:
            raise RuntimeError("Mission Control handoff lookup requires an orchestration_id or a project with an active orchestration.")
        resolved_project_id = self._project_id_for_orchestration(resolved_id, project_id=project_id)
        return self._request("GET", f"/api/orchestrations/{resolved_id}/handoff", params={"project_id": resolved_project_id})

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

    def get_orchestration_events(self, orchestration_id: int, *, project_id: int | None = None) -> list[dict[str, Any]]:
        resolved_project_id = self._project_id_for_orchestration(orchestration_id, project_id=project_id)
        return self._request("GET", f"/api/orchestrations/{orchestration_id}/events", params={"project_id": resolved_project_id})

    def get_agents(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/agents")

    def get_agent_contracts(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/agent-contracts")

    def get_pending_questions(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/questions/pending")

    def get_pending_approvals(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/approvals/pending")

    def get_project_handoff(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/handoff", requires_token=False)

    def get_decision_ledger(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/decision-ledger")

    def get_path_locks(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/path-locks")

    def get_codebase_map(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/codebase-map", requires_token=False)

    def get_codebase_understanding(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/codebase-understanding", requires_token=False)

    def set_import_interview_choice(self, project_id: int, choice: str) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/import/interview-choice", json_body={"choice": choice})

    def get_import_safety(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/import-safety")

    def update_import_safety(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/api/projects/{project_id}/import-safety", json_body=payload)

    def get_project_settings(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", "/api/settings", params={"project_id": project_id})

    def update_project_settings(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", "/api/settings", params={"project_id": project_id}, json_body=payload)

    def get_tool_catalog(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/tools")

    def set_tool_permission(self, tool_id: str, permission_policy: str) -> dict[str, Any]:
        return self._request("PUT", f"/api/tools/{tool_id}/permission", json_body={"permission_policy": permission_policy})

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

    def approve_swarm_plan(self, project_id: int, swarm_plan_id: int) -> dict[str, Any]:
        return self._request("POST", f"/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/approve", json_body={})

    def get_risks(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/risks")

    def get_validation_summary(self, project_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/api/projects/{project_id}/validation-coverage")

    def get_agents_md_status(self, project_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/projects/{project_id}/agents-md/status")

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
        reports = self._request("GET", "/api/diagnostics/reports")
        latest_report = reports[0] if reports else None
        resolved_project_id = project_id
        if resolved_project_id is None and orchestration_id is not None:
            session = self.get_orchestration(orchestration_id)
            resolved_project_id = int(session["project_id"])
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
            "recommended_fixes": plugin_health.get("recommended_fixes", []),
            "recent_reports": reports[:5],
            "platform_profile": latest_report.get("platform_profile", {}) if isinstance(latest_report, dict) else {},
            "performance_profile": latest_report.get("performance_profile", {}) if isinstance(latest_report, dict) else {},
            "safe_debug_commands": latest_report.get("safe_debug_commands", []) if isinstance(latest_report, dict) else [],
            "bundle_path": latest_report.get("bundle_path") if isinstance(latest_report, dict) else None,
            "orchestration_status": status.get("orchestration_status") if status else None,
            "manager_status": status.get("manager_status") if status else None,
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
            session = self.get_orchestration(orchestration_id)
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
            session = self.get_orchestration(orchestration_id)
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

    def _summarize_handoff(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        handoff = payload.get("handoff") if "handoff" in payload else payload
        return {
            "project_id": project_id,
            "project_name": handoff.get("project_name"),
            "status": payload.get("status", handoff.get("status")),
            "ready": payload.get("ready", True),
            "summary": handoff.get("summary"),
            "run_instructions": handoff.get("run_instructions", []),
            "tests_count": handoff.get("tests_count", 0),
            "confidence_level": handoff.get("confidence_level"),
            "evidence_status": handoff.get("evidence_status"),
            "missing_evidence": handoff.get("missing_evidence", []),
            "known_limitations": handoff.get("known_limitations", []),
            "dry_run": handoff.get("dry_run", False),
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

    def _stub_agent_contracts(self, project_id: int) -> dict[str, Any]:
        return {
            "project_id": project_id,
            "support_status": "stubbed",
            "summary": "The backend tracks agent contracts internally, but the MCP bridge does not yet expose a dedicated read endpoint.",
            "todo": "Expose a read-only agent-contract summary endpoint for Codex chat."
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

    def read_resource(self, uri: str) -> dict[str, Any]:
        if not uri.startswith("mission-control://"):
            raise RuntimeError("Unsupported Mission Control resource URI.")
        parts = [segment for segment in uri.removeprefix("mission-control://").split("/") if segment]
        if len(parts) >= 3 and parts[0] == "orchestrations":
            orchestration_id = int(parts[1])
            kind = parts[2]
            if kind == "status":
                return self._summarize_status(self.get_status(orchestration_id=orchestration_id))
            if kind == "events":
                return self._summarize_events(orchestration_id, self.get_orchestration_events(orchestration_id))
        if len(parts) >= 3 and parts[0] == "projects":
            project_id = int(parts[1])
            kind = parts[2]
            if kind == "status":
                project = self.get_project(project_id)
                orchestration_id = self._maybe_orchestration_id(project_id=project_id)
                status = self.get_status(orchestration_id=orchestration_id) if orchestration_id is not None else None
                return self._summarize_project_status(project, status)
            if kind == "agents":
                return self._summarize_agents(project_id, self.get_agents(project_id))
            if kind == "pending-decisions":
                decisions = self.get_pending_decisions(project_id=project_id)
                return self._summarize_pending_decisions(project_id, decisions)
            if kind == "handoff":
                return self._summarize_handoff(project_id, self.get_project_handoff(project_id))
            if kind == "codebase-map":
                codebase_map = self.get_codebase_map(project_id)
                understanding = self.get_codebase_understanding(project_id)
                return self._summarize_codebase_map(codebase_map, understanding)
            if kind == "diagnostics":
                return self._summarize_diagnostics(project_id, self.get_diagnostics(project_id=project_id))
            if kind == "swarm-plan":
                prefs = self.get_swarm_preferences(project_id)
                plan = self.get_swarm_plan(project_id)
                return self._summarize_swarm_plan(project_id, plan, prefs)
            if kind == "risk-register":
                return self._summarize_risks(project_id, self.get_risks(project_id))
            if kind == "agent-contracts":
                return self._summarize_agent_contracts(project_id, self.get_agent_contracts(project_id))
            if kind == "validation-summary":
                return self._summarize_validation(project_id, self.get_validation_summary(project_id))
            if kind == "decision-ledger":
                return self._summarize_decision_ledger(project_id, self.get_decision_ledger(project_id))
            if kind == "path-locks":
                return self._summarize_path_locks(project_id, self.get_path_locks(project_id))
        raise RuntimeError("Unsupported Mission Control resource URI.")
