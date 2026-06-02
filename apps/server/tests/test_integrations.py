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

    preview = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/preview",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}},
        headers=bridge_headers,
    )
    assert preview.status_code == 200
    assert preview.json()["command"] == 'gh issue create --title "Bridge it" --body "Stop lying about status."'
    assert preview.json()["requires_confirmation"] is True
    assert preview.json()["command_ready"] is True
    assert preview.json()["execution_mode"] == "local_cli"

    execute = client.post(
        f"/api/projects/{project_id}/integrations/source_control/actions/create/execute",
        json={"params": {"title": "Bridge it", "body": "Stop lying about status."}, "confirmed": False},
        headers=bridge_headers,
    )
    assert execute.status_code == 200
    assert execute.json()["status"] == "approval_required"


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

    called = {"ran": False}

    def fake_run(*args, **kwargs):
        called["ran"] = True
        raise AssertionError("subprocess.run should not be called when the executable is missing")

    monkeypatch.setattr("integration_registry.subprocess.run", fake_run)

    result = execute_integration_action(
        family_id="source_control",
        action_id="create",
        params={"title": "Demo", "body": "Body"},
        registry_payload=normalize_integration_registry({}, {}),
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
        registry_payload=normalize_integration_registry({}, {}),
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
