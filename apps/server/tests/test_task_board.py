from __future__ import annotations

from models import Agent, Task
from task_board import can_assign_task, paths_conflict


def test_paths_conflict_detects_nested_overlap() -> None:
    assert paths_conflict(["src/api"], ["src"])
    assert paths_conflict(["src"], ["src/api"])
    assert not paths_conflict(["src/api"], ["tests"])


def test_can_assign_task_keeps_path_safety_in_git_workspace() -> None:
    agent = Agent(id=1, project_id=1, name="Builder A", role="Implementation", kind="worker", status="idle", workspace_path="C:/repo")
    other = Agent(
        id=2,
        project_id=1,
        name="Builder B",
        role="Implementation",
        kind="worker",
        status="working",
        workspace_path="C:/repo",
        locked_paths_json=["src"],
    )
    task = Task(
        id=10,
        project_id=1,
        title="Fix overlapping code path",
        goal="Touch the same service tree.",
        scope="Update the overlapping implementation.",
        agent_role="Implementation",
        milestone="Milestone 1",
        allowed_paths_json=["src/api"],
        forbidden_paths_json=[],
        validation_steps_json=["Run focused tests"],
        success_criteria_json=["Change applied safely"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    assert can_assign_task(agent, task, [agent, other], is_git_workspace=True) is False
