from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from db import SessionLocal
from diagnostics import open_folder
from manager import service
from models import ApprovalRequest, Project
from runtime_paths import diagnostics_root
from security import redact_text, redact_value, risk_classifier, security_service
from security.path_validation import PathValidationError, resolve_local_path, resolve_relative_to_root


def create_project(client, name: str, workspace_name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"{name} idea",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "auto",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_low_risk_command_classification() -> None:
    result = risk_classifier.classify({"action_type": "command", "command": "python -m pytest"})
    assert result["risk_level"] == "low"
    assert result["recommended_policy"] == "allow_low_risk"
    assert result["external_access_json"]["accesses_network"] is False


def test_package_install_classification() -> None:
    result = risk_classifier.classify({"action_type": "command", "command": "npm install"})
    assert result["risk_level"] == "high"
    assert result["external_access_json"]["accesses_network"] is True
    assert result["derived_flags"]["modifies_package_files"] is True


def test_delete_command_classification() -> None:
    result = risk_classifier.classify({"action_type": "command", "command": "rm -rf dist"})
    assert result["risk_level"] == "critical"
    assert any("delete files" in reason.lower() for reason in result["reasons_json"])


def test_deploy_classification() -> None:
    result = risk_classifier.classify({"action_type": "command", "command": "vercel deploy"})
    assert result["risk_level"] == "high"
    assert result["external_access_json"]["deploys"] is True


def test_write_outside_workspace_classification() -> None:
    result = risk_classifier.classify(
        {
            "action_type": "command",
            "command": "copy-item build C:/outside/build",
            "writes_outside_workspace": True,
        }
    )
    assert result["risk_level"] == "critical"
    assert result["recommended_policy"] == "deny"


def test_redaction_masks_common_secret_patterns() -> None:
    secret_text = "\n".join(
        [
            "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            "Authorization: Bearer top-secret-token",
            "-----BEGIN PRIVATE KEY-----",
            "private-key-material",
            "-----END PRIVATE KEY-----",
        ]
    )
    redacted_text = redact_text(secret_text)
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz123456" not in redacted_text
    assert "top-secret-token" not in redacted_text
    assert "private-key-material" not in redacted_text
    assert "[redacted private key]" in redacted_text

    redacted_value = redact_value(
        {
            "token": "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
            "nested": {"api_key": "xai-secret-value", "safe": "keep me"},
        }
    )
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in str(redacted_value)
    assert redacted_value["nested"]["safe"] == "keep me"


def test_path_validation_rejects_non_local_and_parent_escape_inputs() -> None:
    try:
        resolve_local_path("https://example.com/repo")
    except PathValidationError as exc:
        assert "local filesystem" in str(exc).lower()
    else:
        raise AssertionError("Expected non-local URL to be rejected.")

    root = Path(sample_workspace("path-validation-root"))
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    safe_child = resolve_relative_to_root(root, "src", must_exist=True)
    assert safe_child == (root / "src").resolve()

    try:
        resolve_relative_to_root(root, "../escape")
    except PathValidationError as exc:
        assert "inside the selected root" in str(exc).lower()
    else:
        raise AssertionError("Expected parent escape path to be rejected.")


def test_open_folder_restricts_to_allowed_roots() -> None:
    report_root = diagnostics_root()
    outside = Path(sample_workspace("outside-diagnostics"))
    outside.mkdir(parents=True, exist_ok=True)
    blocked = open_folder(outside, allowed_roots=[report_root])
    assert blocked["ok"] is False
    assert "outside the allowed locations" in blocked["message"].lower()


def test_frontend_static_resolver_rejects_sibling_prefix_escape(monkeypatch, tmp_path) -> None:
    import main

    dist = tmp_path / "dist"
    sibling = tmp_path / "dist-evil"
    dist.mkdir()
    sibling.mkdir()
    (dist / "index.html").write_text("index", encoding="utf-8")
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(main, "_frontend_dist_dir", lambda: dist)

    resolved = main._frontend_file_for_path("../dist-evil/secret.txt")

    assert resolved == dist / "index.html"


def test_security_policy_defaults_and_project_override(client) -> None:
    global_policy = client.get("/api/security/policy")
    assert global_policy.status_code == 200
    assert global_policy.json()["scope"] == "global"
    assert global_policy.json()["default_command_policy"] == "ask"
    assert global_policy.json()["deployment_policy"] == "deny"

    project = create_project(client, "Security Policy", "security-policy")
    project_policy = client.get(f"/api/projects/{project['id']}/security/policy")
    assert project_policy.status_code == 200
    assert project_policy.json()["scope"] == "project"
    assert project_policy.json()["project_id"] == project["id"]
    assert project_policy.json()["high_risk_requires_user"] is True

    updated = client.put(
        f"/api/projects/{project['id']}/security/policy",
        json={
            "default_command_policy": "allow_low_risk",
            "default_tool_policy": "allow_low_risk",
            "network_access_policy": "ask",
            "write_access_policy": "workspace_write",
            "external_account_policy": "ask",
            "deployment_policy": "ask",
            "destructive_action_policy": "critical_approval",
            "auto_approve_low_risk": True,
            "auto_approve_medium_risk": False,
            "high_risk_requires_user": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["default_command_policy"] == "allow_low_risk"
    assert updated.json()["auto_approve_low_risk"] is True


def test_security_risk_assess_endpoint_persists_redacted_record(client) -> None:
    project = create_project(client, "Risk Assess", "risk-assess")
    response = client.post(
        "/api/security/risk-assess",
        json={
            "project_id": project["id"],
            "action_type": "command",
            "title": "Read .env",
            "summary": "Inspect OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
            "command": "type .env",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project["id"]
    assert payload["risk_level"] == "critical"
    assert "abcdefghijklmnopqrstuvwxyz123456" not in payload["summary"]
    assert payload["recommended_policy"] == "deny"


def test_security_widgets_render_policy_and_empty_states(client) -> None:
    project = create_project(client, "Security Widgets", "security-widgets")

    policy_widget = client.post(
        f"/api/projects/{project['id']}/widgets/add",
        json={"widget_type": "Security Policy"},
    )
    assert policy_widget.status_code == 200
    policy_data = client.get(f"/api/widgets/instances/{policy_widget.json()['id']}/data")
    assert policy_data.status_code == 200
    assert policy_data.json()["status"] == "ready"
    assert any(row["label"] == "Command policy" for row in policy_data.json()["data_json"]["rows"])

    audit_widget = client.post(
        f"/api/projects/{project['id']}/widgets/add",
        json={"widget_type": "Approval Audit Log"},
    )
    assert audit_widget.status_code == 200
    audit_data = client.get(f"/api/widgets/instances/{audit_widget.json()['id']}/data")
    assert audit_data.status_code == 200
    assert audit_data.json()["status"] == "empty"


def test_audit_log_create_and_list(client) -> None:
    project_one = create_project(client, "Audit One", "audit-one")
    project_two = create_project(client, "Audit Two", "audit-two")

    db = SessionLocal()
    try:
        first = db.get(Project, project_one["id"])
        second = db.get(Project, project_two["id"])
        assert first is not None
        assert second is not None
        security_service.log_audit(
            db,
            project=first,
            action_type="command",
            action_summary="npm run build",
            risk_level="low",
            decision="approved",
            decided_by="user",
            reason="Safe local build.",
            metadata_json={"token": "sk-proj-abcdefghijklmnopqrstuvwxyz123456"},
        )
        security_service.log_audit(
            db,
            project=second,
            action_type="tool",
            action_summary="Local diagnostics",
            risk_level="medium",
            decision="auto_approved",
            decided_by="policy",
            reason="Allowed by test policy.",
        )
        db.commit()
    finally:
        db.close()

    global_logs = client.get("/api/security/audit-log")
    assert global_logs.status_code == 200
    assert len(global_logs.json()) == 2
    assert "abcdefghijklmnopqrstuvwxyz123456" not in str(global_logs.json())

    project_logs = client.get(f"/api/projects/{project_one['id']}/security/audit-log")
    assert project_logs.status_code == 200
    assert len(project_logs.json()) == 1
    assert project_logs.json()[0]["project_id"] == project_one["id"]


def test_high_risk_cannot_auto_approve_or_allow_for_project(client) -> None:
    project = create_project(client, "High Risk", "high-risk-approval")

    db = SessionLocal()
    try:
        record = db.get(Project, project["id"])
        assert record is not None
        security_service.update_policy(
            db,
            {
                "default_command_policy": "allow_low_risk",
                "default_tool_policy": "allow_low_risk",
                "network_access_policy": "ask",
                "write_access_policy": "workspace_write",
                "external_account_policy": "ask",
                "deployment_policy": "ask",
                "destructive_action_policy": "critical_approval",
                "auto_approve_low_risk": True,
                "auto_approve_medium_risk": True,
                "high_risk_requires_user": True,
            },
            project=record,
        )
        evaluation = security_service.evaluate_action(
            db,
            {
                "action_type": "command",
                "title": "Deploy release",
                "summary": "Ship build to production",
                "command": "vercel deploy",
            },
            project=record,
        )
        assert evaluation["assessment"]["risk_level"] == "high"
        assert evaluation["decision"] == "pending"

        approval = service._create_approval(
            db,
            record,
            request_type="command",
            title="Deploy release",
            reason_short="Ship build to production",
            risk_level="low",
            cwd=record.workspace_path,
            request_payload_json={"command": "vercel deploy", "deploys": True, "accesses_network": True},
        )
        approval_id = approval.id
        db.commit()
    finally:
        db.close()

    rejected = client.post(f"/api/approvals/{approval_id}/allow-for-project", json={"project_id": project["id"]})
    assert rejected.status_code == 400
    assert "cannot be allowed for the whole project" in rejected.json()["detail"].lower()

    db = SessionLocal()
    try:
        stored = db.get(ApprovalRequest, approval_id)
        assert stored is not None
        assert stored.project_id == project["id"]
        assert stored.status == "pending"
    finally:
        db.close()
