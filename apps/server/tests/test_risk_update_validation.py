from __future__ import annotations

from sqlalchemy import select

from db import SessionLocal
from models import Agent, Project, RiskRecord, SecurityPolicy, Task
from conftest import sample_workspace


def _create_project(client, name: str, workspace_name: str) -> dict:
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
    assert response.status_code == 200, response.text
    return response.json()


def test_risk_update_rejects_owner_agent_from_another_project(client) -> None:
    project_one = _create_project(client, "Risk Owner Project", "risk-owner-project")
    project_two = _create_project(client, "Foreign Agent Project", "foreign-agent-project")

    db = SessionLocal()
    try:
        foreign_agent = Agent(
            project_id=project_two["id"],
            name="Foreign Worker",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project_two["workspace_path"],
        )
        db.add(foreign_agent)
        db.commit()
        foreign_agent_id = foreign_agent.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project_one['id']}/risks",
        json={
            "title": "Cross-project risk owner",
            "description": "Keep owner validation honest.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project_one["id"]},
        json={"project_id": project_one["id"], "owner_agent_id": foreign_agent_id},
    )
    assert response.status_code == 404
    assert "owner agent" in response.json()["detail"].lower()


def test_risk_update_rejects_related_task_from_another_project(client) -> None:
    project_one = _create_project(client, "Risk Task Project", "risk-task-project")
    project_two = _create_project(client, "Foreign Task Project", "foreign-task-project")

    db = SessionLocal()
    try:
        foreign_task = Task(
            project_id=project_two["id"],
            title="Foreign task",
            goal="This task belongs somewhere else.",
            scope="Do not let another project point at it.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["Stay scoped"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(foreign_task)
        db.commit()
        foreign_task_id = foreign_task.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project_one['id']}/risks",
        json={
            "title": "Cross-project risk task",
            "description": "Keep task validation honest.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project_one["id"]},
        json={"project_id": project_one["id"], "related_task_id": foreign_task_id},
    )
    assert response.status_code == 404
    assert "related task" in response.json()["detail"].lower()


def test_risk_update_rejects_nonexistent_related_refs(client) -> None:
    project = _create_project(client, "Missing Refs Project", "missing-refs-project")
    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Missing refs risk",
            "description": "Do not accept fake references.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    owner_response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project["id"]},
        json={"project_id": project["id"], "owner_agent_id": 999_999},
    )
    assert owner_response.status_code == 404
    assert "owner agent" in owner_response.json()["detail"].lower()

    task_response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project["id"]},
        json={"project_id": project["id"], "related_task_id": 999_999},
    )
    assert task_response.status_code == 404
    assert "related task" in task_response.json()["detail"].lower()


def test_risk_update_rejects_foreign_project_scope_even_without_related_ref_changes(client) -> None:
    project_one = _create_project(client, "Scoped Risk Project", "scoped-risk-project")
    project_two = _create_project(client, "Foreign Scoped Risk Project", "foreign-scoped-risk-project")

    created = client.post(
        f"/api/projects/{project_one['id']}/risks",
        json={
            "title": "Scoped update risk",
            "description": "Do not let foreign projects update this by global id.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project_two["id"]},
        json={"description": "foreign overwrite attempt"},
    )
    assert response.status_code == 404
    assert "this project" in response.json()["detail"].lower()


def test_risk_create_dedupe_updates_mutable_fields(client) -> None:
    project = _create_project(client, "Risk Dedupe Update", "risk-dedupe-update")
    db = SessionLocal()
    try:
        owner = Agent(
            project_id=project["id"],
            name="Risk Owner",
            role="Implementation",
            kind="worker",
            status="idle",
            workspace_path=project["workspace_path"],
        )
        task = Task(
            project_id=project["id"],
            title="Risk Task",
            goal="Validate risk dedupe state",
            scope="Keep risk refs scoped.",
            agent_role="Implementation",
            milestone="Validation",
            allowed_paths_json=[],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["State stays current"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        db.add(owner)
        db.add(task)
        db.commit()
        owner_id = owner.id
        task_id = task.id
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "same risk",
            "description": "first",
            "severity": "low",
            "likelihood": "low",
            "mitigation": "m1",
        },
    )
    assert created.status_code == 200, created.text

    updated = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "same risk",
            "description": "second",
            "severity": "high",
            "likelihood": "high",
            "mitigation": "m2",
            "status": "accepted",
            "owner_agent_id": owner_id,
            "related_task_id": task_id,
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["id"] == created.json()["id"]
    assert payload["description"] == "second"
    assert payload["severity"] == "high"
    assert payload["likelihood"] == "high"
    assert payload["mitigation"] == "m2"
    assert payload["status"] == "accepted"
    assert payload["owner_agent_id"] == owner_id
    assert payload["related_task_id"] == task_id


def test_risk_update_rejects_blank_titles(client) -> None:
    project = _create_project(client, "Risk Blank Title", "risk-blank-title")
    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Scoped risk",
            "description": "Keep titles normalized.",
            "severity": "medium",
            "likelihood": "medium",
        },
    )
    assert created.status_code == 200, created.text

    response = client.patch(
        f"/api/risks/{created.json()['id']}",
        params={"project_id": project["id"]},
        json={"title": "   "},
    )
    assert response.status_code == 404
    assert "cannot be blank" in response.json()["detail"].lower()


def test_risk_create_dedupe_cleans_duplicate_open_rows(client) -> None:
    project = _create_project(client, "Risk Duplicate Cleanup", "risk-duplicate-cleanup")
    db = SessionLocal()
    try:
        db.add_all(
            [
                RiskRecord(
                    project_id=project["id"],
                    title="Same Risk",
                    description="Old",
                    severity="low",
                    likelihood="low",
                    status="open",
                    created_by="manager",
                ),
                RiskRecord(
                    project_id=project["id"],
                    title="Same Risk",
                    description="New",
                    severity="medium",
                    likelihood="medium",
                    status="monitoring",
                    created_by="manager",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Same Risk",
            "description": "Canonical",
            "severity": "high",
            "likelihood": "high",
        },
    )
    assert created.status_code == 200, created.text

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(RiskRecord).where(RiskRecord.project_id == project["id"], RiskRecord.title == "Same Risk")))
        assert len(rows) == 1
        assert rows[0].description == "Canonical"
    finally:
        db.close()


def test_common_risks_endpoint_returns_ascii_detail(client) -> None:
    project = _create_project(client, "Common Risks", "common-risks")
    created = client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Deploy drift",
            "description": "Production deploy may drift from local verification.",
            "severity": "high",
            "likelihood": "medium",
            "status": "open",
        },
    )
    assert created.status_code == 200, created.text

    response = client.get("/api/risks/common")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert any(item["title"] == "Deploy drift" and " | " in item["detail"] for item in payload)
    assert all("â€¢" not in item["detail"] for item in payload)


def test_security_policy_get_prefers_latest_row_and_cleans_duplicates(client) -> None:
    project = _create_project(client, "Security Duplicate Policy", "security-duplicate-policy")
    db = SessionLocal()
    try:
        db.add_all(
            [
                SecurityPolicy(
                    scope="project",
                    project_id=project["id"],
                    default_command_policy="ask",
                    default_tool_policy="ask",
                    network_access_policy="ask",
                    write_access_policy="workspace_write",
                    external_account_policy="ask",
                    deployment_policy="deny",
                    destructive_action_policy="critical_approval",
                    auto_approve_low_risk=False,
                    auto_approve_medium_risk=False,
                    high_risk_requires_user=True,
                ),
                SecurityPolicy(
                    scope="project",
                    project_id=project["id"],
                    default_command_policy="allow_low_risk",
                    default_tool_policy="allow_low_risk",
                    network_access_policy="allow",
                    write_access_policy="limited_paths",
                    external_account_policy="deny",
                    deployment_policy="ask",
                    destructive_action_policy="deny",
                    auto_approve_low_risk=True,
                    auto_approve_medium_risk=True,
                    high_risk_requires_user=False,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/projects/{project['id']}/security/policy")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["default_command_policy"] == "allow_low_risk"
    assert payload["write_access_policy"] == "limited_paths"

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(SecurityPolicy).where(SecurityPolicy.project_id == project["id"])))
        assert len(rows) == 1
    finally:
        db.close()


def test_risk_summary_endpoints_report_counts(client) -> None:
    project = _create_project(client, "Risk Summary", "risk-summary")
    client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Deploy drift",
            "description": "Deployment can drift from local validation.",
            "severity": "high",
            "likelihood": "medium",
            "status": "open",
        },
    )
    client.post(
        f"/api/projects/{project['id']}/risks",
        json={
            "title": "Docs lag",
            "description": "Docs can lag implementation.",
            "severity": "low",
            "likelihood": "high",
            "status": "accepted",
        },
    )

    project_summary = client.get(f"/api/projects/{project['id']}/risks/summary")
    assert project_summary.status_code == 200, project_summary.text
    project_payload = project_summary.json()
    assert project_payload["project_id"] == project["id"]
    assert project_payload["total_count"] == 2
    assert project_payload["open_count"] == 2
    assert project_payload["status_counts"]["open"] == 1
    assert project_payload["status_counts"]["accepted"] == 1
    assert project_payload["severity_counts"]["high"] == 1
    assert len(project_payload["top_risks"]) == 2

    global_summary = client.get("/api/risks/summary")
    assert global_summary.status_code == 200, global_summary.text
    global_payload = global_summary.json()
    assert global_payload["total_count"] >= 2
    assert any(item["project_id"] == project["id"] for item in global_payload["top_risks"])
