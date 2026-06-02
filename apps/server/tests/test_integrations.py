from __future__ import annotations

from pathlib import Path

from integration_registry import (
    build_project_integration_status,
    execute_integration_action,
    import_host_state,
    normalize_integration_registry,
    preview_integration_action,
)
from tool_catalog import catalog_with_permissions


def test_tool_catalog_uses_integration_registry_for_github_and_vercel() -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                },
                "hosting_deploy": {
                    "family": "hosting_deploy",
                    "status": "connected",
                    "providers": ["vercel"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                },
            }
        },
        {},
    )

    payload = catalog_with_permissions(
        provider="codex",
        connected_accounts={},
        integration_registry=registry,
        permission_overrides={},
    )
    tools = {item["id"]: item for item in payload}

    assert tools["github-wiki-creator"]["availability"] == "available"
    assert tools["github-deployment-creator"]["availability"] == "available"
    assert tools["deploy-with-vercel"]["availability"] == "available"


def test_project_integrations_and_action_preview_flow(client, bridge_headers, monkeypatch, tmp_path) -> None:
    workspace = str(tmp_path / "integrations-spine")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    Path(workspace, "vercel.json").write_text('{"framework":"nextjs"}\n', encoding="utf-8")
    Path(workspace, "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    Path(workspace, ".github").mkdir(exist_ok=True)
    Path(workspace, ".github", "workflows").mkdir(exist_ok=True)
    Path(workspace, ".github", "workflows", "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"docker", "gh", "vercel", "playwright"} else None,
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "Integration Spine Demo",
            "idea": "Validate cross-host integrations",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    catalog = client.get("/api/integrations/catalog", headers=bridge_headers)
    assert catalog.status_code == 200
    catalog_payload = {item["family"]: item for item in catalog.json()}
    assert "source_control" in catalog_payload
    assert "release_management" in catalog_payload

    project_integrations = client.get(f"/api/projects/{project_id}/integrations", headers=bridge_headers)
    assert project_integrations.status_code == 200
    families = {item["family"]: item for item in project_integrations.json()["families"]}
    assert families["source_control"]["status"] == "ready"
    assert families["containers"]["status"] == "ready"
    assert families["hosting_deploy"]["status"] == "ready"
    assert families["browser_testing"]["status"] == "ready"
    assert families["source_control"]["provider_specific_action_count"] >= 2
    assert families["source_control"]["guided_only_action_count"] == 0

    preview = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/preview",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}},
        headers=bridge_headers,
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["command"] == 'gh issue create --title "Bridge it" --body "Stop lying about status."'
    assert preview_payload["requires_confirmation"] is True
    assert preview_payload["command_ready"] is True
    assert preview_payload["execution_mode"] == "local_cli"
    assert preview_payload["provider"] == "github"
    assert preview_payload["provider_resolution_state"] == "resolved"
    assert preview_payload["provider_support_mode"] == "provider_specific"
    assert preview_payload["supported_providers"] == ["github", "gitlab", "bitbucket"]
    assert preview_payload["supported_provider_count"] == 3
    assert preview_payload["provider_lane_resolved"] is True
    assert preview_payload["provider_context_verified"] is False
    assert preview_payload["provider_context_source"] == "workspace"
    assert preview_payload["provider_context_status"] == "inferred"
    assert preview_payload["provider_verification_required"] is False
    assert preview_payload["provider_verification_reason"] is None
    assert preview_payload["context_required"] is False
    assert preview_payload["context_requirement_reason"] is None
    assert preview_payload["context_available"] is True
    assert preview_payload["suppressed_command_reason"] is None
    assert preview_payload["cli_only_candidates_suppressed"] == []
    assert preview_payload["provider_signal_breakdown"]["github"]["has_non_cli_evidence"] is True
    assert preview_payload["resolved_provider_evidence"]["has_non_cli_evidence"] is True
    assert "GitHub" in preview_payload["provider_guidance"]
    assert preview_payload["provider_guidance"] == preview_payload["notes"][-1]

    execute = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/execute",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}, "confirmed": False},
        headers=bridge_headers,
    )
    assert execute.status_code == 200
    execute_payload = execute.json()
    assert execute_payload["status"] == "approval_required"
    assert execute_payload["provider"] == "github"
    assert execute_payload["provider_resolution_state"] == "resolved"
    assert execute_payload["provider_support_mode"] == "provider_specific"
    assert execute_payload["supported_providers"] == ["github", "gitlab", "bitbucket"]
    assert execute_payload["supported_provider_count"] == 3
    assert execute_payload["provider_lane_resolved"] is True
    assert execute_payload["provider_context_verified"] is False
    assert execute_payload["provider_context_source"] == "workspace"
    assert execute_payload["provider_context_status"] == "inferred"
    assert execute_payload["provider_verification_required"] is False
    assert execute_payload["provider_verification_reason"] is None
    assert execute_payload["context_required"] is False
    assert execute_payload["context_requirement_reason"] is None
    assert execute_payload["context_available"] is True
    assert execute_payload["suppressed_command_reason"] is None
    assert execute_payload["cli_only_candidates_suppressed"] == []
    assert execute_payload["provider_signal_breakdown"]["github"]["has_non_cli_evidence"] is True
    assert execute_payload["resolved_provider_evidence"]["has_non_cli_evidence"] is True
    assert execute_payload["provider_guidance"] == preview_payload["provider_guidance"]


def test_project_integration_api_surfaces_context_suppression_metadata(client, bridge_headers, monkeypatch, tmp_path) -> None:
    workspace = str(tmp_path / "integrations-no-context")
    Path(workspace).mkdir(parents=True, exist_ok=True)
    Path(workspace, "README.md").write_text("# no signals here\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"gh", "vercel", "supabase", "aws", "playwright", "gitleaks", "ollama", "stripe", "npm", "newman", "swagger-cli", "src", "sentry-cli", "chrome"}
        else None,
    )

    project = client.post(
        "/api/projects",
        json={
            "name": "No Context Demo",
            "idea": "Catch CLI-only provider pollution",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    ).json()
    project_id = project["id"]

    project_integrations = client.get(f"/api/projects/{project_id}/integrations", headers=bridge_headers)
    assert project_integrations.status_code == 200
    families = {item["family"]: item for item in project_integrations.json()["families"]}

    payments = families["payments"]
    inspect_action = next(item for item in payments["available_actions"] if item["action_id"] == "inspect")
    assert payments["health"]["provider_resolution_state"] == "suppressed_cli_only"
    assert payments["provider_specific_action_count"] >= 2
    assert payments["guided_only_action_count"] == 0
    assert payments["available_provider_lane_count"] == 0
    assert payments["context_blocked_action_count"] >= 2
    assert payments["verification_blocked_action_count"] == 0
    assert payments["health"]["provider_context_verified"] is False
    assert payments["health"]["provider_context_source"] == "standalone_cli_only"
    assert payments["health"]["provider_context_status"] == "missing"
    assert payments["health"]["connection_provider_count"] == 0
    assert payments["health"]["connection_without_provider_identity"] is False
    assert inspect_action["status"] == "needs_setup"
    assert inspect_action["command_template"] is None
    assert inspect_action["provider_support_mode"] == "provider_specific"
    assert inspect_action["supported_providers"] == ["stripe", "paddle", "lemon_squeezy", "paypal_sandbox"]
    assert inspect_action["supported_provider_count"] == 4
    assert inspect_action["provider_lane_resolved"] is False
    assert inspect_action["provider_context_verified"] is False
    assert inspect_action["provider_context_source"] == "standalone_cli_only"
    assert inspect_action["provider_context_status"] == "missing"
    assert inspect_action["provider_verification_required"] is False
    assert inspect_action["provider_verification_reason"] is None
    assert inspect_action["context_required"] is True
    assert inspect_action["context_requirement_reason"] == "provider_context_missing"
    assert inspect_action["suppressed_command_reason"] == "provider_context_missing"

    preview = client.post(
        f"/api/projects/{project_id}/integrations/payments/actions/inspect/preview",
        json={"params": {}},
        headers=bridge_headers,
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["provider"] is None
    assert preview_payload["command"] is None
    assert preview_payload["command_ready"] is False
    assert preview_payload["execution_mode"] == "unavailable"
    assert preview_payload["provider_resolution_state"] == "suppressed_cli_only"
    assert preview_payload["provider_support_mode"] == "provider_specific"
    assert preview_payload["supported_providers"] == ["stripe", "paddle", "lemon_squeezy", "paypal_sandbox"]
    assert preview_payload["supported_provider_count"] == 4
    assert preview_payload["provider_lane_resolved"] is False
    assert preview_payload["provider_context_verified"] is False
    assert preview_payload["provider_context_source"] == "standalone_cli_only"
    assert preview_payload["provider_context_status"] == "missing"
    assert preview_payload["provider_verification_required"] is False
    assert preview_payload["provider_verification_reason"] is None
    assert preview_payload["context_required"] is True
    assert preview_payload["context_requirement_reason"] == "provider_context_missing"
    assert preview_payload["context_available"] is False
    assert preview_payload["suppressed_command_reason"] == "provider_context_missing"
    assert preview_payload["provider_guidance"] is None
    assert preview_payload["cli_only_candidates_suppressed"] == ["stripe"]
    assert preview_payload["provider_signal_breakdown"]["stripe"]["suppressed_cli_only"] is True
    assert preview_payload["resolved_provider_evidence"] == {}
    assert any("suppressed until Mission Control has real provider context" in note for note in preview_payload["notes"])


def test_import_host_state_endpoint_persists_registry(client, bridge_headers, monkeypatch) -> None:
    monkeypatch.setattr(
        "manager.import_host_state",
        lambda _registry: normalize_integration_registry(
            {
                "connections": {
                    "source_control": {
                        "family": "source_control",
                        "status": "connected",
                        "providers": ["github"],
                        "connection_source": "codex_host",
                        "host_imported": True,
                    }
                },
                "host_imports": {"codex": {"source_control": {"detected": True, "paths": ["C:/Users/mike/.codex/plugins/github"]}}, "claude_code": {}},
            },
            {},
        ),
    )

    imported = client.post("/api/integrations/import-host-state", headers=bridge_headers)
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["status"] == "completed"
    assert payload["connections"][0]["family"] == "source_control"
    assert payload["connections"][0]["host_imported"] is True

    health = client.get("/api/integrations/health", headers=bridge_headers)
    assert health.status_code == 200
    assert health.json()["family_count"] >= 30


def test_import_host_state_preserves_authoritative_connection_state(monkeypatch, tmp_path) -> None:
    host_root = tmp_path / "codex-host"
    plugin_dir = host_root / "plugins" / "github"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text('{"name":"github"}\n', encoding="utf-8")

    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                    "notes": ["Mission Control already verified this lane."],
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry._host_scan_roots",
        lambda: {"codex": [host_root], "claude_code": []},
    )

    imported = import_host_state(registry)
    connection = imported["connections"]["source_control"]

    assert connection["status"] == "connected"
    assert connection["connection_source"] == "mission_control"
    assert connection["host_imported"] is True
    assert connection["providers"] == ["github"]
    assert any("already verified" in note.lower() for note in connection["notes"])
    assert imported["host_imports"]["codex"]["source_control"]["detected"] is True
    assert imported["host_imports"]["codex"]["source_control"]["provider_hints"] == ["github"]


def test_project_integrations_report_partial_when_only_host_or_workspace_signals_exist(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "partial-integration"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "vercel.json").write_text('{"framework":"nextjs"}\n', encoding="utf-8")

    registry = normalize_integration_registry(
        {
            "connections": {
                "hosting_deploy": {
                    "family": "hosting_deploy",
                    "status": "partial",
                    "providers": ["vercel"],
                    "connection_source": "codex_host",
                    "host_imported": True,
                }
            }
        },
        {},
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Partial Demo",
            registry_payload=registry,
        )
    }

    hosting = statuses["hosting_deploy"]
    assert hosting["status"] == "partial"
    assert hosting["resolved_provider"] == "vercel"
    assert hosting["providers"] == ["vercel"]
    assert any("host-imported metadata" in blocker.lower() for blocker in hosting["blockers"])
    assert any("install one of" in fix.lower() for fix in hosting["recommended_fixes"])
    assert hosting["provider_candidates"] == ["vercel"]


def test_project_integrations_treat_connected_linear_lane_as_ready_without_cli(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "work_tracking": {
                    "family": "work_tracking",
                    "status": "connected",
                    "providers": ["linear"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="Linear Ready Demo",
            registry_payload=registry,
        )
    }["work_tracking"]

    assert status["status"] == "ready"
    assert status["resolved_provider"] == "linear"
    assert status["resolved_cli_candidates"] == []
    assert status["guided_action_count"] >= 1
    assert not any("install one of" in item.lower() for item in status["recommended_fixes"])


def test_project_integrations_treat_connected_bitbucket_lane_as_ready_without_cli(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["bitbucket"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="Bitbucket Ready Demo",
            registry_payload=registry,
        )
    }["source_control"]

    assert status["status"] == "ready"
    assert status["resolved_provider"] == "bitbucket"
    assert status["guided_action_count"] >= 1
    assert not any("install one of" in item.lower() for item in status["recommended_fixes"])


def test_project_integrations_treat_connected_notion_lane_as_ready_without_cli(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "docs_systems": {
                    "family": "docs_systems",
                    "status": "connected",
                    "providers": ["notion"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="Notion Ready Demo",
            registry_payload=registry,
        )
    }["docs_systems"]

    assert status["status"] == "ready"
    assert status["resolved_provider"] == "notion"
    assert status["guided_action_count"] >= 1
    assert status["resolved_cli_candidates"] == []
    assert not any("install one of" in item.lower() for item in status["recommended_fixes"])


def test_execute_integration_action_is_shell_free_and_blocks_missing_executable(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)
    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    called = {"ran": False}

    def fake_run(*args, **kwargs):
        called["ran"] = True
        raise AssertionError("subprocess.run should not be called when the executable is missing")

    monkeypatch.setattr("integration_registry.subprocess.run", fake_run)

    result = execute_integration_action(
        family_id="source_control",
        action_id="create",
        params={"title": "Demo", "body": "Body"},
        registry_payload=registry,
        workspace_path=None,
        project_name="Shell Safety",
        confirmed=True,
    )

    assert result["status"] == "blocked"
    assert result["approval_required"] is False
    assert "not available on PATH" in result["stderr"]
    assert called["ran"] is False


def test_execute_integration_action_parses_quoted_args_correctly(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda command: f"C:/tools/{command}.exe" if command == "gh" else None)
    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "created"
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr("integration_registry.subprocess.run", fake_run)

    result = execute_integration_action(
        family_id="source_control",
        action_id="create",
        params={"title": 'Need "quotes" now', "body": "spaces still matter"},
        registry_payload=registry,
        workspace_path=None,
        project_name="Quote Demo",
        confirmed=True,
    )

    assert result["status"] == "completed"
    assert captured["args"] == [
        "gh",
        "issue",
        "create",
        "--title",
        'Need "quotes" now',
        "--body",
        "spaces still matter",
    ]


def test_connect_and_disconnect_actions_update_registry_state() -> None:
    registry = normalize_integration_registry({}, {})

    connected = execute_integration_action(
        family_id="source_control",
        action_id="connect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Connect Demo",
        confirmed=False,
    )
    assert connected["status"] == "completed"
    assert connected["updated_registry"]["connections"]["source_control"]["status"] == "partial"
    assert connected["updated_registry"]["connections"]["source_control"]["connection_source"] == "manual"

    disconnected = execute_integration_action(
        family_id="source_control",
        action_id="disconnect",
        params={},
        registry_payload=connected["updated_registry"],
        workspace_path=None,
        project_name="Connect Demo",
        confirmed=True,
    )
    assert disconnected["status"] == "completed"
    assert disconnected["updated_registry"]["connections"]["source_control"]["status"] == "disconnected"


def test_provider_specific_preview_prefers_gitlab_for_gitlab_repo(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "gitlab-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".gitlab-ci.yml").write_text("stages: [test]\n", encoding="utf-8")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text(
        '[remote "origin"]\n    url = git@gitlab.com:demo/project.git\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "glab" else None,
    )

    preview = preview_integration_action(
        family_id="source_control",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="GitLab Demo",
    )

    assert preview["provider"] == "gitlab"
    assert preview["command"] == "glab repo view"


def test_provider_specific_preview_does_not_trust_github_substring_inside_evil_host(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "evil-github-lookalike"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text(
        '[remote "origin"]\n    url = https://github.com.evil.example/demo/project.git\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    preview = preview_integration_action(
        family_id="source_control",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Evil Host Demo",
    )

    assert preview["provider"] is None
    assert preview["provider_candidates"] == []


def test_provider_specific_preview_accepts_self_hosted_gitlab_hostname(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "gitlab-self-hosted"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text(
        '[remote "origin"]\n    url = ssh://git@gitlab.internal.example:2222/demo/project.git\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "glab" else None,
    )

    preview = preview_integration_action(
        family_id="source_control",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Self-Hosted GitLab Demo",
    )

    assert preview["provider"] == "gitlab"
    assert preview["command"] == "glab repo view"


def test_provider_specific_preview_prefers_devcontainer_when_available(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "devcontainer-repo"
    (workspace / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (workspace / ".devcontainer" / "devcontainer.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"docker", "devcontainer"} else None,
    )

    preview = preview_integration_action(
        family_id="containers",
        action_id="open",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Devcontainer Demo",
    )

    assert preview["provider"] == "devcontainer"
    assert preview["command"] == "devcontainer up --workspace-folder ."


def test_provider_specific_preview_prefers_netlify_for_netlify_repo(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "netlify-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "netlify.toml").write_text("[build]\npublish='dist'\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "netlify" else None,
    )

    preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="deploy",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Netlify Demo",
    )

    assert preview["provider"] == "netlify"
    assert preview["command"] == "netlify deploy --prod"


def test_provider_specific_preview_prefers_github_actions_for_workflow_repo(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "workflow-repo"
    (workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "gh" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="GitHub Actions Demo",
    )

    assert preview["provider"] == "github_actions"
    assert preview["command"] == "gh run list --limit 10 --json databaseId,status,conclusion,name,workflowName"


def test_provider_specific_preview_resolves_bitbucket_with_guided_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "bitbucket-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "bitbucket-pipelines.yml").write_text("pipelines:\n  default: []\n", encoding="utf-8")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text(
        '[remote "origin"]\n    url = git@bitbucket.org:demo/project.git\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    preview = preview_integration_action(
        family_id="source_control",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Bitbucket Demo",
    )

    assert preview["provider"] == "bitbucket"
    assert preview["command"] is None
    assert any("bitbucket" in note.lower() and "adapter" in note.lower() for note in preview["notes"])


def test_provider_specific_preview_accepts_ssh_bitbucket_host_with_port(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "bitbucket-ssh-port"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text(
        '[remote "origin"]\n    url = ssh://git@bitbucket.org:7999/demo/project.git\n',
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    preview = preview_integration_action(
        family_id="source_control",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Bitbucket SSH Demo",
    )

    assert preview["provider"] == "bitbucket"
    assert preview["provider_candidates"] == ["bitbucket"]


def test_provider_specific_preview_prefers_jira_over_generic_issue_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "jira-repo"
    (workspace / ".jira").mkdir(parents=True, exist_ok=True)
    (workspace / ".jira" / "config.json").write_text('{"project":"MC"}\n', encoding="utf-8")
    (workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "acli" else None,
    )

    preview = preview_integration_action(
        family_id="work_tracking",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Jira Demo",
    )

    assert preview["provider"] == "jira"
    assert preview["command"] == 'acli jira workitem search --jql "order by updated DESC" --limit 20 --json'


def test_provider_specific_preview_surfaces_jira_create_param_requirements(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "jira-create-repo"
    (workspace / ".jira").mkdir(parents=True, exist_ok=True)
    (workspace / ".jira" / "config.json").write_text('{"project":"MC"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "acli" else None,
    )

    preview = preview_integration_action(
        family_id="work_tracking",
        action_id="create",
        params={"title": "Broken deploy", "body": "Still not good enough."},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Jira Create Demo",
    )

    assert preview["provider"] == "jira"
    assert sorted(preview["missing_params"]) == ["issue_type", "project_key"]
    assert 'acli jira workitem create' in str(preview["command"])
    assert preview["execution_mode"] == "local_cli"


def test_provider_specific_preview_surfaces_linear_guidance_without_fake_cli(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "linear-repo"
    (workspace / ".linear").mkdir(parents=True, exist_ok=True)
    (workspace / ".linear" / "workspace.json").write_text('{"name":"MC"}\n', encoding="utf-8")

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    preview = preview_integration_action(
        family_id="work_tracking",
        action_id="create",
        params={"title": "Agent drift", "body": "Still happening."},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Linear Demo",
    )

    assert preview["provider"] == "linear"
    assert preview["command"] is None
    assert any("linear.new" in note.lower() or "graphql" in note.lower() for note in preview["notes"])


def test_provider_specific_preview_uses_gitlab_ci_run_inspection(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "gitlab-ci-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".gitlab-ci.yml").write_text("stages: [test]\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "glab" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect_run",
        params={"run_id": "12345"},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="GitLab CI Demo",
    )

    assert preview["provider"] == "gitlab_ci"
    assert preview["command"] == 'glab ci get --pipeline-id "12345" --with-job-details --output json'


def test_provider_specific_preview_uses_gitlab_ci_log_tail(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "gitlab-ci-logs"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".gitlab-ci.yml").write_text("stages: [test]\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "glab" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="tail_logs",
        params={"run_id": "987"},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="GitLab CI Logs",
    )

    assert preview["provider"] == "gitlab_ci"
    assert preview["command"] == 'glab ci trace --pipeline-id "987"'


def test_provider_specific_preview_uses_github_actions_run_inspection(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "github-actions-run"
    (workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "gh" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect_run",
        params={"run_id": "654321"},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="GitHub Actions Run",
    )

    assert preview["provider"] == "github_actions"
    assert preview["command"] == 'gh run view "654321"'


def test_provider_specific_preview_inferrs_cloudflare_pages_deploy_directory(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "cloudflare-pages-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "wrangler.toml").write_text('pages_build_output_dir = "dist"\n', encoding="utf-8")
    (workspace / "dist").mkdir()

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "wrangler" else None,
    )

    preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="deploy",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Cloudflare Pages Demo",
    )

    assert preview["provider"] == "cloudflare_pages"
    assert preview["command"] == 'wrangler pages deploy "dist"'
    assert any("directory" in note.lower() for note in preview["notes"])
    assert preview["defaulted_params"] == {"directory": "dist"}


def test_provider_specific_preview_uses_railway_status_and_logs(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "railway-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "railway.json").write_text('{"build":{"builder":"NIXPACKS"}}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "railway" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Railway Demo",
    )
    logs_preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="tail_logs",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Railway Demo",
    )

    assert inspect_preview["provider"] == "railway"
    assert inspect_preview["command"] == "railway status --json"
    assert logs_preview["provider"] == "railway"
    assert logs_preview["command"] == "railway logs --deployment --latest --lines 200 --json"


def test_provider_specific_preview_requires_render_service_and_resource_ids(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "render-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "render.yaml").write_text("services: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "render" else None,
    )

    deploy_preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="deploy",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Render Demo",
    )
    logs_preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="tail_logs",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Render Demo",
    )

    assert deploy_preview["provider"] == "render"
    assert deploy_preview["missing_params"] == ["service_id"]
    assert "render deploys create {service_id_q} --wait" == deploy_preview["command"]
    assert logs_preview["provider"] == "render"
    assert logs_preview["missing_params"] == ["resource_id"]
    assert "render logs --resources {resource_id_q} --limit 200 --output json" == logs_preview["command"]


def test_provider_specific_preview_prefers_opentofu_for_tofu_repo(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "tofu-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "tofu.hcl").write_text("terraform {}\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "tofu" else None,
    )

    validate_preview = preview_integration_action(
        family_id="terraform",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="OpenTofu Demo",
    )
    deploy_preview = preview_integration_action(
        family_id="terraform",
        action_id="deploy",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="OpenTofu Demo",
    )

    assert validate_preview["provider"] == "opentofu"
    assert validate_preview["command"] == "tofu validate"
    assert deploy_preview["provider"] == "opentofu"
    assert deploy_preview["command"] == "tofu apply -auto-approve"


def test_provider_specific_preview_prefers_azure_commands(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "cloud_platforms": {
                    "family": "cloud_platforms",
                    "status": "connected",
                    "providers": ["azure"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "az" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="cloud_platforms",
        action_id="inspect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Azure Demo",
    )
    open_preview = preview_integration_action(
        family_id="cloud_platforms",
        action_id="open",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Azure Demo",
    )

    assert inspect_preview["provider"] == "azure"
    assert inspect_preview["command"] == "az account show --output json"
    assert open_preview["provider"] == "azure"
    assert open_preview["command"] == "az login"


def test_provider_specific_preview_prefers_gcp_commands(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "cloud_platforms": {
                    "family": "cloud_platforms",
                    "status": "connected",
                    "providers": ["gcp"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "gcloud" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="cloud_platforms",
        action_id="inspect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="GCP Demo",
    )

    assert inspect_preview["provider"] == "gcp"
    assert inspect_preview["command"] == "gcloud config list --format json"


def test_provider_specific_preview_prefers_cypress_for_cypress_repo(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "cypress-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "cypress.config.ts").write_text("export default {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "cypress" else None,
    )

    preview = preview_integration_action(
        family_id="browser_testing",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Cypress Demo",
    )

    assert preview["provider"] == "cypress"
    assert preview["command"] == "cypress run"


def test_provider_specific_preview_supports_circleci_inspect_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "circleci-repo"
    (workspace / ".circleci").mkdir(parents=True, exist_ok=True)
    (workspace / ".circleci" / "config.yml").write_text("version: 2.1\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "circleci" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="CircleCI Demo",
    )

    assert preview["provider"] == "circleci"
    assert preview["command"] == "circleci config validate .circleci/config.yml"
    assert preview["command_ready"] is True


def test_provider_specific_preview_supports_buildkite_inspect_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "buildkite-repo"
    (workspace / ".buildkite").mkdir(parents=True, exist_ok=True)
    (workspace / ".buildkite" / "pipeline.yml").write_text("steps: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "buildkite-agent" else None,
    )

    preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Buildkite Demo",
    )

    assert preview["provider"] == "buildkite"
    assert preview["command"] == "buildkite-agent pipeline upload --dry-run .buildkite/pipeline.yml"
    assert preview["command_ready"] is True


def test_provider_specific_preview_supports_codeql_scan_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "codeql-repo"
    (workspace / ".github" / "codeql").mkdir(parents=True, exist_ok=True)
    (workspace / ".github" / "codeql" / "config.yml").write_text("name: codeql\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "codeql" else None,
    )

    preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="CodeQL Demo",
    )

    assert preview["provider"] == "codeql"
    assert preview["command"] == "codeql resolve qlpacks"
    assert preview["command_ready"] is True


def test_provider_specific_preview_supports_firebase_neon_and_planetscale_lanes(monkeypatch, tmp_path) -> None:
    firebase_workspace = tmp_path / "firebase-repo"
    firebase_workspace.mkdir(parents=True, exist_ok=True)
    (firebase_workspace / "firebase.json").write_text('{"firestore":{}}\n', encoding="utf-8")

    neon_workspace = tmp_path / "neon-repo"
    neon_workspace.mkdir(parents=True, exist_ok=True)
    (neon_workspace / "neon.json").write_text('{"project":"demo"}\n', encoding="utf-8")

    planetscale_workspace = tmp_path / "pscale-repo"
    planetscale_workspace.mkdir(parents=True, exist_ok=True)
    (planetscale_workspace / "pscale.yml").write_text("org: demo\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"firebase", "neon", "pscale"} else None,
    )

    firebase_preview = preview_integration_action(
        family_id="database_platforms",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(firebase_workspace),
        project_name="Firebase Demo",
    )
    neon_preview = preview_integration_action(
        family_id="database_platforms",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(neon_workspace),
        project_name="Neon Demo",
    )
    planetscale_preview = preview_integration_action(
        family_id="database_platforms",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(planetscale_workspace),
        project_name="PlanetScale Demo",
    )

    assert firebase_preview["provider"] == "firebase"
    assert firebase_preview["command"] == "firebase apps:list --json"
    assert firebase_preview["command_ready"] is True
    assert neon_preview["provider"] == "neon"
    assert neon_preview["command"] == "neon projects list --output json"
    assert neon_preview["command_ready"] is True
    assert planetscale_preview["provider"] == "planetscale"
    assert planetscale_preview["command"] == "pscale database list"
    assert planetscale_preview["command_ready"] is True


def test_provider_specific_preview_supports_kubernetes_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "k8s-repo"
    (workspace / "k8s").mkdir(parents=True, exist_ok=True)
    (workspace / "k8s" / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "kubectl" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="kubernetes",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Kubernetes Demo",
    )
    deploy_preview = preview_integration_action(
        family_id="kubernetes",
        action_id="deploy",
        params={"path": "k8s/deployment.yaml"},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Kubernetes Demo",
    )

    assert inspect_preview["provider"] == "kubernetes"
    assert inspect_preview["command"] == "kubectl config current-context"
    assert inspect_preview["command_ready"] is True
    assert deploy_preview["provider"] == "kubernetes"
    assert deploy_preview["command"] == 'kubectl apply -f "k8s/deployment.yaml"'
    assert deploy_preview["command_ready"] is True


def test_multi_provider_families_no_longer_fall_back_to_unrelated_generic_commands(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    notion_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "docs_systems": {
                        "family": "docs_systems",
                        "status": "connected",
                        "providers": ["notion"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Notion Demo",
    )
    logrocket_preview = preview_integration_action(
        family_id="observability",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "observability": {
                        "family": "observability",
                        "status": "connected",
                        "providers": ["logrocket"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="LogRocket Demo",
    )

    assert notion_preview["provider"] == "notion"
    assert notion_preview["command"] is None
    assert notion_preview["execution_mode"] == "guided_remote"
    assert logrocket_preview["provider"] == "logrocket"
    assert logrocket_preview["command"] is None
    assert logrocket_preview["execution_mode"] == "guided_remote"


def test_provider_specific_preview_supports_sentry_datadog_and_newrelic_lanes(monkeypatch, tmp_path) -> None:
    sentry_workspace = tmp_path / "sentry-repo"
    sentry_workspace.mkdir(parents=True, exist_ok=True)
    (sentry_workspace / "sentry.properties").write_text("defaults.url=https://sentry.io/\n", encoding="utf-8")

    datadog_workspace = tmp_path / "datadog-repo"
    datadog_workspace.mkdir(parents=True, exist_ok=True)
    (datadog_workspace / "datadog.yaml").write_text("api_key: redacted\n", encoding="utf-8")

    newrelic_workspace = tmp_path / "newrelic-repo"
    newrelic_workspace.mkdir(parents=True, exist_ok=True)
    (newrelic_workspace / "newrelic.js").write_text("exports.config = {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"sentry-cli", "datadog-ci", "newrelic"} else None,
    )

    sentry_inspect = preview_integration_action(
        family_id="observability",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(sentry_workspace),
        project_name="Sentry Demo",
    )
    sentry_tail = preview_integration_action(
        family_id="observability",
        action_id="tail",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(sentry_workspace),
        project_name="Sentry Demo",
    )
    datadog_inspect = preview_integration_action(
        family_id="observability",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(datadog_workspace),
        project_name="Datadog Demo",
    )
    datadog_tail = preview_integration_action(
        family_id="observability",
        action_id="tail",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(datadog_workspace),
        project_name="Datadog Demo",
    )
    newrelic_inspect = preview_integration_action(
        family_id="observability",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(newrelic_workspace),
        project_name="New Relic Demo",
    )

    assert sentry_inspect["provider"] == "sentry"
    assert sentry_inspect["command"] == "sentry-cli info"
    assert sentry_inspect["command_ready"] is True
    assert sentry_tail["provider"] == "sentry"
    assert sentry_tail["command"] == "sentry-cli releases list"
    assert sentry_tail["command_ready"] is True
    assert datadog_inspect["provider"] == "datadog"
    assert datadog_inspect["command"] == "datadog-ci --version"
    assert datadog_inspect["command_ready"] is True
    assert datadog_tail["provider"] == "datadog"
    assert datadog_tail["command"] == "datadog-ci gate evaluate"
    assert datadog_tail["command_ready"] is True
    assert newrelic_inspect["provider"] == "new_relic"
    assert newrelic_inspect["command"] == "newrelic --version"
    assert newrelic_inspect["command_ready"] is True


def test_project_integrations_detect_datadog_and_newrelic_from_workspace_and_cli(monkeypatch, tmp_path) -> None:
    datadog_workspace = tmp_path / "datadog-repo"
    datadog_workspace.mkdir(parents=True, exist_ok=True)
    (datadog_workspace / "datadog.yaml").write_text("api_key: redacted\n", encoding="utf-8")

    newrelic_workspace = tmp_path / "newrelic-repo"
    newrelic_workspace.mkdir(parents=True, exist_ok=True)
    (newrelic_workspace / "newrelic.js").write_text("exports.config = {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"datadog-ci", "newrelic"} else None,
    )

    datadog_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(datadog_workspace),
            project_name="Datadog Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["observability"]
    newrelic_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(newrelic_workspace),
            project_name="New Relic Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["observability"]

    assert datadog_status["resolved_provider"] == "datadog"
    assert datadog_status["status"] == "ready"
    assert datadog_status["resolved_cli_candidates"] == ["datadog-ci"]
    assert newrelic_status["resolved_provider"] == "new_relic"
    assert newrelic_status["status"] == "ready"
    assert newrelic_status["resolved_cli_candidates"] == ["newrelic"]


def test_guided_preview_surfaces_figma_and_chatops_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    figma_preview = preview_integration_action(
        family_id="figma",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"figma": {"family": "figma", "status": "connected", "providers": ["figma"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Figma Demo",
    )
    slack_preview = preview_integration_action(
        family_id="chatops",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"chatops": {"family": "chatops", "status": "connected", "providers": ["slack"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Slack Demo",
    )

    assert figma_preview["provider"] == "figma"
    assert figma_preview["command"] is None
    assert figma_preview["execution_mode"] == "guided_remote"
    assert any("api-backed design lane" in note.lower() for note in figma_preview["notes"])
    assert slack_preview["provider"] == "slack"
    assert slack_preview["command"] is None
    assert slack_preview["execution_mode"] == "guided_remote"
    assert any("api-backed lane" in note.lower() for note in slack_preview["notes"])


def test_guided_preview_surfaces_bitbucket_pipeline_and_docs_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    bitbucket_preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect_run",
        params={"run_id": "123"},
        registry_payload=normalize_integration_registry(
            {"connections": {"ci_cd": {"family": "ci_cd", "status": "connected", "providers": ["bitbucket_pipelines"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Bitbucket Pipelines Demo",
    )
    confluence_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"docs_systems": {"family": "docs_systems", "status": "connected", "providers": ["confluence"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Confluence Demo",
    )

    assert bitbucket_preview["provider"] == "bitbucket_pipelines"
    assert bitbucket_preview["command"] is None
    assert bitbucket_preview["execution_mode"] == "guided_remote"
    assert any("api-backed adapter lane" in note.lower() for note in bitbucket_preview["notes"])
    assert confluence_preview["provider"] == "confluence"
    assert confluence_preview["command"] is None
    assert confluence_preview["execution_mode"] == "guided_remote"
    assert any("documentation lane" in note.lower() for note in confluence_preview["notes"])


def test_guided_preview_surfaces_teams_notion_and_logrocket_without_commands(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    teams_preview = preview_integration_action(
        family_id="chatops",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"chatops": {"family": "chatops", "status": "connected", "providers": ["teams"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Teams Demo",
    )
    notion_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="sync",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"docs_systems": {"family": "docs_systems", "status": "connected", "providers": ["notion"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Notion Demo",
    )
    logrocket_preview = preview_integration_action(
        family_id="observability",
        action_id="tail",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"observability": {"family": "observability", "status": "connected", "providers": ["logrocket"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LogRocket Demo",
    )

    assert teams_preview["provider"] == "teams"
    assert teams_preview["command"] is None
    assert teams_preview["execution_mode"] == "guided_remote"
    assert any("microsoft teams" in note.lower() and "api-backed lane" in note.lower() for note in teams_preview["notes"])
    assert notion_preview["provider"] == "notion"
    assert notion_preview["command"] is None
    assert notion_preview["execution_mode"] == "guided_remote"
    assert any("notion sync" in note.lower() and "api-backed lane" in note.lower() for note in notion_preview["notes"])
    assert logrocket_preview["provider"] == "logrocket"
    assert logrocket_preview["command"] is None
    assert logrocket_preview["execution_mode"] == "guided_remote"
    assert any("logrocket" in note.lower() and "telemetry review" in note.lower() for note in logrocket_preview["notes"])


def test_guided_preview_surfaces_feature_flag_and_analytics_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    launchdarkly_preview = preview_integration_action(
        family_id="feature_flags",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"feature_flags": {"family": "feature_flags", "status": "connected", "providers": ["launchdarkly"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LaunchDarkly Demo",
    )
    analytics_preview = preview_integration_action(
        family_id="analytics",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"analytics": {"family": "analytics", "status": "connected", "providers": ["posthog"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="PostHog Demo",
    )

    assert launchdarkly_preview["provider"] == "launchdarkly"
    assert launchdarkly_preview["command"] is None
    assert any("feature-flag lane" in note.lower() for note in launchdarkly_preview["notes"])
    assert analytics_preview["provider"] == "posthog"
    assert analytics_preview["command"] is None
    assert any("analytics lane" in note.lower() for note in analytics_preview["notes"])


def test_guided_preview_surfaces_statsig_amplitude_and_lmstudio_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    statsig_preview = preview_integration_action(
        family_id="feature_flags",
        action_id="sync",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"feature_flags": {"family": "feature_flags", "status": "connected", "providers": ["statsig"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Statsig Demo",
    )
    amplitude_preview = preview_integration_action(
        family_id="analytics",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"analytics": {"family": "analytics", "status": "connected", "providers": ["amplitude"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Amplitude Demo",
    )
    lmstudio_preview = preview_integration_action(
        family_id="local_model_runtimes",
        action_id="open",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"local_model_runtimes": {"family": "local_model_runtimes", "status": "connected", "providers": ["lm_studio"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LM Studio Demo",
    )

    assert statsig_preview["provider"] == "statsig"
    assert statsig_preview["command"] is None
    assert any("statsig sync" in note.lower() and "api-backed lane" in note.lower() for note in statsig_preview["notes"])
    assert amplitude_preview["provider"] == "amplitude"
    assert amplitude_preview["command"] is None
    assert any("analytics lane" in note.lower() for note in amplitude_preview["notes"])
    assert lmstudio_preview["provider"] == "lm_studio"
    assert lmstudio_preview["command"] is None
    assert any("runtime bridge" in note.lower() for note in lmstudio_preview["notes"])


def test_guided_preview_surfaces_configcat_mixpanel_and_freshdesk_without_commands(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    configcat_preview = preview_integration_action(
        family_id="feature_flags",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"feature_flags": {"family": "feature_flags", "status": "connected", "providers": ["configcat"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="ConfigCat Demo",
    )
    mixpanel_preview = preview_integration_action(
        family_id="analytics",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"analytics": {"family": "analytics", "status": "connected", "providers": ["mixpanel"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Mixpanel Demo",
    )
    freshdesk_preview = preview_integration_action(
        family_id="support_desk",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"support_desk": {"family": "support_desk", "status": "connected", "providers": ["freshdesk"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Freshdesk Demo",
    )

    assert configcat_preview["provider"] == "configcat"
    assert configcat_preview["command"] is None
    assert configcat_preview["execution_mode"] == "guided_remote"
    assert any("feature-flag lane" in note.lower() for note in configcat_preview["notes"])
    assert mixpanel_preview["provider"] == "mixpanel"
    assert mixpanel_preview["command"] is None
    assert mixpanel_preview["execution_mode"] == "guided_remote"
    assert any("analytics lane" in note.lower() for note in mixpanel_preview["notes"])
    assert freshdesk_preview["provider"] == "freshdesk"
    assert freshdesk_preview["command"] is None
    assert freshdesk_preview["execution_mode"] == "guided_remote"
    assert any("freshdesk ticket creation" in note.lower() and "api-backed lane" in note.lower() for note in freshdesk_preview["notes"])


def test_guided_preview_surfaces_dependabot_and_opengrok_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    dependabot_preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["dependabot"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Dependabot Demo",
    )
    opengrok_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "TODO"},
        registry_payload=normalize_integration_registry(
            {"connections": {"code_search": {"family": "code_search", "status": "connected", "providers": ["opengrok"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="OpenGrok Demo",
    )

    assert dependabot_preview["provider"] == "dependabot"
    assert dependabot_preview["command"] is None
    assert dependabot_preview["execution_mode"] == "guided_remote"
    assert any("dependabot" in note.lower() and "guided remote lane" in note.lower() for note in dependabot_preview["notes"])
    assert opengrok_preview["provider"] == "opengrok"
    assert opengrok_preview["command"] is None
    assert opengrok_preview["execution_mode"] == "guided_remote"
    assert any("code-search lane" in note.lower() for note in opengrok_preview["notes"])


def test_guided_preview_surfaces_vector_database_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    pinecone_preview = preview_integration_action(
        family_id="vector_databases",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"vector_databases": {"family": "vector_databases", "status": "connected", "providers": ["pinecone"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Pinecone Demo",
    )
    qdrant_preview = preview_integration_action(
        family_id="vector_databases",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"vector_databases": {"family": "vector_databases", "status": "connected", "providers": ["qdrant"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Qdrant Demo",
    )

    assert pinecone_preview["provider"] == "pinecone"
    assert pinecone_preview["command"] is None
    assert any("vector-store lane" in note.lower() for note in pinecone_preview["notes"])
    assert qdrant_preview["provider"] == "qdrant"
    assert qdrant_preview["command"] is None
    assert any("vector-store lane" in note.lower() for note in qdrant_preview["notes"])


def test_guided_preview_surfaces_support_auth_payment_release_and_runtime_guidance(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    intercom_preview = preview_integration_action(
        family_id="support_desk",
        action_id="search",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"support_desk": {"family": "support_desk", "status": "connected", "providers": ["intercom"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Intercom Demo",
    )
    okta_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["okta"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Okta Demo",
    )
    paddle_preview = preview_integration_action(
        family_id="payments",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"payments": {"family": "payments", "status": "connected", "providers": ["paddle"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Paddle Demo",
    )
    lmstudio_preview = preview_integration_action(
        family_id="local_model_runtimes",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"local_model_runtimes": {"family": "local_model_runtimes", "status": "connected", "providers": ["lm_studio"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LM Studio Demo",
    )
    launchnotes_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["launchnotes"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LaunchNotes Demo",
    )

    assert intercom_preview["provider"] == "intercom"
    assert any("support lane" in note.lower() for note in intercom_preview["notes"])
    assert okta_preview["provider"] == "okta"
    assert any("auth lane" in note.lower() for note in okta_preview["notes"])
    assert paddle_preview["provider"] == "paddle"
    assert any("payment lane" in note.lower() for note in paddle_preview["notes"])
    assert lmstudio_preview["provider"] == "lm_studio"
    assert any("runtime bridge" in note.lower() for note in lmstudio_preview["notes"])
    assert launchnotes_preview["provider"] == "launchnotes"
    assert any("release lane" in note.lower() for note in launchnotes_preview["notes"])


def test_guided_preview_surfaces_discord_lemon_squeezy_and_workos_without_commands(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    discord_preview = preview_integration_action(
        family_id="chatops",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"chatops": {"family": "chatops", "status": "connected", "providers": ["discord"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Discord Demo",
    )
    lemonsqueezy_preview = preview_integration_action(
        family_id="payments",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"payments": {"family": "payments", "status": "connected", "providers": ["lemon_squeezy"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Lemon Squeezy Demo",
    )
    workos_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["workos"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="WorkOS Demo",
    )

    assert discord_preview["provider"] == "discord"
    assert discord_preview["command"] is None
    assert discord_preview["execution_mode"] == "guided_remote"
    assert any("discord message creation" in note.lower() and "api-backed lane" in note.lower() for note in discord_preview["notes"])
    assert lemonsqueezy_preview["provider"] == "lemon_squeezy"
    assert lemonsqueezy_preview["command"] is None
    assert lemonsqueezy_preview["execution_mode"] == "guided_remote"
    assert any("lemon squeezy" in note.lower() and "api-backed lane" in note.lower() for note in lemonsqueezy_preview["notes"])
    assert workos_preview["provider"] == "workos"
    assert workos_preview["command"] is None
    assert workos_preview["execution_mode"] == "guided_remote"
    assert any("auth lane" in note.lower() for note in workos_preview["notes"])


def test_guided_preview_surfaces_zendesk_paypal_clerk_and_launchnotes_without_commands(monkeypatch) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    zendesk_preview = preview_integration_action(
        family_id="support_desk",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"support_desk": {"family": "support_desk", "status": "connected", "providers": ["zendesk"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Zendesk Demo",
    )
    paypal_preview = preview_integration_action(
        family_id="payments",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"payments": {"family": "payments", "status": "connected", "providers": ["paypal_sandbox"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="PayPal Sandbox Demo",
    )
    clerk_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["clerk"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Clerk Demo",
    )
    launchnotes_preview = preview_integration_action(
        family_id="release_management",
        action_id="create",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["launchnotes"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="LaunchNotes Demo",
    )

    assert zendesk_preview["provider"] == "zendesk"
    assert zendesk_preview["command"] is None
    assert any("zendesk ticket creation" in note.lower() and "api-backed lane" in note.lower() for note in zendesk_preview["notes"])
    assert paypal_preview["provider"] == "paypal_sandbox"
    assert paypal_preview["command"] is None
    assert any("payment lane" in note.lower() for note in paypal_preview["notes"])
    assert clerk_preview["provider"] == "clerk"
    assert clerk_preview["command"] is None
    assert any("auth lane" in note.lower() for note in clerk_preview["notes"])
    assert launchnotes_preview["provider"] == "launchnotes"
    assert launchnotes_preview["command"] is None
    assert any("launchnotes release publishing" in note.lower() and "api-backed lane" in note.lower() for note in launchnotes_preview["notes"])


def test_cli_backed_preview_surfaces_auth_secret_payment_and_release_guidance(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"auth0", "firebase", "supabase", "op", "doppler", "vault", "aws", "gcloud", "stripe", "release-please", "changeset", "semantic-release", "gh"}
        else None,
    )

    auth0_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["auth0"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Auth0 Guidance Demo",
    )
    firebase_auth_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["firebase_auth"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Firebase Auth Guidance Demo",
    )
    supabase_auth_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"auth_providers": {"family": "auth_providers", "status": "connected", "providers": ["supabase_auth"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Supabase Auth Guidance Demo",
    )
    onepassword_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"secrets": {"family": "secrets", "status": "connected", "providers": ["onepassword"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="1Password Guidance Demo",
    )
    stripe_preview = preview_integration_action(
        family_id="payments",
        action_id="create",
        params={"name": "Test Customer"},
        registry_payload=normalize_integration_registry({"connections": {"payments": {"family": "payments", "status": "connected", "providers": ["stripe"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Stripe Guidance Demo",
    )
    release_please_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["release_please"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Release Please Guidance Demo",
    )
    changesets_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["changesets"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="Changesets Guidance Demo",
    )
    semantic_release_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["semantic_release"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="semantic-release Guidance Demo",
    )
    github_releases_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["github_releases"], "connection_source": "mission_control", "host_imported": False}}}, {}),
        workspace_path=None,
        project_name="GitHub Releases Guidance Demo",
    )

    assert any("live remote auth state" in note.lower() for note in auth0_preview["notes"])
    assert any("live remote auth state" in note.lower() for note in firebase_auth_preview["notes"])
    assert any("live remote auth state" in note.lower() for note in supabase_auth_preview["notes"])
    assert any("live vault/session state" in note.lower() for note in onepassword_preview["notes"])
    assert any("mutates remote test state" in note.lower() for note in stripe_preview["notes"])
    assert any("release metadata" in note.lower() for note in release_please_preview["notes"])
    assert any("changeset graph" in note.lower() for note in changesets_preview["notes"])
    assert any("commit history" in note.lower() for note in semantic_release_preview["notes"])
    assert any("live remote release state" in note.lower() for note in github_releases_preview["notes"])


def test_default_provider_guidance_surfaces_for_ci_deploy_database_and_cluster_lanes(monkeypatch, tmp_path) -> None:
    ci_workspace = tmp_path / "gha-repo"
    (ci_workspace / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (ci_workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    deploy_workspace = tmp_path / "vercel-repo"
    deploy_workspace.mkdir(parents=True, exist_ok=True)
    (deploy_workspace / "vercel.json").write_text("{}\n", encoding="utf-8")

    supabase_workspace = tmp_path / "supabase-repo"
    (supabase_workspace / "supabase").mkdir(parents=True, exist_ok=True)
    (supabase_workspace / "supabase" / "config.toml").write_text("project_id='demo'\n", encoding="utf-8")

    k8s_workspace = tmp_path / "k8s-repo"
    (k8s_workspace / "k8s").mkdir(parents=True, exist_ok=True)
    (k8s_workspace / "k8s" / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"gh", "vercel", "supabase", "kubectl"} else None,
    )

    github_actions_preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(ci_workspace),
        project_name="GitHub Actions Guidance Demo",
    )
    vercel_preview = preview_integration_action(
        family_id="hosting_deploy",
        action_id="deploy",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(deploy_workspace),
        project_name="Vercel Guidance Demo",
    )
    supabase_preview = preview_integration_action(
        family_id="database_platforms",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(supabase_workspace),
        project_name="Supabase Guidance Demo",
    )
    kubernetes_preview = preview_integration_action(
        family_id="kubernetes",
        action_id="deploy",
        params={"path": "k8s/deployment.yaml"},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(k8s_workspace),
        project_name="Kubernetes Guidance Demo",
    )

    assert any("live remote workflow state" in note.lower() for note in github_actions_preview["notes"])
    assert any("mutates remote deployment state" in note.lower() for note in vercel_preview["notes"])
    assert any("live platform state" in note.lower() for note in supabase_preview["notes"])
    assert any("mutates live cluster state" in note.lower() for note in kubernetes_preview["notes"])


def test_default_provider_guidance_surfaces_for_validation_and_search_lanes(monkeypatch, tmp_path) -> None:
    api_workspace = tmp_path / "postman-repo"
    api_workspace.mkdir(parents=True, exist_ok=True)
    (api_workspace / "orders.postman_collection.json").write_text('{"info":{"name":"orders"}}\n', encoding="utf-8")

    search_workspace = tmp_path / "sourcegraph-repo"
    search_workspace.mkdir(parents=True, exist_ok=True)
    (search_workspace / "README.md").write_text("Sourcegraph handles code search.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"newman", "src"} else None,
    )

    postman_preview = preview_integration_action(
        family_id="api_clients",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(api_workspace),
        project_name="Postman Guidance Demo",
    )
    sourcegraph_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "TODO"},
        registry_payload=normalize_integration_registry(
            {"connections": {"code_search": {"family": "code_search", "status": "connected", "providers": ["sourcegraph"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=str(search_workspace),
        project_name="Sourcegraph Guidance Demo",
    )

    assert any("runs the current collection state" in note.lower() for note in postman_preview["notes"])
    assert any("live indexed search state" in note.lower() for note in sourcegraph_preview["notes"])


def test_host_token_aliases_detect_new_relic_launch_darkly_work_os_and_github_releases(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    new_relic_workspace = tmp_path / "new-relic-repo"
    new_relic_workspace.mkdir(parents=True, exist_ok=True)
    (new_relic_workspace / "README.md").write_text("New Relic handles release telemetry.\n", encoding="utf-8")

    launchdarkly_workspace = tmp_path / "launch-darkly-repo"
    launchdarkly_workspace.mkdir(parents=True, exist_ok=True)
    (launchdarkly_workspace / "README.md").write_text("Launch Darkly controls staged rollouts.\n", encoding="utf-8")

    workos_workspace = tmp_path / "work-os-repo"
    workos_workspace.mkdir(parents=True, exist_ok=True)
    (workos_workspace / "README.md").write_text("Work OS handles enterprise auth routing.\n", encoding="utf-8")

    github_releases_workspace = tmp_path / "github-releases-repo"
    github_releases_workspace.mkdir(parents=True, exist_ok=True)
    (github_releases_workspace / "README.md").write_text("GitHub Releases publishes artifacts for this product.\n", encoding="utf-8")

    new_relic_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(new_relic_workspace),
            project_name="New Relic Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["observability"]
    launchdarkly_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(launchdarkly_workspace),
            project_name="Launch Darkly Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["feature_flags"]
    workos_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workos_workspace),
            project_name="Work OS Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["auth_providers"]
    github_releases_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(github_releases_workspace),
            project_name="GitHub Releases Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["release_management"]

    assert new_relic_status["resolved_provider"] == "new_relic"
    assert new_relic_status["status"] == "partial"
    assert launchdarkly_status["resolved_provider"] == "launchdarkly"
    assert launchdarkly_status["status"] == "partial"
    assert workos_status["resolved_provider"] == "workos"
    assert workos_status["status"] == "partial"
    assert github_releases_status["resolved_provider"] == "github_releases"
    assert github_releases_status["status"] == "partial"


def test_workspace_token_aliases_detect_help_scout_lmstudio_and_launch_notes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    help_workspace = tmp_path / "helpscout-repo"
    help_workspace.mkdir(parents=True, exist_ok=True)
    (help_workspace / "README.md").write_text("HelpScout handles our support inbox.\n", encoding="utf-8")

    lm_workspace = tmp_path / "lmstudio-repo"
    lm_workspace.mkdir(parents=True, exist_ok=True)
    (lm_workspace / "README.md").write_text("LMStudio runs local checkpoints for demos.\n", encoding="utf-8")

    launch_workspace = tmp_path / "launchnotes-repo"
    launch_workspace.mkdir(parents=True, exist_ok=True)
    (launch_workspace / "README.md").write_text("Launch Notes keeps external release comms consistent.\n", encoding="utf-8")

    help_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(help_workspace),
            project_name="HelpScout Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["support_desk"]
    lm_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(lm_workspace),
            project_name="LMStudio Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["local_model_runtimes"]
    launch_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(launch_workspace),
            project_name="Launch Notes Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["release_management"]

    assert help_status["resolved_provider"] == "help_scout"
    assert help_status["status"] == "partial"
    assert lm_status["resolved_provider"] == "lm_studio"
    assert lm_status["status"] == "partial"
    assert launch_status["resolved_provider"] == "launchnotes"
    assert launch_status["status"] == "partial"


def test_workspace_token_aliases_detect_teams_and_lemon_squeezy(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    teams_workspace = tmp_path / "teams-repo"
    teams_workspace.mkdir(parents=True, exist_ok=True)
    (teams_workspace / "README.md").write_text("Microsoft Teams carries internal launch comms.\n", encoding="utf-8")

    lemon_workspace = tmp_path / "lemon-repo"
    lemon_workspace.mkdir(parents=True, exist_ok=True)
    (lemon_workspace / "README.md").write_text("LemonSqueezy handles test purchases for this app.\n", encoding="utf-8")

    teams_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(teams_workspace),
            project_name="Teams Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["chatops"]
    lemon_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(lemon_workspace),
            project_name="Lemon Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["payments"]

    assert teams_status["resolved_provider"] == "teams"
    assert teams_status["status"] == "partial"
    assert lemon_status["resolved_provider"] == "lemon_squeezy"
    assert lemon_status["status"] == "partial"


def test_workspace_token_aliases_detect_opengrok_and_chroma(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    opengrok_workspace = tmp_path / "opengrok-repo"
    opengrok_workspace.mkdir(parents=True, exist_ok=True)
    (opengrok_workspace / "README.md").write_text("Open Grok powers legacy code search here.\n", encoding="utf-8")

    chroma_workspace = tmp_path / "chroma-repo"
    chroma_workspace.mkdir(parents=True, exist_ok=True)
    (chroma_workspace / "README.md").write_text("Chroma DB stores local embeddings for fast retrieval.\n", encoding="utf-8")

    opengrok_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(opengrok_workspace),
            project_name="OpenGrok Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["code_search"]
    chroma_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(chroma_workspace),
            project_name="Chroma Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["vector_databases"]

    assert opengrok_status["resolved_provider"] == "opengrok"
    assert opengrok_status["status"] == "partial"
    assert chroma_status["resolved_provider"] == "chroma"
    assert chroma_status["status"] == "partial"


def test_provider_specific_preview_supports_chrome_devtools_and_cdp_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "chrome" else None,
    )

    chrome_inspect = preview_integration_action(
        family_id="browser_devtools",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "browser_devtools": {
                        "family": "browser_devtools",
                        "status": "connected",
                        "providers": ["chrome_devtools"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Chrome DevTools Demo",
    )
    cdp_open = preview_integration_action(
        family_id="browser_devtools",
        action_id="open",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "browser_devtools": {
                        "family": "browser_devtools",
                        "status": "connected",
                        "providers": ["cdp"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="CDP Demo",
    )

    assert chrome_inspect["provider"] == "chrome_devtools"
    assert chrome_inspect["command"] == "chrome --version"
    assert chrome_inspect["command_ready"] is True
    assert cdp_open["provider"] == "cdp"
    assert cdp_open["command"] == "chrome --remote-debugging-port=9222 about:blank"
    assert cdp_open["command_ready"] is True


def test_project_integrations_detect_browser_devtools_from_workspace_tokens_and_cli(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "devtools-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Use Chrome DevTools to inspect the live page.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "chrome" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="DevTools Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["browser_devtools"]

    assert status["resolved_provider"] == "chrome_devtools"
    assert status["status"] == "ready"
    assert status["resolved_cli_candidates"] == ["chrome"]
    assert status["local_action_count"] >= 1


def test_provider_specific_preview_supports_docusaurus_docs_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "docusaurus-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "docusaurus.config.js").write_text("module.exports = {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "npm" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Docusaurus Demo",
    )

    assert inspect_preview["provider"] == "docusaurus"
    assert inspect_preview["command"] == "npm exec docusaurus -- --help"


def test_provider_specific_preview_supports_storybook_validate_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "storybook-repo"
    (workspace / ".storybook").mkdir(parents=True, exist_ok=True)
    (workspace / ".storybook" / "main.ts").write_text("export default {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "npm" else None,
    )

    preview = preview_integration_action(
        family_id="storybook",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Storybook Demo",
    )

    assert preview["provider"] == "storybook"
    assert preview["command"] == "npm exec storybook -- build"
    assert preview["command_ready"] is True


def test_provider_specific_preview_supports_pypi_maven_nuget_and_rubygems_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"twine", "mvn", "dotnet", "gem"} else None,
    )

    pypi_preview = preview_integration_action(
        family_id="package_registries",
        action_id="publish",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "package_registries": {
                        "family": "package_registries",
                        "status": "connected",
                        "providers": ["pypi"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="PyPI Demo",
    )
    maven_preview = preview_integration_action(
        family_id="package_registries",
        action_id="publish",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "package_registries": {
                        "family": "package_registries",
                        "status": "connected",
                        "providers": ["maven"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Maven Demo",
    )
    nuget_preview = preview_integration_action(
        family_id="package_registries",
        action_id="publish",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "package_registries": {
                        "family": "package_registries",
                        "status": "connected",
                        "providers": ["nuget"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="NuGet Demo",
    )
    rubygems_preview = preview_integration_action(
        family_id="package_registries",
        action_id="publish",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "package_registries": {
                        "family": "package_registries",
                        "status": "connected",
                        "providers": ["rubygems"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="RubyGems Demo",
    )

    assert pypi_preview["provider"] == "pypi"
    assert pypi_preview["missing_params"] == ["artifact"]
    assert pypi_preview["command"] == "twine upload {artifact_q}"
    assert maven_preview["provider"] == "maven"
    assert maven_preview["command"] == "mvn deploy -DskipTests"
    assert maven_preview["command_ready"] is True
    assert nuget_preview["provider"] == "nuget"
    assert nuget_preview["missing_params"] == ["artifact"]
    assert nuget_preview["command"] == "dotnet nuget push {artifact_q}"
    assert rubygems_preview["provider"] == "rubygems"
    assert rubygems_preview["missing_params"] == ["artifact"]
    assert rubygems_preview["command"] == "gem push {artifact_q}"


def test_project_integrations_detect_pypi_from_workspace_and_cli(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "pypi-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "twine" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="PyPI Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]

    assert status["resolved_provider"] == "pypi"
    assert status["status"] == "ready"
    assert status["resolved_cli_candidates"] == ["twine"]
    assert status["local_action_count"] >= 1


def test_provider_specific_preview_supports_release_please_and_semantic_release_lanes(monkeypatch, tmp_path) -> None:
    release_please_workspace = tmp_path / "release-please-repo"
    release_please_workspace.mkdir(parents=True, exist_ok=True)
    (release_please_workspace / ".release-please-manifest.json").write_text('{"packages":{}}\n', encoding="utf-8")

    semantic_workspace = tmp_path / "semantic-release-repo"
    semantic_workspace.mkdir(parents=True, exist_ok=True)
    (semantic_workspace / ".releaserc").write_text('{"branches":["main"]}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"release-please", "semantic-release"} else None,
    )

    release_please_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(release_please_workspace),
        project_name="Release Please Demo",
    )
    semantic_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(semantic_workspace),
        project_name="Semantic Release Demo",
    )

    assert release_please_preview["provider"] == "release_please"
    assert release_please_preview["command"] == "release-please manifest-pr --dry-run"
    assert release_please_preview["command_ready"] is True
    assert semantic_preview["provider"] == "semantic_release"
    assert semantic_preview["command"] == "semantic-release --dry-run"
    assert semantic_preview["command_ready"] is True


def test_provider_specific_preview_supports_vllm_runtime(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "local_model_runtimes": {
                    "family": "local_model_runtimes",
                    "status": "connected",
                    "providers": ["vllm"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "vllm" else None,
    )

    preview = preview_integration_action(
        family_id="local_model_runtimes",
        action_id="inspect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="vLLM Demo",
    )

    assert preview["provider"] == "vllm"
    assert preview["command"] == "vllm --help"


def test_provider_specific_preview_supports_npm_publish_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "package_registries": {
                    "family": "package_registries",
                    "status": "connected",
                    "providers": ["npm"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "npm" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="npm Demo",
    )
    publish_preview = preview_integration_action(
        family_id="package_registries",
        action_id="publish",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="npm Demo",
    )

    assert inspect_preview["provider"] == "npm"
    assert inspect_preview["command"] == "npm whoami"
    assert publish_preview["provider"] == "npm"
    assert publish_preview["command"] == "npm publish"


def test_provider_specific_preview_supports_changesets_and_github_release_lanes(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "changesets-repo"
    (workspace / ".changeset").mkdir(parents=True, exist_ok=True)
    (workspace / ".changeset" / "hello.md").write_text("---\n---\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"changeset", "gh"} else None,
    )

    draft_preview = preview_integration_action(
        family_id="release_management",
        action_id="draft",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Changesets Demo",
    )

    github_registry = normalize_integration_registry(
        {
            "connections": {
                "release_management": {
                    "family": "release_management",
                    "status": "connected",
                    "providers": ["github_releases"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    create_preview = preview_integration_action(
        family_id="release_management",
        action_id="create",
        params={},
        registry_payload=github_registry,
        workspace_path=str(workspace),
        project_name="GitHub Releases Demo",
    )

    assert draft_preview["provider"] == "changesets"
    assert draft_preview["command"] == "changeset status"
    assert create_preview["provider"] == "github_releases"
    assert create_preview["missing_params"] == ["tag"]
    assert create_preview["command"] == "gh release create {tag_q}"


def test_provider_specific_preview_supports_bruno_collection_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "bruno-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "bruno.json").write_text('{"name":"demo"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "bru" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="api_clients",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Bruno Demo",
    )
    validate_preview = preview_integration_action(
        family_id="api_clients",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Bruno Demo",
    )

    assert inspect_preview["provider"] == "bruno"
    assert inspect_preview["command"] == "bru --version"
    assert validate_preview["provider"] == "bruno"
    assert validate_preview["command"] == "bru run"


def test_provider_specific_preview_supports_postman_collection_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "postman-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "orders.postman_collection.json").write_text('{"info":{"name":"orders"}}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "newman" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="api_clients",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Postman Demo",
    )
    validate_preview = preview_integration_action(
        family_id="api_clients",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Postman Demo",
    )

    assert inspect_preview["provider"] == "postman"
    assert inspect_preview["command"] == "newman --version"
    assert validate_preview["provider"] == "postman"
    assert validate_preview["command"] == 'newman run "orders.postman_collection.json"'
    assert validate_preview["defaulted_params"] == {"collection": "orders.postman_collection.json"}
    assert validate_preview["command_ready"] is True


def test_provider_specific_preview_supports_insomnia_collection_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "insomnia-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "insomnia.json").write_text('{"resources":[]}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "inso" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="api_clients",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Insomnia Demo",
    )
    validate_preview = preview_integration_action(
        family_id="api_clients",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Insomnia Demo",
    )

    assert inspect_preview["provider"] == "insomnia"
    assert inspect_preview["command"] == "inso --version"
    assert validate_preview["provider"] == "insomnia"
    assert validate_preview["command"] == 'inso run test "insomnia.json"'
    assert validate_preview["defaulted_params"] == {"collection": "insomnia.json"}
    assert validate_preview["command_ready"] is True


def test_provider_specific_preview_supports_auth0_inspect_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "auth_providers": {
                    "family": "auth_providers",
                    "status": "connected",
                    "providers": ["auth0"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "auth0" else None,
    )

    preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Auth0 Demo",
    )

    assert preview["provider"] == "auth0"
    assert preview["command"] == "auth0 apps list --json"
    assert preview["command_ready"] is True


def test_project_integrations_detect_auth0_from_workspace_and_cli(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "auth0-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "auth0.json").write_text('{"AUTH0_DOMAIN":"demo"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "auth0" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Auth0 Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["auth_providers"]

    assert status["resolved_provider"] == "auth0"
    assert status["status"] == "ready"
    assert status["resolved_cli_candidates"] == ["auth0"]
    assert status["local_action_count"] >= 1


def test_provider_specific_preview_supports_semgrep_scan_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "semgrep-repo"
    (workspace / ".semgrep").mkdir(parents=True, exist_ok=True)
    (workspace / ".semgrep" / "rules.yml").write_text("rules: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "semgrep" else None,
    )

    preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Semgrep Demo",
    )

    assert preview["provider"] == "semgrep"
    assert preview["command"] == "semgrep scan --json"


def test_provider_specific_preview_supports_trivy_scan_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "trivy-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "trivy.yaml").write_text("scan:\n  skip-dirs: []\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "trivy" else None,
    )

    preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Trivy Demo",
    )

    assert preview["provider"] == "trivy"
    assert preview["command"] == "trivy fs --format json ."


def test_provider_specific_preview_supports_snyk_scan_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "security_scanners": {
                    "family": "security_scanners",
                    "status": "connected",
                    "providers": ["snyk"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "snyk" else None,
    )

    preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Snyk Demo",
    )

    assert preview["provider"] == "snyk"
    assert preview["command"] == "snyk test --json"


def test_provider_specific_preview_supports_vault_and_doppler_inspect_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"vault", "doppler"} else None,
    )

    vault_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "secrets": {
                        "family": "secrets",
                        "status": "connected",
                        "providers": ["vault"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Vault Demo",
    )
    doppler_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "secrets": {
                        "family": "secrets",
                        "status": "connected",
                        "providers": ["doppler"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Doppler Demo",
    )

    assert vault_preview["provider"] == "vault"
    assert vault_preview["command"] == "vault status -format=json"
    assert doppler_preview["provider"] == "doppler"
    assert doppler_preview["command"] == "doppler configs"


def test_provider_specific_preview_supports_onepassword_aws_and_gcp_secret_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"op", "aws", "gcloud"} else None,
    )

    onepassword_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "secrets": {
                        "family": "secrets",
                        "status": "connected",
                        "providers": ["onepassword"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="1Password Demo",
    )
    aws_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "secrets": {
                        "family": "secrets",
                        "status": "connected",
                        "providers": ["aws_secrets_manager"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="AWS Secrets Demo",
    )
    gcp_preview = preview_integration_action(
        family_id="secrets",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "secrets": {
                        "family": "secrets",
                        "status": "connected",
                        "providers": ["gcp_secret_manager"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="GCP Secrets Demo",
    )

    assert onepassword_preview["provider"] == "onepassword"
    assert onepassword_preview["command"] == "op vault list --format json"
    assert onepassword_preview["command_ready"] is True
    assert aws_preview["provider"] == "aws_secrets_manager"
    assert aws_preview["command"] == "aws secretsmanager list-secrets --max-results 20 --output json"
    assert aws_preview["command_ready"] is True
    assert gcp_preview["provider"] == "gcp_secret_manager"
    assert gcp_preview["command"] == "gcloud secrets list --format json"
    assert gcp_preview["command_ready"] is True


def test_project_integrations_detect_onepassword_from_workspace_tokens_and_cli(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "onepassword-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("This service uses 1Password for secret delivery.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "op" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="1Password Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]

    assert status["resolved_provider"] == "onepassword"
    assert status["status"] == "ready"
    assert status["resolved_cli_candidates"] == ["op"]
    assert status["local_action_count"] >= 1


def test_project_integrations_detect_aws_and_gcp_secret_manager_from_workspace_tokens(monkeypatch, tmp_path) -> None:
    aws_workspace = tmp_path / "aws-secrets-repo"
    aws_workspace.mkdir(parents=True, exist_ok=True)
    (aws_workspace / "README.md").write_text("This app uses AWS Secrets Manager for runtime secrets.\n", encoding="utf-8")

    gcp_workspace = tmp_path / "gcp-secrets-repo"
    gcp_workspace.mkdir(parents=True, exist_ok=True)
    (gcp_workspace / "README.md").write_text("This app syncs keys through GCP Secret Manager.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"aws", "gcloud"} else None,
    )

    aws_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(aws_workspace),
            project_name="AWS Secrets Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]
    gcp_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(gcp_workspace),
            project_name="GCP Secrets Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]

    assert aws_status["resolved_provider"] == "aws_secrets_manager"
    assert aws_status["status"] == "ready"
    assert aws_status["resolved_cli_candidates"] == ["aws"]
    assert gcp_status["resolved_provider"] == "gcp_secret_manager"
    assert gcp_status["status"] == "ready"
    assert gcp_status["resolved_cli_candidates"] == ["gcloud"]


def test_provider_specific_preview_supports_stripe_create_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "payments": {
                    "family": "payments",
                    "status": "connected",
                    "providers": ["stripe"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "stripe" else None,
    )

    missing_preview = preview_integration_action(
        family_id="payments",
        action_id="create",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Stripe Demo",
    )
    complete_preview = preview_integration_action(
        family_id="payments",
        action_id="create",
        params={"name": "Mission Control Test Customer"},
        registry_payload=registry,
        workspace_path=None,
        project_name="Stripe Demo",
    )

    assert missing_preview["provider"] == "stripe"
    assert missing_preview["missing_params"] == ["name"]
    assert missing_preview["command"] == "stripe customers create --name {name_q}"
    assert complete_preview["command"] == 'stripe customers create --name "Mission Control Test Customer"'


def test_provider_specific_preview_supports_openapi_spec_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "openapi-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "openapi.yaml").write_text("openapi: 3.1.0\ninfo:\n  title: Demo\n  version: 1.0.0\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "swagger-cli" else None,
    )

    inspect_preview = preview_integration_action(
        family_id="openapi",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="OpenAPI Demo",
    )
    validate_preview = preview_integration_action(
        family_id="openapi",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="OpenAPI Demo",
    )

    assert inspect_preview["provider"] == "openapi"
    assert inspect_preview["defaulted_params"] == {"spec": "openapi.yaml"}
    assert inspect_preview["command"] == 'swagger-cli validate "openapi.yaml"'
    assert validate_preview["provider"] == "openapi"
    assert validate_preview["command"] == 'swagger-cli validate "openapi.yaml"'


def test_provider_specific_preview_supports_sourcegraph_query_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "code_search": {
                    "family": "code_search",
                    "status": "connected",
                    "providers": ["sourcegraph"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "src" else None,
    )

    missing_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={},
        registry_payload=registry,
        workspace_path=None,
        project_name="Sourcegraph Demo",
    )
    complete_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "repo:mission-control integration"},
        registry_payload=registry,
        workspace_path=None,
        project_name="Sourcegraph Demo",
    )

    assert missing_preview["provider"] == "sourcegraph"
    assert missing_preview["missing_params"] == ["query"]
    assert missing_preview["command"] == "src search -json {query_q}"
    assert complete_preview["command"] == 'src search -json "repo:mission-control integration"'


def test_provider_specific_preview_supports_zoekt_query_lane(monkeypatch) -> None:
    registry = normalize_integration_registry(
        {
            "connections": {
                "code_search": {
                    "family": "code_search",
                    "status": "connected",
                    "providers": ["zoekt"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "zoekt-query" else None,
    )

    preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "symbol:ManagerService"},
        registry_payload=registry,
        workspace_path=None,
        project_name="Zoekt Demo",
    )

    assert preview["provider"] == "zoekt"
    assert preview["command"] == 'zoekt-query "symbol:ManagerService"'


def test_provider_specific_preview_supports_supabase_and_firebase_auth_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"supabase", "firebase"} else None,
    )

    supabase_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "auth_providers": {
                        "family": "auth_providers",
                        "status": "connected",
                        "providers": ["supabase_auth"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Supabase Auth Demo",
    )
    firebase_preview = preview_integration_action(
        family_id="auth_providers",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {
                "connections": {
                    "auth_providers": {
                        "family": "auth_providers",
                        "status": "connected",
                        "providers": ["firebase_auth"],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        ),
        workspace_path=None,
        project_name="Firebase Auth Demo",
    )

    assert supabase_preview["provider"] == "supabase_auth"
    assert supabase_preview["command"] == "supabase projects list"
    assert firebase_preview["provider"] == "firebase_auth"
    assert firebase_preview["command"] == "firebase apps:list --json"


def test_project_integrations_surface_provider_specific_required_params_and_host_import_artifacts(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "integration-status-details"
    (workspace / ".jira").mkdir(parents=True, exist_ok=True)
    (workspace / ".jira" / "config.json").write_text('{"project":"MC"}\n', encoding="utf-8")

    registry = normalize_integration_registry(
        {
            "connections": {
                "work_tracking": {
                    "family": "work_tracking",
                    "status": "partial",
                    "providers": ["jira"],
                    "connection_source": "codex_host",
                    "host_imported": True,
                }
            },
            "host_imports": {
                "codex": {
                    "work_tracking": {
                        "detected": True,
                        "paths": ["C:/Users/mike/.codex/plugins/jira/plugin.json"],
                        "provider_hints": ["jira"],
                    }
                },
                "claude_code": {},
            },
        },
        {},
    )

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "acli" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Integration Details Demo",
            registry_payload=registry,
        )
    }["work_tracking"]

    create_action = next(item for item in status["available_actions"] if item["action_id"] == "create")

    assert status["resolved_provider"] == "jira"
    assert status["providers"] == ["jira"]
    assert status["resolved_cli_candidates"] == ["acli"]
    assert status["available_action_count"] >= 1
    assert status["local_action_count"] >= 1
    assert any(item["type"] == "host_import_path" and item["host"] == "codex" for item in status["artifacts"])
    assert create_action["required_params"] == ["title", "body", "project_key", "issue_type"]
    assert create_action["command_ready"] is True
    assert create_action["execution_mode"] == "local_cli"


def test_project_integrations_detect_terraform_provider_and_cli_from_workspace(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "terraform-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "main.tf").write_text("terraform {}\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "terraform" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Terraform Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["terraform"]

    assert status["resolved_provider"] == "terraform"
    assert status["resolved_cli_candidates"] == ["terraform"]
    assert status["status"] == "ready"
    assert status["health"]["resolved_cli_detected"] == ["terraform"]


def test_project_integrations_detect_mintlify_provider_and_cli_from_workspace(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "mintlify-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "mint.json").write_text('{"name":"Docs"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "mintlify" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Mintlify Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["docs_systems"]

    assert status["resolved_provider"] == "mintlify"
    assert status["resolved_cli_candidates"] == ["mintlify"]
    assert status["status"] == "ready"
    assert status["health"]["resolved_cli_detected"] == ["mintlify"]


def test_project_integrations_expose_cloud_provider_cli_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"aws", "az", "gcloud"} else None,
    )

    aws_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="AWS Ready Demo",
            registry_payload=normalize_integration_registry(
                {"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["aws"], "connection_source": "mission_control", "host_imported": False}}},
                {},
            ),
        )
    }["cloud_platforms"]
    azure_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="Azure Ready Demo",
            registry_payload=normalize_integration_registry(
                {"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["azure"], "connection_source": "mission_control", "host_imported": False}}},
                {},
            ),
        )
    }["cloud_platforms"]
    gcp_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=None,
            project_name="GCP Ready Demo",
            registry_payload=normalize_integration_registry(
                {"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["gcp"], "connection_source": "mission_control", "host_imported": False}}},
                {},
            ),
        )
    }["cloud_platforms"]

    assert aws_status["resolved_provider"] == "aws"
    assert aws_status["resolved_cli_candidates"] == ["aws"]
    assert azure_status["resolved_provider"] == "azure"
    assert azure_status["resolved_cli_candidates"] == ["az"]
    assert gcp_status["resolved_provider"] == "gcp"
    assert gcp_status["resolved_cli_candidates"] == ["gcloud"]


def test_project_integrations_expose_browser_runner_and_gitleaks_cli_candidates(monkeypatch, tmp_path) -> None:
    playwright_workspace = tmp_path / "playwright-repo"
    playwright_workspace.mkdir(parents=True, exist_ok=True)
    (playwright_workspace / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")

    cypress_workspace = tmp_path / "cypress-repo"
    cypress_workspace.mkdir(parents=True, exist_ok=True)
    (cypress_workspace / "cypress.config.ts").write_text("export default {};\n", encoding="utf-8")

    gitleaks_workspace = tmp_path / "gitleaks-repo"
    gitleaks_workspace.mkdir(parents=True, exist_ok=True)
    (gitleaks_workspace / ".gitleaks.toml").write_text("title = \"demo\"\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"playwright", "cypress", "gitleaks"} else None,
    )

    playwright_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(playwright_workspace),
            project_name="Playwright Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["browser_testing"]
    cypress_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(cypress_workspace),
            project_name="Cypress Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["browser_testing"]
    gitleaks_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(gitleaks_workspace),
            project_name="Gitleaks Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]

    assert playwright_status["resolved_provider"] == "playwright"
    assert playwright_status["resolved_cli_candidates"] == ["playwright"]
    assert cypress_status["resolved_provider"] == "cypress"
    assert cypress_status["resolved_cli_candidates"] == ["cypress"]
    assert gitleaks_status["resolved_provider"] == "gitleaks"
    assert gitleaks_status["resolved_cli_candidates"] == ["gitleaks"]


def test_provider_token_matching_no_longer_confuses_doppler_with_onepassword(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "doppler-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Doppler manages secrets for this service.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "doppler" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Doppler Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]

    assert status["resolved_provider"] == "doppler"
    assert status["resolved_cli_candidates"] == ["doppler"]
    assert status["health"]["resolved_cli_detected"] == ["doppler"]


def test_project_integrations_detect_ollama_provider_and_preview_open_lane(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "ollama-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Ollama serves local checkpoints for this project.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "ollama" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Ollama Workspace Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["local_model_runtimes"]
    preview = preview_integration_action(
        family_id="local_model_runtimes",
        action_id="open",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Ollama Workspace Demo",
    )

    assert status["resolved_provider"] == "ollama"
    assert status["resolved_cli_candidates"] == ["ollama"]
    assert status["health"]["resolved_cli_detected"] == ["ollama"]
    assert preview["provider"] == "ollama"
    assert preview["command"] == "ollama serve"
    assert preview["command_ready"] is True


def test_workspace_config_detection_resolves_semgrep_codeql_openapi_and_auth_providers_without_cli(tmp_path) -> None:
    semgrep_workspace = tmp_path / "semgrep-config-repo"
    (semgrep_workspace / ".semgrep").mkdir(parents=True, exist_ok=True)
    (semgrep_workspace / ".semgrep" / "rules.yml").write_text("rules: []\n", encoding="utf-8")

    codeql_workspace = tmp_path / "codeql-config-repo"
    (codeql_workspace / ".github" / "codeql").mkdir(parents=True, exist_ok=True)
    (codeql_workspace / ".github" / "codeql" / "config.yml").write_text("name: codeql\n", encoding="utf-8")

    openapi_workspace = tmp_path / "openapi-config-repo"
    openapi_workspace.mkdir(parents=True, exist_ok=True)
    (openapi_workspace / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")

    swagger_workspace = tmp_path / "swagger-config-repo"
    swagger_workspace.mkdir(parents=True, exist_ok=True)
    (swagger_workspace / "swagger.yaml").write_text('swagger: "2.0"\n', encoding="utf-8")

    firebase_auth_workspace = tmp_path / "firebase-auth-repo"
    firebase_auth_workspace.mkdir(parents=True, exist_ok=True)
    (firebase_auth_workspace / "firebase.json").write_text("{}\n", encoding="utf-8")

    supabase_auth_workspace = tmp_path / "supabase-auth-repo"
    (supabase_auth_workspace / "supabase").mkdir(parents=True, exist_ok=True)
    (supabase_auth_workspace / "supabase" / "config.toml").write_text("[project]\n", encoding="utf-8")

    auth0_workspace = tmp_path / "auth0-config-repo"
    (auth0_workspace / ".auth0").mkdir(parents=True, exist_ok=True)
    (auth0_workspace / ".auth0" / "config.json").write_text("{}\n", encoding="utf-8")

    semgrep_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(semgrep_workspace),
            project_name="Semgrep Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]
    codeql_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(codeql_workspace),
            project_name="CodeQL Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]
    openapi_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(openapi_workspace),
            project_name="OpenAPI Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["openapi"]
    swagger_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(swagger_workspace),
            project_name="Swagger Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["openapi"]
    firebase_auth_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(firebase_auth_workspace),
            project_name="Firebase Auth Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["auth_providers"]
    supabase_auth_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(supabase_auth_workspace),
            project_name="Supabase Auth Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["auth_providers"]
    auth0_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(auth0_workspace),
            project_name="Auth0 Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["auth_providers"]

    assert semgrep_status["resolved_provider"] == "semgrep"
    assert semgrep_status["status"] == "partial"
    assert ".semgrep/rules.yml" in semgrep_status["health"]["workspace_config_files"]
    assert codeql_status["resolved_provider"] == "codeql"
    assert codeql_status["status"] == "partial"
    assert ".github/codeql/config.yml" in codeql_status["health"]["workspace_config_files"]
    assert openapi_status["resolved_provider"] == "openapi"
    assert openapi_status["status"] == "partial"
    assert "openapi.yaml" in openapi_status["health"]["workspace_config_files"]
    assert swagger_status["resolved_provider"] == "swagger"
    assert swagger_status["status"] == "partial"
    assert "swagger.yaml" in swagger_status["health"]["workspace_config_files"]
    assert firebase_auth_status["resolved_provider"] == "firebase_auth"
    assert firebase_auth_status["status"] == "partial"
    assert "firebase.json" in firebase_auth_status["health"]["workspace_config_files"]
    assert supabase_auth_status["resolved_provider"] == "supabase_auth"
    assert supabase_auth_status["status"] == "partial"
    assert "supabase/config.toml" in supabase_auth_status["health"]["workspace_config_files"]
    assert auth0_status["resolved_provider"] == "auth0"
    assert auth0_status["status"] == "partial"
    assert ".auth0/config.json" in auth0_status["health"]["workspace_config_files"]


def test_workspace_token_detection_resolves_provider_identity_without_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    doppler_workspace = tmp_path / "doppler-token-repo"
    doppler_workspace.mkdir(parents=True, exist_ok=True)
    (doppler_workspace / "README.md").write_text("Doppler manages runtime secrets.\n", encoding="utf-8")

    vault_workspace = tmp_path / "vault-token-repo"
    vault_workspace.mkdir(parents=True, exist_ok=True)
    (vault_workspace / "README.md").write_text("Vault stores runtime secrets.\n", encoding="utf-8")

    sourcegraph_workspace = tmp_path / "sourcegraph-token-repo"
    sourcegraph_workspace.mkdir(parents=True, exist_ok=True)
    (sourcegraph_workspace / "README.md").write_text("Sourcegraph indexes this codebase.\n", encoding="utf-8")

    zoekt_workspace = tmp_path / "zoekt-token-repo"
    zoekt_workspace.mkdir(parents=True, exist_ok=True)
    (zoekt_workspace / "README.md").write_text("Zoekt powers code search here.\n", encoding="utf-8")

    stripe_workspace = tmp_path / "stripe-token-repo"
    stripe_workspace.mkdir(parents=True, exist_ok=True)
    (stripe_workspace / "README.md").write_text("Stripe handles sandbox billing.\n", encoding="utf-8")

    vllm_workspace = tmp_path / "vllm-token-repo"
    vllm_workspace.mkdir(parents=True, exist_ok=True)
    (vllm_workspace / "README.md").write_text("vLLM serves local models.\n", encoding="utf-8")

    doppler_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(doppler_workspace),
            project_name="Doppler Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]
    vault_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(vault_workspace),
            project_name="Vault Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["secrets"]
    sourcegraph_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(sourcegraph_workspace),
            project_name="Sourcegraph Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["code_search"]
    zoekt_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(zoekt_workspace),
            project_name="Zoekt Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["code_search"]
    stripe_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(stripe_workspace),
            project_name="Stripe Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["payments"]
    vllm_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(vllm_workspace),
            project_name="vLLM Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["local_model_runtimes"]

    assert doppler_status["resolved_provider"] == "doppler"
    assert doppler_status["status"] == "partial"
    assert vault_status["resolved_provider"] == "vault"
    assert vault_status["status"] == "partial"
    assert sourcegraph_status["resolved_provider"] == "sourcegraph"
    assert sourcegraph_status["status"] == "partial"
    assert zoekt_status["resolved_provider"] == "zoekt"
    assert zoekt_status["status"] == "partial"
    assert stripe_status["resolved_provider"] == "stripe"
    assert stripe_status["status"] == "partial"
    assert vllm_status["resolved_provider"] == "vllm"
    assert vllm_status["status"] == "partial"


def test_provider_specific_preview_supports_insomnia_hidden_workspace_collection(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "insomnia-hidden-repo"
    (workspace / ".insomnia").mkdir(parents=True, exist_ok=True)
    (workspace / ".insomnia" / "collection.json").write_text('{"resources":[]}\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "inso" else None,
    )

    preview = preview_integration_action(
        family_id="api_clients",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Insomnia Hidden Workspace Demo",
    )

    assert preview["provider"] == "insomnia"
    assert preview["defaulted_params"] == {"collection": ".insomnia/collection.json"}
    assert preview["command"] == 'inso run test ".insomnia/collection.json"'


def test_project_integrations_detect_vllm_cli_metadata(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "vllm-ready-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("vLLM serves local models.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command == "vllm" else None,
    )

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="vLLM Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["local_model_runtimes"]

    assert status["resolved_provider"] == "vllm"
    assert status["resolved_cli_candidates"] == ["vllm"]
    assert status["health"]["resolved_cli_detected"] == ["vllm"]


def test_workspace_token_detection_resolves_scanner_providers_without_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    snyk_workspace = tmp_path / "snyk-token-repo"
    snyk_workspace.mkdir(parents=True, exist_ok=True)
    (snyk_workspace / "README.md").write_text("Snyk scans dependencies before release.\n", encoding="utf-8")

    semgrep_workspace = tmp_path / "semgrep-token-repo"
    semgrep_workspace.mkdir(parents=True, exist_ok=True)
    (semgrep_workspace / "README.md").write_text("Semgrep rules protect this repo.\n", encoding="utf-8")

    trivy_workspace = tmp_path / "trivy-token-repo"
    trivy_workspace.mkdir(parents=True, exist_ok=True)
    (trivy_workspace / "README.md").write_text("Trivy scans container images here.\n", encoding="utf-8")

    snyk_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(snyk_workspace),
            project_name="Snyk Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]
    semgrep_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(semgrep_workspace),
            project_name="Semgrep Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]
    trivy_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(trivy_workspace),
            project_name="Trivy Token Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]

    assert snyk_status["resolved_provider"] == "snyk"
    assert snyk_status["status"] == "partial"
    assert semgrep_status["resolved_provider"] == "semgrep"
    assert semgrep_status["status"] == "partial"
    assert trivy_status["resolved_provider"] == "trivy"
    assert trivy_status["status"] == "partial"


def test_workspace_config_detection_resolves_snyk_provider_without_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    workspace = tmp_path / "snyk-config-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".snyk").write_text("version: v1.25.0\n", encoding="utf-8")

    status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Snyk Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["security_scanners"]

    assert status["resolved_provider"] == "snyk"
    assert status["status"] == "partial"
    assert ".snyk" in status["health"]["workspace_config_files"]


def test_provider_specific_preview_surfaces_scanner_spec_search_and_vllm_guidance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"snyk", "semgrep", "trivy", "codeql", "swagger-cli", "src", "zoekt-query", "vllm"}
        else None,
    )

    snyk_preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["snyk"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Snyk Guidance Demo",
    )
    semgrep_preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["semgrep"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Semgrep Guidance Demo",
    )
    trivy_preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["trivy"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Trivy Guidance Demo",
    )
    codeql_preview = preview_integration_action(
        family_id="security_scanners",
        action_id="scan",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["codeql"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="CodeQL Guidance Demo",
    )

    openapi_workspace = tmp_path / "openapi-guidance-repo"
    openapi_workspace.mkdir(parents=True, exist_ok=True)
    (openapi_workspace / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    swagger_workspace = tmp_path / "swagger-guidance-repo"
    swagger_workspace.mkdir(parents=True, exist_ok=True)
    (swagger_workspace / "swagger.yaml").write_text('swagger: "2.0"\n', encoding="utf-8")

    openapi_preview = preview_integration_action(
        family_id="openapi",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(openapi_workspace),
        project_name="OpenAPI Guidance Demo",
    )
    swagger_preview = preview_integration_action(
        family_id="openapi",
        action_id="validate",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(swagger_workspace),
        project_name="Swagger Guidance Demo",
    )
    sourcegraph_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "ManagerService"},
        registry_payload=normalize_integration_registry(
            {"connections": {"code_search": {"family": "code_search", "status": "connected", "providers": ["sourcegraph"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Sourcegraph Guidance Demo",
    )
    zoekt_preview = preview_integration_action(
        family_id="code_search",
        action_id="search",
        params={"query": "ManagerService"},
        registry_payload=normalize_integration_registry(
            {"connections": {"code_search": {"family": "code_search", "status": "connected", "providers": ["zoekt"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Zoekt Guidance Demo",
    )
    vllm_preview = preview_integration_action(
        family_id="local_model_runtimes",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"local_model_runtimes": {"family": "local_model_runtimes", "status": "connected", "providers": ["vllm"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="vLLM Guidance Demo",
    )

    assert any("dependency graph" in note.lower() for note in snyk_preview["notes"])
    assert any("ruleset" in note.lower() for note in semgrep_preview["notes"])
    assert any("artifact or repository contents" in note.lower() for note in trivy_preview["notes"])
    assert any("query-pack" in note.lower() for note in codeql_preview["notes"])
    assert any("current spec file" in note.lower() for note in openapi_preview["notes"])
    assert any("current spec file" in note.lower() for note in swagger_preview["notes"])
    assert any("live indexed search state" in note.lower() for note in sourcegraph_preview["notes"])
    assert any("live index state" in note.lower() for note in zoekt_preview["notes"])
    assert any("local model-server state" in note.lower() for note in vllm_preview["notes"])


def test_workspace_config_detection_resolves_package_registry_providers_without_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    docker_workspace = tmp_path / "dockerhub-config-repo"
    docker_workspace.mkdir(parents=True, exist_ok=True)
    (docker_workspace / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    nuget_workspace = tmp_path / "nuget-config-repo"
    nuget_workspace.mkdir(parents=True, exist_ok=True)
    (nuget_workspace / "demo.nuspec").write_text("<package/>\n", encoding="utf-8")

    rubygems_workspace = tmp_path / "rubygems-config-repo"
    rubygems_workspace.mkdir(parents=True, exist_ok=True)
    (rubygems_workspace / "Gemfile").write_text('source "https://rubygems.org"\n', encoding="utf-8")

    docker_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(docker_workspace),
            project_name="Docker Hub Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]
    nuget_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(nuget_workspace),
            project_name="NuGet Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]
    rubygems_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(rubygems_workspace),
            project_name="RubyGems Config Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]

    assert docker_status["resolved_provider"] == "docker_hub"
    assert docker_status["status"] == "partial"
    assert "Dockerfile" in docker_status["health"]["workspace_config_files"]
    assert nuget_status["resolved_provider"] == "nuget"
    assert nuget_status["status"] == "partial"
    assert "demo.nuspec" in nuget_status["health"]["workspace_config_files"]
    assert rubygems_status["resolved_provider"] == "rubygems"
    assert rubygems_status["status"] == "partial"
    assert "Gemfile" in rubygems_status["health"]["workspace_config_files"]


def test_project_integrations_detect_package_registry_provider_specific_cli_from_workspace(monkeypatch, tmp_path) -> None:
    docker_workspace = tmp_path / "dockerhub-ready-repo"
    docker_workspace.mkdir(parents=True, exist_ok=True)
    (docker_workspace / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")

    nuget_workspace = tmp_path / "nuget-ready-repo"
    nuget_workspace.mkdir(parents=True, exist_ok=True)
    (nuget_workspace / "demo.nuspec").write_text("<package/>\n", encoding="utf-8")

    rubygems_workspace = tmp_path / "rubygems-ready-repo"
    rubygems_workspace.mkdir(parents=True, exist_ok=True)
    (rubygems_workspace / "Gemfile").write_text('source "https://rubygems.org"\n', encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"docker", "dotnet", "gem"} else None,
    )

    docker_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(docker_workspace),
            project_name="Docker Hub Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]
    nuget_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(nuget_workspace),
            project_name="NuGet Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]
    rubygems_status = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(rubygems_workspace),
            project_name="RubyGems Ready Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }["package_registries"]

    assert docker_status["resolved_provider"] == "docker_hub"
    assert docker_status["resolved_cli_candidates"] == ["docker"]
    assert docker_status["health"]["resolved_cli_detected"] == ["docker"]
    assert docker_status["status"] == "ready"
    assert nuget_status["resolved_provider"] == "nuget"
    assert nuget_status["resolved_cli_candidates"] == ["dotnet"]
    assert nuget_status["health"]["resolved_cli_detected"] == ["dotnet"]
    assert nuget_status["status"] == "ready"
    assert rubygems_status["resolved_provider"] == "rubygems"
    assert rubygems_status["resolved_cli_candidates"] == ["gem"]
    assert rubygems_status["health"]["resolved_cli_detected"] == ["gem"]
    assert rubygems_status["status"] == "ready"


def test_provider_specific_preview_surfaces_package_registry_and_docusaurus_guidance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"npm", "twine", "mvn", "cargo", "dotnet", "gem", "docker"}
        else None,
    )

    docusaurus_workspace = tmp_path / "docusaurus-guidance-repo"
    docusaurus_workspace.mkdir(parents=True, exist_ok=True)
    (docusaurus_workspace / "docusaurus.config.ts").write_text("export default {};\n", encoding="utf-8")

    npm_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["npm"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="npm Guidance Demo",
    )
    pypi_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["pypi"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="PyPI Guidance Demo",
    )
    maven_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["maven"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Maven Guidance Demo",
    )
    crates_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["crates"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="crates.io Guidance Demo",
    )
    nuget_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["nuget"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="NuGet Guidance Demo",
    )
    rubygems_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["rubygems"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="RubyGems Guidance Demo",
    )
    dockerhub_preview = preview_integration_action(
        family_id="package_registries",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry(
            {"connections": {"package_registries": {"family": "package_registries", "status": "connected", "providers": ["docker_hub"], "connection_source": "mission_control", "host_imported": False}}},
            {},
        ),
        workspace_path=None,
        project_name="Docker Hub Guidance Demo",
    )
    docusaurus_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="sync",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(docusaurus_workspace),
        project_name="Docusaurus Guidance Demo",
    )

    assert any("current auth/session and registry configuration" in note.lower() for note in npm_preview["notes"])
    assert any("upload environment" in note.lower() for note in pypi_preview["notes"])
    assert any("build and repository configuration" in note.lower() for note in maven_preview["notes"])
    assert any("crates.io inspection uses the local cargo cli" in note.lower() for note in crates_preview["notes"])
    assert any("nuget inspection uses the local cli" in note.lower() for note in nuget_preview["notes"])
    assert any("rubygems inspection uses the local cli" in note.lower() for note in rubygems_preview["notes"])
    assert any("local docker cli" in note.lower() and "local engine and auth context" in note.lower() for note in dockerhub_preview["notes"])
    assert any("does not claim a live remote publish by itself" in note.lower() for note in docusaurus_preview["notes"])


def test_provider_specific_action_overrides_relax_local_devcontainer_and_docusaurus_semantics(monkeypatch, tmp_path) -> None:
    devcontainer_workspace = tmp_path / "devcontainer-override-repo"
    (devcontainer_workspace / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (devcontainer_workspace / ".devcontainer" / "devcontainer.json").write_text("{}\n", encoding="utf-8")

    docusaurus_workspace = tmp_path / "docusaurus-override-repo"
    docusaurus_workspace.mkdir(parents=True, exist_ok=True)
    (docusaurus_workspace / "docusaurus.config.ts").write_text("export default {};\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"devcontainer", "npm"} else None,
    )

    devcontainer_preview = preview_integration_action(
        family_id="containers",
        action_id="open",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(devcontainer_workspace),
        project_name="Devcontainer Override Demo",
    )
    docusaurus_preview = preview_integration_action(
        family_id="docs_systems",
        action_id="sync",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(docusaurus_workspace),
        project_name="Docusaurus Override Demo",
    )

    assert devcontainer_preview["provider"] == "devcontainer"
    assert devcontainer_preview["risk_level"] == "low"
    assert devcontainer_preview["permission_policy"] == "ask_once_per_project"
    assert devcontainer_preview["requires_confirmation"] is False
    assert devcontainer_preview["mutates_remote_state"] is False
    assert devcontainer_preview["provider_guidance"] == devcontainer_preview["notes"][-1]
    assert "mutates remote state" not in devcontainer_preview["provider_guidance"].lower()

    assert docusaurus_preview["provider"] == "docusaurus"
    assert docusaurus_preview["risk_level"] == "low"
    assert docusaurus_preview["permission_policy"] == "ask_once_per_project"
    assert docusaurus_preview["requires_confirmation"] is False
    assert docusaurus_preview["mutates_remote_state"] is False
    assert docusaurus_preview["provider_guidance"] == docusaurus_preview["notes"][-1]


def test_provider_specific_action_overrides_relax_local_validation_lanes(monkeypatch, tmp_path) -> None:
    postman_workspace = tmp_path / "postman-override-repo"
    postman_workspace.mkdir(parents=True, exist_ok=True)
    (postman_workspace / "orders.postman_collection.json").write_text("{}\n", encoding="utf-8")

    insomnia_workspace = tmp_path / "insomnia-override-repo"
    (insomnia_workspace / ".insomnia").mkdir(parents=True, exist_ok=True)
    (insomnia_workspace / ".insomnia" / "collection.json").write_text("{}\n", encoding="utf-8")

    bruno_workspace = tmp_path / "bruno-override-repo"
    bruno_workspace.mkdir(parents=True, exist_ok=True)
    (bruno_workspace / "bruno.json").write_text("{}\n", encoding="utf-8")

    openapi_workspace = tmp_path / "openapi-override-repo"
    openapi_workspace.mkdir(parents=True, exist_ok=True)
    (openapi_workspace / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")

    swagger_workspace = tmp_path / "swagger-override-repo"
    swagger_workspace.mkdir(parents=True, exist_ok=True)
    (swagger_workspace / "swagger.yaml").write_text('swagger: "2.0"\n', encoding="utf-8")

    storybook_workspace = tmp_path / "storybook-override-repo"
    (storybook_workspace / ".storybook").mkdir(parents=True, exist_ok=True)
    (storybook_workspace / ".storybook" / "main.ts").write_text("export default {}\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"newman", "inso", "bru", "swagger-cli", "npm", "storybook"}
        else None,
    )

    previews = [
        preview_integration_action(family_id="api_clients", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(postman_workspace), project_name="Postman Override Demo"),
        preview_integration_action(family_id="api_clients", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(insomnia_workspace), project_name="Insomnia Override Demo"),
        preview_integration_action(family_id="api_clients", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(bruno_workspace), project_name="Bruno Override Demo"),
        preview_integration_action(family_id="openapi", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(openapi_workspace), project_name="OpenAPI Override Demo"),
        preview_integration_action(family_id="openapi", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(swagger_workspace), project_name="Swagger Override Demo"),
        preview_integration_action(family_id="storybook", action_id="validate", params={}, registry_payload=normalize_integration_registry({}, {}), workspace_path=str(storybook_workspace), project_name="Storybook Override Demo"),
    ]

    for preview in previews:
        assert preview["risk_level"] == "low"
        assert preview["permission_policy"] == "ask_once_per_project"
        assert preview["requires_confirmation"] is False
        assert preview["mutates_remote_state"] is False
        assert preview["provider_guidance"] == preview["notes"][-1]


def test_project_integrations_surface_effective_action_metadata(monkeypatch, tmp_path) -> None:
    devcontainer_workspace = tmp_path / "effective-metadata-repo"
    (devcontainer_workspace / ".devcontainer").mkdir(parents=True, exist_ok=True)
    (devcontainer_workspace / ".devcontainer" / "devcontainer.json").write_text("{}\n", encoding="utf-8")
    (devcontainer_workspace / "docusaurus.config.ts").write_text("export default {};\n", encoding="utf-8")
    (devcontainer_workspace / "orders.postman_collection.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"devcontainer", "npm", "newman"} else None,
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(devcontainer_workspace),
            project_name="Effective Metadata Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }

    container_open = next(item for item in statuses["containers"]["available_actions"] if item["action_id"] == "open")
    docs_sync = next(item for item in statuses["docs_systems"]["available_actions"] if item["action_id"] == "sync")
    postman_validate = next(item for item in statuses["api_clients"]["available_actions"] if item["action_id"] == "validate")

    assert container_open["provider"] == "devcontainer"
    assert container_open["risk_level"] == "low"
    assert container_open["permission_policy"] == "ask_once_per_project"
    assert container_open["requires_confirmation"] is False
    assert container_open["mutates_remote_state"] is False
    assert docs_sync["provider"] == "docusaurus"
    assert docs_sync["risk_level"] == "low"
    assert docs_sync["permission_policy"] == "ask_once_per_project"
    assert docs_sync["requires_confirmation"] is False
    assert docs_sync["mutates_remote_state"] is False
    assert postman_validate["provider"] == "postman"
    assert postman_validate["risk_level"] == "low"
    assert postman_validate["permission_policy"] == "ask_once_per_project"
    assert postman_validate["requires_confirmation"] is False
    assert postman_validate["mutates_remote_state"] is False


def test_import_host_state_uses_alias_aware_provider_hints(monkeypatch, tmp_path) -> None:
    codex_root = tmp_path / "codex-host"
    claude_root = tmp_path / "claude-host"
    for rel in [
        "launch darkly/project.json",
        "new relic/account.json",
        "github releases/config.json",
        "helpscout/mailbox.json",
        "lmstudio/models.json",
        "lemon squeezy/store.json",
    ]:
        path = codex_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "integration_registry._host_scan_roots",
        lambda: {"codex": [codex_root], "claude_code": [claude_root]},
    )

    registry = import_host_state(None)
    connections = registry["connections"]

    assert connections["feature_flags"]["providers"] == ["launchdarkly"]
    assert connections["observability"]["providers"] == ["new_relic"]
    assert connections["release_management"]["providers"] == ["github_releases"]
    assert connections["support_desk"]["providers"] == ["help_scout"]
    assert connections["local_model_runtimes"]["providers"] == ["lm_studio"]
    assert connections["payments"]["providers"] == ["lemon_squeezy"]


def test_project_integrations_expose_missing_provider_cli_metadata_for_release_docs_and_tofu(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"changeset", "gh", "npm", "tofu"} else None,
    )

    changesets_root = tmp_path / "changesets"
    (changesets_root / ".changeset").mkdir(parents=True, exist_ok=True)
    (changesets_root / ".changeset" / "config.json").write_text("{}", encoding="utf-8")
    changesets_statuses = build_project_integration_status(
        workspace_path=str(changesets_root),
        project_name="changesets-demo",
        registry_payload=None,
    )
    changesets_status = next(item for item in changesets_statuses if item["family"] == "release_management")
    assert changesets_status["resolved_provider"] == "changesets"
    assert changesets_status["resolved_cli_candidates"] == ["changeset"]
    assert changesets_status["health"]["resolved_cli_detected"] == ["changeset"]

    releases_root = tmp_path / "github-releases"
    releases_root.mkdir(parents=True, exist_ok=True)
    (releases_root / "README.md").write_text("github releases\n", encoding="utf-8")
    releases_statuses = build_project_integration_status(
        workspace_path=str(releases_root),
        project_name="github-releases-demo",
        registry_payload=None,
    )
    releases_status = next(item for item in releases_statuses if item["family"] == "release_management")
    assert releases_status["resolved_provider"] == "github_releases"
    assert releases_status["resolved_cli_candidates"] == ["gh"]
    assert releases_status["health"]["resolved_cli_detected"] == ["gh"]

    docusaurus_root = tmp_path / "docusaurus"
    docusaurus_root.mkdir(parents=True, exist_ok=True)
    (docusaurus_root / "docusaurus.config.js").write_text("export default {};\n", encoding="utf-8")
    docusaurus_statuses = build_project_integration_status(
        workspace_path=str(docusaurus_root),
        project_name="docusaurus-demo",
        registry_payload=None,
    )
    docusaurus_status = next(item for item in docusaurus_statuses if item["family"] == "docs_systems")
    assert docusaurus_status["resolved_provider"] == "docusaurus"
    assert docusaurus_status["resolved_cli_candidates"] == ["npm"]
    assert docusaurus_status["health"]["resolved_cli_detected"] == ["npm"]

    tofu_root = tmp_path / "tofu"
    tofu_root.mkdir(parents=True, exist_ok=True)
    (tofu_root / "tofu.hcl").write_text("terraform {}\n", encoding="utf-8")
    tofu_statuses = build_project_integration_status(
        workspace_path=str(tofu_root),
        project_name="tofu-demo",
        registry_payload=None,
    )
    tofu_status = next(item for item in tofu_statuses if item["family"] == "terraform")
    assert tofu_status["resolved_provider"] == "opentofu"
    assert tofu_status["resolved_cli_candidates"] == ["tofu"]
    assert tofu_status["health"]["resolved_cli_detected"] == ["tofu"]


def test_provider_specific_preview_surfaces_ci_collection_and_tofu_guidance(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"circleci", "buildkite-agent", "newman", "inso", "bru", "tofu"}
        else None,
    )

    circle_root = tmp_path / "circle"
    (circle_root / ".circleci").mkdir(parents=True, exist_ok=True)
    (circle_root / ".circleci" / "config.yml").write_text("version: 2.1\n", encoding="utf-8")
    circle_preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=None,
        workspace_path=str(circle_root),
        project_name="circle-demo",
    )
    assert "CircleCI" in circle_preview["provider_guidance"]
    assert circle_preview["provider_guidance"] == circle_preview["notes"][-1]

    buildkite_root = tmp_path / "buildkite"
    (buildkite_root / ".buildkite").mkdir(parents=True, exist_ok=True)
    (buildkite_root / ".buildkite" / "pipeline.yml").write_text("steps: []\n", encoding="utf-8")
    buildkite_preview = preview_integration_action(
        family_id="ci_cd",
        action_id="inspect",
        params={},
        registry_payload=None,
        workspace_path=str(buildkite_root),
        project_name="buildkite-demo",
    )
    assert "Buildkite" in buildkite_preview["provider_guidance"]
    assert buildkite_preview["provider_guidance"] == buildkite_preview["notes"][-1]

    collection_cases = [
        ("postman", "postman.json", "Postman"),
        ("insomnia", ".insomnia/workspace.json", "Insomnia"),
        ("bruno", "bruno.json", "Bruno"),
    ]
    for provider, relpath, brand in collection_cases:
        root = tmp_path / provider
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        preview = preview_integration_action(
            family_id="api_clients",
            action_id="validate",
            params={},
            registry_payload=None,
            workspace_path=str(root),
            project_name=f"{provider}-demo",
        )
        assert brand in preview["provider_guidance"]
        assert preview["provider_guidance"] == preview["notes"][-1]

    tofu_root = tmp_path / "opentofu"
    tofu_root.mkdir(parents=True, exist_ok=True)
    (tofu_root / "tofu.hcl").write_text("terraform {}\n", encoding="utf-8")
    tofu_preview = preview_integration_action(
        family_id="terraform",
        action_id="validate",
        params={},
        registry_payload=None,
        workspace_path=str(tofu_root),
        project_name="tofu-preview",
    )
    assert "OpenTofu" in tofu_preview["provider_guidance"]
    assert tofu_preview["provider_guidance"] == tofu_preview["notes"][-1]


def test_project_integrations_no_longer_claim_partial_from_standalone_clis_without_context(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "plain-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Plain project documentation only.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"gh", "npm", "newman", "playwright", "snyk", "ollama", "changeset"}
        else None,
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Standalone CLI Demo",
            registry_payload=None,
        )
    }

    for family_id in (
        "source_control",
        "api_clients",
        "browser_testing",
        "package_registries",
        "security_scanners",
        "local_model_runtimes",
        "release_management",
    ):
        status = statuses[family_id]
        assert status["status"] == "needs_setup"
        assert status["health"]["standalone_cli_detected"] is True
        assert status["health"]["signal_sources"] == ["standalone_cli"]
        assert status["local_action_count"] == 0
        assert status["safe_commands"] == []
        assert any("standalone local clis" in blocker.lower() for blocker in status["blockers"])

    source_control_search = next(item for item in statuses["source_control"]["available_actions"] if item["action_id"] == "search")
    api_validate = next(item for item in statuses["api_clients"]["available_actions"] if item["action_id"] == "validate")
    release_draft = next(item for item in statuses["release_management"]["available_actions"] if item["action_id"] == "draft")
    assert source_control_search["status"] == "needs_setup"
    assert api_validate["status"] == "needs_setup"
    assert release_draft["status"] == "needs_setup"


def test_workspace_token_matching_uses_boundaries_for_short_family_tokens(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "boundary-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text(
        "Workshop notes about saws, decision records, snpmodule wrappers, and cdphelper internals.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Boundary Demo",
            registry_payload=None,
        )
    }

    assert statuses["cloud_platforms"]["health"]["workspace_token_hits"] == []
    assert statuses["ci_cd"]["health"]["workspace_token_hits"] == []
    assert statuses["package_registries"]["health"]["workspace_token_hits"] == []
    assert statuses["browser_devtools"]["health"]["workspace_token_hits"] == []
    assert statuses["cloud_platforms"]["status"] == "needs_setup"
    assert statuses["browser_devtools"]["status"] == "needs_setup"


def test_workspace_scanning_no_longer_uses_host_only_tokens_like_chrome(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "chrome-mention-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text(
        "This documentation mentions Chrome and Docker as ordinary product references.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Host Token Boundary Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }

    assert statuses["browser_devtools"]["health"]["workspace_token_hits"] == []
    assert statuses["browser_devtools"]["status"] == "needs_setup"
    assert statuses["package_registries"]["health"]["workspace_token_hits"] == []
    assert statuses["package_registries"]["status"] == "needs_setup"


def test_provider_specific_action_overrides_relax_local_scan_and_runtime_lanes(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "local-safety"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    (workspace / "cypress.config.ts").write_text("export default {};\n", encoding="utf-8")
    (workspace / ".snyk").write_text("version: v1.0.0\n", encoding="utf-8")
    (workspace / ".semgrep").mkdir(parents=True, exist_ok=True)
    (workspace / ".semgrep" / "rules.yml").write_text("rules: []\n", encoding="utf-8")
    (workspace / ".github").mkdir(exist_ok=True)
    (workspace / ".github" / "codeql").mkdir(exist_ok=True)
    (workspace / ".github" / "codeql" / "config.yml").write_text("name: codeql\n", encoding="utf-8")
    (workspace / "trivy.yaml").write_text("scan: true\n", encoding="utf-8")
    (workspace / ".gitleaks.toml").write_text("[allowlist]\n", encoding="utf-8")
    (workspace / "README.md").write_text("ollama and vllm live here\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"playwright", "cypress", "snyk", "semgrep", "codeql", "trivy", "gitleaks", "ollama", "vllm"}
        else None,
    )

    previews = [
        preview_integration_action(family_id="browser_testing", action_id="validate", params={}, registry_payload=None, workspace_path=str(workspace), project_name="Playwright Demo"),
        preview_integration_action(family_id="browser_testing", action_id="validate", params={}, registry_payload=normalize_integration_registry({"connections": {"browser_testing": {"family": "browser_testing", "status": "connected", "providers": ["cypress"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Cypress Demo"),
        preview_integration_action(family_id="security_scanners", action_id="scan", params={}, registry_payload=normalize_integration_registry({"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["snyk"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Snyk Demo"),
        preview_integration_action(family_id="security_scanners", action_id="scan", params={}, registry_payload=normalize_integration_registry({"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["semgrep"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Semgrep Demo"),
        preview_integration_action(family_id="security_scanners", action_id="scan", params={}, registry_payload=normalize_integration_registry({"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["codeql"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="CodeQL Demo"),
        preview_integration_action(family_id="security_scanners", action_id="scan", params={}, registry_payload=normalize_integration_registry({"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["trivy"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Trivy Demo"),
        preview_integration_action(family_id="security_scanners", action_id="scan", params={}, registry_payload=normalize_integration_registry({"connections": {"security_scanners": {"family": "security_scanners", "status": "connected", "providers": ["gitleaks"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Gitleaks Demo"),
        preview_integration_action(family_id="local_model_runtimes", action_id="open", params={}, registry_payload=normalize_integration_registry({"connections": {"local_model_runtimes": {"family": "local_model_runtimes", "status": "connected", "providers": ["ollama"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Ollama Demo"),
        preview_integration_action(family_id="local_model_runtimes", action_id="open", params={}, registry_payload=normalize_integration_registry({"connections": {"local_model_runtimes": {"family": "local_model_runtimes", "status": "connected", "providers": ["vllm"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="vLLM Demo"),
    ]

    for preview in previews:
        assert preview["risk_level"] == "low"
        assert preview["permission_policy"] == "ask_once_per_project"
        assert preview["requires_confirmation"] is False
        assert preview["mutates_remote_state"] is False


def test_provider_specific_action_overrides_relax_local_cloud_release_and_observability_lanes(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "cloud-release"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "sentry.properties").write_text("defaults.url=https://example.invalid\n", encoding="utf-8")
    (workspace / "datadog.yaml").write_text("site: datadoghq.com\n", encoding="utf-8")
    (workspace / ".release-please-manifest.json").write_text("{}\n", encoding="utf-8")
    (workspace / ".changeset").mkdir(parents=True, exist_ok=True)
    (workspace / ".changeset" / "config.json").write_text("{}\n", encoding="utf-8")
    (workspace / ".releaserc").write_text("{}\n", encoding="utf-8")
    (workspace / "README.md").write_text("github releases and cloud workflows\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"aws", "az", "gcloud", "sentry-cli", "datadog-ci", "release-please", "changeset", "semantic-release", "gh"}
        else None,
    )

    previews = [
        preview_integration_action(family_id="cloud_platforms", action_id="open", params={}, registry_payload=normalize_integration_registry({"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["aws"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="AWS Demo"),
        preview_integration_action(family_id="cloud_platforms", action_id="open", params={}, registry_payload=normalize_integration_registry({"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["azure"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Azure Demo"),
        preview_integration_action(family_id="cloud_platforms", action_id="open", params={}, registry_payload=normalize_integration_registry({"connections": {"cloud_platforms": {"family": "cloud_platforms", "status": "connected", "providers": ["gcp"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="GCP Demo"),
        preview_integration_action(family_id="observability", action_id="tail", params={}, registry_payload=normalize_integration_registry({"connections": {"observability": {"family": "observability", "status": "connected", "providers": ["sentry"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Sentry Demo"),
        preview_integration_action(family_id="observability", action_id="tail", params={}, registry_payload=normalize_integration_registry({"connections": {"observability": {"family": "observability", "status": "connected", "providers": ["datadog"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Datadog Demo"),
        preview_integration_action(family_id="release_management", action_id="draft", params={}, registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["release_please"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Release Please Demo"),
        preview_integration_action(family_id="release_management", action_id="draft", params={}, registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["changesets"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="Changesets Demo"),
        preview_integration_action(family_id="release_management", action_id="draft", params={}, registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["semantic_release"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="semantic-release Demo"),
        preview_integration_action(family_id="release_management", action_id="draft", params={}, registry_payload=normalize_integration_registry({"connections": {"release_management": {"family": "release_management", "status": "connected", "providers": ["github_releases"], "connection_source": "mission_control", "host_imported": False}}}, {}), workspace_path=str(workspace), project_name="GitHub Releases Demo"),
    ]

    for preview in previews:
        assert preview["risk_level"] == "low"
        assert preview["permission_policy"] == "ask_once_per_project"
        assert preview["requires_confirmation"] is False
        assert preview["mutates_remote_state"] is False


def test_project_integrations_surface_signal_source_metadata(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "signal-sources"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / ".github").mkdir(exist_ok=True)
    (workspace / ".github" / "workflows").mkdir(exist_ok=True)
    (workspace / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")

    monkeypatch.setattr("integration_registry.shutil.which", lambda command: f"C:/tools/{command}.exe" if command == "gh" else None)

    registry = normalize_integration_registry(
        {
            "connections": {
                "source_control": {
                    "family": "source_control",
                    "status": "connected",
                    "providers": ["github"],
                    "connection_source": "mission_control",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    statuses = build_project_integration_status(
        workspace_path=str(workspace),
        project_name="Signal Sources Demo",
        registry_payload=registry,
    )
    source_control = next(item for item in statuses if item["family"] == "source_control")

    assert source_control["health"]["connection_detected"] is True
    assert source_control["health"]["workspace_signal_detected"] is True
    assert source_control["health"]["host_import_detected"] is False
    assert source_control["health"]["standalone_cli_detected"] is False
    assert source_control["health"]["signal_sources"] == ["connection", "workspace"]


def test_provider_specific_guidance_surfaces_for_source_control_ci_and_deploy_lanes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"gh", "glab", "vercel", "wrangler", "railway"}
        else None,
    )

    cases = [
        ("source_control", "github", "search", {}, "GitHub inspection"),
        ("source_control", "gitlab", "search", {}, "GitLab inspection"),
        ("work_tracking", "github_issues", "search", {}, "GitHub Issues inspection"),
        ("ci_cd", "github_actions", "inspect_run", {"run_id": "42"}, "GitHub Actions run inspection"),
        ("ci_cd", "gitlab_ci", "tail_logs", {"run_id": "42"}, "GitLab CI log inspection"),
        ("hosting_deploy", "vercel", "inspect", {}, "Vercel inspection"),
        ("hosting_deploy", "cloudflare_pages", "tail_logs", {}, "Cloudflare Pages log inspection"),
        ("hosting_deploy", "railway", "deploy", {}, "Railway deploy uses"),
    ]

    for family_id, provider, action_id, params, expected in cases:
        registry = normalize_integration_registry(
            {
                "connections": {
                    family_id: {
                        "family": family_id,
                        "status": "connected",
                        "providers": [provider],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        )
        preview = preview_integration_action(
            family_id=family_id,
            action_id=action_id,
            params=params,
            registry_payload=registry,
            workspace_path=None,
            project_name=f"{provider}-guidance",
        )
        assert expected in preview["provider_guidance"]
        assert preview["provider_guidance"] == preview["notes"][-1]


def test_provider_specific_guidance_surfaces_for_platform_observability_and_devtools_lanes(monkeypatch) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"supabase", "firebase", "neon", "pscale", "sentry-cli", "datadog-ci", "newrelic", "kubectl", "npm", "chrome"}
        else None,
    )

    cases = [
        ("database_platforms", "supabase", "inspect", "Supabase inspection"),
        ("database_platforms", "firebase", "inspect", "Firebase inspection"),
        ("database_platforms", "neon", "inspect", "Neon inspection"),
        ("database_platforms", "planetscale", "inspect", "PlanetScale inspection"),
        ("observability", "sentry", "inspect", "Sentry inspection"),
        ("observability", "datadog", "tail", "Datadog telemetry inspection"),
        ("observability", "new_relic", "inspect", "New Relic inspection"),
        ("kubernetes", "kubernetes", "inspect", "Kubernetes inspection"),
        ("storybook", "storybook", "validate", "Storybook validation"),
        ("browser_devtools", "chrome_devtools", "inspect", "Chrome DevTools inspection"),
        ("browser_devtools", "cdp", "open", "Chrome DevTools Protocol startup"),
    ]

    for family_id, provider, action_id, expected in cases:
        registry = normalize_integration_registry(
            {
                "connections": {
                    family_id: {
                        "family": family_id,
                        "status": "connected",
                        "providers": [provider],
                        "connection_source": "mission_control",
                        "host_imported": False,
                    }
                }
            },
            {},
        )
        preview = preview_integration_action(
            family_id=family_id,
            action_id=action_id,
            params={},
            registry_payload=registry,
            workspace_path=None,
            project_name=f"{provider}-guidance",
        )
        assert expected in preview["provider_guidance"]
        assert preview["provider_guidance"] == preview["notes"][-1]


def test_provider_scoring_suppresses_cli_only_pollution_across_multi_provider_families(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"npm", "gh", "acli", "supabase", "firebase", "neon", "pscale", "src", "zoekt-query", "stripe"}
        else None,
    )

    cases = [
        ("docs_systems", "Notion keeps docs synced.\n", "notion", ["docusaurus"], "docusaurus"),
        ("work_tracking", "Linear plans our sprint work.\n", "linear", ["github_issues", "jira"], "github_issues"),
        ("database_platforms", "Firebase powers auth and data.\n", "firebase", ["supabase", "neon", "planetscale"], "supabase"),
        ("payments", "LemonSqueezy handles test purchases.\n", "lemon_squeezy", ["stripe"], "stripe"),
        ("code_search", "Open Grok powers legacy search.\n", "opengrok", ["sourcegraph", "zoekt"], "sourcegraph"),
    ]

    family_to_repo = {
        "docs_systems": "docs-repo",
        "work_tracking": "work-repo",
        "database_platforms": "data-repo",
        "payments": "payments-repo",
        "code_search": "search-repo",
    }
    for family_id, readme_text, expected_provider, suppressed, polluted in cases:
        workspace = tmp_path / family_to_repo[family_id]
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "README.md").write_text(readme_text, encoding="utf-8")
        status = next(
            item
            for item in build_project_integration_status(
                workspace_path=str(workspace),
                project_name=f"{family_id}-demo",
                registry_payload=normalize_integration_registry({}, {}),
            )
            if item["family"] == family_id
        )
        assert status["resolved_provider"] == expected_provider
        assert polluted not in status["provider_candidates"]
        assert all(provider in status["health"]["cli_only_candidates_suppressed"] for provider in suppressed)
        assert status["health"]["resolved_provider_evidence"]["workspace_token"] == 30
        assert status["health"]["resolved_provider_evidence"]["has_non_cli_evidence"] is True


def test_provider_scoring_breakdown_and_preview_expose_suppressed_cli_only_candidates(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "notion-docs"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Notion keeps docs synced.\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"npm", "mintlify"} else None,
    )

    status = next(
        item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Notion Docs Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
        if item["family"] == "docs_systems"
    )
    preview = preview_integration_action(
        family_id="docs_systems",
        action_id="inspect",
        params={},
        registry_payload=normalize_integration_registry({}, {}),
        workspace_path=str(workspace),
        project_name="Notion Docs Demo",
    )

    assert status["resolved_provider"] == "notion"
    assert status["health"]["provider_signal_breakdown"]["notion"]["workspace_token"] == 30
    assert status["health"]["provider_signal_breakdown"]["docusaurus"]["suppressed_cli_only"] is True
    assert status["health"]["provider_signal_breakdown"]["mintlify"]["suppressed_cli_only"] is True
    assert sorted(status["health"]["cli_only_candidates_suppressed"]) == ["docusaurus", "mintlify"]
    assert preview["resolved_provider_evidence"]["workspace_token"] == 30
    assert preview["provider_signal_breakdown"]["notion"]["has_non_cli_evidence"] is True
    assert sorted(preview["cli_only_candidates_suppressed"]) == ["docusaurus", "mintlify"]


def test_preview_suppresses_family_default_and_provider_specific_commands_without_provider_context(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "plain-repo"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("plain repo\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"gh", "vercel", "supabase", "aws", "playwright", "gitleaks", "ollama", "stripe", "npm", "newman", "swagger-cli", "src", "sentry-cli", "chrome", "release-please"}
        else None,
    )

    cases = [
        ("source_control", "search", "provider_specific", ["github", "gitlab", "bitbucket"]),
        ("hosting_deploy", "inspect", "provider_specific", ["vercel", "netlify", "cloudflare_pages", "railway", "render"]),
        ("database_platforms", "inspect", "provider_specific", ["supabase", "firebase", "neon", "planetscale"]),
        ("cloud_platforms", "inspect", "provider_specific", ["aws", "azure", "gcp"]),
        ("browser_testing", "validate", "provider_specific", ["playwright", "cypress"]),
        ("security_scanners", "scan", "provider_specific", ["dependabot", "gitleaks", "codeql", "snyk", "semgrep", "trivy"]),
        ("local_model_runtimes", "inspect", "provider_specific", ["ollama", "vllm", "lm_studio"]),
        ("payments", "inspect", "provider_specific", ["stripe", "paddle", "lemon_squeezy", "paypal_sandbox"]),
        ("hosting_deploy", "tail_logs", "provider_specific", ["cloudflare_pages", "railway", "render"]),
        ("observability", "tail", "provider_specific", ["sentry", "logrocket", "datadog"]),
        ("docs_systems", "sync", "provider_specific", ["notion", "confluence", "docusaurus"]),
        ("cloud_platforms", "open", "provider_specific", ["aws", "azure", "gcp"]),
        ("api_clients", "inspect", "provider_specific", ["postman", "insomnia", "bruno"]),
        ("api_clients", "validate", "provider_specific", ["postman", "insomnia", "bruno"]),
        ("openapi", "inspect", "provider_specific", ["openapi", "swagger"]),
        ("openapi", "validate", "provider_specific", ["openapi", "swagger"]),
        ("package_registries", "inspect", "provider_specific", ["npm", "pypi", "maven", "crates", "nuget", "rubygems", "docker_hub"]),
        ("package_registries", "publish", "provider_specific", ["npm", "pypi", "maven", "crates", "nuget", "rubygems", "docker_hub"]),
        ("local_model_runtimes", "open", "provider_specific", ["ollama", "vllm", "lm_studio"]),
        ("code_search", "search", "provider_specific", ["sourcegraph", "opengrok", "zoekt"]),
        ("browser_devtools", "inspect", "provider_specific", ["chrome_devtools", "cdp"]),
        ("browser_devtools", "open", "provider_specific", ["chrome_devtools", "cdp"]),
        ("payments", "create", "provider_specific", ["stripe", "paddle", "lemon_squeezy", "paypal_sandbox"]),
        ("auth_providers", "inspect", "provider_specific", ["auth0", "clerk", "workos", "okta", "firebase_auth", "supabase_auth"]),
        ("secrets", "inspect", "provider_specific", ["onepassword", "doppler", "vault", "aws_secrets_manager", "gcp_secret_manager"]),
        ("release_management", "draft", "provider_specific", ["release_please", "changesets", "semantic_release", "github_releases", "launchnotes"]),
        ("release_management", "create", "provider_specific", ["release_please", "changesets", "semantic_release", "github_releases", "launchnotes"]),
    ]
    for family_id, action_id, support_mode, supported in cases:
        preview = preview_integration_action(
            family_id=family_id,
            action_id=action_id,
            params={},
            registry_payload=normalize_integration_registry({}, {}),
            workspace_path=str(workspace),
            project_name="Plain Preview Demo",
        )
        assert preview["provider"] is None
        assert preview["command"] is None
        assert preview["command_ready"] is False
        assert preview["execution_mode"] == "unavailable"
        assert preview["provider_resolution_state"] == "suppressed_cli_only"
        assert preview["context_required"] is True
        assert preview["context_requirement_reason"] == "provider_context_missing"
        assert preview["context_available"] is False
        assert preview["suppressed_command_reason"] == "provider_context_missing"
        assert preview["provider_support_mode"] == support_mode
        assert sorted(preview["supported_providers"]) == sorted(supported)
        assert preview["supported_provider_count"] == len(supported)
        assert preview["provider_lane_resolved"] is False
        assert any("suppressed until mission control has real provider context" in note.lower() for note in preview["notes"])


def test_project_integrations_surface_context_required_for_provider_specific_actions_when_provider_context_is_missing(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "plain-status"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("plain repo\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"gh", "vercel", "supabase", "aws", "newman", "chrome", "stripe", "release-please"} else None,
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Plain Status Demo",
            registry_payload=normalize_integration_registry({}, {}),
        )
    }

    for family_id, action_id, support_mode, supported in (
        ("source_control", "search", "provider_specific", ["github", "gitlab", "bitbucket"]),
        ("hosting_deploy", "inspect", "provider_specific", ["vercel", "netlify", "cloudflare_pages", "railway", "render"]),
        ("database_platforms", "inspect", "provider_specific", ["supabase", "firebase", "neon", "planetscale"]),
        ("cloud_platforms", "inspect", "provider_specific", ["aws", "azure", "gcp"]),
        ("api_clients", "inspect", "provider_specific", ["postman", "insomnia", "bruno"]),
        ("browser_devtools", "inspect", "provider_specific", ["chrome_devtools", "cdp"]),
        ("payments", "create", "provider_specific", ["stripe", "paddle", "lemon_squeezy", "paypal_sandbox"]),
        ("release_management", "draft", "provider_specific", ["release_please", "changesets", "semantic_release", "github_releases", "launchnotes"]),
    ):
        status = statuses[family_id]
        action = next(item for item in status["available_actions"] if item["action_id"] == action_id)
        assert status["health"]["provider_resolution_state"] == "suppressed_cli_only"
        assert action["status"] == "needs_setup"
        assert action["command_template"] is None
        assert action["context_required"] is True
        assert action["context_requirement_reason"] == "provider_context_missing"
        assert action["suppressed_command_reason"] == "provider_context_missing"
        assert action["provider_support_mode"] == support_mode
        assert sorted(action["supported_providers"]) == sorted(supported)
        assert action["supported_provider_count"] == len(supported)
        assert action["provider_lane_resolved"] is False


def test_execute_integration_action_reports_provider_context_block_for_provider_specific_lanes(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "plain-execute"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("plain repo\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"newman", "stripe", "release-please"} else None,
    )

    for family_id, action_id in (
        ("api_clients", "inspect"),
        ("payments", "create"),
        ("release_management", "draft"),
    ):
        result = execute_integration_action(
            family_id=family_id,
            action_id=action_id,
            params={"name": "Test User"} if family_id == "payments" else {},
            registry_payload=normalize_integration_registry({}, {}),
            workspace_path=str(workspace),
            project_name="Plain Execute Demo",
            confirmed=False,
        )
        assert result["status"] == "blocked"
        assert result["command"] is None
        assert result["provider"] is None
        assert result["context_required"] is True
        assert result["context_requirement_reason"] == "provider_context_missing"
        assert result["suppressed_command_reason"] == "provider_context_missing"
        assert "needs real provider context" in result["stderr"].lower()


def test_provider_specific_actions_stay_needs_setup_when_only_family_level_context_exists(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "family-context-only"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("project context exists but no provider identity\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe" if command in {"newman", "chrome", "stripe", "release-please"} else None,
    )

    registry = normalize_integration_registry(
        {
            "connections": {
                "api_clients": {
                    "family": "api_clients",
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                },
                "browser_devtools": {
                    "family": "browser_devtools",
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                },
                "payments": {
                    "family": "payments",
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                },
                "release_management": {
                    "family": "release_management",
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                },
            }
        },
        {},
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Family Context Demo",
            registry_payload=registry,
        )
    }

    for family_id, action_id in (
        ("api_clients", "inspect"),
        ("browser_devtools", "inspect"),
        ("payments", "create"),
        ("release_management", "draft"),
    ):
        action = next(item for item in statuses[family_id]["available_actions"] if item["action_id"] == action_id)
        assert action["status"] == "needs_setup"
        assert action["command_template"] is None
        assert action["execution_mode"] == "unavailable"
        assert action["context_required"] is True
        assert action["context_requirement_reason"] == "provider_context_missing"
        assert action["suppressed_command_reason"] == "provider_context_missing"


def test_connected_families_without_provider_identity_no_longer_claim_ready(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "connected-no-provider"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("generic project context only\n", encoding="utf-8")

    monkeypatch.setattr(
        "integration_registry.shutil.which",
        lambda command: f"C:/tools/{command}.exe"
        if command in {"gh", "vercel", "supabase", "aws", "newman", "chrome", "stripe", "release-please"}
        else None,
    )

    registry = normalize_integration_registry(
        {
            "connections": {
                family_id: {
                    "family": family_id,
                    "status": "connected",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                }
                for family_id in {"source_control", "hosting_deploy", "database_platforms", "cloud_platforms", "api_clients", "browser_devtools", "payments", "release_management"}
            }
        },
        {},
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Connected No Provider Demo",
            registry_payload=registry,
        )
    }

    for family_id in ("source_control", "hosting_deploy", "database_platforms", "cloud_platforms", "api_clients", "browser_devtools", "payments", "release_management"):
        status = statuses[family_id]
        assert status["status"] == "partial"
        assert status["resolved_provider"] is None
        assert status["available_provider_lane_count"] == 0
        assert status["context_blocked_action_count"] >= 1
        assert status["health"]["provider_context_verified"] is False
        assert status["health"]["provider_context_source"] == "connection_family_only"
        assert status["health"]["connection_provider_count"] == 0
        assert status["health"]["connection_without_provider_identity"] is True
        assert any("lacks verified provider identity" in blocker.lower() for blocker in status["blockers"])
        assert any("explicit provider selection" in fix.lower() for fix in status["recommended_fixes"])


def test_workspace_inferred_provider_does_not_upgrade_connected_family_without_verified_provider(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "docs-no-verified-provider"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Notion keeps docs synced.\n", encoding="utf-8")

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    registry = normalize_integration_registry(
        {
            "connections": {
                "docs_systems": {
                    "family": "docs_systems",
                    "status": "connected",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    status = next(
        item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Docs No Provider Demo",
            registry_payload=registry,
        )
        if item["family"] == "docs_systems"
    )

    assert status["status"] == "partial"
    assert status["resolved_provider"] == "notion"
    assert status["available_provider_lane_count"] >= 1
    assert status["verification_blocked_action_count"] == 1
    assert status["health"]["provider_context_verified"] is False
    assert status["health"]["provider_context_source"] == "workspace"
    assert status["health"]["provider_context_status"] == "inferred"
    assert status["health"]["connection_without_provider_identity"] is True
    assert "sync" in status["health"]["verification_blocked_action_ids"]
    assert any("workspace or host signals suggest `notion`" in fix.lower() for fix in status["recommended_fixes"])
    inspect_action = next(item for item in status["available_actions"] if item["action_id"] == "inspect")
    sync_action = next(item for item in status["available_actions"] if item["action_id"] == "sync")
    assert inspect_action["status"] == "available"
    assert inspect_action["provider_context_status"] == "inferred"
    assert inspect_action["provider_verification_required"] is False
    assert sync_action["status"] == "needs_setup"
    assert sync_action["provider_context_status"] == "inferred"
    assert sync_action["provider_verification_required"] is True
    assert sync_action["provider_verification_reason"] == "provider_verification_required"


def test_single_provider_connected_family_still_reports_ready_with_verified_context(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "single-provider-ready"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("kubernetes cluster docs\n", encoding="utf-8")

    monkeypatch.setattr("integration_registry.shutil.which", lambda command: f"C:/tools/{command}.exe" if command == "kubectl" else None)

    registry = normalize_integration_registry(
        {
            "connections": {
                "kubernetes": {
                    "family": "kubernetes",
                    "status": "connected",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                }
            }
        },
        {},
    )

    status = next(
        item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Kubernetes Ready Demo",
            registry_payload=registry,
        )
        if item["family"] == "kubernetes"
    )

    assert status["status"] == "ready"
    assert status["resolved_provider"] == "kubernetes"
    assert status["available_provider_lane_count"] >= 1
    assert status["health"]["provider_context_verified"] is True
    assert status["health"]["provider_context_source"] == "connection"
    assert status["health"]["provider_context_status"] == "verified"
    assert status["health"]["connection_provider_count"] == 0


def test_unverified_guided_remote_mutations_no_longer_claim_available_across_host_backed_families(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "host-backed-unverified"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text(
        "Bitbucket repository workflow. Linear sprint planning. Slack workspace notifications. "
        "Notion keeps docs synced. LaunchDarkly feature flags. Intercom support. "
        "Lemon Squeezy payments. LaunchNotes release updates.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    registry = normalize_integration_registry(
        {
            "connections": {
                family_id: {
                    "family": family_id,
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                }
                for family_id in {"source_control", "work_tracking", "chatops", "docs_systems", "feature_flags", "support_desk", "payments", "release_management"}
            }
        },
        {},
    )

    statuses = {
        item["family"]: item
        for item in build_project_integration_status(
            workspace_path=str(workspace),
            project_name="Host Backed Unverified Demo",
            registry_payload=registry,
        )
    }

    for family_id, action_id, expected_provider in (
        ("source_control", "create", "bitbucket"),
        ("work_tracking", "create", "linear"),
        ("chatops", "create", "slack"),
        ("docs_systems", "sync", "notion"),
        ("feature_flags", "sync", "launchdarkly"),
        ("support_desk", "create", "intercom"),
        ("payments", "create", "lemon_squeezy"),
        ("release_management", "create", "launchnotes"),
    ):
        status = statuses[family_id]
        action = next(item for item in status["available_actions"] if item["action_id"] == action_id)
        assert action["status"] == "needs_setup"
        assert action["provider"] == expected_provider
        assert action["execution_mode"] == "guided_remote"
        assert action["provider_context_status"] == "inferred"
        assert action["provider_verification_required"] is True
        assert action["provider_verification_reason"] == "provider_verification_required"
        assert status["verification_blocked_action_count"] >= 1
        assert action_id in status["health"]["verification_blocked_action_ids"]
        assert any("guided actions remain blocked" in blocker.lower() for blocker in status["blockers"])


def test_preview_and_execute_surface_provider_verification_requirement_for_guided_remote_mutations(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "guided-remote-preview"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "README.md").write_text("Notion keeps docs synced. Slack workspace notifications. LaunchNotes release updates.\n", encoding="utf-8")

    monkeypatch.setattr("integration_registry.shutil.which", lambda _command: None)

    registry = normalize_integration_registry(
        {
            "connections": {
                family_id: {
                    "family": family_id,
                    "status": "partial",
                    "providers": [],
                    "connection_source": "manual",
                    "host_imported": False,
                }
                for family_id in {"docs_systems", "chatops", "release_management"}
            }
        },
        {},
    )

    for family_id, action_id, provider, params in (
        ("docs_systems", "sync", "notion", {}),
        ("chatops", "create", "slack", {"message": "Heads up"}),
        ("release_management", "create", "launchnotes", {}),
    ):
        preview = preview_integration_action(
            family_id=family_id,
            action_id=action_id,
            params=params,
            registry_payload=registry,
            workspace_path=str(workspace),
            project_name="Guided Remote Preview Demo",
        )
        assert preview["provider"] == provider
        assert preview["provider_context_status"] == "inferred"
        assert preview["provider_verification_required"] is True
        assert preview["provider_verification_reason"] == "provider_verification_required"
        assert any("guided remote mutation remains blocked" in note.lower() for note in preview["notes"])

        result = execute_integration_action(
            family_id=family_id,
            action_id=action_id,
            params=params,
            registry_payload=registry,
            workspace_path=str(workspace),
            project_name="Guided Remote Preview Demo",
            confirmed=False,
        )
        assert result["status"] == "blocked"
        assert result["approval_required"] is False
        assert result["provider_verification_required"] is True
        assert result["provider_verification_reason"] == "provider_verification_required"
        assert "must verify the live provider identity" in result["stderr"].lower()
