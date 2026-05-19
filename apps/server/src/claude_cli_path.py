from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def _iter_existing_paths(entries: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        try:
            resolved = str(Path(entry).expanduser().resolve())
        except OSError:
            continue
        lowered = resolved.lower()
        if lowered in seen or not Path(resolved).exists():
            continue
        seen.add(lowered)
        unique.append(resolved)
    return unique


def claude_command_path() -> str | None:
    env_paths = [
        os.environ.get("MISSION_CONTROL_CLAUDE_PATH"),
        os.environ.get("CLAUDE_CLI_PATH"),
    ]
    for explicit in _iter_existing_paths([value for value in env_paths if value]):
        if Path(explicit).is_file():
            return explicit

    for candidate in ("claude", "claude.cmd", "claude.exe", "claude.ps1", "claude.bat"):
        resolved = shutil.which(candidate)
        if resolved:
            return str(Path(resolved).resolve())

    home = Path.home()
    candidate_files = [
        home / ".local" / "bin" / "claude",
        home / ".local" / "bin" / "claude.exe",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
    ]

    if platform.system().lower() == "windows":
        app_data = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
        candidate_files.extend(
            [
                app_data / "npm" / "claude.cmd",
                app_data / "npm" / "claude.ps1",
                app_data / "npm" / "claude",
                local_app_data / "Programs" / "Claude" / "claude.exe",
            ]
        )

    for candidate in candidate_files:
        if candidate.exists():
            try:
                return str(candidate.resolve())
            except OSError:
                return str(candidate)
    return None
