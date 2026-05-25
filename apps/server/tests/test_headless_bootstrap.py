from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path

from bootstrap.environment_probe import probe_environment, summarize_path_entries
from bootstrap.headless_config import build_headless_config, normalize_transport, write_headless_config
from bootstrap.runner_autowire import autowire_headless, get_headless_config, repair_headless
from bootstrap.runner_probe import probe_claude_cli, probe_dry_run, probe_ollama, probe_runners, summarize_runner_status


ROOT = Path(__file__).resolve().parents[3]


def test_environment_probe_handles_missing_tools_and_redacts_secret_like_entries(monkeypatch) -> None:
    monkeypatch.setenv("PATH", r"C:\tools;OPENAI_API_KEY=sk-proj-secret-value;C:\more-tools")
    monkeypatch.setattr(
        "bootstrap.environment_probe.probe_core_tools",
        lambda: {
            "git": {"detected": False, "path": None, "version": None},
            "node": {"detected": False, "path": None, "version": None},
            "npm": {"detected": False, "path": None, "version": None},
            "python": {"detected": True, "path": "C:/Python/python.exe", "version": "Python 3.12.0"},
            "pip": {"detected": True, "path": "C:/Python/Scripts/pip.exe", "version": "pip 24.0"},
            "uv": {"detected": False, "path": None, "version": None},
            "powershell": {"detected": True, "path": "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "version": "5.1"},
        },
    )

    summary = summarize_path_entries(os.environ["PATH"])
    joined = "\n".join(summary["entries"])
    assert summary["count"] >= 2
    assert "sk-proj-secret-value" not in joined

    payload = probe_environment(workspace_path=str(ROOT))
    assert payload["mission_control"]["runtime_path"]
    assert payload["mission_control"]["install_path"]
    assert payload["core_tools"]["git"]["detected"] is False


def test_environment_probe_marks_only_real_checkout_conflicts(monkeypatch, tmp_path) -> None:
    workspace_repo = tmp_path / "repo"
    workspace_repo.mkdir(parents=True, exist_ok=True)
    (workspace_repo / "apps" / "server" / "src" / "main.py").parent.mkdir(parents=True, exist_ok=True)
    (workspace_repo / "apps" / "server" / "src" / "main.py").write_text("app", encoding="utf-8")
    (workspace_repo / "scripts" / "start-mission-control-daemon.ps1").parent.mkdir(parents=True, exist_ok=True)
    (workspace_repo / "scripts" / "start-mission-control-daemon.ps1").write_text("start", encoding="utf-8")
    (workspace_repo / "plugins" / "mission-control" / "plugin.json").parent.mkdir(parents=True, exist_ok=True)
    (workspace_repo / "plugins" / "mission-control" / "plugin.json").write_text("{}", encoding="utf-8")

    app_support = tmp_path / "app-support"
    app_support.mkdir(parents=True, exist_ok=True)
    codex_plugin_home = tmp_path / ".codex" / "plugins" / "mission-control"
    codex_plugin_home.mkdir(parents=True, exist_ok=True)
    (codex_plugin_home / "plugin.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bootstrap.environment_probe.REPO_ROOT", workspace_repo)
    monkeypatch.setattr("bootstrap.environment_probe.APP_SUPPORT_ROOT", app_support)
    monkeypatch.setattr("bootstrap.environment_probe.get_codex_home", lambda: tmp_path / ".codex")

    discovered = probe_environment(workspace_path=str(workspace_repo))["discovered_installs"]
    by_kind = {item["kind"]: item for item in discovered}

    assert by_kind["workspace_repo"]["markers"]["install_conflict"] is True
    assert by_kind["app_support_root"]["markers"]["install_conflict"] is False
    assert by_kind["codex_plugin_home"]["markers"]["install_conflict"] is False


def test_dry_run_runner_is_always_available() -> None:
    probe = probe_dry_run()
    assert probe["available"] is True
    assert probe["configured"] is True
    assert probe["safe_default"] is True


def test_runner_probe_reports_missing_tools_and_api_billing(monkeypatch) -> None:
    missing_probe = {"detected": False, "path": None, "version": None}

    monkeypatch.setattr("bootstrap.runner_probe.probe_command", lambda *names: missing_probe)
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_codex_status",
        lambda: {
            "authenticated": False,
            "cli_detected": False,
            "cli_version": None,
            "login_status": "Not logged in",
            "auth_mode": None,
            "mcp_servers": [],
            "local_skills": [],
        },
    )
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_ollama_status",
        lambda endpoint=None: {"reachable": False, "available_models": [], "cli_version": "http://localhost:11434", "summary": "offline"},
    )
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_claude_code_status",
        lambda: {"cli_detected": False, "cli_version": None, "available_models": [], "login_status": "unknown"},
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-super-secret-value")

    probes = {probe["runner_id"]: probe for probe in probe_runners()}
    assert probes["dry_run"]["configured"] is True
    assert probes["codex_cli"]["install_status"] == "missing"
    assert probes["ollama"]["install_status"] == "installed_not_running"
    assert probes["claude_cli"]["install_status"] == "missing"
    assert probes["openai_api"]["billing_warning"]
    assert probes["openai_api"]["configured"] is True
    assert probes["openai_api"]["install_status"] == "external_configured"
    assert probes["openai_api"]["details_json"]["adapter_recipe_source"] == "builtin"
    assert "custom_api" not in probes
    assert "sk-proj-super-secret-value" not in str(probes["openai_api"])


def test_ollama_probe_reports_running_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "bootstrap.runner_probe.probe_command",
        lambda *names: {"detected": True, "path": "C:/tools/ollama.exe", "version": "ollama version 0.4.0"},
    )
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_ollama_status",
        lambda endpoint=None: {
            "reachable": True,
            "available_models": ["qwen2.5-coder:7b"],
            "cli_version": "http://localhost:11434",
            "summary": "online",
        },
    )

    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_custom_status",
        lambda adapter_command=None, adapter_args=None: {"cli_detected": True},
    )

    probe = probe_ollama(adapter_command="python", adapter_args=["scripts/ollama_adapter.py"])
    assert probe["available"] is True
    assert probe["configured"] is True
    assert probe["safe_default"] is True
    assert "qwen2.5-coder:7b" in probe["models"]


def test_claude_cli_missing_state(monkeypatch) -> None:
    monkeypatch.setattr(
        "bootstrap.runner_probe.probe_command",
        lambda *names: {"detected": False, "path": None, "version": None},
    )
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_claude_code_status",
        lambda: {"cli_detected": False, "cli_version": None, "available_models": [], "login_status": "unknown"},
    )

    probe = probe_claude_cli()
    assert probe["available"] is False
    assert probe["install_status"] == "missing"


def test_claude_cli_probe_prefers_resolved_cli_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "bootstrap.runner_probe.probe_command",
        lambda *names: {"detected": False, "path": None, "version": None},
    )
    monkeypatch.setattr(
        "bootstrap.runner_probe.detect_claude_code_status",
        lambda: {
            "cli_detected": True,
            "cli_path": "/opt/homebrew/bin/claude",
            "cli_execution_available": True,
            "cli_version": "claude 1.2.3",
            "available_models": ["sonnet"],
            "login_status": "Interactive Claude Code login is managed outside Mission Control.",
        },
    )

    probe = probe_claude_cli()
    assert probe["available"] is True
    assert probe["configured"] is True
    assert probe["install_status"] == "ready_auth_unknown"
    assert probe["command_path"] == "/opt/homebrew/bin/claude"


def test_autowire_generates_safe_headless_config_and_repair_preserves_install_id(monkeypatch) -> None:
    fake_runner_summary = {
        "status": "degraded",
        "runners": [
            {
                "runner_id": "dry_run",
                "label": "Dry-run",
                "available": True,
                "configured": True,
                "auth_status": "not_required",
                "install_status": "ready",
                "command_path": None,
                "version": None,
                "safe_default": True,
                "requires_user_action": False,
                "recommended_fix": None,
                "billing_warning": None,
                "models": [],
                "details_json": {},
                "checked_at": "2026-05-18T00:00:00Z",
            },
            {
                "runner_id": "codex_cli",
                "label": "Codex CLI",
                "available": True,
                "configured": True,
                "auth_status": "authenticated",
                "install_status": "ready",
                "command_path": "C:/tools/codex.exe",
                "version": "codex 1.0.0",
                "safe_default": True,
                "requires_user_action": False,
                "recommended_fix": None,
                "billing_warning": None,
                "models": [],
                "details_json": {},
                "checked_at": "2026-05-18T00:00:00Z",
            },
            {
                "runner_id": "openai_api",
                "label": "OpenAI API",
                "available": True,
                "configured": True,
                "auth_status": "authenticated",
                "install_status": "external_configured",
                "command_path": None,
                "version": None,
                "safe_default": False,
                "requires_user_action": False,
                "recommended_fix": "API-backed runner is available through external secure environment configuration.",
                "billing_warning": "OpenAI API may incur API billing.",
                "models": [],
                "details_json": {"env_var": "OPENAI_API_KEY"},
                "checked_at": "2026-05-18T00:00:00Z",
            },
        ],
        "enabled_runners": ["dry_run", "codex_cli", "openai_api"],
        "safe_defaults": ["dry_run", "codex_cli"],
        "checked_at": "2026-05-18T00:00:00Z",
    }

    async def fake_health() -> dict:
        return {
            "status": "degraded",
            "checks": [
                {"key": "mission_control_daemon_reachable", "status": "ready", "summary": "running"},
                {"key": "mcp_server_reachable", "status": "degraded", "summary": "not configured yet"},
            ],
            "recommended_next_steps": ["Reload Codex MCP config."],
            "safe_troubleshooting_commands": [],
            "codex_chat_markdown": "health",
            "checked_at": "2026-05-18T00:00:00Z",
            "notes": [],
        }

    monkeypatch.setattr("bootstrap.runner_autowire.summarize_runner_status", lambda: fake_runner_summary)
    monkeypatch.setattr("bootstrap.runner_autowire.mission_control_plugin_health", fake_health)

    report = asyncio.run(autowire_headless(workspace_path=str(ROOT)))
    assert report["status"] == "degraded"
    assert report["headless_config"]["dashboard_enabled"] is False
    assert "operator_recommendations" in report
    assert "Dry-run" in report["configured_runners"]
    assert "OpenAI API" in report["configured_runners"]
    assert "sk-proj" not in str(report)

    config = get_headless_config()
    install_id = config["install_id"]
    repaired = asyncio.run(repair_headless())
    assert repaired["headless_config"]["install_id"] == install_id


def test_environment_probe_reports_stored_mcp_transport(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    write_headless_config(
        {
            "install_id": "x",
            "install_path": str(ROOT),
            "runtime_path": str(runtime_root),
            "headless_only": True,
            "dashboard_enabled": False,
            "daemon_host": "127.0.0.1",
            "daemon_port": 8010,
            "mcp_transport": "disabled",
            "mcp_port": None,
            "enabled_runners": ["dry_run"],
            "runner_configs": {},
            "default_runner_policy": {},
            "default_model_policy": {},
            "safe_mode_defaults": {},
            "plugin_paths": [],
            "skills_paths": [],
            "created_at": "now",
            "updated_at": "now",
            "redaction_status": "clean",
        },
        str(runtime_root),
    )

    payload = probe_environment(runtime_path=str(runtime_root))

    assert payload["mcp_status"]["transport"] == "disabled"


def test_headless_config_rejects_unsupported_http_mcp_transport() -> None:
    assert normalize_transport("http") == "stdio"
    config = build_headless_config(
        probes=[],
        install_path=str(ROOT),
        runtime_path=None,
        daemon_host="127.0.0.1",
        daemon_port=8010,
        mcp_transport="http",
        mcp_port=8123,
        headless_only=True,
    )
    assert config["mcp_transport"] == "stdio"
    assert config["mcp_port"] is None


def test_headless_config_and_environment_probe_honor_requested_install_path(monkeypatch, tmp_path) -> None:
    install_root = tmp_path / "portable-install"
    (install_root / "plugins" / "mission-control" / "mcp").mkdir(parents=True, exist_ok=True)
    (install_root / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    runtime_root = tmp_path / "runtime"
    config = build_headless_config(
        probes=[],
        install_path=str(install_root),
        runtime_path=str(runtime_root),
        daemon_host="127.0.0.1",
        daemon_port=8010,
        mcp_transport="stdio",
        mcp_port=None,
        headless_only=True,
    )

    assert any(path.startswith(str(install_root.resolve())) for path in config["plugin_paths"])
    assert any(path.startswith(str(install_root.resolve())) for path in config["skills_paths"])

    monkeypatch.setattr("bootstrap.environment_probe.REPO_ROOT", tmp_path / "different-repo")
    payload = probe_environment(install_path=str(install_root), runtime_path=str(runtime_root))
    assert payload["mission_control"]["install_path"].endswith("portable-install")
    assert any("portable-install" in path for path in payload["plugin_paths"])


def test_get_headless_config_is_read_only(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(
        "bootstrap.runner_autowire.summarize_runner_status",
        lambda: {"runners": [], "status": "degraded", "enabled_runners": [], "safe_defaults": [], "checked_at": "now"},
    )

    config = get_headless_config(runtime_path=str(runtime_root))

    assert config["runtime_path"] == str(runtime_root.resolve())
    assert not (runtime_root / "headless" / "headless.json").exists()


def test_headless_endpoints_and_runner_status_endpoint(client, bridge_headers, monkeypatch) -> None:
    fake_config = {
        "config_path": str(ROOT / ".runtime-test" / "headless" / "headless.json"),
        "install_id": "abc123",
        "install_path": str(ROOT),
        "runtime_path": str(ROOT / ".runtime-test"),
        "headless_only": True,
        "dashboard_enabled": False,
        "daemon_host": "127.0.0.1",
        "daemon_port": 8010,
        "mcp_transport": "stdio",
        "mcp_port": None,
        "enabled_runners": ["dry_run", "codex_cli"],
        "runner_configs": {},
        "default_runner_policy": {},
        "default_model_policy": {},
        "safe_mode_defaults": {},
        "plugin_paths": [],
        "skills_paths": [],
        "created_at": "2026-05-18T00:00:00Z",
        "updated_at": "2026-05-18T00:00:00Z",
        "redaction_status": "clean",
    }

    async def fake_health() -> dict:
        return {
            "status": "ready",
            "checks": [],
            "recommended_next_steps": [],
            "safe_troubleshooting_commands": [],
            "codex_chat_markdown": "ok",
            "checked_at": "2026-05-18T00:00:00Z",
            "notes": [],
        }

    async def fake_report(**kwargs) -> dict:
        return {
            "status": "ready",
            "install_path": str(ROOT),
            "runtime_path": str(ROOT / ".runtime-test"),
            "daemon_status": "ready",
            "mcp_status": "ready",
            "configured_runners": ["Dry-run", "Codex CLI"],
            "unavailable_runners": [],
            "user_actions_required": [],
            "warnings": [],
            "next_codex_prompt": "Use Mission Control for this repo and fix the failing tests.",
            "redaction_status": "clean",
            "created_at": "2026-05-18T00:00:00Z",
            "codex_chat_markdown": "install ok",
            "headless_config": fake_config,
            "plugin_health": {
                "status": "ready",
                "checks": [],
                "recommended_next_steps": [],
                "safe_troubleshooting_commands": [],
                "codex_chat_markdown": "ok",
                "checked_at": "2026-05-18T00:00:00Z",
                "notes": [],
            },
        }

    monkeypatch.setattr("main.get_headless_health", fake_health)
    monkeypatch.setattr("main.get_headless_config", lambda: fake_config)
    monkeypatch.setattr("main.autowire_headless", fake_report)
    monkeypatch.setattr("main.repair_headless", fake_report)
    monkeypatch.setattr(
        "main.summarize_runner_status",
        lambda: {
            "status": "ready",
            "runners": [],
            "enabled_runners": ["dry_run", "codex_cli"],
            "safe_defaults": ["dry_run", "codex_cli"],
            "checked_at": "2026-05-18T00:00:00Z",
        },
    )

    assert client.get("/api/headless/health", headers=bridge_headers).status_code == 200
    assert client.get("/api/headless/config").status_code == 200
    assert client.get("/api/runners/status").status_code == 200
    assert client.post("/api/headless/autowire", json={}, headers=bridge_headers).status_code == 200
    assert client.post("/api/headless/repair", json={}, headers=bridge_headers).status_code == 200


def test_scripts_and_headless_skills_exist() -> None:
    script_paths = [
        ROOT / "scripts" / "install-mission-control-plugin.ps1",
        ROOT / "scripts" / "install-mission-control-plugin.bat",
        ROOT / "scripts" / "install-mission-control-plugin.sh",
        ROOT / "scripts" / "mission-control-manage.py",
        ROOT / "scripts" / "mission_control_manage.py",
        ROOT / "scripts" / "update-mission-control-plugin.ps1",
        ROOT / "scripts" / "update-mission-control-plugin.bat",
        ROOT / "scripts" / "update-mission-control-plugin.sh",
        ROOT / "scripts" / "uninstall-mission-control-plugin.ps1",
        ROOT / "scripts" / "uninstall-mission-control-plugin.bat",
        ROOT / "scripts" / "uninstall-mission-control-plugin.sh",
        ROOT / "scripts" / "uninstall-mission-control-plugin.py",
        ROOT / "scripts" / "start-mission-control-daemon.ps1",
        ROOT / "scripts" / "start-mission-control-daemon.sh",
        ROOT / "scripts" / "stop-mission-control-daemon.ps1",
        ROOT / "scripts" / "stop-mission-control-daemon.sh",
        ROOT / "scripts" / "start-mission-control-mcp.ps1",
        ROOT / "scripts" / "mission-control-headless-health.ps1",
        ROOT / "scripts" / "mission-control-bootstrap.py",
        ROOT / "scripts" / "api_provider_adapter.py",
    ]
    for path in script_paths:
        assert path.exists(), f"Missing script: {path}"

    skill_paths = [
        ROOT / ".codex" / "skills" / "mission-control-install-from-github" / "SKILL.md",
        ROOT / ".codex" / "skills" / "mission-control-update" / "SKILL.md",
        ROOT / ".codex" / "skills" / "mission-control-uninstall" / "SKILL.md",
        ROOT / ".codex" / "skills" / "mission-control-autowire-providers" / "SKILL.md",
        ROOT / ".codex" / "skills" / "mission-control-headless-health" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-install-from-github" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-update" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-uninstall" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-autowire-providers" / "SKILL.md",
        ROOT / "plugins" / "mission-control" / "skills" / "mission-control-headless-health" / "SKILL.md",
    ]
    for path in skill_paths:
        assert path.exists(), f"Missing skill: {path}"
        content = path.read_text(encoding="utf-8")
        assert "Codex chat agent is not the Mission Control Manager." in content
        assert "Never require the standalone UI." in content or "Never require UI interaction." in content


def test_runner_status_summary_degrades_to_dry_run_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "bootstrap.runner_probe.probe_runners",
        lambda ollama_endpoint=None, adapter_command=None, adapter_args=None: [
            {
                "runner_id": "dry_run",
                "label": "Dry-run",
                "available": True,
                "configured": True,
                "safe_default": True,
            }
        ],
    )
    summary = summarize_runner_status()
    assert summary["status"] == "degraded"
    assert summary["enabled_runners"] == ["dry_run"]


def test_uninstall_script_removes_plugin_bundle_and_mission_control_skills(tmp_path) -> None:
    module_path = ROOT / "scripts" / "uninstall-mission-control-plugin.py"
    spec = importlib.util.spec_from_file_location("mission_control_uninstall", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    codex_home = tmp_path / ".codex"
    plugin_dir = codex_home / "plugins" / "mission-control"
    skill_dir = codex_home / "skills" / "mission-control-status"
    unrelated_skill = codex_home / "skills" / "something-else"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    skill_dir.mkdir(parents=True, exist_ok=True)
    unrelated_skill.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text("{}", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("# status", encoding="utf-8")
    (unrelated_skill / "SKILL.md").write_text("# keep", encoding="utf-8")

    payload = module.uninstall_plugin_bundle(codex_home, dry_run=False)

    assert payload["plugin_removed"] is True
    assert payload["removed_skill_count"] == 1
    assert payload["removed_skills"] == ["mission-control-status"]
    assert not plugin_dir.exists()
    assert not skill_dir.exists()
    assert unrelated_skill.exists()
