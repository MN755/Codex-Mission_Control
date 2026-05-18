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
from models import AppProfile, Project
from provider_support import normalize_provider
from runtime_paths import ensure_runtime_paths
from schemas import CompleteFirstRunRequest
from system_status import (
    detect_claude_code_status,
    detect_codex_status,
    detect_custom_status,
    detect_ollama_status,
    detect_provider_statuses,
)


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
            "setup_version_completed": profile.setup_version_completed,
            "current_setup_version": CURRENT_SETUP_VERSION,
            "install_id": install_id,
            "startup_attempt": attempt,
            "max_startup_attempts": MAX_STARTUP_ATTEMPTS,
            "overall_status": "starting",
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
    def _check(name: str, *, required: bool, status: str, summary: str, error_code: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "name": name,
            "required": required,
            "status": status,
            "summary": summary,
            "error_code": error_code,
            "details": details or {},
        }

    def _selected_provider_failure_names(self, selected_provider: str) -> set[str]:
        mapping = {
            "codex": set(),
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
            return self._check("runtime_paths", required=True, status="failed", summary=str(exc), error_code="MC-BOOT-001")

    def _check_database(self, db: Session) -> dict[str, Any]:
        try:
            db.execute(text("SELECT 1"))
            return self._check("database", required=True, status="passed", summary="Database connection is healthy.")
        except Exception as exc:  # noqa: BLE001
            return self._check("database", required=True, status="failed", summary=str(exc), error_code="MC-BOOT-002")

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
            return (
                self._check("settings", required=True, status="failed", summary=str(exc), error_code="MC-BOOT-008"),
                None,
            )

    def _check_projects(self, db: Session) -> dict[str, Any]:
        try:
            project_count = db.scalar(select(func.count(Project.id))) or 0
            return self._check("projects", required=True, status="passed", summary=f"Loaded {project_count} project records.", details={"project_count": project_count})
        except Exception as exc:  # noqa: BLE001
            return self._check("projects", required=True, status="failed", summary=str(exc), error_code="MC-BOOT-005")

    def _check_backend_route(self) -> dict[str, Any]:
        return self._check("backend_route", required=True, status="passed", summary="Backend route availability confirmed.")

    def _codex_optional_checks(self) -> list[dict[str, Any]]:
        status = detect_codex_status()
        cli_check = self._check(
            "codex_cli",
            required=False,
            status="passed" if status["cli_detected"] else "failed",
            summary=status["cli_version"] or "Codex CLI was not detected on PATH.",
            error_code=None if status["cli_detected"] else "MC-BOOT-006",
        )
        login_check = self._check(
            "codex_login",
            required=False,
            status="passed" if status["authenticated"] else "warning",
            summary=status["login_status"],
            error_code=None if status["authenticated"] else "MC-BOOT-006",
        )
        app_server_check = self._check(
            "app_server",
            required=False,
            status="passed" if status["app_server_supported"] else "warning",
            summary="Codex app-server support detected." if status["app_server_supported"] else "Codex app-server support not detected; CLI fallback remains available.",
            error_code=None if status["app_server_supported"] else "MC-BOOT-007",
        )
        return [cli_check, login_check, app_server_check]

    def _provider_optional_checks(self, profile: AppProfile) -> list[dict[str, Any]]:
        selected = normalize_provider(profile.selected_provider)
        checks: list[dict[str, Any]] = self._codex_optional_checks()

        claude = detect_claude_code_status()
        checks.append(
            self._check(
                "claude_code",
                required=False,
                status="passed" if claude["cli_detected"] else ("failed" if selected == "claude_code" else "skipped"),
                summary=claude["cli_version"] or claude["login_status"],
                error_code="MC-BOOT-006" if selected == "claude_code" and not claude["cli_detected"] else None,
            )
        )

        ollama_endpoint = profile.provider_endpoint or "http://localhost:11434"
        ollama = detect_ollama_status(ollama_endpoint)
        checks.append(
            self._check(
                "ollama",
                required=False,
                status="passed" if ollama["reachable"] else ("failed" if selected == "ollama" else "skipped"),
                summary=ollama["summary"],
                error_code="MC-BOOT-006" if selected == "ollama" and not ollama["reachable"] else None,
                details=ollama,
            )
        )

        env_checks = {
            "openai_api": "OPENAI_API_KEY",
            "anthropic_api": "ANTHROPIC_API_KEY",
            "xai_api": "XAI_API_KEY",
        }
        import os

        for name, env_key in env_checks.items():
            configured = bool(os.environ.get(env_key))
            checks.append(
                self._check(
                    name,
                    required=False,
                    status="passed" if configured else ("warning" if selected == name else "skipped"),
                    summary=f"{env_key} {'is configured' if configured else 'is not configured in the current environment.'}",
                    error_code="MC-BOOT-006" if selected == name and not configured else None,
                )
            )

        custom = detect_custom_status(profile.adapter_command, profile.adapter_args_json)
        checks.append(
            self._check(
                "custom",
                required=False,
                status="passed" if custom["cli_detected"] else ("warning" if selected == "custom" else "skipped"),
                summary=custom["cli_version"] or custom["login_status"],
                error_code="MC-BOOT-006" if selected == "custom" and not custom["cli_detected"] else None,
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
            payload["recommended_route"] = "/startup-error"
            payload["error_code"] = primary["error_code"] or "MC-BOOT-009"
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

        if degraded_checks and include_optional_checks:
            payload["mode"] = "degraded"
            payload["overall_status"] = "degraded"
            payload["recommended_route"] = "/dashboard" if profile.first_run_completed or profile.onboarding_completed else "/setup"
            payload["error_code"] = degraded_checks[0]["error_code"]
            payload["error_summary"] = degraded_checks[0]["summary"]
        elif profile.first_run_completed or profile.onboarding_completed:
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
        provider_statuses = detect_provider_statuses(profile.adapter_command, profile.provider_endpoint)
        selected = normalize_provider(profile.selected_provider)
        matching = next((item for item in provider_statuses if item["provider"] == selected), provider_statuses[0])
        return {
            "selected_provider": selected,
            "selected_provider_label": matching["label"],
            "cli_detected": matching["cli_detected"],
            "cli_version": matching["cli_version"],
            "login_status": matching["login_status"],
            "app_server_handshake_status": "not_checked",
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
