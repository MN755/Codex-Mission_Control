from __future__ import annotations

from pathlib import Path

from system_status import _parse_configured_mcp_servers, _strip_codex_cli_noise, detect_codex_status, detect_custom_status


def test_strip_codex_cli_noise_removes_arg0_warnings() -> None:
    output = "\n".join(
        [
            "WARNING: failed to clean up stale arg0 temp dirs: Access is denied. (os error 5)",
            'WARNING: proceeding, even though we could not update PATH: Access is denied. (os error 5) at path "C:\\\\Users\\\\mike\\\\.codex\\\\tmp\\\\arg0\\\\codex-arg0W7gELB"',
            "Logged in using ChatGPT",
        ]
    )

    assert _strip_codex_cli_noise(output) == "Logged in using ChatGPT"


def test_detect_codex_status_distinguishes_present_cli_from_runtime_execution_limit(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "skills").mkdir(parents=True, exist_ok=True)
    config_path = codex_home / "config.toml"
    config_path.write_text(
        """
[mcp_servers."mission-control"]
command = "python"
cwd = "C:/repos/Codex Mission Control/apps/mcp-server"
""".strip(),
        encoding="utf-8",
    )

    cli_path = tmp_path / "codex.exe"
    cli_path.write_text("", encoding="utf-8")

    monkeypatch.setattr("system_status.get_codex_home", lambda: codex_home)
    monkeypatch.setattr("system_status.codex_command_path", lambda: str(cli_path))
    monkeypatch.setattr("system_status._run_command", lambda args: (False, ""))

    payload = detect_codex_status()

    assert payload["cli_detected"] is True
    assert payload["cli_path"] == str(cli_path)
    assert payload["cli_path_exists"] is True
    assert payload["cli_execution_available"] is False
    assert payload["configured_mcp_servers"]
    assert payload["configured_mcp_servers"][0]["name"] == "mission-control"
    assert payload["mcp_state"]["mission_control"]["configured"] is True
    assert payload["mcp_state"]["mission_control"]["app_loaded"] is None
    assert "cli execution is unavailable from this runtime" in " ".join(payload["notes"]).lower()


def test_detect_codex_status_uses_live_mcp_discovery_when_available(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "skills" / "mission-control-status").mkdir(parents=True, exist_ok=True)
    (codex_home / "skills" / "mission-control-status" / "SKILL.md").write_text("status", encoding="utf-8")
    (codex_home / "config.toml").write_text("", encoding="utf-8")

    cli_path = tmp_path / "codex.exe"
    cli_path.write_text("", encoding="utf-8")

    def fake_run(args: list[str]) -> tuple[bool, str]:
        if args[1:] == ["--version"]:
            return True, "codex 1.0.0"
        if args[1:] == ["login", "status"]:
            return True, "Logged in using ChatGPT"
        if args[1:] == ["mcp", "list", "--json"]:
            return True, '[{"name":"mission-control","status":"connected"}]'
        if args[1:] == ["app-server", "--help"]:
            return True, "Run the app server"
        return False, ""

    monkeypatch.setattr("system_status.get_codex_home", lambda: codex_home)
    monkeypatch.setattr("system_status.codex_command_path", lambda: str(cli_path))
    monkeypatch.setattr("system_status._run_command", fake_run)

    payload = detect_codex_status()

    assert payload["cli_detected"] is True
    assert payload["cli_execution_available"] is True
    assert payload["authenticated"] is True
    assert payload["supports_app_server"] is True
    assert payload["mcp_servers"] == [{"name": "mission-control", "status": "connected"}]
    assert payload["mcp_state"]["mission_control"]["app_loaded"] is True
    assert payload["mcp_state"]["mission_control"]["discovery_source"] == "cli"


def test_parse_configured_mcp_servers_python310_fallback_preserves_metadata(monkeypatch) -> None:
    monkeypatch.setattr("system_status.tomllib", None)
    payload = _parse_configured_mcp_servers(
        """
[mcp_servers."mission-control"]
command = "python"
cwd = "C:/repo/apps/mcp-server"
transport = "stdio"
status = "enabled"
""".strip()
    )

    assert payload == [
        {
            "name": "mission-control",
            "command": "python",
            "cwd": "C:/repo/apps/mcp-server",
            "transport": "stdio",
            "status": "enabled",
        }
    ]


def test_detect_custom_status_uses_path_lookup_without_direct_path_probe(monkeypatch) -> None:
    monkeypatch.setattr("system_status.resolve_adapter_recipe", lambda provider, command, args: None)
    monkeypatch.setattr("system_status.Path", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Path should not be used here")))
    monkeypatch.setattr("system_status.shutil.which", lambda command: "/safe/bin/custom-adapter" if command == "custom-adapter" else None)

    payload = detect_custom_status("custom-adapter", ["--project", "demo"])

    assert payload["cli_detected"] is True
    assert payload["cli_path"] == "custom-adapter"
    assert payload["cli_path_exists"] is True
    assert payload["cli_execution_available"] is True
    assert payload["cli_version"] == "custom-adapter --project demo"


def test_detect_custom_status_rejects_missing_custom_path_probe(monkeypatch) -> None:
    monkeypatch.setattr("system_status.resolve_adapter_recipe", lambda provider, command, args: None)
    monkeypatch.setattr("system_status.Path", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Path should not be used here")))
    monkeypatch.setattr("system_status.shutil.which", lambda _command: None)

    payload = detect_custom_status("../../tmp/definitely-not-an-adapter", ["--project", "demo"])

    assert payload["cli_detected"] is False
    assert payload["cli_path"] == "../../tmp/definitely-not-an-adapter"
    assert payload["cli_path_exists"] is False
    assert payload["cli_execution_available"] is False
    assert payload["cli_version"] is None


def test_detect_custom_status_reports_missing_adapter_blocker(monkeypatch) -> None:
    monkeypatch.setattr("system_status.resolve_adapter_recipe", lambda provider, command, args: None)
    monkeypatch.setattr("system_status.shutil.which", lambda _command: None)

    payload = detect_custom_status("missing-adapter", [])

    assert payload["cli_detected"] is False


def test_detect_system_status_reports_runtime_blockers_for_selected_provider(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("system_status.detect_codex_status", lambda: {
        "provider": "codex",
        "label": "Codex",
        "cli_detected": True,
        "cli_path": "codex",
        "cli_path_exists": True,
        "cli_execution_available": True,
        "cli_version": "codex 1.0.0",
        "login_status": "Logged in using ChatGPT",
        "auth_mode": "chatgpt",
        "authenticated": True,
        "app_server_supported": True,
        "configured_plugins": [],
        "configured_mcp_servers": [],
        "local_skills": [],
        "mcp_servers": [],
        "mcp_state": {},
        "notes": [],
    })
    monkeypatch.setattr("system_status.detect_claude_code_status", lambda: {
        "provider": "claude_code",
        "label": "Claude Code",
        "cli_detected": False,
        "cli_path": None,
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "Claude CLI was not detected.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": False,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
    })
    monkeypatch.setattr("system_status.detect_ollama_status", lambda endpoint=None: {
        "provider": "ollama",
        "label": "Ollama",
        "cli_detected": False,
        "cli_path": None,
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "Ollama endpoint not reachable.",
        "auth_mode": "local",
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": True,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "Ollama endpoint not reachable.",
    })
    monkeypatch.setattr("system_status.detect_nvidia_nim_status", lambda endpoint=None: {
        "provider": "nvidia_nim",
        "label": "NVIDIA NIM",
        "cli_detected": False,
        "cli_path": endpoint or "https://integrate.api.nvidia.com",
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "NVIDIA NIM endpoint is not reachable.",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "offline",
        "endpoint": endpoint or "https://integrate.api.nvidia.com",
        "endpoint_configured": False,
        "api_key_configured": False,
        "auth_required": True,
    })
    monkeypatch.setattr("system_status.detect_webwright_status", lambda: {"summary": "not installed"})
    monkeypatch.setattr("system_status.shutil.which", lambda _command: None)

    from system_status import detect_system_status

    payload = detect_system_status(
        selected_provider="openai_api",
        adapter_command="missing-adapter",
        adapter_args=["--project", "demo"],
    )

    assert payload["selected_provider"] == "openai_api"
    assert payload["runtime_ready"] is False
    assert payload["runtime_status"] == "blocked"
    assert "api_key_missing" in payload["runtime_blockers"]
    assert "adapter_command_unavailable" in payload["runtime_blockers"]


def test_detect_system_status_reports_dynamo_runtime_when_selected(monkeypatch) -> None:
    monkeypatch.setattr("system_status.detect_codex_status", lambda: {
        "provider": "codex",
        "label": "Codex",
        "cli_detected": True,
        "cli_path": "codex",
        "cli_path_exists": True,
        "cli_execution_available": True,
        "cli_version": "codex 1.0.0",
        "login_status": "Logged in using ChatGPT",
        "auth_mode": "chatgpt",
        "authenticated": True,
        "app_server_supported": True,
        "configured_plugins": [],
        "configured_mcp_servers": [],
        "local_skills": [],
        "mcp_servers": [],
        "mcp_state": {},
        "notes": [],
    })
    monkeypatch.setattr("system_status.detect_claude_code_status", lambda: {
        "provider": "claude_code",
        "label": "Claude Code",
        "cli_detected": False,
        "cli_path": None,
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "missing",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": False,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
    })
    monkeypatch.setattr("system_status.detect_ollama_status", lambda endpoint=None: {
        "provider": "ollama",
        "label": "Ollama",
        "cli_detected": False,
        "cli_path": None,
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "missing",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": True,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "missing",
    })
    monkeypatch.setattr("system_status.detect_nvidia_nim_status", lambda endpoint=None: {
        "provider": "nvidia_nim",
        "label": "NVIDIA NIM",
        "cli_detected": False,
        "cli_path": endpoint or "https://integrate.api.nvidia.com",
        "cli_path_exists": False,
        "cli_execution_available": False,
        "cli_version": None,
        "login_status": "missing",
        "auth_mode": None,
        "authenticated": False,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": [],
        "notes": [],
        "reachable": False,
        "summary": "missing",
        "endpoint": endpoint or "https://integrate.api.nvidia.com",
        "endpoint_configured": False,
        "api_key_configured": False,
        "auth_required": True,
    })
    monkeypatch.setattr("system_status.detect_nvidia_dynamo_status", lambda endpoint=None: {
        "provider": "nvidia_dynamo",
        "label": "NVIDIA Dynamo",
        "cli_detected": True,
        "cli_path": endpoint or "http://dynamo.local:8000",
        "cli_path_exists": True,
        "cli_execution_available": True,
        "cli_version": endpoint or "http://dynamo.local:8000",
        "login_status": "reachable",
        "auth_mode": "optional",
        "authenticated": True,
        "auth_status_detectable": True,
        "supports_model_override": True,
        "supports_reasoning_effort": False,
        "supports_app_server": False,
        "supports_builtin_auth": False,
        "available_models": ["Qwen/Qwen3-0.6B"],
        "notes": [],
        "reachable": True,
        "summary": "reachable",
        "endpoint": endpoint or "http://dynamo.local:8000",
        "endpoint_configured": True,
        "api_key_configured": False,
        "auth_required": False,
    })
    monkeypatch.setattr("system_status.detect_webwright_status", lambda: {"summary": "not installed"})
    monkeypatch.setattr("system_status.detect_custom_status", lambda command=None, args=None: {
        "provider": "custom",
        "cli_detected": True,
    })

    from system_status import detect_system_status

    payload = detect_system_status(
        selected_provider="nvidia_dynamo",
        adapter_command="custom-adapter",
        ollama_endpoint="http://dynamo.local:8000",
    )

    assert payload["selected_provider"] == "nvidia_dynamo"
    assert payload["selected_provider_label"] == "NVIDIA Dynamo"
    assert payload["runtime_ready"] is True
    assert payload["runtime_status"] == "ready"
    assert payload["runtime_blockers"] == []
