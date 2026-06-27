from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_manage_module():
    module_path = ROOT / "scripts" / "mission_control_manage.py"
    spec = importlib.util.spec_from_file_location("mission_control_manage", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("mission_control_manage", module)
    spec.loader.exec_module(module)
    return module


def test_codex_config_registration_round_trip(tmp_path) -> None:
    module = _load_manage_module()
    codex_home = tmp_path / ".codex"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    config_path = codex_home / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('[mcp_servers."other"]\ncommand = "python"\n', encoding="utf-8")

    registered = module.upsert_codex_config(
        codex_home,
        repo_root,
        sys.executable,
        backend_host="127.0.0.1",
        backend_port=8010,
        plugin_id="mission-control@local",
        dry_run=False,
    )
    assert registered["status"] == "updated"
    text = config_path.read_text(encoding="utf-8")
    assert '[mcp_servers."mission-control"]' in text
    assert '[plugins."mission-control@local"]' in text
    assert str(repo_root).replace("\\", "/") in text
    assert 'scripts/serve-mission-control-mcp.py' in text

    removed = module.remove_codex_config_registration(codex_home, dry_run=False)
    assert removed["status"] == "removed"
    cleaned = config_path.read_text(encoding="utf-8")
    assert '[mcp_servers."mission-control"]' not in cleaned
    assert '[mcp_servers."other"]' in cleaned


def test_sync_codex_bundle_copies_plugin_and_mission_control_skills(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / "plugins" / "mission-control"
    skill_root = repo_root / ".codex" / "skills"
    codex_home = tmp_path / ".codex-home"

    (plugin_root / ".codex-plugin" / "plugin.json").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "mission-control", "display_name": "Mission Control", "version": "1.4.0"}),
        encoding="utf-8",
    )
    (plugin_root / "skills" / "mission-control-install-from-github" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / "skills" / "mission-control-install-from-github" / "SKILL.md").write_text("# plugin install", encoding="utf-8")
    (skill_root / "mission-control-install-from-github" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "mission-control-install-from-github" / "SKILL.md").write_text("# install", encoding="utf-8")
    (skill_root / "mission-control-update" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "mission-control-update" / "SKILL.md").write_text("# update", encoding="utf-8")
    (skill_root / "not-mission-control" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "not-mission-control" / "SKILL.md").write_text("# ignore", encoding="utf-8")
    stale_cache = codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.2.0"
    stale_cache.mkdir(parents=True, exist_ok=True)
    (stale_cache / "plugin.json").write_text("{}", encoding="utf-8")

    payload = module.sync_codex_bundle(repo_root, codex_home, dry_run=False)

    assert payload["status"] == "ready"
    assert payload["plugin_source"] == str(plugin_root)
    assert payload["plugin_name"] == "mission-control"
    assert payload["plugin_display_name"] == "Mission Control"
    assert (codex_home / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json").exists()
    assert (codex_home / "plugins" / "mission-control" / "skills" / "mission-control-install-from-github" / "SKILL.md").exists()
    assert (codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.4.0" / ".codex-plugin" / "plugin.json").exists()
    assert not (codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.2.0").exists()
    assert payload["cache_sync"]["plugin_version"] == "1.4.0"
    assert payload["cache_sync"]["stale_versions_removed"] == ["1.2.0"]
    assert (codex_home / "skills" / "mission-control-install-from-github" / "SKILL.md").exists()
    assert (codex_home / "skills" / "mission-control-update" / "SKILL.md").exists()
    assert not (codex_home / "skills" / "not-mission-control").exists()


def test_sync_local_plugin_marketplace_creates_discoverable_plugin_entry(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / "plugins" / "mission-control"
    agents_home = tmp_path / ".agents"

    (plugin_root / ".codex-plugin" / "plugin.json").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "mission-control",
                "version": "1.2.0",
                "interface": {"displayName": "Mission Control"},
            }
        ),
        encoding="utf-8",
    )
    (plugin_root / "assets" / "mission-control-logo.png").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / "assets" / "mission-control-logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    payload = module.sync_local_plugin_marketplace(repo_root, agents_home, dry_run=False)

    assert payload["status"] == "ready"
    assert payload["plugin_id"] == "mission-control@local"
    assert (agents_home.parent / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json").exists()
    marketplace = json.loads((agents_home / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "local"
    assert any(entry["name"] == "mission-control" for entry in marketplace["plugins"])
    assert payload["plugin_source_exists"] is True
    assert payload["plugin_destination_exists_after"] is True
    assert payload["marketplace_path_exists"] is True


def test_sync_codex_bundle_requires_codex_plugin_manifest_before_reporting_ready(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / "plugins" / "mission-control"
    codex_home = tmp_path / ".codex-home"
    stale_cache = codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.2.0"

    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "plugin.json").write_text(
        json.dumps({"name": "mission-control", "display_name": "Mission Control", "version": "1.4.0"}),
        encoding="utf-8",
    )
    stale_cache.mkdir(parents=True, exist_ok=True)
    (stale_cache / "plugin.json").write_text("{}", encoding="utf-8")

    payload = module.sync_codex_bundle(repo_root, codex_home, dry_run=False)

    assert payload["status"] == "missing"
    assert payload["plugin_manifest"]["status"] == "missing"
    assert payload["plugin_source_exists"] is True
    assert payload["plugin_destination_exists_after"] is False
    assert payload["plugin_files_copied"] == 0
    assert payload["cache_sync"]["status"] == "missing"
    assert payload["cache_sync"]["stale_versions_removed"] == []
    assert stale_cache.exists()


def test_sync_codex_bundle_does_not_report_ready_or_prune_cache_without_plugin_source(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    codex_home = tmp_path / ".codex-home"
    stale_cache = codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.2.0"

    stale_cache.mkdir(parents=True, exist_ok=True)
    (stale_cache / "plugin.json").write_text("{}", encoding="utf-8")

    payload = module.sync_codex_bundle(repo_root, codex_home, dry_run=False)

    assert payload["status"] == "missing"
    assert payload["plugin_manifest"]["status"] == "missing"
    assert payload["plugin_source_exists"] is False
    assert payload["cache_sync"]["status"] == "missing"
    assert payload["cache_sync"]["stale_versions_removed"] == []
    assert stale_cache.exists()


def test_sync_local_plugin_marketplace_requires_plugin_source_before_writing_marketplace(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    agents_home = tmp_path / ".agents"

    payload = module.sync_local_plugin_marketplace(repo_root, agents_home, dry_run=False)

    assert payload["status"] == "missing"
    assert payload["plugin_manifest"]["status"] == "missing"
    assert payload["plugin_source_exists"] is False
    assert payload["plugin_destination_exists_after"] is False
    assert payload["marketplace_path_exists"] is False
    assert not (agents_home / "plugins" / "marketplace.json").exists()


def test_sync_local_plugin_marketplace_requires_codex_plugin_manifest_before_reporting_ready(tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    plugin_root = repo_root / "plugins" / "mission-control"
    agents_home = tmp_path / ".agents"

    plugin_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / "plugin.json").write_text(
        json.dumps({"name": "mission-control", "display_name": "Mission Control", "version": "1.4.0"}),
        encoding="utf-8",
    )

    payload = module.sync_local_plugin_marketplace(repo_root, agents_home, dry_run=False)

    assert payload["status"] == "missing"
    assert payload["plugin_manifest"]["status"] == "missing"
    assert payload["plugin_source_exists"] is True
    assert payload["plugin_destination_exists_after"] is False
    assert payload["marketplace_path_exists"] is False
    assert not (agents_home / "plugins" / "marketplace.json").exists()


def test_detect_claude_assets_reports_packaged_commands_and_agents() -> None:
    module = _load_manage_module()

    payload = module.detect_claude_assets(ROOT)

    assert payload["status"] == "ready"
    assert not payload["missing"]
    assert payload["packaged_command_count"] >= 18
    assert payload["packaged_agent_count"] >= 15
    assert "mission-control-feature-dev" in payload["packaged_commands"]
    assert "mission-control-code-review" in payload["packaged_commands"]
    assert "mission-control-understand" in payload["packaged_commands"]
    assert "mission-control-rag-design" in payload["packaged_commands"]
    assert "code-explorer" in payload["packaged_agents"]
    assert "security-auditor" in payload["packaged_agents"]
    assert "knowledge-graph-builder" in payload["packaged_agents"]
    assert "retrieval-architect" in payload["packaged_agents"]


def test_ensure_python_packages_skips_reinstall_when_modules_are_already_importable(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    (repo_root / "apps" / "server").mkdir(parents=True, exist_ok=True)
    (repo_root / "apps" / "mcp-server").mkdir(parents=True, exist_ok=True)

    calls: list[list[str]] = []

    class Completed:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, cwd=None, capture_output=None, text=None, timeout=None, check=None):
        calls.append(list(command))
        if len(command) >= 2 and command[1] == "-c":
            return Completed(returncode=0)
        raise AssertionError("pip install should not run when the dependency probe succeeds")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.ensure_python_packages(repo_root, sys.executable, dry_run=False, skip=False)

    assert [item["status"] for item in payload] == ["already_satisfied", "already_satisfied"]
    assert len(calls) == 2
    assert all(command[1] == "-c" for command in calls)


def test_run_management_workflow_uninstall_cleans_bundle_and_config(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"
    (codex_home / "plugins" / "mission-control").mkdir(parents=True, exist_ok=True)
    (codex_home / "plugins" / "cache" / "local" / "mission-control" / "1.2.0").mkdir(parents=True, exist_ok=True)
    (codex_home / "skills" / "mission-control-status").mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").parent.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(module.build_codex_mcp_block(repo_root, sys.executable), encoding="utf-8")
    (agents_home.parent / "plugins" / "mission-control").mkdir(parents=True, exist_ok=True)
    (agents_home / "plugins").mkdir(parents=True, exist_ok=True)
    (agents_home / "plugins" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "local",
                "plugins": [
                    {
                        "name": "mission-control",
                        "source": {"source": "local", "path": "./plugins/mission-control"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "run_stop_daemon", lambda repo_root: {"status": "ready", "message": "stopped"})

    payload = module.run_management_workflow(action="uninstall", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["reload_guidance"]["required"] is False
    assert payload["stop_daemon"]["status"] == "ready"
    assert payload["uninstall"]["plugin_removed"] is True
    assert payload["uninstall"]["plugin_cache_removed"] is True
    assert payload["uninstall"]["removed_skill_count"] == 1
    assert payload["marketplace_cleanup"]["plugin_removed"] is True
    assert payload["marketplace_cleanup"]["marketplace_changed"] is True
    assert '[mcp_servers."mission-control"]' not in (codex_home / "config.toml").read_text(encoding="utf-8")
    assert not (codex_home / "plugins" / "cache" / "local" / "mission-control").exists()


def test_run_management_workflow_install_reports_reload_requirement(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "ensure_python_packages", lambda *args, **kwargs: [{"name": "backend", "status": "skipped"}])
    monkeypatch.setattr(module, "sync_local_plugin_marketplace", lambda *args, **kwargs: {"status": "ready", "plugin_id": "mission-control@local"})
    monkeypatch.setattr(module, "sync_codex_bundle", lambda *args, **kwargs: {"status": "ready", "plugin_source": "plugin", "plugin_destination": "dest"})
    monkeypatch.setattr(module, "upsert_codex_config", lambda *args, **kwargs: {"status": "updated", "changed": True})
    monkeypatch.setattr(
        module,
        "run_bootstrap",
        lambda *args, **kwargs: {
            "status": "ready",
            "install_report": {
                "active_repo_root": str(repo_root),
                "configured_runners": ["Dry-run", "Ollama"],
                "unavailable_runners": [],
                "user_actions_required": [],
                "readiness_matrix": [
                    {"label": "Backend daemon reachable", "state": "ready", "summary": "Daemon answered locally."},
                    {"label": "MCP bridge callable", "state": "degraded", "summary": "Codex reload still required."},
                ],
            },
        },
    )
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})

    payload = module.run_management_workflow(action="install", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["reload_guidance"]["required"] is True
    assert payload["reload_guidance"]["codex"] is True
    assert payload["reload_guidance"]["claude"] is True
    assert "Force-quit and reopen Codex and Claude Code" in payload["codex_chat_markdown"]
    assert "Codex should show `Mission Control` as an available plugin" in payload["codex_chat_markdown"]


def test_run_management_workflow_install_degrades_when_sync_or_asset_steps_degrade(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "ensure_python_packages", lambda *args, **kwargs: [{"name": "backend", "status": "skipped"}])
    monkeypatch.setattr(module, "sync_local_plugin_marketplace", lambda *args, **kwargs: {"status": "degraded", "plugin_id": "mission-control@local"})
    monkeypatch.setattr(module, "sync_codex_bundle", lambda *args, **kwargs: {"status": "degraded", "plugin_source": "plugin", "plugin_destination": "dest"})
    monkeypatch.setattr(module, "upsert_codex_config", lambda *args, **kwargs: {"status": "ready", "changed": True})
    monkeypatch.setattr(
        module,
        "run_bootstrap",
        lambda *args, **kwargs: {
            "status": "ready",
            "install_report": {
                "active_repo_root": str(repo_root),
                "configured_runners": ["Dry-run"],
                "unavailable_runners": [],
                "user_actions_required": [],
                "readiness_matrix": [
                    {"label": "Backend daemon reachable", "state": "ready", "summary": "Daemon answered locally."},
                ],
            },
        },
    )
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "degraded", "missing": ["mission-control-update"], "slash_commands": []})

    payload = module.run_management_workflow(action="install", dry_run=False)

    assert payload["bootstrap"]["status"] == "ready"
    assert payload["marketplace_sync"]["status"] == "degraded"
    assert payload["codex_sync"]["status"] == "degraded"
    assert payload["claude_assets"]["status"] == "degraded"
    assert payload["status"] == "degraded"
    assert "Open the Codex plugin picker" in payload["codex_chat_markdown"]
    assert "approve the project MCP server from `.mcp.json`" in payload["codex_chat_markdown"]
    assert "rerun `python scripts/mission-control-manage.py update`" in payload["codex_chat_markdown"]
    assert "Backend daemon reachable: ready - Daemon answered locally." in payload["codex_chat_markdown"]


def test_run_management_workflow_uninstall_mentions_reopen_for_stale_state(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "run_stop_daemon", lambda repo_root: {"status": "ready", "message": "stopped"})
    monkeypatch.setattr(module, "uninstall_codex_bundle", lambda *args, **kwargs: {"plugin_removed": True, "removed_skill_count": 2, "config": {"status": "removed"}, "status": "ready"})
    monkeypatch.setattr(module, "remove_local_plugin_marketplace", lambda *args, **kwargs: {"status": "ready", "plugin_removed": True, "marketplace_changed": True})
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})

    payload = module.run_management_workflow(action="uninstall", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["reload_guidance"]["required"] is False
    assert "stale cached plugin or MCP state" in payload["codex_chat_markdown"]
    assert "force-quit and reopen the app" in payload["codex_chat_markdown"]


def test_run_management_workflow_codex_smoke_reports_runtime_limit(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})
    monkeypatch.setattr(module, "run_bootstrap", lambda *args, **kwargs: {"status": "ready"})
    monkeypatch.setattr(
        module,
        "_probe_backend_health",
        lambda repo_root: {
            "status": "ready",
            "reachable": True,
            "summary": "Mission Control daemon health endpoint returned HTTP 200.",
            "url": "http://127.0.0.1:8010/api/health",
        },
    )
    monkeypatch.setattr(
        module,
        "_probe_mission_control_mcp_stdio",
        lambda codex_status: {
            "status": "degraded",
            "summary": "Mission Control MCP stdio handshake did not return a callable tool surface.",
            "callable": False,
        },
    )
    monkeypatch.setattr(
        module,
        "_load_server_module",
        lambda repo_root, module_name: type(
            "FakeSystemStatus",
            (),
            {
                "detect_codex_status": staticmethod(
                    lambda: {
                        "cli_detected": True,
                        "cli_path": "C:/tools/codex.exe",
                        "cli_execution_available": False,
                        "authenticated": False,
                        "login_status": "CLI path found, but login status could not be queried from this runtime.",
                        "mcp_state": {
                            "mission_control": {
                                "configured": True,
                                "app_loaded": None,
                            }
                        },
                    }
                )
            },
        )(),
    )

    payload = module.run_management_workflow(action="codex-smoke", dry_run=False)

    assert payload["status"] == "degraded"
    assert payload["smoke_runnable"] is False
    assert "codex-smoke --json" in payload["recommended_command"]
    assert payload["mcp_stdio_probe"]["callable"] is False
    assert "Codex CLI execution available: degraded" in payload["codex_chat_markdown"]
    assert "current runtime cannot execute it directly" in payload["codex_chat_markdown"]


def test_run_management_workflow_codex_smoke_reports_ready_state(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})
    monkeypatch.setattr(module, "run_bootstrap", lambda *args, **kwargs: {"status": "ready"})
    monkeypatch.setattr(
        module,
        "_probe_backend_health",
        lambda repo_root: {
            "status": "ready",
            "reachable": True,
            "summary": "Mission Control daemon health endpoint returned HTTP 200.",
            "url": "http://127.0.0.1:8010/api/health",
        },
    )
    monkeypatch.setattr(
        module,
        "_probe_mission_control_mcp_stdio",
        lambda codex_status: {
            "status": "ready",
            "summary": "Mission Control MCP stdio handshake succeeded with 3 tools, 2 resource templates, and 1 prompt.",
            "callable": True,
            "tool_count": 3,
            "resource_template_count": 2,
            "prompt_count": 1,
        },
    )
    monkeypatch.setattr(
        module,
        "_load_server_module",
        lambda repo_root, module_name: type(
            "FakeSystemStatus",
            (),
            {
                "detect_codex_status": staticmethod(
                    lambda: {
                        "cli_detected": True,
                        "cli_path": "C:/tools/codex.exe",
                        "cli_execution_available": True,
                        "authenticated": True,
                        "login_status": "Logged in via ChatGPT.",
                        "mcp_state": {
                            "mission_control": {
                                "configured": True,
                                "app_loaded": True,
                            }
                        },
                    }
                )
            },
        )(),
    )

    payload = module.run_management_workflow(action="codex-smoke", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["smoke_runnable"] is True
    assert payload["codex_status"]["mcp_state"]["mission_control"]["callable"] is True
    assert "Mission Control was discovered in the live Codex MCP server list." in payload["codex_chat_markdown"]
    assert "What this proves" in payload["codex_chat_markdown"]


def test_run_management_workflow_codex_smoke_can_waive_auth_for_isolated_validation(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})
    monkeypatch.setattr(module, "run_bootstrap", lambda *args, **kwargs: {"status": "ready"})
    monkeypatch.setattr(
        module,
        "_probe_backend_health",
        lambda repo_root: {
            "status": "ready",
            "reachable": True,
            "summary": "Mission Control daemon health endpoint returned HTTP 200.",
            "url": "http://127.0.0.1:8010/api/health",
        },
    )
    monkeypatch.setattr(
        module,
        "_probe_mission_control_mcp_stdio",
        lambda codex_status: {
            "status": "ready",
            "summary": "Mission Control MCP stdio handshake succeeded with 3 tools, 2 resource templates, and 1 prompt.",
            "callable": True,
            "tool_count": 3,
            "resource_template_count": 2,
            "prompt_count": 1,
        },
    )
    monkeypatch.setattr(
        module,
        "_load_server_module",
        lambda repo_root, module_name: type(
            "FakeSystemStatus",
            (),
            {
                "detect_codex_status": staticmethod(
                    lambda: {
                        "cli_detected": True,
                        "cli_path": "C:/tools/codex.exe",
                        "cli_execution_available": True,
                        "authenticated": False,
                        "login_status": "Not logged in",
                        "mcp_state": {
                            "mission_control": {
                                "configured": True,
                                "app_loaded": True,
                            }
                        },
                    }
                )
            },
        )(),
    )

    payload = module.run_management_workflow(
        action="codex-smoke",
        dry_run=False,
        allow_unauthenticated=True,
    )

    assert payload["status"] == "ready"
    assert payload["smoke_runnable"] is True
    assert payload["require_authenticated"] is False
    assert payload["smoke_reasons"] == []
    assert "Authentication required: no" in payload["codex_chat_markdown"]


def test_run_management_workflow_codex_smoke_stays_ready_when_bootstrap_is_only_degraded(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "detect_claude_assets", lambda repo_root: {"status": "ready", "missing": [], "slash_commands": []})
    monkeypatch.setattr(module, "run_bootstrap", lambda *args, **kwargs: {"status": "degraded"})
    monkeypatch.setattr(
        module,
        "_probe_backend_health",
        lambda repo_root: {
            "status": "ready",
            "reachable": True,
            "summary": "Mission Control daemon health endpoint returned HTTP 200.",
            "url": "http://127.0.0.1:8010/api/health",
        },
    )
    monkeypatch.setattr(
        module,
        "_probe_mission_control_mcp_stdio",
        lambda codex_status: {
            "status": "ready",
            "summary": "Mission Control MCP stdio handshake succeeded with 3 tools, 2 resource templates, and 1 prompt.",
            "callable": True,
            "tool_count": 3,
            "resource_template_count": 2,
            "prompt_count": 1,
        },
    )
    monkeypatch.setattr(
        module,
        "_load_server_module",
        lambda repo_root, module_name: type(
            "FakeSystemStatus",
            (),
            {
                "detect_codex_status": staticmethod(
                    lambda: {
                        "cli_detected": True,
                        "cli_path": "C:/tools/codex.exe",
                        "cli_execution_available": True,
                        "authenticated": True,
                        "login_status": "Logged in via ChatGPT.",
                        "mcp_state": {
                            "mission_control": {
                                "configured": True,
                                "app_loaded": True,
                            }
                        },
                    }
                )
            },
        )(),
    )

    payload = module.run_management_workflow(action="codex-smoke", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["smoke_runnable"] is True
    assert payload["bootstrap"]["status"] == "degraded"


def test_run_management_workflow_orchestration_watch_saves_snapshot_and_reports_updates(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "_controller_binding", lambda repo_root: {"base_url": "http://127.0.0.1:8010", "token": "token"})

    current = {"round": 1}

    def fake_http_json(method, url, *, payload=None, headers=None, timeout=20.0):
        if "/status-summary" in url:
            return {"fallback_markdown": f"status summary round {current['round']}"}
        if "/handoff-summary" in url:
            return {
                "fallback_markdown": f"handoff summary round {current['round']}",
                "machine_payload_json": {"status": "not_ready" if current["round"] == 1 else "ready"},
            }
        if "/pending-decisions" in url:
            return [] if current["round"] == 1 else [{"id": 77, "decision_type": "command_approval"}]
        if "/events?" in url:
            if current["round"] == 1:
                return [{"id": 10, "event_type": "background_turn_started", "payload_json": {"reason": "resume"}}]
            return [
                {"id": 10, "event_type": "background_turn_started", "payload_json": {"reason": "resume"}},
                {"id": 11, "event_type": "background_turn_completed", "payload_json": {"reason": "resume", "status": "running"}},
            ]
        if "/event-digest" in url:
            return {"fallback_markdown": f"event digest round {current['round']}"}
        if "/status" in url:
            if current["round"] == 1:
                return {
                    "project_name": "Loop Improvements Shadow Repo",
                    "orchestration_status": "planning",
                    "manager_status": "Mission Control queued work.",
                    "active_agents": [],
                }
            return {
                "project_name": "Loop Improvements Shadow Repo",
                "orchestration_status": "running",
                "manager_status": "Mission Control is continuing in the background.",
                "active_agents": [{"id": 8, "name": "Service Flow Builder", "status": "working", "runner_type": "codex_cli"}],
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    first = module.run_management_workflow(
        action="orchestration-watch",
        project_id=5,
        orchestration_id=9,
        dry_run=False,
    )

    assert first["status"] == "ready"
    assert first["updates"] == ["No previous snapshot existed. Saved the first baseline for future update checks."]
    assert Path(first["snapshot_path"]).exists()

    current["round"] = 2
    second = module.run_management_workflow(
        action="orchestration-watch",
        project_id=5,
        orchestration_id=9,
        dry_run=False,
    )

    assert second["status"] == "ready"
    assert any("Orchestration status changed" in item for item in second["updates"])
    assert any("Pending decisions changed" in item for item in second["updates"])
    assert any("Active agent roster changed" in item for item in second["updates"])
    assert any("new orchestration event" in item for item in second["updates"])
    assert "orchestration-watch --project-id 5 --orchestration-id 9" in second["recommended_command"]


def test_run_management_workflow_orchestration_watch_can_resolve_workspace(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"
    workspace = tmp_path / "shadow-repo"
    workspace.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "_controller_binding", lambda repo_root: {"base_url": "http://127.0.0.1:8010", "token": "token"})

    def fake_http_json(method, url, *, payload=None, headers=None, timeout=20.0):
        if url.endswith("/api/mission-control/resume-workspace"):
            return {
                "project": {"id": 5, "name": "Loop Improvements Shadow Repo"},
                "orchestration": {"id": 12},
            }
        if "/status-summary" in url:
            return {"fallback_markdown": "status summary"}
        if "/handoff-summary" in url:
            return {"fallback_markdown": "handoff summary", "machine_payload_json": {"status": "not_ready"}}
        if "/pending-decisions" in url:
            return []
        if "/events?" in url:
            return []
        if "/event-digest" in url:
            return {"fallback_markdown": "event digest"}
        if "/status" in url:
            return {
                "project_name": "Loop Improvements Shadow Repo",
                "orchestration_status": "planning",
                "manager_status": "Queued.",
                "active_agents": [],
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    payload = module.run_management_workflow(
        action="orchestration-watch",
        workspace_path=str(workspace),
        dry_run=False,
        save_state=False,
    )

    assert payload["status"] == "ready"
    assert payload["project_id"] == 5
    assert payload["orchestration_id"] == 12
    assert payload["resume_lookup"]["project"]["id"] == 5


def test_run_management_workflow_orchestration_display_builds_live_frame(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "_controller_binding", lambda repo_root: {"base_url": "http://127.0.0.1:8010", "token": "token"})
    monkeypatch.setattr(module, "_display_terminal_width", lambda: 100)

    def fake_http_json(method, url, *, payload=None, headers=None, timeout=20.0):
        if "/status-summary" in url:
            return {
                "fallback_markdown": "status summary",
                "machine_payload_json": {
                    "current_work": [
                        "Task 61 is now the next active step.",
                        "Task 63 closed the trust gap around task 60.",
                    ],
                    "next_expected_step": "Route the next safe background step.",
                    "current_blockers": [],
                },
            }
        if "/handoff-summary" in url:
            return {"fallback_markdown": "handoff summary", "machine_payload_json": {"status": "not_ready"}}
        if "/pending-decisions" in url:
            return [{"id": 77, "decision_type": "command_approval"}]
        if "/events?" in url:
            return [
                {"id": 10, "event_type": "background_turn_started", "payload_json": {"reason": "resume"}},
                {"id": 11, "event_type": "background_turn_completed", "payload_json": {"status": "running"}},
            ]
        if "/event-digest" in url:
            return {"fallback_markdown": "event digest"}
        if "/status" in url:
            return {
                "project_name": "Loop Improvements Shadow Repo",
                "orchestration_status": "running",
                "manager_status": "Mission Control is continuing in the background.",
                "manager": {
                    "id": 1,
                    "name": "Mission Control Manager",
                    "status": "running",
                    "runner_type": "codex_cli",
                    "active_model": "gpt-5-codex",
                    "current_action": "Reviewing the worker reports and routing the next step.",
                },
                "active_agents": [
                    {
                        "id": 8,
                        "name": "Service Flow Builder",
                        "status": "working",
                        "runner_type": "codex_cli",
                        "active_model": "gpt-5-codex",
                        "current_action": "Fix daemon listener stability under load.",
                    }
                ],
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    payload = module.run_management_workflow(
        action="orchestration-display",
        project_id=5,
        orchestration_id=9,
        dry_run=False,
        save_state=False,
        display_ansi=False,
    )

    assert payload["status"] == "ready"
    assert "MISSION CONTROL LIVE" in payload["display_frame"]
    assert "MISSION CONTROL" in payload["display_frame"]
    assert "Manager: Mission Control Manager" in payload["display_frame"]
    assert "Runner: codex_cli | Model: gpt-5-codex | Status: running" in payload["display_frame"]
    assert "Agent: Service Flow Builder" in payload["display_frame"]
    assert "Runner: codex_cli | Model: gpt-5-codex | Status: working" in payload["display_frame"]
    assert "Task 63 closed the trust gap around task 60." in payload["display_frame"]
    assert payload["display_command"].startswith("python scripts/mission-control-manage.py orchestration-display")
    assert "Launch command" in payload["codex_chat_markdown"]


def test_main_orchestration_display_once_prints_frame(monkeypatch, tmp_path, capsys) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(module, "_controller_binding", lambda repo_root: {"base_url": "http://127.0.0.1:8010", "token": "token"})
    monkeypatch.setattr(module, "_display_terminal_width", lambda: 96)

    def fake_http_json(method, url, *, payload=None, headers=None, timeout=20.0):
        if "/status-summary" in url:
            return {"fallback_markdown": "status summary", "machine_payload_json": {"current_work": ["Routing the next step."], "next_expected_step": "Continue the run."}}
        if "/handoff-summary" in url:
            return {"fallback_markdown": "handoff summary", "machine_payload_json": {"status": "not_ready"}}
        if "/pending-decisions" in url:
            return []
        if "/events?" in url:
            return []
        if "/event-digest" in url:
            return {"fallback_markdown": "event digest"}
        if "/status" in url:
            return {
                "project_name": "Loop Improvements Shadow Repo",
                "orchestration_status": "planning",
                "manager_status": "Mission Control queued work.",
                "manager": {
                    "id": 1,
                    "name": "Mission Control Manager",
                    "status": "running",
                    "runner_type": "codex_cli",
                    "active_model": "gpt-5-codex",
                },
                "active_agents": [],
            }
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(module, "_http_json", fake_http_json)

    assert module.main(["orchestration-display", "--project-id", "5", "--orchestration-id", "9", "--once", "--no-ansi"]) == 0
    output = capsys.readouterr().out
    assert "MISSION CONTROL LIVE" in output
    assert "MISSION CONTROL" in output
    assert "Press Ctrl+C to stop the live display." in output


def test_parse_args_orchestration_display_defaults_to_one_second_refresh() -> None:
    module = _load_manage_module()
    args = module.parse_args(["orchestration-display", "--project-id", "5", "--orchestration-id", "9"])
    assert args.refresh_seconds == 1.0


def test_orchestration_display_status_colors_cover_working_waiting_and_stopped() -> None:
    module = _load_manage_module()

    assert module._status_color("working") == "1;32"
    assert module._status_color("idle") == "1;33"
    assert module._status_color("waiting") == "1;33"
    assert module._status_color("stopped") == "1;31"
    assert module._status_color("stuck") == "1;31"


def test_run_management_workflow_codex_restart_smoke_reports_detached_job(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(
        module,
        "launch_codex_restart_smoke",
        lambda repo_root, python_command, launch_wait_seconds=25: {
            "status": "launched",
            "launcher_pid": 4242,
            "results_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.json"),
            "log_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.log"),
            "launch_wait_seconds": launch_wait_seconds,
            "recommended_resume_minutes": 3,
        },
    )

    payload = module.run_management_workflow(action="codex-restart-smoke", dry_run=False, launch_wait_seconds=30)

    assert payload["status"] == "ready"
    assert payload["restart_smoke"]["launcher_pid"] == 4242
    assert payload["reload_guidance"]["codex"] is True
    assert "Codex will be force-quit." in payload["codex_chat_markdown"]
    assert "Suggested resume minutes: 3" in payload["codex_chat_markdown"]


def test_run_management_workflow_codex_restart_smoke_status_reports_last_artifact(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(
        module,
        "load_codex_restart_smoke_status",
        lambda repo_root: {
            "status": "ready",
            "summary": "Restart smoke completed with status ready.",
            "results_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.json"),
            "log_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.log"),
            "artifact": {
                "status": "ready",
                "smoke": {
                    "smoke_checks": [
                        {
                            "label": "Codex CLI execution available",
                            "state": "ready",
                            "summary": "Codex CLI can be executed from this runtime.",
                        }
                    ]
                },
            },
        },
    )

    payload = module.run_management_workflow(action="codex-restart-smoke-status", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["restart_smoke_status"]["status"] == "ready"
    assert "### Restart smoke status" in payload["codex_chat_markdown"]
    assert "Codex CLI execution available: ready" in payload["codex_chat_markdown"]


def test_main_allows_missing_restart_smoke_status(monkeypatch, tmp_path, capsys) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(
        module,
        "load_codex_restart_smoke_status",
        lambda repo_root: {
            "status": "missing",
            "summary": "No restart smoke result artifact exists yet.",
            "results_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.json"),
            "log_path": str(repo_root / ".runtime" / "codex-restart-smoke" / "latest.log"),
        },
    )

    assert module.main(["codex-restart-smoke-status", "--json"]) == 0
    assert "No restart smoke result artifact exists yet." in capsys.readouterr().out


def test_packaged_plugin_manifest_is_ready_for_codex_sync() -> None:
    plugin_root = ROOT / "plugins" / "mission-control"
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "mission-control"
    assert manifest["interface"]["displayName"] == "Mission Control"
    assert "approvals" in manifest["interface"]["shortDescription"].lower()
    assert "manager" in manifest["interface"]["longDescription"].lower()
    assert "diagnose the failing tests" in " ".join(manifest["interface"]["defaultPrompt"]).lower()
    assert manifest["version"]
    assert (plugin_root / "assets" / "mission-control-logo.png").exists()
    assert manifest["skills"] == "./skills/"

    catalog_manifest = json.loads((ROOT / "plugins" / "mission-control" / "plugin.json").read_text(encoding="utf-8"))
    assert catalog_manifest["manifest_format"] == "codex-plugin-v1"

    for skill_name in ("mission-control-install-from-github", "mission-control-update", "mission-control-uninstall"):
        assert (plugin_root / "skills" / skill_name / "SKILL.md").exists()


def test_build_recursive_improvement_profile_uses_isolated_repo_and_port(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        module,
        "_controller_binding",
        lambda repo_root: {
            "host": "127.0.0.1",
            "port": 8010,
            "mode": "daemon",
            "base_url": "http://127.0.0.1:8010",
            "token": "controller-token",
        },
    )
    monkeypatch.setattr(module, "_port_in_use", lambda host, port: port == 8100)

    profile = module.build_recursive_improvement_profile(repo_root, shadow_name="Loop Improvements", backend_port=8100)

    assert profile["shadow_name"] == "loop-improvements"
    assert profile["target_repo_root"].endswith("repo")
    assert profile["target_backend_port"] == 8101
    assert profile["controller_port"] == 8010
    module.validate_recursive_improvement_profile(profile)


def test_prepare_recursive_improvement_shadow_writes_launcher_config(tmp_path, monkeypatch) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "README.md").write_text("# Mission Control\n", encoding="utf-8")
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo_root / "apps" / "server" / "src").mkdir(parents=True, exist_ok=True)
    (repo_root / "apps" / "server" / "src" / "main.py").write_text("pass\n", encoding="utf-8")
    source_codex_home = tmp_path / ".codex-source"
    source_codex_home.mkdir(parents=True, exist_ok=True)
    (source_codex_home / "auth.json").write_text('{"tokens":{"access_token":"redacted"}}', encoding="utf-8")
    (source_codex_home / ".credentials.json").write_text('{"connector":"redacted"}', encoding="utf-8")
    (source_codex_home / "installation_id").write_text("install-id", encoding="utf-8")

    monkeypatch.setattr(
        module,
        "_controller_binding",
        lambda repo_root: {
            "host": "127.0.0.1",
            "port": 8010,
            "mode": "daemon",
            "base_url": "http://127.0.0.1:8010",
            "token": "controller-token",
        },
    )
    monkeypatch.setattr(module, "_port_in_use", lambda host, port: False)
    monkeypatch.setattr(
        module,
        "_ensure_shadow_git_repository",
        lambda *args, **kwargs: {"status": "ready", "git_dir": str(tmp_path / ".git"), "initialized": True},
    )
    profile = module.build_recursive_improvement_profile(repo_root, shadow_name="recursive-shadow")

    payload = module.prepare_recursive_improvement_shadow(
        repo_root,
        profile,
        dry_run=False,
        recreate=False,
        source_codex_home=source_codex_home,
    )

    assert payload["status"] == "ready"
    assert Path(payload["target_repo_root"]).exists()
    assert (Path(payload["target_repo_root"]) / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    launcher_config = json.loads(Path(payload["launcher_config_path"]).read_text(encoding="utf-8"))
    assert launcher_config["backendPort"] == profile["target_backend_port"]
    assert launcher_config["launcherLogDir"] == profile["target_launcher_dir"]
    assert Path(payload["profile_path"]).exists()
    assert payload["auth_mirror"]["copied_files"] == ["auth.json", ".credentials.json", "installation_id"]
    assert (Path(profile["target_codex_home"]) / "auth.json").exists()
    assert payload["git_repository"]["status"] == "ready"


def test_ensure_shadow_git_repository_initializes_standalone_repo(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    source_repo = tmp_path / "source"
    target_repo = tmp_path / "target"
    source_repo.mkdir(parents=True, exist_ok=True)
    target_repo.mkdir(parents=True, exist_ok=True)
    (source_repo / ".git").mkdir(parents=True, exist_ok=True)
    (source_repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    commands: list[list[str]] = []

    class Completed:
        def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(command, cwd=None, env=None, capture_output=None, text=None, timeout=None, check=None):
        commands.append(list(command))
        (Path(cwd) / ".git").mkdir(parents=True, exist_ok=True)
        return Completed(returncode=0, stdout="Initialized empty Git repository")

    monkeypatch.setattr(module.shutil, "which", lambda name: "C:/Program Files/Git/cmd/git.exe" if name in {"git", "git.exe"} else None)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module._ensure_shadow_git_repository(source_repo, target_repo, dry_run=False)

    assert payload["status"] == "ready"
    assert payload["initialized"] is True
    assert commands == [["C:/Program Files/Git/cmd/git.exe", "init", "-b", "main"]]
    assert (target_repo / ".git").exists()


def test_run_recursive_improvement_workflow_uses_real_codex_mode_for_shadow(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    shadow_root = repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow"
    target_repo = shadow_root / "repo"
    target_runtime = shadow_root / "runtime"
    target_runtime.mkdir(parents=True, exist_ok=True)
    (target_runtime / "daemon.token").write_text("shadow-token", encoding="utf-8")
    profile = {
        "shadow_name": "recursive-shadow",
        "shadow_root": str(shadow_root),
        "target_repo_root": str(target_repo),
        "target_runtime_root": str(target_runtime),
        "target_backend_host": "127.0.0.1",
        "target_backend_port": 8110,
        "target_transcript_path": str(shadow_root / "target-transcript.md"),
        "controller_transcript_path": str(shadow_root / "controller-transcript.md"),
        "target_install_report_path": str(shadow_root / "target-install.json"),
        "target_smoke_report_path": str(shadow_root / "target-smoke.json"),
        "controller_report_path": str(shadow_root / "controller-run.json"),
        "controller_identity_path": str(shadow_root / "controller-identity.json"),
        "target_identity_path": str(shadow_root / "target-identity.json"),
        "controller_repo_root": str(repo_root),
        "controller_port": 8010,
        "target_launcher_dir": str(shadow_root / "launcher"),
        "target_launcher_config": str(shadow_root / "shadow.config.json"),
        "target_codex_home": str(shadow_root / "codex-home"),
        "target_agents_home": str(shadow_root / "agents-home"),
        "target_app_home": str(shadow_root / "app-home"),
        "profile_path": str(shadow_root / "profile.json"),
        "created_at": "2026-06-09T00:00:00+00:00",
    }
    captured_modes: list[tuple[str, str]] = []

    monkeypatch.setattr(module, "build_recursive_improvement_profile", lambda *args, **kwargs: profile)
    monkeypatch.setattr(
        module,
        "prepare_recursive_improvement_shadow",
        lambda *args, **kwargs: {"status": "ready", "target_repo_root": str(target_repo), "auth_mirror": {"status": "ready"}},
    )
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: tmp_path / ".codex")
    monkeypatch.setattr(
        module,
        "_invoke_shadow_manage_action",
        lambda profile, python_command, action, skip_python_setup=True, extra_args=None: (
            {"status": "ready"}
            if action == "install"
            else {
                "status": "ready",
                "smoke_runnable": True,
                "codex_status": {"authenticated": True},
            }
        ),
    )
    monkeypatch.setattr(
        module,
        "_controller_binding",
        lambda repo_root: {"base_url": "http://127.0.0.1:8010", "token": "controller-token", "host": "127.0.0.1", "port": 8010, "mode": "daemon"},
    )
    monkeypatch.setattr(
        module,
        "_daemon_identity_snapshot",
        lambda base_url, token: {
            "repo_root": str(target_repo) if "8110" in base_url else str(repo_root),
            "port": 8110 if "8110" in base_url else 8010,
        },
    )
    monkeypatch.setattr(module, "_write_artifact", lambda path, payload: None)

    def fake_run_headless_happy_path(*, base_url, token, workspace_path, task_request, transcript_path, project_name, mode="dry_run"):
        captured_modes.append((project_name, mode))
        return {"status": "ready", "transcript_path": transcript_path, "mode_used": mode}

    monkeypatch.setattr(module, "_run_headless_happy_path", fake_run_headless_happy_path)

    payload = module.run_recursive_improvement_workflow(
        repo_root=repo_root,
        python_command=sys.executable,
        shadow_name="recursive-shadow",
        backend_port=8110,
        skip_python_setup=True,
        recreate_shadow=False,
        controller_mode="auto",
        controller_task_request=None,
    )

    assert payload["status"] == "ready"
    assert captured_modes[0][1] == "codex_cli"
    assert captured_modes[1][1] == "auto"


def test_run_headless_happy_path_marks_real_codex_downgrade_as_degraded(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    transcript_path = tmp_path / "transcript.md"
    responses: list[dict | list | None] = [
        {
            "project": {"id": 7},
            "attach_outcome": "imported_existing_codebase",
            "source_type": "existing_folder",
            "project_name": "shadow-project",
        },
        {
            "next_route": "/projects/7",
            "questions": [],
            "manager_note": "Skip the interview for the imported repo.",
        },
        {
            "project_id": 7,
            "write_permission_status": "write_allowed",
        },
        {
            "project_id": 7,
            "provider": "codex",
            "runner_mode": "cli",
            "sandbox_mode": "workspace-write",
            "approval_policy": "on-request",
        },
        {
            "orchestration": {
                "id": 11,
                "mode": "dry_run",
                "metadata_json": {"simulated": True},
            },
            "status_summary": {"fallback_markdown": "Dry-run orchestration is waiting for a user decision before it can continue."},
            "pending_decisions": [],
            "mode_used": "dry_run",
        },
        {"id": 11, "status": "completed"},
        {"fallback_markdown": "Dry-run orchestration completed with a simulated handoff."},
        [],
        {"fallback_markdown": "Dry run validation simulated."},
        {"fallback_markdown": "This summary is based on simulated execution and recorded dry-run evidence only.", "message_type": "blocked"},
        [],
    ]

    def fake_http_json(method: str, url: str, **kwargs):
        assert responses, f"Unexpected call: {method} {url}"
        return responses.pop(0)

    monkeypatch.setattr(module, "_http_json", fake_http_json)
    monkeypatch.setattr(module, "_write_artifact", lambda path, payload: None)

    payload = module._run_headless_happy_path(
        base_url="http://127.0.0.1:8112",
        token="shadow-token",
        workspace_path=str(tmp_path),
        task_request="Use real Codex agents only.",
        transcript_path=str(transcript_path),
        project_name="shadow-project",
        mode="codex_cli",
    )

    assert payload["status"] == "degraded"
    assert payload["resolved_mode"] == "dry_run"
    assert payload["simulated"] is True
    assert payload["real_runner_verified"] is False
    assert "expected mission control to use codex_cli" in str(payload["real_runner_failure_reason"]).lower()


def test_run_management_workflow_recursive_improvement_reports_isolated_case_study(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"

    monkeypatch.setattr(module, "resolve_repo_root", lambda **kwargs: repo_root)
    monkeypatch.setattr(module, "resolve_codex_home", lambda override=None: codex_home)
    monkeypatch.setattr(module, "resolve_agents_home", lambda override=None: agents_home)
    monkeypatch.setattr(module, "resolve_python_command", lambda explicit=None: sys.executable)
    monkeypatch.setattr(
        module,
        "run_recursive_improvement_workflow",
        lambda **kwargs: {
            "status": "ready",
            "shadow_profile": {
                "shadow_name": "recursive-shadow",
                "target_repo_root": str(repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow" / "repo"),
                "target_runtime_root": str(repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow" / "runtime"),
                "target_backend_port": 8110,
            },
            "shadow_install": {"status": "ready"},
            "shadow_smoke": {"status": "ready"},
            "controller_identity": {"repo_root": str(repo_root), "port": 8010},
            "target_identity": {"repo_root": str(repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow" / "repo"), "port": 8110},
            "target_happy_path": {"transcript_path": str(repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow" / "target-transcript.md")},
            "controller_happy_path": {"transcript_path": str(repo_root / ".runtime" / "recursive-improvement" / "recursive-shadow" / "controller-transcript.md")},
            "collision_guard": {"isolated": True},
        },
    )

    payload = module.run_management_workflow(action="recursive-improvement", dry_run=False)

    assert payload["status"] == "ready"
    assert payload["reload_guidance"]["required"] is False
    assert "Recursive improvement" in payload["codex_chat_markdown"]
    assert "recursive improvement" in payload["codex_chat_markdown"].lower()
    assert "Shadow port: 8110" in payload["codex_chat_markdown"]
