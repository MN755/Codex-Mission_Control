from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import LAUNCHER_ROOT, RUNTIME_LOGS_ROOT
from daemon_state import daemon_identity_snapshot, read_daemon_metadata, resolve_backend_binding
from device_profile import detect_device_profile, detect_performance_profile, platform_debug_commands
from runtime_paths import diagnostics_root, runtime_path_payload
from security.path_validation import PathValidationError, ensure_within_roots
from security.redaction import redact_text, redact_value
from system_status import detect_git_status


SENSITIVE_ENV_KEYS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "CODEX_API_KEY"}


def _tail(path: Path, max_lines: int = 40) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        return [redact_text(line) for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-max_lines:]]
    except OSError:
        return []


def _redact_value(value: str) -> str:
    return str(redact_value(value))


def _sanitized_environment() -> dict[str, str]:
    payload: dict[str, str] = {}
    for key in sorted(SENSITIVE_ENV_KEYS):
        if key in os.environ:
            payload[key] = _redact_value(os.environ[key])
    return payload


def _write_bundle(bundle_path: Path, *, markdown_path: Path, json_path: Path) -> None:
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(markdown_path, arcname=markdown_path.name)
        bundle.write(json_path, arcname=json_path.name)


def _bundle_metadata(bundle_path: Path) -> dict[str, Any]:
    if not bundle_path.exists():
        return {"path": str(bundle_path), "exists": False, "member_count": 0, "members": [], "size_bytes": 0}
    try:
        with zipfile.ZipFile(bundle_path, "r") as bundle:
            members = bundle.namelist()
    except (OSError, zipfile.BadZipFile):
        members = []
    return {
        "path": str(bundle_path),
        "exists": True,
        "member_count": len(members),
        "members": members,
        "size_bytes": bundle_path.stat().st_size,
    }


def _load_report_metadata(json_path: Path) -> dict[str, Any]:
    if not json_path.exists():
        return {}
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    startup_status = payload.get("startup_status", {})
    return {
        "report_id": payload.get("report_id"),
        "summary": str(startup_status.get("error_summary") or startup_status.get("overall_status") or "Diagnostic report"),
        "error_code": startup_status.get("error_code"),
        "project_id": payload.get("project_id"),
        "project_name": payload.get("project_name"),
        "workspace_path": payload.get("workspace_path"),
        "platform_profile": payload.get("platform_profile") if isinstance(payload.get("platform_profile"), dict) else {},
        "performance_profile": payload.get("performance_profile") if isinstance(payload.get("performance_profile"), dict) else {},
        "safe_debug_commands": list(payload.get("safe_debug_commands") or []),
        "runtime_blockers": [str(item) for item in list(payload.get("runtime_blockers") or [])],
        "backend_binding": payload.get("backend_binding") if isinstance(payload.get("backend_binding"), dict) else {},
        "daemon_identity": payload.get("daemon_identity") if isinstance(payload.get("daemon_identity"), dict) else {},
        "daemon_metadata": payload.get("daemon_metadata") if isinstance(payload.get("daemon_metadata"), dict) else {},
        "repo_version_control": payload.get("repo_version_control") if isinstance(payload.get("repo_version_control"), dict) else {},
        "bundle_path": payload.get("bundle_path"),
        "bundle_members": [str(item) for item in list(payload.get("bundle_members") or [])],
        "bundle_metadata": payload.get("bundle_metadata") if isinstance(payload.get("bundle_metadata"), dict) else {},
        "timestamp": payload.get("timestamp"),
    }


def write_diagnostic_report(
    *,
    startup_status: dict[str, Any],
    system_status: dict[str, Any],
    settings_status: dict[str, Any] | None,
    recent_errors: dict[str, Any] | None,
    project_id: int | None = None,
    project_name: str | None = None,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc)
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    report_id = f"diagnostic-{stamp}"
    report_dir = diagnostics_root()
    markdown_path = report_dir / f"{report_id}.md"
    json_path = report_dir / f"{report_id}.json"
    bundle_path = report_dir / f"{report_id}-bundle.zip"
    device_profile = detect_device_profile()
    performance_profile = detect_performance_profile()
    backend_port = int(system_status.get("backend_port") or startup_status.get("backend_port") or 8010)
    safe_debug_commands = platform_debug_commands(backend_port=backend_port)
    backend_binding = resolve_backend_binding()
    daemon_identity = daemon_identity_snapshot()
    daemon_metadata = read_daemon_metadata()
    repo_version_control = detect_git_status(workspace_path=workspace_path)
    runtime_blockers = [str(item) for item in list(system_status.get("runtime_blockers") or [])]

    launcher_logs = []
    if LAUNCHER_ROOT.exists():
        for name in ("daemon.stdout.log", "daemon.stderr.log", "backend.stdout.log", "frontend.stdout.log", "desktop.stdout.log"):
            launcher_logs.extend(_tail(LAUNCHER_ROOT / name, max_lines=10))

    runtime_logs = []
    if RUNTIME_LOGS_ROOT.exists():
        log_files = sorted(RUNTIME_LOGS_ROOT.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        for path in log_files[:3]:
            runtime_logs.append({"path": str(path), "tail": _tail(path, max_lines=10)})

    recommended_fixes = []
    for check in startup_status.get("checks", []):
        if check.get("status") == "failed":
            recommended_fixes.append(str(check.get("recommended_fix") or f"Review the `{check.get('name')}` check: {check.get('summary')}"))
    if not recommended_fixes:
        recommended_fixes.append("Review optional provider checks and confirm the selected local runner is installed.")

    payload = {
        "timestamp": timestamp.isoformat(),
        "report_id": report_id,
        "startup_status": redact_value(startup_status),
        "system_status": redact_value(system_status),
        "settings_status": redact_value(settings_status),
        "recent_errors": redact_value(recent_errors),
        "platform": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python": sys.version,
            "node_detected": bool(shutil.which("node")),
            "npm_detected": bool(shutil.which("npm") or shutil.which("npm.cmd")),
        },
        "runtime_paths": runtime_path_payload(),
        "backend_binding": redact_value(backend_binding),
        "daemon_identity": redact_value(daemon_identity),
        "daemon_metadata": redact_value(daemon_metadata),
        "repo_version_control": redact_value(repo_version_control),
        "sanitized_environment": _sanitized_environment(),
        "recent_launcher_logs": launcher_logs,
        "recent_runtime_logs": redact_value(runtime_logs),
        "runtime_blockers": runtime_blockers,
        "recommended_fixes": recommended_fixes,
        "project_id": project_id,
        "project_name": project_name,
        "workspace_path": workspace_path,
        "platform_profile": device_profile,
        "performance_profile": performance_profile,
        "safe_debug_commands": safe_debug_commands,
        "bundle_path": str(bundle_path),
        "bundle_members": [markdown_path.name, json_path.name],
    }

    markdown = [
        "# Mission Control Diagnostic Report",
        "",
        f"- Timestamp: {payload['timestamp']}",
        f"- Startup mode: {startup_status.get('mode')}",
        f"- Overall status: {startup_status.get('overall_status')}",
        f"- Error code: {startup_status.get('error_code') or 'None'}",
        f"- Project scope: {project_name or workspace_path or 'global app diagnostics'}",
        f"- Report ID: {report_id}",
        "",
        "## Failed checks",
        "",
    ]
    failed_checks = [check for check in startup_status.get("checks", []) if check.get("status") == "failed"]
    if failed_checks:
        markdown.extend(
            [
                f"- `{check.get('name')}`: {check.get('summary')} ({check.get('error_code') or 'no code'})"
                for check in failed_checks
            ]
        )
    else:
        markdown.append("- No failed checks were recorded.")
    markdown.extend(
        [
            "",
            "## Required checks",
            "",
        ]
    )
    for check in startup_status.get("checks", []):
        marker = "required" if check.get("required") else "optional"
        markdown.append(f"- `{check.get('name')}` [{marker}]: {check.get('status')} - {check.get('summary')}")
    markdown.extend(
        [
            "",
            "## Runtime paths",
            "",
        ]
    )
    markdown.extend([f"- {key}: `{value}`" for key, value in runtime_path_payload().items()])
    markdown.extend(
        [
            "",
            "## Runtime blockers",
            "",
        ]
    )
    if runtime_blockers:
        markdown.extend([f"- `{item}`" for item in runtime_blockers])
    else:
        markdown.append("- No runtime blockers were recorded in the selected provider snapshot.")
    markdown.extend(
        [
            "",
            "## Provider status",
            "",
            f"- Selected provider: {system_status.get('selected_provider_label')}",
            f"- CLI detected: {system_status.get('cli_detected')}",
            f"- Login status: {system_status.get('login_status')}",
            f"- App-server handshake: {system_status.get('app_server_handshake_status')}",
            f"- Runtime summary: {system_status.get('runtime_summary') or 'Unavailable'}",
            "",
            "## Repo Git readiness",
            "",
            f"- Status: {repo_version_control.get('status')}",
            f"- Summary: {repo_version_control.get('summary')}",
            f"- Safe directory: {repo_version_control.get('safe_directory') if repo_version_control.get('safe_directory') is not None else 'Unknown'}",
            "",
            "## Daemon identity",
            "",
            f"- Backend binding source: {backend_binding.get('source')}",
            f"- Daemon mode: {daemon_identity.get('mode')}",
            f"- Metadata status: {daemon_metadata.get('status')}",
            "",
            "## Device profile",
            "",
            f"- Platform: {device_profile.get('platform_label')}",
            f"- Architecture: {device_profile.get('architecture')}",
            f"- CPU count: {device_profile.get('cpu_count')}",
            f"- Memory (GB): {device_profile.get('memory_total_gb') if device_profile.get('memory_total_gb') is not None else 'Unknown'}",
            "",
            "## Performance guardrails",
            "",
            f"- Resource tier: {performance_profile.get('resource_tier')}",
            f"- Lag risk: {performance_profile.get('lag_risk')}",
            f"- Recommended swarm max agents: {performance_profile.get('recommended_swarm_max_agents')}",
            "",
            "## Safe debug commands",
            "",
        ]
    )
    markdown.extend([f"- `{command}`" for command in safe_debug_commands])
    markdown.extend(
        [
            "",
            "## Recommended fixes",
            "",
        ]
    )
    markdown.extend([f"- {fix}" for fix in recommended_fixes])
    markdown.extend(
        [
            "",
            "## Platform hints",
            "",
        ]
    )
    markdown.extend([f"- {item}" for item in list(device_profile.get("platform_hints") or [])])
    markdown.extend(
        [
            "",
            "## Recent launcher logs",
            "",
            "```text",
            *launcher_logs[-30:],
            "```",
            "",
        ]
    )

    markdown_path.write_text("\n".join(markdown).strip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_bundle(bundle_path, markdown_path=markdown_path, json_path=json_path)
    payload["bundle_metadata"] = _bundle_metadata(bundle_path)
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    _write_bundle(bundle_path, markdown_path=markdown_path, json_path=json_path)
    return {
        "path": str(markdown_path),
        "json_path": str(json_path),
        "bundle_path": str(bundle_path),
        "report_id": report_id,
        "summary": startup_status.get("error_summary") or startup_status.get("overall_status") or "Diagnostic report generated.",
        "error_code": startup_status.get("error_code"),
        "recommended_fixes": recommended_fixes,
        "project_id": project_id,
        "project_name": project_name,
        "workspace_path": workspace_path,
        "platform_profile": device_profile,
        "performance_profile": performance_profile,
        "safe_debug_commands": safe_debug_commands,
        "runtime_blockers": runtime_blockers,
        "backend_binding": redact_value(backend_binding),
        "daemon_identity": redact_value(daemon_identity),
        "daemon_metadata": redact_value(daemon_metadata),
        "repo_version_control": redact_value(repo_version_control),
        "bundle_members": list(payload["bundle_members"]),
        "bundle_metadata": dict(payload["bundle_metadata"]),
        "problem": {
            "type": f"https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#{str(startup_status.get('error_code') or '').lower()}",
            "title": "Mission Control diagnostic failure" if startup_status.get("error_code") else "Mission Control diagnostic report",
            "status": 500 if startup_status.get("error_code") else 200,
            "detail": startup_status.get("error_summary") or "Diagnostic report generated.",
            "instance": str(markdown_path),
            "code": startup_status.get("error_code") or "",
            "family": next((str(check.get("family") or "") for check in startup_status.get("checks", []) if check.get("error_code") == startup_status.get("error_code")), ""),
            "severity": next((str(check.get("severity") or "error") for check in startup_status.get("checks", []) if check.get("error_code") == startup_status.get("error_code")), "error"),
            "breakpoint": next((str(check.get("breakpoint") or "") for check in startup_status.get("checks", []) if check.get("error_code") == startup_status.get("error_code")), ""),
            "retryable": bool(next((check.get("retryable") for check in startup_status.get("checks", []) if check.get("error_code") == startup_status.get("error_code")), False)),
            "user_action_required": bool(next((check.get("user_action_required") for check in startup_status.get("checks", []) if check.get("error_code") == startup_status.get("error_code")), False)),
            "recommended_fix": recommended_fixes[0] if recommended_fixes else "",
            "correlation_id": str(
                next(
                    (
                        check.get("correlation_id") or ""
                        for check in startup_status.get("checks", [])
                        if check.get("error_code") == startup_status.get("error_code")
                    ),
                    "",
                )
            ),
            "orchestration_id": None,
            "project_id": None,
            "runner": None,
            "redaction_status": "redacted",
            "safe_details": {},
        }
        if startup_status.get("error_code")
        else None,
    }


def open_folder(path: str | Path, *, allowed_roots: list[str | Path] | None = None) -> dict[str, Any]:
    try:
        target = ensure_within_roots(path, allowed_roots or [diagnostics_root()], must_exist=True)
    except PathValidationError as exc:
        return {"ok": False, "path": str(path), "message": str(exc)}
    if not target.is_dir():
        return {"ok": False, "path": str(target), "message": "Path must be a directory."}
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(target), "message": str(exc)}
    return {"ok": True, "path": str(target), "message": "Opened diagnostics folder."}


def list_diagnostic_reports() -> list[dict[str, Any]]:
    report_dir = diagnostics_root()
    items: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("diagnostic-*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        json_path = path.with_suffix(".json")
        summary = "Diagnostic report"
        error_code: str | None = None
        project_id: int | None = None
        project_name: str | None = None
        workspace_path: str | None = None
        created_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        platform_profile: dict[str, Any] = {}
        performance_profile: dict[str, Any] = {}
        safe_debug_commands: list[str] = []
        runtime_blockers: list[str] = []
        backend_binding: dict[str, Any] = {}
        daemon_identity: dict[str, Any] = {}
        daemon_metadata: dict[str, Any] = {}
        repo_version_control: dict[str, Any] = {}
        bundle_path: str | None = None
        bundle_members: list[str] = []
        bundle_metadata: dict[str, Any] = {}
        report_id: str | None = None
        if json_path.exists():
            metadata = _load_report_metadata(json_path)
            report_id = str(metadata.get("report_id")) if metadata.get("report_id") else None
            summary = str(metadata.get("summary") or summary)
            error_code = metadata.get("error_code")
            project_id = int(metadata["project_id"]) if isinstance(metadata.get("project_id"), int) else None
            project_name = str(metadata["project_name"]) if metadata.get("project_name") else None
            workspace_path = str(metadata["workspace_path"]) if metadata.get("workspace_path") else None
            platform_profile = dict(metadata.get("platform_profile") or {})
            performance_profile = dict(metadata.get("performance_profile") or {})
            safe_debug_commands = [str(item) for item in list(metadata.get("safe_debug_commands") or [])]
            runtime_blockers = [str(item) for item in list(metadata.get("runtime_blockers") or [])]
            backend_binding = dict(metadata.get("backend_binding") or {})
            daemon_identity = dict(metadata.get("daemon_identity") or {})
            daemon_metadata = dict(metadata.get("daemon_metadata") or {})
            repo_version_control = dict(metadata.get("repo_version_control") or {})
            bundle_path = str(metadata.get("bundle_path")) if metadata.get("bundle_path") else None
            bundle_members = [str(item) for item in list(metadata.get("bundle_members") or [])]
            bundle_metadata = dict(metadata.get("bundle_metadata") or {})
            timestamp = metadata.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    pass
        items.append(
            {
                "path": str(path),
                "json_path": str(json_path) if json_path.exists() else None,
                "report_id": report_id,
                "created_at": created_at,
                "error_code": error_code,
                "summary": summary,
                "project_id": project_id,
                "project_name": project_name,
                "workspace_path": workspace_path,
                "bundle_path": bundle_path,
                "bundle_members": bundle_members,
                "bundle_metadata": bundle_metadata,
                "platform_profile": platform_profile,
                "performance_profile": performance_profile,
                "safe_debug_commands": safe_debug_commands,
                "runtime_blockers": runtime_blockers,
                "backend_binding": backend_binding,
                "daemon_identity": daemon_identity,
                "daemon_metadata": daemon_metadata,
                "repo_version_control": repo_version_control,
            }
        )
    return items
