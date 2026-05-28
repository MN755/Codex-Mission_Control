from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _which(command: str) -> str | None:
    return shutil.which(command)


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _module_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _run_command(args: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _string_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _workspace_signals(workspace_path: Path) -> list[str]:
    signals: list[str] = []
    package_json = workspace_path / "package.json"
    if package_json.exists():
        payload = _read_json(package_json) or {}
        dependencies = {
            **(payload.get("dependencies") if isinstance(payload.get("dependencies"), dict) else {}),
            **(payload.get("devDependencies") if isinstance(payload.get("devDependencies"), dict) else {}),
        }
        if "@playwright/test" in dependencies or "playwright" in dependencies:
            signals.append("package.json already references Playwright.")
    if any(workspace_path.glob("playwright.config.*")):
        signals.append("Playwright config file detected in the workspace root.")
    if (workspace_path / "tests" / "e2e").exists() or (workspace_path / "e2e").exists():
        signals.append("End-to-end test folder detected.")
    pyproject = workspace_path / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
        if "playwright" in text:
            signals.append("pyproject.toml mentions Playwright.")
    for requirements_name in ("requirements.txt", "requirements-dev.txt"):
        requirement_path = workspace_path / requirements_name
        if requirement_path.exists():
            text = requirement_path.read_text(encoding="utf-8", errors="ignore").lower()
            if "playwright" in text:
                signals.append(f"{requirements_name} mentions Playwright.")
    return _string_list(signals)


def _install_commands() -> list[str]:
    python_cmd = Path(sys.executable).name or "python"
    return [
        "git clone https://github.com/microsoft/Webwright",
        "cd Webwright",
        f"{python_cmd} -m pip install -e .",
        "playwright install chromium",
    ]


def _bridge_markdown(
    *,
    project_name: str,
    summary: str,
    install_status: str,
    launch_command: str | None,
    workspace_signals: list[str],
    recommended_fix: str | None,
    install_commands: list[str],
) -> str:
    lines = [
        "## Mission Control Webwright",
        "",
        f"- Project: **{project_name}**",
        f"- Install status: `{install_status}`",
        f"- Summary: {summary}",
    ]
    if launch_command:
        lines.append(f"- Launch command: `{launch_command}`")
    if workspace_signals:
        lines.extend(["", "### Workspace signals", *[f"- {item}" for item in workspace_signals]])
    if recommended_fix:
        lines.extend(["", "### Recommended fix", f"- {recommended_fix}"])
    lines.extend(["", "### Upstream install commands", *[f"- `{item}`" for item in install_commands]])
    lines.extend(
        [
            "",
            "### Mission Control posture",
            "- Mission Control already provides the bridge surface; you only need the Webwright runtime if you want the browser-agent harness itself.",
            "- Prefer Webwright for multi-step browser flows, screenshot-backed verification, and reusable browser scripts.",
        ]
    )
    return "\n".join(lines)


def detect_webwright_status(*, workspace_path: str | Path | None = None, project_name: str | None = None) -> dict[str, Any]:
    workspace_root = Path(workspace_path).expanduser().resolve() if workspace_path else None
    workspace_signals = _workspace_signals(workspace_root) if workspace_root and workspace_root.exists() else []

    cli_path = _which("webwright")
    playwright_cli_path = _which("playwright")
    python_package_detected = _has_module("webwright")
    playwright_package_detected = _has_module("playwright")
    version = _module_version("webwright")

    cli_output = ""
    if cli_path:
        _, cli_output = _run_command([cli_path, "--help"])

    cli_detected = bool(cli_path)
    playwright_cli_detected = bool(playwright_cli_path)
    available = bool((cli_detected or python_package_detected) and playwright_package_detected)
    launch_command = cli_path if cli_detected else (f"{Path(sys.executable).name} -m webwright.run.cli" if python_package_detected else None)
    install_status = "missing"
    recommended_fix: str | None = None
    summary = "Webwright is not installed in the current Mission Control runtime."
    notes = [
        "Webwright is an optional browser-agent companion, not a Mission Control model provider or manager replacement.",
        "The upstream Webwright quick start installs the runtime from a local checkout and then installs Chromium through Playwright.",
        "Mission Control treats Webwright as a code-as-action browser lane for multi-step web tasks and screenshot-backed verification.",
    ]
    use_cases = [
        "Multi-step browser automation that should end as a reusable script.",
        "Screenshot-backed web validation instead of hand-wavy browser claims.",
        "Browser tasks where code, logs, and rerunnable artifacts matter more than a persistent session.",
    ]

    if available:
        install_status = "ready"
        summary = "Webwright runtime and Playwright package are both detectable from the current Mission Control runtime."
    elif cli_detected or python_package_detected:
        install_status = "partial"
        summary = "Webwright runtime is present, but Playwright is not fully detectable from the current Mission Control runtime."
        recommended_fix = "Install the Playwright Python package and browser runtime before expecting Webwright-backed browser automation to work cleanly."
    elif playwright_package_detected or playwright_cli_detected:
        install_status = "partial"
        summary = "Playwright is present, but the Webwright runtime itself is not installed."
        recommended_fix = "Install Webwright from the upstream repository before routing browser-agent work to it."
    else:
        recommended_fix = "Clone the upstream Webwright repository, install it into the same Python environment as Mission Control, and install the Chromium browser runtime."

    if workspace_signals and install_status != "ready" and recommended_fix:
        recommended_fix = f"{recommended_fix} This workspace already shows Playwright or E2E signals, so the missing piece is probably worth fixing instead of pretending browser coverage is manual forever."

    return {
        "project_name": project_name or (workspace_root.name if workspace_root else "Current project"),
        "workspace_path": str(workspace_root) if workspace_root else None,
        "available": available,
        "install_status": install_status,
        "cli_detected": cli_detected,
        "cli_path": cli_path,
        "python_package_detected": python_package_detected,
        "playwright_package_detected": playwright_package_detected,
        "playwright_cli_detected": playwright_cli_detected,
        "version": version,
        "launch_command": launch_command,
        "workspace_signals": workspace_signals,
        "summary": summary,
        "recommended_fix": recommended_fix,
        "recommended_install_commands": _install_commands(),
        "use_cases": use_cases,
        "notes": notes,
        "bridge_markdown": _bridge_markdown(
            project_name=project_name or (workspace_root.name if workspace_root else "Current project"),
            summary=summary,
            install_status=install_status,
            launch_command=launch_command,
            workspace_signals=workspace_signals,
            recommended_fix=recommended_fix,
            install_commands=_install_commands(),
        ),
        "details": {
            "cli_help_detected": bool(cli_output),
            "runtime_python": sys.executable,
            "host_platform": os.name,
        },
    }
