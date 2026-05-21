from __future__ import annotations

from conftest import sample_workspace
from models import Agent, Project, Task
from prompts import build_prompt_profile, manager_action_prompt, manager_interview_prompt, manager_swarm_prompt, worker_task_prompt


def test_build_prompt_profile_prefers_compact_local_rules_for_small_ollama_model() -> None:
    profile = build_prompt_profile(provider="ollama", model="qwen2.5:7b", reasoning_effort="medium")

    assert profile.tier == "weak_local"
    assert profile.label == "compact local model"
    assert any("smallest valid output shape" in rule for rule in profile.manager_rules)


def test_manager_action_prompt_includes_elite_model_guidance() -> None:
    project = Project(name="Prompt Demo", idea="Ship a reliable backend flow", workspace_path=sample_workspace("prompt-manager"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="plan.generate",
        objective="Produce a tight MVP plan.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the backend workflow."},
        user_name="Operator",
        provider="codex",
        model="gpt-5.5",
        reasoning_effort="high",
    )

    assert "Treat the current model as: elite planner." in prompt
    assert "evaluate multiple plausible approaches before choosing one" in prompt
    assert "These are default biases, not hard laws." in prompt


def test_manager_action_prompt_adds_compact_decomposition_biases_for_weak_model() -> None:
    project = Project(name="Prompt Demo", idea="Ship a reliable backend flow", workspace_path=sample_workspace("prompt-decompose"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_action_prompt(
        project,
        docs_path=f"{project.workspace_path}/mission-control",
        action="tasks.decompose",
        objective="Turn the plan into execution-ready tasks.",
        response_schema={"summary_markdown": "string"},
        payload={"goal": "Fix the backend workflow."},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Task-specific decision biases:" in prompt
    assert "Default to a compact task set with crisp titles and minimal overlap." in prompt
    assert "Prefer concrete path or subsystem boundaries over vague phases." in prompt


def test_manager_interview_prompt_adds_high_signal_biases_without_becoming_rigid() -> None:
    project = Project(name="Prompt Demo", idea="Build a local-first tool", workspace_path=sample_workspace("prompt-interview"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_interview_prompt(
        project,
        action="interview.strategy",
        objective="Generate the first adaptive interview batch.",
        payload={"known": [], "unknowns": ["runtime", "scope"]},
        response_schema={"next_questions": []},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Prefer 2-3 sharp questions in the next batch unless the payload makes more strictly necessary." in prompt
    assert "These are default biases, not hard laws." in prompt


def test_manager_swarm_prompt_adds_conservative_biases_for_weak_model() -> None:
    project = Project(name="Prompt Demo", idea="Parallelize a medium codebase safely", workspace_path=sample_workspace("prompt-swarm"), status="draft", runner_mode="auto", manager_mode="auto")

    prompt = manager_swarm_prompt(
        project,
        payload={"goal": "Parallelize work safely."},
        response_schema={"specs": []},
        user_name="Operator",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Default to a conservative roster and low coordination complexity unless the payload strongly justifies expansion." in prompt
    assert "Avoid duplicate specialists unless their path ownership or mission is clearly different." in prompt


def test_worker_task_prompt_includes_weak_model_guardrails() -> None:
    project = Project(name="Prompt Demo", idea="Fix a failing function", workspace_path=sample_workspace("prompt-worker"), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=2,
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Correct the failing behavior in the implementation.",
        scope="Update only the src implementation needed for the fix.",
        agent_role="Implementation",
        milestone="Milestone 1",
        allowed_paths_json=["src"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused test command"],
        success_criteria_json=["The expected behavior is restored"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Treat the current model as: compact local model." in prompt
    assert "Favor one narrow change at a time" in prompt
    assert "Do not claim a fix, refactor, or validation result unless the output proves it directly." in prompt


def test_worker_task_prompt_adds_validation_biases_for_non_edit_task() -> None:
    project = Project(name="Prompt Demo", idea="Investigate a failure", workspace_path=sample_workspace("prompt-validate"), status="building", runner_mode="auto", manager_mode="auto")
    agent = Agent(project_id=1, name="Worker", role="Validation", kind="worker", status="idle", workspace_path=project.workspace_path)
    task = Task(
        id=3,
        project_id=1,
        title="Reproduce the failing behavior and isolate the smallest broken path",
        goal="Confirm the current failure locally.",
        scope="Inspect the repo and capture focused validation evidence.",
        agent_role="Validation",
        milestone="Milestone 1",
        allowed_paths_json=["src", "tests"],
        forbidden_paths_json=["docs"],
        validation_steps_json=["Run the focused test command"],
        success_criteria_json=["The failure is reproduced honestly"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )

    prompt = worker_task_prompt(
        project,
        agent,
        task,
        docs_path=f"{project.workspace_path}/mission-control",
        provider="ollama",
        model="qwen2.5:7b",
        reasoning_effort="medium",
    )

    assert "Do not claim file changes for reproduce, inspect, or validation work unless the task explicitly requires an edit." in prompt
    assert "Bias toward crisp evidence capture" in prompt
