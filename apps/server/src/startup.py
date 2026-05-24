from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app_profile import complete_first_run, get_or_create_app_profile
from config import DEFAULT_APPROVAL_POLICY, DEFAULT_RUNNER_MODE, DEFAULT_SANDBOX
from diagnostics import write_diagnostic_report
from errors import MissionControlError
from models import AppProfile, Project
from provider_support import normalize_provider
from runtime_paths import ensure_runtime_paths
from schemas import CompleteFirstRunRequest
from system_status import detect_codex_status, detect_provider_statuses


CURRENT_SETUP_VERSION = "startup-v1"
MAX_STARTUP_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StartupCoordinator:
    def __init__(self) -> None:
        self.last_status: dict[str, Any] | None = None
        self.last_started_at = _now()

    def _base_payload(self, profile: AppProfile, *, attempt: int) -> dict[str, Any]:
        started_at = self.last_started_at if attempt > 1 and self.last_status else _now()
        self.last_started_at = started_at
        install_id = profile.install_id or "missing-install-id"
        return {
            "mode": "regular",
            "first_run_completed": bool(profile.first_run_completed or profile.onboarding_completed),
            "onboarding_complete": bool(profile.first_run_completed or profile.onboarding_completed),
            "setup_version_completed": profile.setup_version_completed,
            "current_setup_version": CURRENT_SETUP_VERSION,
            "install_id": install_id,
            "startup_attempt": attempt,
            "max_startup_attempts": MAX_STARTUP_ATTEMPTS,
            "overall_status": "starting",
            "backend_ready": False,
            "checks": [],
            "recommended_route": "/startup",
            "error_code": None,
            "error_summary": None,
            "diagnostic_report_path": None,
            "degraded_reasons": [],
            "failed_checks": [],
            "startup_started_at": started_at,
            "last_completed_at": None,
        }

    @staticmethod
    def _check(
        name: str,
        *,
        required: bool,
        status: str,
        summary: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        error: MissionControlError | None = None,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "required": required,
            "status": status,
            "summary": summary,
            "error_code": error.code if error is not None else error_code,
            "family": error.family if error is not None else None,
            "severity": error.severity if error is not None else None,
            "breakpoint": error.breakpoint if error is not None else None,
            "retryable": bool(error.retryable) if error is not None else None,
            "user_action_required": bool(error.user_action_required) if error is not None else None,
            "recommended_fix": error.recommended_fix if error is not None else None,
            "correlation_id": error.correlation_id if error is not None else None,
            "details": details or {},
        }

    def _selected_provider_failure_names(self, selected_provider: str) -> set[str]:
        mapping = {
            "codex": {"codex_cli", "codex_login", "app_server"},
            "claude_code": {"claude_code"},
            "ollama": {"ollama"},
            "openai_api": {"openai_api"},
            "anthropic_api": {"anthropic_api"},
            "xai_api": {"xai_api"},
            "custom": {"custom"},
        }
        return mapping.get(normalize_provider(selected_provider), set())

    def _check_runtime_paths(self) -> dict[str, Any]:
        try:
            paths = ensure_runtime_paths()
            return self._check("runtime_paths", required=True, status="passed", summary="Runtime folders are available.", details=paths)
        except Exception as exc:  # noqa: BLE001
            error = MissionControlError(
                code="MC-BOOT-RUNTIME-PATH-001",
                detail=str(exc),
                breakpoint="bootstrap.start",
                caused_by=exc,
            )
            return self._check("runtime_paths", required=True, status="failed", summary=error.detail or str(exc), error=error)

    def _check_database(self, db: Session) -> dict[str, Any]:
        try:
            db.execute(text("SELECT 1"))
            return self._check("database", required=True, status="passed", summary="Database connection is healthy.")
        except Exception as exc:  # noqa: BLE001
            error = MissionControlError(
                code="MC-STORAGE-DB-UNAVAILABLE-001",
                detail=str(exc),
                breakpoint="bootstrap.health_check",
                caused_by=exc,
            )
            return self._check("database", required=True, status="failed", summary=error.detail or str(exc), error=error)

    def _check_settings(self, db: Session) -> tuple[dict[str, Any], AppProfile | None]:
        try:
            profile = get_or_create_app_profile(db)
            if not profile.install_id:
                profile.install_id = "missing-install-id"
            if not profile.selected_provider:
                profile.selected_provider = normalize_provider(profile.preferred_provider_choice)
            return (
                self._check(
                    "settings",
                    required=True,
                    status="passed",
                    summary="App startup state loaded.",
                    details={
                        "first_run_completed": bool(profile.first_run_completed or profile.onboarding_completed),
                        "selected_provider": normalize_provider(profile.selected_provider),
                    },
                ),
                profile,
            )
        except Exception as exc:  # noqa: BLE001
            error = MissionControlError(
                code="MC-BOOT-DEPENDENCY-MISSING-001",
                detail=str(exc),
                breakpoint="bootstrap.environment_probe",
                caused_by=exc,
            )
            return (
                self._check("settings", required=True, status="failed", summary=error.detail or str(exc), error=error),
                None,
            )

    def _check_projects(self, db: Session) -> dict[str, Any]:
        try:
            project_count = db.scalar(select(func.count(Project.id))) or 0
            return self._check("projects", required=True, status="passed", summary=f"Loaded {project_count} project records.", details={"project_count": project_count})
        except Exception as exc:  # noqa: BLE001
            error = MissionControlError(
                code="MC-STORAGE-DB-UNAVAILABLE-001",
                detail=str(exc),
                breakpoint="bootstrap.health_check",
                caused_by=exc,
            )
            return self._check("projects", required=True, status="failed", summary=error.detail or str(exc), error=error)

    def _check_backend_route(self) -> dict[str, Any]:
        return self._check("backend_route", required=True, status="passed", summary="Backend route availability confirmed.")

    def _codex_optional_checks(self) -> list[dict[str, Any]]:
        status = detect_codex_status()
        cli_check = self._check(
            "codex_cli",
            required=False,
            status="passed" if status["cli_detected"] else "failed",
            summary=status["cli_version"] or ("Codex CLI path was detected." if status["cli_detected"] else "Codex CLI was not detected on PATH."),
            error=None
            if status["cli_detected"]
            else MissionControlError(code="MC-CODEX-CLI-MISSING-001", breakpoint="codex_cli.detect"),
        )
        login_check = self._check(
            "codex_login",
            required=False,
            status="passed" if status["authenticated"] else "warning",
            summary=status["login_status"],
            error=None
            if status["authenticated"]
            else MissionControlError(code="MC-CODEX-LOGIN-UNKNOWN-001", breakpoint="codex_cli.login_status", severity="warning"),
        )
        app_server_check = self._check(
            "app_server",
            required=False,
            status="passed" if status["app_server_supported"] else "warning",
            summary="Codex app-server support detected." if status["app_server_supported"] else "Codex app-server support not detected; CLI fallback remains available.",
            error=None if status["app_server_supported"] else MissionControlError(code="MC-DAEMON-HEALTH-FAILED-001", breakpoint="daemon.health_check", severity="warning"),
        )
        return [cli_check, login_check, app_server_check]

    def _provider_optional_checks(self, profile: AppProfile) -> list[dict[str, Any]]:
        selected = normalize_provider(profile.selected_provider)
        checks: list[dict[str, Any]] = self._codex_optional_checks()
        provider_statuses = detect_provider_statuses(profile.adapter_command, profile.provider_endpoint, list(profile.adapter_args_json or []))
        by_provider = {item["provider"]: item for item in provider_statuses}

        checks.append(
            self._check(
                "claude_code",
                required=False,
                status=(
                    "failed"
                    if selected == "claude_code" and not by_provider["claude_code"]["cli_detected"]
                    else "warning"
                    if selected == "claude_code"
                    else "skipped"
                ),
                summary=str(by_provider["claude_code"].get("runtime_summary") or by_provider["claude_code"]["login_status"]),
                error=(
                    MissionControlError(code="MC-CLAUDE-CLI-MISSING-001", breakpoint="claude_cli.detect")
                    if selected == "claude_code" and not by_provider["claude_code"]["cli_detected"]
                    else MissionControlError(code="MC-CLAUDE-AUTH-UNKNOWN-001", breakpoint="claude_cli.auth_status", severity="warning")
                    if selected == "claude_code"
                    else None
                ),
                details=by_provider["claude_code"],
            )
        )

        for provider_name, error_code, breakpoint in (
            ("ollama", "MC-OLLAMA-SERVER-OFFLINE-001", "ollama.server_check"),
            ("openai_api", "MC-API-KEY-MISSING-001", "api_provider.auth_check"),
            ("anthropic_api", "MC-API-KEY-MISSING-001", "api_provider.auth_check"),
            ("xai_api", "MC-API-KEY-MISSING-001", "api_provider.auth_check"),
            ("custom", "MC-RUNNER-NONE-AVAILABLE-001", "runner.select"),
        ):
            provider_status = by_provider[provider_name]
            is_selected = selected == provider_name
            checks.append(
                self._check(
                    provider_name,
                    required=False,
                    status="passed" if provider_status.get("runtime_ready") else ("failed" if is_selected else "skipped"),
                    summary=str(provider_status.get("runtime_summary") or provider_status.get("login_status") or "Runtime status unavailable."),
                    error=MissionControlError(code=error_code, breakpoint=breakpoint, severity="warning") if is_selected and not provider_status.get("runtime_ready") else None,
                    details=provider_status,
                )
            )

        accounts = profile.connected_accounts_json or {}
        for account_name in ("github", "vercel", "notion"):
            account = accounts.get(account_name) if isinstance(accounts, dict) else None
            status = "skipped"
            summary = "Not connected."
            if isinstance(account, dict):
                state = str(account.get("status") or "not_connected")
                if state == "connected":
                    status = "passed"
                    summary = "Connected."
                elif state in {"configure_manually", "coming_soon"}:
                    status = "warning"
                    summary = f"Status: {state.replace('_', ' ')}."
            checks.append(self._check(account_name, required=False, status=status, summary=summary))

        return checks

    def _finalize(self, db: Session, profile: AppProfile, payload: dict[str, Any], *, include_optional_checks: bool) -> dict[str, Any]:
        required_failures = [check for check in payload["checks"] if check["required"] and check["status"] == "failed"]
        selected_provider = normalize_provider(profile.selected_provider)
        provider_failure_names = self._selected_provider_failure_names(selected_provider)
        degraded_checks = [
            check
            for check in payload["checks"]
            if (not check["required"]) and check["name"] in provider_failure_names and check["status"] == "failed"
        ]
        payload["failed_checks"] = [check["name"] for check in payload["checks"] if check["status"] == "failed"]
        payload["degraded_reasons"] = [check["summary"] for check in degraded_checks]
        payload["last_completed_at"] = _now()

        if required_failures:
            primary = required_failures[0]
            payload["mode"] = "error"
            payload["overall_status"] = "error"
            payload["backend_ready"] = False
            payload["recommended_route"] = "/startup-error"
            payload["error_code"] = primary["error_code"] or "MC-UNKNOWN-UNEXPECTED-001"
            payload["error_summary"] = primary["summary"]
            profile.recent_startup_error_json = {
                "error_code": payload["error_code"],
                "error_summary": payload["error_summary"],
                "failed_checks": payload["failed_checks"],
                "attempt": payload["startup_attempt"],
            }
            if payload["startup_attempt"] >= MAX_STARTUP_ATTEMPTS:
                report = write_diagnostic_report(
                    startup_status=payload,
                    system_status=self._system_status_snapshot(profile),
                    settings_status={"selected_provider": selected_provider, "default_runner_mode": profile.default_runner_mode},
                    recent_errors=profile.recent_startup_error_json,
                )
                payload["diagnostic_report_path"] = report["path"]
            self.last_status = payload
            db.flush()
            return payload

        payload["backend_ready"] = True
        setup_completed = bool(profile.first_run_completed or profile.onboarding_completed)
        if degraded_checks and include_optional_checks and setup_completed:
            payload["mode"] = "degraded"
            payload["overall_status"] = "degraded"
            payload["recommended_route"] = "/dashboard"
            payload["error_code"] = degraded_checks[0]["error_code"]
            payload["error_summary"] = degraded_checks[0]["summary"]
        elif setup_completed:
            payload["mode"] = "regular"
            payload["overall_status"] = "ready"
            payload["recommended_route"] = "/dashboard"
        else:
            payload["mode"] = "first_time"
            payload["overall_status"] = "ready"
            payload["recommended_route"] = "/setup"

        if payload["overall_status"] == "ready":
            profile.recent_startup_error_json = None
        self.last_status = payload
        db.flush()
        return payload

    def _system_status_snapshot(self, profile: AppProfile) -> dict[str, Any]:
        provider_statuses = detect_provider_statuses(profile.adapter_command, profile.provider_endpoint, list(profile.adapter_args_json or []))
        selected = normalize_provider(profile.selected_provider)
        matching = next((item for item in provider_statuses if item["provider"] == selected), provider_statuses[0])
        return {
            "selected_provider": selected,
            "selected_provider_label": matching["label"],
            "cli_detected": matching["cli_detected"],
            "cli_version": matching["cli_version"],
            "login_status": matching["login_status"],
            "app_server_handshake_status": "not_checked",
            "runtime_ready": bool(matching.get("runtime_ready")),
            "runtime_summary": matching.get("runtime_summary"),
        }

    def get_status(self, db: Session) -> dict[str, Any]:
        if self.last_status is None:
            return self.run_checks(db, attempt_number=1, include_optional_checks=True)
        return self.last_status

    def run_checks(self, db: Session, *, attempt_number: int, include_optional_checks: bool = True) -> dict[str, Any]:
        profile = get_or_create_app_profile(db)
        payload = self._base_payload(profile, attempt=attempt_number)
        settings_check, refreshed_profile = self._check_settings(db)
        profile = refreshed_profile or profile
        payload["checks"].append(self._check_runtime_paths())
        payload["checks"].append(self._check_database(db))
        payload["checks"].append(settings_check)
        payload["checks"].append(self._check_projects(db))
        payload["checks"].append(self._check_backend_route())
        if include_optional_checks:
            payload["checks"].extend(self._provider_optional_checks(profile))
        return self._finalize(db, profile, payload, include_optional_checks=include_optional_checks)

    def retry(self, db: Session, *, attempt_number: int, failed_check: str | None, retry_mode: str) -> dict[str, Any]:
        bounded_attempt = min(max(attempt_number, 1), MAX_STARTUP_ATTEMPTS)
        payload = self.run_checks(db, attempt_number=bounded_attempt, include_optional_checks=True)
        if payload["overall_status"] == "error" and bounded_attempt < MAX_STARTUP_ATTEMPTS:
            payload["overall_status"] = "retrying"
            payload["error_summary"] = f"Retrying after {failed_check or 'startup failure'} using {retry_mode} mode."
        self.last_status = payload
        return payload

    def complete_first_run(self, db: Session, payload: CompleteFirstRunRequest) -> AppProfile:
        profile = complete_first_run(db, payload, setup_version=CURRENT_SETUP_VERSION)
        self.last_status = None
        return profile

    def run_diagnostics(self, db: Session) -> dict[str, Any]:
        profile = get_or_create_app_profile(db)
        startup_status = self.last_status or self.run_checks(db, attempt_number=1, include_optional_checks=True)
        report = write_diagnostic_report(
            startup_status=startup_status,
            system_status=self._system_status_snapshot(profile),
            settings_status={"selected_provider": normalize_provider(profile.selected_provider), "default_runner_mode": profile.default_runner_mode},
            recent_errors=profile.recent_startup_error_json,
        )
        startup_status["diagnostic_report_path"] = report["path"]
        self.last_status = startup_status
        return report


startup_service = StartupCoordinator()
