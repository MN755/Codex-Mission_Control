from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_bootstrap_module():
    module_path = ROOT / "scripts" / "mission-control-bootstrap.py"
    spec = importlib.util.spec_from_file_location("mission_control_bootstrap_script", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("mission_control_bootstrap_script", module)
    spec.loader.exec_module(module)
    return module


def test_mcp_check_uses_daemon_client_and_server_client_arg(monkeypatch, tmp_path) -> None:
    module = _load_bootstrap_module()
    repo_root = tmp_path / "repo"
    (repo_root / "plugins" / "mission-control" / "mcp").mkdir(parents=True, exist_ok=True)
    (repo_root / "plugins" / "mission-control" / "plugin.json").write_text("{}", encoding="utf-8")
    (repo_root / "plugins" / "mission-control" / "mcp" / "mission-control-mcp.example.json").write_text("{}", encoding="utf-8")
    (repo_root / ".codex" / "plugins" / "mission-control").mkdir(parents=True, exist_ok=True)
    (repo_root / ".codex" / "plugins" / "mission-control" / "plugin.json").write_text("{}", encoding="utf-8")
    (repo_root / ".codex" / "skills").mkdir(parents=True, exist_ok=True)
    (repo_root / "apps" / "mcp-server" / "src" / "mission_control_mcp_server").mkdir(parents=True, exist_ok=True)
    (repo_root / "apps" / "mcp-server" / "src" / "mission_control_mcp_server" / "__main__.py").write_text("pass", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, base_url: str | None = None) -> None:
            captured["base_url"] = base_url

    class FakeServer:
        def __init__(self, client=None) -> None:
            captured["client"] = client

        def call_tool(self, name: str, arguments: dict | None = None):
            captured["tool_name"] = name
            return {"structuredContent": {"status": "ready"}}

    monkeypatch.setitem(sys.modules, "mission_control_mcp_server.client", type("ClientModule", (), {"MissionControlDaemonClient": FakeClient}))
    monkeypatch.setitem(sys.modules, "mission_control_mcp_server.server", type("ServerModule", (), {"MissionControlMcpServer": FakeServer}))

    payload = module._mcp_check(repo_root, base_url="http://127.0.0.1:8010")

    assert payload["status"] == "ready"
    assert payload["authenticated_tool_call"]["status"] == "ready"
    assert captured["base_url"] == "http://127.0.0.1:8010"
    assert isinstance(captured["client"], FakeClient)
    assert captured["tool_name"] == "mission_control_plugin_health"
