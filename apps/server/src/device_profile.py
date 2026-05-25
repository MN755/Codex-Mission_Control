from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any


def _safe_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _windows_memory_bytes() -> int | None:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) == 0:  # type: ignore[attr-defined]
        return None
    return int(status.ullTotalPhys)


def _linux_memory_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                kib = _safe_int(parts[1])
                if kib is not None:
                    return kib * 1024
    return None


def _macos_memory_bytes() -> int | None:
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return _safe_int(completed.stdout)


def _total_memory_bytes(system_name: str) -> int | None:
    lowered = system_name.lower()
    if lowered == "windows":
        return _windows_memory_bytes()
    if lowered == "linux":
        return _linux_memory_bytes()
    if lowered == "darwin":
        return _macos_memory_bytes()
    return None


def _linux_distro() -> str | None:
    try:
        payload = platform.freedesktop_os_release()
    except Exception:  # noqa: BLE001
        return None
    name = str(payload.get("PRETTY_NAME") or payload.get("NAME") or "").strip()
    return name or None


def _platform_identity() -> tuple[str, str, str, dict[str, Any]]:
    system_name = platform.system()
    release = platform.release()
    version = platform.version()
    details: dict[str, Any] = {}

    if system_name == "Windows":
        build = None
        parts = version.split(".")
        if parts:
            build = _safe_int(parts[-1])
        if build is not None and build >= 22000:
            return "windows_11", "Windows 11", system_name, {"build": build, "release": release, "version": version}
        return "windows_10", "Windows 10", system_name, {"build": build, "release": release, "version": version}
    if system_name == "Darwin":
        mac_version = platform.mac_ver()[0] or release
        return "macos", f"macOS {mac_version}", system_name, {"release": release, "version": mac_version}
    if system_name == "Linux":
        distro = _linux_distro()
        label = distro or f"Linux {release}"
        return "linux", label, system_name, {"release": release, "version": version, "distro": distro}
    return "unknown", platform.platform(), system_name, {"release": release, "version": version}


def _resource_tier(cpu_count: int, memory_gb: float | None) -> tuple[str, int, str]:
    if cpu_count <= 4 or (memory_gb is not None and memory_gb < 8):
        return "small", 3, "high"
    if cpu_count <= 8 or (memory_gb is not None and memory_gb < 16):
        return "medium", 5, "medium"
    if cpu_count <= 12 or (memory_gb is not None and memory_gb < 24):
        return "large", 7, "low"
    return "workstation", 9, "low"


def _platform_hints(platform_key: str) -> list[str]:
    if platform_key == "windows_10":
        return [
            "Windows 10 commonly hides CLI tools behind PATH or WindowsApps shim issues. Verify the real executable path, not just the command name.",
            "Prefer PowerShell-based health and support-bundle commands when the desktop app reload path is involved.",
        ]
    if platform_key == "windows_11":
        return [
            "Windows 11 commonly reports desktop app shims as present even when the current runtime cannot execute them directly.",
            "If Codex or Claude were just installed or updated, fully quit and reopen the host app before treating plugin discovery as broken.",
        ]
    if platform_key == "macos":
        return [
            "On macOS, full app quit-and-reopen beats soft reloads when MCP registrations change.",
            "Gatekeeper, TCC, and shell PATH differences can make a CLI visible in Terminal but unavailable to a desktop-hosted runtime.",
        ]
    if platform_key == "linux":
        return [
            "On Linux, desktop integration quality varies by distro, shell, and packaging method; verify PATH and xdg-open availability explicitly.",
            "If loopback health is fine but app-level integration is not, compare the desktop app environment with the shell environment instead of assuming the daemon is wrong.",
        ]
    return ["Unknown platform family. Fall back to loopback health, runtime paths, and support-bundle output first."]


@lru_cache(maxsize=1)
def detect_device_profile() -> dict[str, Any]:
    platform_key, label, system_name, details = _platform_identity()
    cpu_count = max(1, os.cpu_count() or 1)
    memory_bytes = _total_memory_bytes(system_name)
    memory_gb = round(memory_bytes / (1024**3), 1) if memory_bytes else None
    resource_tier, recommended_agents, lag_risk = _resource_tier(cpu_count, memory_gb)
    return {
        "platform_key": platform_key,
        "platform_label": label,
        "system": system_name,
        "architecture": platform.machine() or platform.processor() or "unknown",
        "cpu_count": cpu_count,
        "memory_total_bytes": memory_bytes,
        "memory_total_gb": memory_gb,
        "resource_tier": resource_tier,
        "recommended_swarm_max_agents": recommended_agents,
        "lag_risk": lag_risk,
        "platform_hints": _platform_hints(platform_key),
        **details,
    }


def detect_performance_profile() -> dict[str, Any]:
    device = detect_device_profile()
    recommended_agents = int(device.get("recommended_swarm_max_agents") or 3)
    lag_risk = str(device.get("lag_risk") or "medium")
    notes = [
        f"Mission Control should keep live swarm size at or below {recommended_agents} agent(s) on this device to avoid unnecessary local load.",
    ]
    if lag_risk == "high":
        notes.append("Prefer compact swarms and avoid heavy local multi-agent runs unless they are clearly justified.")
    elif lag_risk == "medium":
        notes.append("Balanced swarm settings are fine, but maximum parallelism is likely wasteful here.")
    else:
        notes.append("This device can tolerate a broader swarm, but more agents still create coordination debt.")
    return {
        "resource_tier": device.get("resource_tier"),
        "lag_risk": lag_risk,
        "recommended_swarm_max_agents": recommended_agents,
        "dynamic_spawning_recommended": recommended_agents >= 5,
        "notes": notes,
    }


def recommended_swarm_max_agents() -> int:
    return int(detect_performance_profile()["recommended_swarm_max_agents"])


def platform_debug_commands(*, backend_port: int = 8010) -> list[str]:
    device = detect_device_profile()
    platform_key = str(device.get("platform_key") or "unknown")
    if platform_key.startswith("windows"):
        return [
            ".\\scripts\\mission-control-headless-health.ps1 -Json",
            ".\\scripts\\mission-control-support-bundle.ps1",
            f"Invoke-WebRequest http://127.0.0.1:{backend_port}/api/health",
            f"Get-NetTCPConnection -LocalPort {backend_port} -ErrorAction SilentlyContinue",
            "Get-ChildItem .runtime\\diagnostics",
            "Get-ChildItem .runtime\\logs",
        ]
    return [
        "./scripts/mission-control-headless-health.sh --json",
        "./scripts/mission-control-support-bundle.sh",
        f"curl -fsS http://127.0.0.1:{backend_port}/api/health",
        f"lsof -nP -iTCP:{backend_port} -sTCP:LISTEN",
        "ls -la .runtime/diagnostics",
        "ls -la .runtime/logs",
    ]
