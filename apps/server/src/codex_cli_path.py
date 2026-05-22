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


def codex_command_path() -> str | None:
    env_paths = [
        os.environ.get("MISSION_CONTROL_CODEX_PATH"),
        os.environ.get("CODEX_CLI_PATH"),
    ]
    for explicit in _iter_existing_paths([value for value in env_paths if value]):
        if Path(explicit).is_file():
            return explicit

    if platform.system().lower() != "windows":
        for candidate in ("codex", "codex.cmd", "codex.exe", "codex.ps1", "codex.bat"):
            resolved = shutil.which(candidate)
            if resolved:
                return str(Path(resolved).resolve())
        return None

    home = Path.home()
    local_app_data = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
    temp_root = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "")
    candidate_files = [
        local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe",
        local_app_data / "OpenAI" / "Codex" / "bin" / "codex.cmd",
        local_app_data / "Programs" / "OpenAI Codex" / "codex.exe",
        local_app_data / "Programs" / "Codex" / "codex.exe",
        local_app_data / "Microsoft" / "WindowsApps" / "codex.exe",
        home / ".local" / "bin" / "codex",
        home / ".local" / "bin" / "codex.exe",
    ]
    versioned_bin_root = local_app_data / "OpenAI" / "Codex" / "bin"
    if versioned_bin_root.exists():
        versioned_entries = sorted(
            (path / "codex.exe" for path in versioned_bin_root.iterdir() if path.is_dir()),
            reverse=True,
        )
        candidate_files.extend(versioned_entries)
    if temp_root:
        candidate_files.extend(
            [
                temp_root / "codex.exe",
                temp_root / "codex.cmd",
                temp_root / "codex.ps1",
            ]
        )
    for candidate in candidate_files:
        if candidate.exists():
            try:
                return str(candidate.resolve())
            except OSError:
                return str(candidate)

    for candidate in ("codex", "codex.cmd", "codex.exe", "codex.ps1", "codex.bat"):
        resolved = shutil.which(candidate)
        if resolved:
            return str(Path(resolved).resolve())
    return None
