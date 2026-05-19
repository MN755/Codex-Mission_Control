from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from codex_cli_path import codex_command_path
from security.redaction import redact_text


VERSION_ARGUMENTS: dict[str, list[str]] = {
    "git": ["--version"],
    "node": ["--version"],
    "npm": ["--version"],
    "pnpm": ["--version"],
    "yarn": ["--version"],
    "python": ["--version"],
    "pip": ["--version"],
    "uv": ["--version"],
    "codex": ["--version"],
    "ollama": ["--version"],
    "claude": ["--version"],
}


def _run_command(args: list[str], *, timeout: int = 12) -> tuple[bool, str]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    output = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, redact_text(output)


def command_path(*names: str) -> str | None:
    if names and any(name.startswith("codex") for name in names if name):
        resolved_codex = codex_command_path()
        if resolved_codex:
            return resolved_codex
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return str(Path(resolved).resolve())
    return None


def probe_command(*names: str, version_args: list[str] | None = None) -> dict[str, Any]:
    path_text = command_path(*names)
    detected = path_text is not None
    version = None
    command_name = next((name for name in names if name), names[0] if names else "")
    args = version_args if version_args is not None else VERSION_ARGUMENTS.get(command_name, ["--version"])
    if detected:
        ok, output = _run_command([path_text, *args])
        version = output if ok and output else None
    return {
        "detected": detected,
        "path": path_text,
        "version": version,
    }


def probe_powershell() -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return {"detected": False, "path": None, "version": None}
    path_text = command_path("powershell", "pwsh")
    if path_text is None:
        return {"detected": False, "path": None, "version": None}
    ok, output = _run_command([path_text, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"])
    return {
        "detected": True,
        "path": path_text,
        "version": output if ok and output else None,
    }


def probe_core_tools() -> dict[str, dict[str, Any]]:
    tools = {
        "git": probe_command("git"),
        "node": probe_command("node"),
        "npm": probe_command("npm", "npm.cmd"),
        "pnpm": probe_command("pnpm", "pnpm.cmd"),
        "yarn": probe_command("yarn", "yarn.cmd"),
        "python": probe_command("python", "py"),
        "pip": probe_command("pip", "pip3"),
        "uv": probe_command("uv", "uv.exe"),
        "codex": probe_command("codex"),
        "ollama": probe_command("ollama"),
        "claude": probe_command("claude"),
        "powershell": probe_powershell(),
    }
    return tools
