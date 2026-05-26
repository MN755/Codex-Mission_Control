from __future__ import annotations

from pathlib import Path

from conftest import sample_workspace
from db import SessionLocal
from models import Plan


def create_project(client, name: str, workspace_name: str) -> dict:
    return client.post(
        "/api/projects",
        json={
            "name": name,
            "idea": f"Build {name}",
            "workspace_path": sample_workspace(workspace_name),
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    ).json()


def create_workspace_layout(workspace_name: str, directories: list[str]) -> str:
    workspace = Path(sample_workspace(workspace_name))
    workspace.mkdir(parents=True, exist_ok=True)
    for directory in directories:
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    return workspace.as_posix()


def update_swarm_preferences(client, project_id: int, **overrides) -> dict:
    payload = {
        "optimization_mode": "balanced",
        "swarm_aggressiveness": "medium",
        "max_agents": 8,
        "require_approval_above_agent_count": 10,
        "allow_dynamic_spawning": True,
        "allow_dynamic_retirement": True,
        "docs_depth": "standard",
        "testing_depth": "standard",
    }
    payload.update(overrides)
    response = client.put(f"/api/projects/{project_id}/swarm/preferences", json=payload)
    assert response.status_code == 200
    return response.json()


def insert_plan(project_id: int, *, version: int = 1, status: str = "pending_approval") -> int:
    db = SessionLocal()
    try:
        plan = Plan(
            project_id=project_id,
            version=version,
            content_markdown="# Plan\n",
            status=status,
            summary_json={"milestones": ["Milestone 1 - Vertical slice"]},
        )
        db.add(plan)
        db.commit()
        return plan.id
    finally:
        db.close()


def test_default_swarm_preferences_created(client) -> None:
    project = create_project(client, "Swarm Defaults", "swarm-defaults")

    response = client.get(f"/api/projects/{project['id']}/swarm/preferences")

    assert response.status_code == 200
    payload = response.json()
    assert payload["optimization_mode"] == "balanced"
    assert payload["swarm_aggressiveness"] == "medium"
    assert payload["max_agents"] == 8


def test_fastest_build_prefers_multiple_implementation_agents(client) -> None:
    project = create_project(client, "Fastest Build", "swarm-fastest")
    update_swarm_preferences(client, project["id"], optimization_mode="fastest_build", swarm_aggressiveness="large", max_agents=8)

    response = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Ship a vertical slice fast."})

    assert response.status_code == 200
    payload = response.json()
    archetypes = [spec["archetype"] for spec in payload["specs"]]
    assert payload["mode"] == "fastest_build"
    assert sum(1 for archetype in archetypes if archetype in {"feature", "backend", "frontend", "integration"}) >= 3
    assert archetypes.count("docs") <= 1


def test_documentation_heavy_spawns_multiple_docs_specialists(client) -> None:
    project = create_project(client, "Docs Swarm", "swarm-docs")
    update_swarm_preferences(client, project["id"], optimization_mode="documentation_heavy", docs_depth="publishable", max_agents=8)

    response = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Produce publishable docs."})

    assert response.status_code == 200
    payload = response.json()
    docs_specs = [spec for spec in payload["specs"] if spec["archetype"] == "docs"]
    assert payload["mode"] == "documentation_heavy"
    assert len(docs_specs) >= 3
    assert any("README" in spec["name"] for spec in docs_specs)
    assert any("API" in spec["name"] for spec in docs_specs)


def test_high_quality_emphasizes_review_test_and_security(client) -> None:
    project = create_project(client, "Quality Swarm", "swarm-quality")
    update_swarm_preferences(
        client,
        project["id"],
        optimization_mode="high_quality",
        testing_depth="release_grade",
        max_agents=8,
    )

    response = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Favor safety and validation."})

    assert response.status_code == 200
    payload = response.json()
    archetypes = {spec["archetype"] for spec in payload["specs"]}
    assert payload["mode"] == "high_quality"
    assert {"test", "reviewer", "security"}.issubset(archetypes)


def test_massive_codebase_generates_repo_mapping_and_subsystem_agents(client) -> None:
    workspace = create_workspace_layout(
        "swarm-massive",
        ["src", "apps", "services", "packages", "docs", "tests", "infra", "data"],
    )
    project = client.post(
        "/api/projects",
        json={
            "name": "Massive Codebase",
            "idea": "Coordinate a large multi-subsystem repository.",
            "workspace_path": workspace,
            "provider": "codex",
            "runner_mode": "dry_run",
            "manager_mode": "deterministic",
        },
    ).json()
    update_swarm_preferences(client, project["id"], optimization_mode="massive_codebase", swarm_aggressiveness="large", max_agents=8)

    response = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Map and split a large repo safely."})

    assert response.status_code == 200
    payload = response.json()
    archetypes = {spec["archetype"] for spec in payload["specs"]}
    assert payload["mode"] == "massive_codebase"
    assert {"research", "architect", "integration"}.issubset(archetypes)
    assert any("Subsystem Builder" in spec["name"] for spec in payload["specs"])


def test_max_agents_and_approval_threshold_are_respected(client) -> None:
    project = create_project(client, "Capped Swarm", "swarm-capped")
    update_swarm_preferences(
        client,
        project["id"],
        optimization_mode="documentation_heavy",
        docs_depth="publishable",
        max_agents=3,
        require_approval_above_agent_count=2,
    )

    response = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Cap the swarm aggressively."})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["specs"]) <= 3
    assert payload["max_agent_count"] == 3
    assert payload["recommended_agent_count"] <= 3
    assert payload["approval_required"] is True
    assert payload["approved_by_user"] is False

    spawn = client.post(f"/api/projects/{project['id']}/swarm/spawn")
    assert spawn.status_code == 400


def test_swarm_specs_are_project_scoped_and_events_are_recorded(client) -> None:
    project_one = create_project(client, "Scoped Swarm One", "swarm-scope-one")
    project_two = create_project(client, "Scoped Swarm Two", "swarm-scope-two")
    update_swarm_preferences(client, project_one["id"], optimization_mode="fastest_build")
    update_swarm_preferences(client, project_two["id"], optimization_mode="documentation_heavy")

    plan_one = client.post(f"/api/projects/{project_one['id']}/swarm/plan", json={"goal": "Plan one."}).json()
    plan_two = client.post(f"/api/projects/{project_two['id']}/swarm/plan", json={"goal": "Plan two."}).json()

    assert all(spec["project_id"] == project_one["id"] for spec in plan_one["specs"])
    assert all(spec["project_id"] == project_two["id"] for spec in plan_two["specs"])

    events = client.get(f"/api/projects/{project_one['id']}/swarm/events").json()
    assert any(event["event_type"] == "swarm_plan_created" for event in events)
    assert any(event["event_type"] == "agent_spec_created" for event in events)


def test_scaling_changes_plan_and_records_events(client) -> None:
    project = create_project(client, "Scale Swarm", "swarm-scale")
    update_swarm_preferences(client, project["id"], optimization_mode="balanced", swarm_aggressiveness="medium", max_agents=8, require_approval_above_agent_count=20)

    original_plan = client.post(f"/api/projects/{project['id']}/swarm/plan", json={"goal": "Start balanced."}).json()
    approve = client.post(f"/api/projects/{project['id']}/swarm/plan/{original_plan['id']}/approve")
    assert approve.status_code == 200
    spawn = client.post(f"/api/projects/{project['id']}/swarm/spawn")
    assert spawn.status_code == 200

    scale_up = client.post(f"/api/projects/{project['id']}/swarm/scale", json={"direction": "up", "reason": "Need more parallel implementation lanes.", "count": 1})
    assert scale_up.status_code == 200
    assert scale_up.json()["swarm_plan"]["id"] != original_plan["id"]

    scale_down = client.post(f"/api/projects/{project['id']}/swarm/scale", json={"direction": "down", "reason": "Too much coordination overhead.", "count": 1})
    assert scale_down.status_code == 200

    events = client.get(f"/api/projects/{project['id']}/swarm/events").json()
    assert any(event["event_type"] == "swarm_scaled_up" for event in events)
    assert any(event["event_type"] == "swarm_scaled_down" for event in events)


def test_swarm_plan_rejects_nonexistent_milestone_id(client) -> None:
    project = create_project(client, "Swarm Missing Milestone", "swarm-missing-milestone")

    response = client.post(
        f"/api/projects/{project['id']}/swarm/plan",
        json={"goal": "Stay scoped.", "milestone_id": 999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Plan not found"


def test_swarm_plan_rejects_foreign_milestone_id(client) -> None:
    project_one = create_project(client, "Swarm Local Milestone", "swarm-local-milestone")
    project_two = create_project(client, "Swarm Foreign Milestone", "swarm-foreign-milestone")
    foreign_plan_id = insert_plan(project_two["id"])

    response = client.post(
        f"/api/projects/{project_one['id']}/swarm/plan",
        json={"goal": "Do not borrow milestones.", "milestone_id": foreign_plan_id},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Plan not found in this project"


def test_approve_swarm_plan_returns_404_for_other_project_plan(client) -> None:
    project_one = create_project(client, "Approve Local Swarm", "approve-local-swarm")
    project_two = create_project(client, "Approve Foreign Swarm", "approve-foreign-swarm")
    foreign_plan = client.post(f"/api/projects/{project_two['id']}/swarm/plan", json={"goal": "Foreign swarm."}).json()

    response = client.post(f"/api/projects/{project_one['id']}/swarm/plan/{foreign_plan['id']}/approve")

    assert response.status_code == 404
    assert "not found in this project" in response.json()["detail"].lower()


def test_revise_swarm_plan_returns_404_for_other_project_plan(client) -> None:
    project_one = create_project(client, "Revise Local Swarm", "revise-local-swarm")
    project_two = create_project(client, "Revise Foreign Swarm", "revise-foreign-swarm")
    foreign_plan = client.post(f"/api/projects/{project_two['id']}/swarm/plan", json={"goal": "Foreign swarm."}).json()

    response = client.post(
        f"/api/projects/{project_one['id']}/swarm/plan/{foreign_plan['id']}/revise",
        json={"note": "Use the actual project plan."},
    )

    assert response.status_code == 404
    assert "not found in this project" in response.json()["detail"].lower()


def test_generate_plan_returns_400_without_interview_session(client) -> None:
    project = create_project(client, "Plan Missing Interview", "plan-missing-interview")

    response = client.post(f"/api/projects/{project['id']}/plan/generate", json={"force_rebuild": True})

    assert response.status_code == 400
    assert "interview session required" in response.json()["detail"].lower()


def test_approve_plan_returns_404_when_project_has_no_plan(client) -> None:
    project = create_project(client, "Approve Missing Plan", "approve-missing-plan")

    response = client.post(f"/api/projects/{project['id']}/plan/approve", json={"action": "approve_build"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Plan not found"


def test_dry_run_swarm_behavior_changes_by_preference(client) -> None:
    fast_project = create_project(client, "Fast Dry Run", "swarm-dry-fast")
    docs_project = create_project(client, "Docs Dry Run", "swarm-dry-docs")
    update_swarm_preferences(client, fast_project["id"], optimization_mode="fastest_build", swarm_aggressiveness="large", max_agents=8)
    update_swarm_preferences(client, docs_project["id"], optimization_mode="documentation_heavy", docs_depth="publishable", max_agents=8)

    fast_plan = client.post(f"/api/projects/{fast_project['id']}/swarm/plan", json={"goal": "Fast slice."}).json()
    docs_plan = client.post(f"/api/projects/{docs_project['id']}/swarm/plan", json={"goal": "Docs swarm."}).json()

    fast_archetypes = [spec["archetype"] for spec in fast_plan["specs"]]
    docs_archetypes = [spec["archetype"] for spec in docs_plan["specs"]]

    assert sum(1 for archetype in fast_archetypes if archetype in {"feature", "backend", "integration"}) >= 3
    assert docs_archetypes.count("docs") >= 3
