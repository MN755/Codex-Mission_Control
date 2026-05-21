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
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "mission-control", "display_name": "Mission Control"}), encoding="utf-8")
    (plugin_root / "skills" / "mission-control-install-from-github" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / "skills" / "mission-control-install-from-github" / "SKILL.md").write_text("# plugin install", encoding="utf-8")
    (skill_root / "mission-control-install-from-github" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "mission-control-install-from-github" / "SKILL.md").write_text("# install", encoding="utf-8")
    (skill_root / "mission-control-update" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "mission-control-update" / "SKILL.md").write_text("# update", encoding="utf-8")
    (skill_root / "not-mission-control" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_root / "not-mission-control" / "SKILL.md").write_text("# ignore", encoding="utf-8")

    payload = module.sync_codex_bundle(repo_root, codex_home, dry_run=False)

    assert payload["status"] == "ready"
    assert payload["plugin_source"] == str(plugin_root)
    assert payload["plugin_name"] == "mission-control"
    assert payload["plugin_display_name"] == "Mission Control"
    assert (codex_home / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json").exists()
    assert (codex_home / "plugins" / "mission-control" / "skills" / "mission-control-install-from-github" / "SKILL.md").exists()
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
    (plugin_root / "assets" / "icon.svg").parent.mkdir(parents=True, exist_ok=True)
    (plugin_root / "assets" / "icon.svg").write_text("<svg />", encoding="utf-8")

    payload = module.sync_local_plugin_marketplace(repo_root, agents_home, dry_run=False)

    assert payload["status"] == "ready"
    assert payload["plugin_id"] == "mission-control@local"
    assert (agents_home.parent / "plugins" / "mission-control" / ".codex-plugin" / "plugin.json").exists()
    marketplace = json.loads((agents_home / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["name"] == "local"
    assert any(entry["name"] == "mission-control" for entry in marketplace["plugins"])


def test_run_management_workflow_uninstall_cleans_bundle_and_config(monkeypatch, tmp_path) -> None:
    module = _load_manage_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    codex_home = tmp_path / ".codex"
    agents_home = tmp_path / ".agents"
    (codex_home / "plugins" / "mission-control").mkdir(parents=True, exist_ok=True)
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
    assert payload["uninstall"]["removed_skill_count"] == 1
    assert payload["marketplace_cleanup"]["plugin_removed"] is True
    assert payload["marketplace_cleanup"]["marketplace_changed"] is True
    assert '[mcp_servers."mission-control"]' not in (codex_home / "config.toml").read_text(encoding="utf-8")


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
                "configured_runners": ["Dry-run", "Ollama"],
                "unavailable_runners": [],
                "user_actions_required": [],
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


def test_packaged_plugin_manifest_is_ready_for_codex_sync() -> None:
    plugin_root = ROOT / "plugins" / "mission-control"
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "mission-control"
    assert manifest["interface"]["displayName"] == "Mission Control"
    assert manifest["version"]
    assert (plugin_root / "assets" / "icon.svg").exists()
    assert manifest["skills"] == "./skills/"

    for skill_name in ("mission-control-install-from-github", "mission-control-update", "mission-control-uninstall"):
        assert (plugin_root / "skills" / skill_name / "SKILL.md").exists()
