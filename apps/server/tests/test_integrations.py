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
    assert any(item["type"] == "host_import_path" and item["host"] == "codex" for item in status["artifacts"])
    assert create_action["required_params"] == ["title", "body", "project_key", "issue_type"]
    assert create_action["command_ready"] is True
    assert create_action["execution_mode"] == "local_cli"
