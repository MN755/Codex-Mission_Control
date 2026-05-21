from __future__ import annotations

from pathlib import Path

from system_status import detect_codex_status


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
