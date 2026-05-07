from __future__ import annotations

from pathlib import Path

from models import Agent, Project, Task


TASK_COLUMNS = ["backlog", "assigned", "working", "waiting_on_paths", "needs_review", "done", "blocked"]


def build_initial_tasks(project: Project) -> list[dict]:
    docs_path = str(Path(project.workspace_path) / "mission-control")
    return [
        {
            "title": "Milestone 1: runnable vertical slice foundation",
            "goal": "Create the smallest end-to-end slice that can launch locally and prove the product shape.",
            "scope": "Establish the minimum runnable flow, core wiring, and first-run clarity without expanding into polish work.",
            "agent_role": "Primary implementation",
            "milestone": "Milestone 1 - Runnable vertical slice",
            "allowed_paths_json": ["src", "app", "frontend", "ui"],
            "forbidden_paths_json": [],
            "validation_steps_json": ["Launch the app or workflow locally", "Record the exact run command", "Document blockers if the slice cannot run"],
            "success_criteria_json": ["A real vertical slice exists", "The operator can launch the slice locally"],
            "estimated_complexity": "medium",
            "dependencies_json": [],
            "priority": 10,
        },
        {
            "title": "Milestone 1: operator-facing usability pass",
            "goal": "Tighten the core workflow so a first-time user can understand and use it without guesswork.",
            "scope": "Improve labels, run messaging, and the operator path after the base slice exists.",
            "agent_role": "Secondary implementation",
            "milestone": "Milestone 1 - Runnable vertical slice",
            "allowed_paths_json": ["ui", "frontend", "src"],
            "forbidden_paths_json": ["tests", docs_path],
            "validation_steps_json": ["Walk through the main user path", "Capture the remaining rough edges"],
            "success_criteria_json": ["The main workflow is usable", "The demo is not obviously fake or broken"],
            "estimated_complexity": "small",
            "dependencies_json": [],
            "priority": 20,
        },
        {
            "title": "Milestone 2: validation and handoff",
            "goal": "Verify the MVP, update docs, and prepare the final handoff instructions.",
            "scope": "Focus on tests, validation evidence, run instructions, limitations, and next steps.",
            "agent_role": "Validation, docs, and handoff",
            "milestone": "Milestone 2 - Validation and handoff",
            "allowed_paths_json": ["tests", "docs", docs_path],
            "forbidden_paths_json": [],
            "validation_steps_json": ["Run available tests", "Update final docs", "Prepare handoff notes"],
            "success_criteria_json": ["Validation results are recorded truthfully", "The handoff is actionable for the user"],
            "estimated_complexity": "medium",
            "dependencies_json": [],
            "priority": 30,
        },
    ]


def paths_conflict(left: list[str] | None, right: list[str] | None) -> bool:
    if not left or not right:
        return False
    normalized_left = {path.lower() for path in left}
    normalized_right = {path.lower() for path in right}
    if "." in normalized_left or "." in normalized_right:
        return True
    if normalized_left & normalized_right:
        return True
    return any(
        left_path.startswith(f"{right_path}/") or right_path.startswith(f"{left_path}/")
        for left_path in normalized_left
        for right_path in normalized_right
    )


def conflicting_agents(task: Task, other_agents: list[Agent]) -> list[Agent]:
    return [
        other
        for other in other_agents
        if other.status in {"starting", "working"} and paths_conflict(other.locked_paths_json, task.allowed_paths_json)
    ]


def can_assign_task(agent: Agent, task: Task, other_agents: list[Agent], is_git_workspace: bool) -> bool:
    if task.status not in {"backlog", "assigned", "waiting_on_paths"}:
        return False
    if is_git_workspace:
        return True
    return not any(other.id != agent.id for other in conflicting_agents(task, other_agents))
