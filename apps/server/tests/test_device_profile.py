from __future__ import annotations

from types import SimpleNamespace

import device_profile
from manager import service


def test_detect_device_profile_classifies_windows_11(monkeypatch) -> None:
    monkeypatch.setattr(device_profile.platform, "system", lambda: "Windows")
    monkeypatch.setattr(device_profile.platform, "release", lambda: "10")
    monkeypatch.setattr(device_profile.platform, "version", lambda: "10.0.22631")
    monkeypatch.setattr(device_profile.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(device_profile.os, "cpu_count", lambda: 12)
    monkeypatch.setattr(device_profile, "_total_memory_bytes", lambda system_name: 32 * 1024**3)
    device_profile.detect_device_profile.cache_clear()

    profile = device_profile.detect_device_profile()
    assert profile["platform_key"] == "windows_11"
    assert profile["platform_label"] == "Windows 11"
    assert profile["recommended_swarm_max_agents"] >= 7


def test_swarm_capacity_limit_respects_device_cap(monkeypatch) -> None:
    monkeypatch.setattr("manager.recommended_swarm_max_agents", lambda: 3)
    preferences = SimpleNamespace(swarm_aggressiveness="maximum", max_agents=12)

    assert service._swarm_capacity_limit(preferences) == 3
