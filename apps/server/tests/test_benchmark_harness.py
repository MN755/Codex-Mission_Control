from __future__ import annotations
import json
import subprocess
from pathlib import Path

import pytest

from benchmark_harness import (
    analyze_task_execution,
    apply_solver_test_patch,
    audit_task_readiness,
    BenchmarkTaskResult,
    BenchmarkTaskSpec,
    HarnessRunConfig,
    ValidationCommandResult,
    benchmark_preflight,
    build_manager_issue_prompt,
    build_meaningful_workspace_diff,
    build_project_issue_context,
    build_repo_context,
    build_workspace_diff,
    checkout_workspace_commit,
    classify_failure_category,
    detect_python_bootstrap_commands,
    detect_setup_commands,
    detect_validation_commands,
    extract_task_summary,
    filter_benchmark_protected_changed_files,
    load_task_manifest,
    meaningful_patch_paths,
    persist_summary,
    recover_timeout_task_result,
    run_evaluator_validation,
    run_validation_commands,
    select_tasks,
    stage_workspace_snapshot,
    summarize_results,
    task_flow_completed,
    task_flow_terminal,
    unwrap_nested_result_payload,
)
from scripts.run_swe_bench_harness import (
    _active_execution_tasks,
    _agent_is_busy,
    _benchmark_workspace_path,
    _command_needs_windows_cpp_toolchain,
    _completion_grace_seconds,
    _detect_local_setup_blocker,
    _ensure_project_write_permission,
    _finalize_workspace_diff,
    _fetch_project_state,
    _poll_run,
    _resolve_adapter_launch,
    _seed_benchmark_project,
    _should_enter_completion_grace,
    _should_run_post_poll_validation,
    _should_stop_for_evaluator_convergence,
    _extract_pytest_plugin_packages,
    _should_request_manager_recovery,
    _select_decision_option,
    _startable_task_sort_key,
    _task_is_restartable_after_prior_start,
    _wrap_command_for_windows_cpp_toolchain,
    _task_launch_was_already_claimed,
    _should_wait_for_transient_launch_block,
    _should_wait_for_worker_capacity,
    _worker_subprocess_timeout_seconds,
)
from scripts.run_swe_bench_harness import _task_has_superseded_waiting_reason as _script_task_has_superseded_waiting_reason
import scripts.run_swe_bench_harness as harness_script


def test_load_task_manifest_supports_jsonl_and_ignores_sensitive_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "tasks.jsonl"
    manifest.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "instance_id": "astropy__1",
                        "problem_statement": "Fix the regression.",
                        "repo_path": "C:/repos/astropy",
                        "validation_commands": ["python -m pytest tests/test_bug.py"],
                        "FAIL_TO_PASS": '["tests/test_bug.py::test_regression"]',
                        "patch": "do not use me",
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    tasks = load_task_manifest(manifest)

    assert len(tasks) == 1
    assert tasks[0].instance_id == "astropy__1"
    assert tasks[0].validation_commands == ["python -m pytest tests/test_bug.py"]
    assert tasks[0].fail_to_pass == ["tests/test_bug.py::test_regression"]
    assert "patch" not in tasks[0].metadata


def test_benchmark_task_spec_to_dict_redacts_sensitive_test_patch() -> None:
    task = BenchmarkTaskSpec(
        instance_id="demo__1",
        problem_statement="Fix the bug.",
        repo_path="C:/repos/demo",
        test_patch="diff --git a/tests/test_bug.py b/tests/test_bug.py",
    )

    public_payload = task.to_dict()
    private_payload = task.to_dict(include_sensitive=True)

    assert "test_patch" not in public_payload
    assert private_payload["test_patch"] == "diff --git a/tests/test_bug.py b/tests/test_bug.py"


def test_detect_python_bootstrap_commands_handles_legacy_setuptools_repo(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools", "setuptools_scm>=6.2", "wheel", "extension-helpers"]',
                "build-backend = 'setuptools.build_meta'",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n", encoding="utf-8")
    package_dir = tmp_path / "demo" / "wcs"
    package_dir.mkdir(parents=True)
    (package_dir / "setup_package.py").write_text(
        "from setuptools.dep_util import newer_group\n",
        encoding="utf-8",
    )

    commands = detect_python_bootstrap_commands(tmp_path)

    assert commands == [
        'python -m pip install --disable-pip-version-check --no-input --no-index "setuptools<70"',
        'python -m pip install --disable-pip-version-check --no-input --no-index setuptools "setuptools_scm>=6.2" wheel extension-helpers',
        "python setup.py egg_info",
        "python setup.py build_ext --inplace --build-temp build-temp --build-lib build-lib",
    ]


def test_detect_python_bootstrap_commands_adds_inplace_build_for_extension_repo(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text(
        "\n".join(
            [
                "from setuptools import Extension, setup",
                "setup(ext_modules=[Extension('demo._speedups', sources=['demo/_speedups.c'])])",
            ]
        ),
        encoding="utf-8",
    )

    commands = detect_python_bootstrap_commands(tmp_path)

    assert commands == [
        "python setup.py egg_info",
        "python setup.py build_ext --inplace --build-temp build-temp --build-lib build-lib",
    ]


def test_detect_python_bootstrap_commands_skips_inplace_build_for_pure_python_repo(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n", encoding="utf-8")

    commands = detect_python_bootstrap_commands(tmp_path)

    assert commands == ["python setup.py egg_info"]


def test_benchmark_workspace_path_defaults_to_repo_local_root(tmp_path: Path) -> None:
    task_output_dir = tmp_path / "tests" / "swe-bench-lite-runs" / "sample-run" / "0001-astropy__astropy-12907"
    workspace_path = _benchmark_workspace_path(task_output_dir)

    assert workspace_path.parent.name == "_swe_bench_workspaces"
    assert workspace_path.name.startswith("0001-astropy__astropy-12907")
    assert "_swe_bench_workspaces" in workspace_path.as_posix()


def test_resolve_adapter_launch_absolutizes_repo_relative_adapter_arg() -> None:
    config = HarnessRunConfig(
        tasks_path="tests/local_swe_bench_smoke_manifest.json",
        output_root="tests/swe-bench-lite-runs",
        run_label="adapter-path",
        adapter_command="python",
        adapter_args=["scripts/ollama_adapter.py"],
    )

    adapter_command, adapter_args = _resolve_adapter_launch(config)

    assert adapter_command == "python"
    assert adapter_args == [harness_script.ADAPTER_PATH.as_posix()]


def test_resolve_adapter_launch_preserves_non_path_adapter_args() -> None:
    config = HarnessRunConfig(
        tasks_path="tests/local_swe_bench_smoke_manifest.json",
        output_root="tests/swe-bench-lite-runs",
        run_label="adapter-flags",
        adapter_command="python",
        adapter_args=["scripts/ollama_adapter.py", "--temperature", "0"],
    )

    _adapter_command, adapter_args = _resolve_adapter_launch(config)

    assert adapter_args[0] == harness_script.ADAPTER_PATH.as_posix()
    assert adapter_args[1:] == ["--temperature", "0"]


def test_ensure_project_write_permission_promotes_imported_read_only_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_call_api(_client, method: str, route: str, _trajectory_path: Path, *, params=None, json_body=None):
        calls.append((method, route, json_body))
        return {"project_id": 1, "write_permission_status": "write_allowed"}

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)

    payload = _ensure_project_write_permission(
        object(),
        {"id": 1, "source_type": "existing_folder", "write_permission_status": "read_only"},
        tmp_path / "trajectory.jsonl",
    )

    assert payload == {"project_id": 1, "write_permission_status": "write_allowed"}
    assert calls == [
        (
            "POST",
            "/api/projects/1/write-permission",
            {"write_permission_status": "write_allowed"},
        )
    ]


def test_ensure_project_write_permission_skips_non_read_only_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_call_api(_client, method: str, route: str, _trajectory_path: Path, *, params=None, json_body=None):
        calls.append((method, route))
        return {}

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)

    payload = _ensure_project_write_permission(
        object(),
        {"id": 1, "source_type": "existing_folder", "write_permission_status": "write_allowed"},
        tmp_path / "trajectory.jsonl",
    )

    assert payload is None
    assert calls == []


def test_seed_benchmark_project_generates_tasks_without_manager_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = HarnessRunConfig(
        tasks_path="tests/local_swe_bench_smoke_manifest.json",
        output_root="tests/swe-bench-lite-runs",
        run_label="seed-project",
        enable_swarm_planning=False,
    )
    calls: list[str] = []

    def fake_call_api(_client, method: str, route: str, _trajectory_path: Path, *, params=None, json_body=None):
        calls.append(f"{method} {route}")
        if route.endswith("/change-requests"):
            return {"id": 7}
        if route.endswith("/tasks/generate"):
            return {"count": 3}
        raise AssertionError(f"Unexpected API call: {method} {route}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)

    payloads = _seed_benchmark_project(
        object(),
        1,
        "Fix the benchmark task.",
        config,
        tmp_path / "trajectory.jsonl",
    )

    assert payloads == {
        "change_request": {"id": 7},
        "task_generation": {"count": 3},
    }
    assert calls == [
        "POST /api/projects/1/change-requests",
        "POST /api/projects/1/tasks/generate",
    ]


def test_extract_pytest_plugin_packages_maps_unrecognized_options() -> None:
    stderr_text = """
ERROR: usage: __main__.py [options] [file_or_dir] [file_or_dir] [...]
__main__.py: error: unrecognized arguments: --doctest-rst --remote-data
"""

    packages = _extract_pytest_plugin_packages(stderr_text)

    assert packages == ["pytest-doctestplus", "pytest-remotedata"]


def test_harness_waits_for_busy_worker_capacity() -> None:
    busy_agents = [
        {"id": 4, "status": "starting", "current_task_id": 5},
        {"id": 2, "status": "idle", "current_task_id": None},
    ]
    idle_agents = [
        {"id": 4, "status": "idle", "current_task_id": None},
    ]

    assert _agent_is_busy(busy_agents[0]) is True
    assert _agent_is_busy(idle_agents[0]) is False
    assert _should_wait_for_worker_capacity("No idle worker is available.", busy_agents) is True
    assert _should_wait_for_worker_capacity("Agent already has an active unfinished run.", busy_agents) is True
    assert _should_wait_for_worker_capacity("Task already has an active unfinished run.", busy_agents) is True
    assert _should_wait_for_worker_capacity("No idle worker is available.", idle_agents) is False
    assert _script_task_has_superseded_waiting_reason({"waiting_reason": "Superseded after Mission Control accepted downstream completed task #3."}) is True
    assert _script_task_has_superseded_waiting_reason({"waiting_reason": "Waiting for path ownership to clear."}) is False


def test_harness_treats_path_conflict_as_transient_when_new_active_work_appears() -> None:
    tasks = [
        {
            "id": 9,
            "status": "working",
            "assigned_agent_id": 6,
        }
    ]
    agents = [
        {
            "id": 6,
            "status": "starting",
            "current_task_id": 9,
        }
    ]

    assert _active_execution_tasks(tasks) == tasks
    assert _should_wait_for_transient_launch_block(
        "Validation Specialist owns astropy/modeling/tests, astropy/modeling",
        tasks,
        agents,
    ) is True


def test_active_execution_tasks_ignores_assigned_dependency_waiters() -> None:
    tasks = [
        {
            "id": 2,
            "status": "blocked",
            "assigned_agent_id": 4,
        },
        {
            "id": 3,
            "status": "assigned",
            "assigned_agent_id": 6,
            "dependencies_json": [2],
            "waiting_reason": "Waiting for task dependencies to finish.",
        },
    ]
    task_statuses = {2: "blocked", 3: "assigned"}

    assert _active_execution_tasks(tasks, task_statuses) == []


def test_active_execution_tasks_ignores_stale_assigned_retry_without_live_worker() -> None:
    tasks = [
        {
            "id": 2,
            "status": "assigned",
            "assigned_agent_id": 4,
            "failure_count": 1,
            "waiting_reason": "Manager requested one fix retry.",
            "dependencies_json": [],
        }
    ]
    agents = [{"id": 4, "status": "waiting", "current_task_id": None}]
    task_statuses = {2: "assigned"}

    assert _active_execution_tasks(tasks, task_statuses, agents) == []


def test_harness_treats_not_startable_as_transient_when_task_was_already_claimed() -> None:
    tasks = [
        {
            "id": 6,
            "status": "working",
            "assigned_agent_id": 4,
        }
    ]
    agents = [
        {
            "id": 4,
            "status": "starting",
            "current_task_id": 6,
        }
    ]

    assert _task_launch_was_already_claimed(6, tasks, agents) is True
    assert _should_wait_for_transient_launch_block(
        "Task is not in a startable state.",
        tasks,
        agents,
        task_id=6,
    ) is True


def test_task_launch_was_already_claimed_ignores_stale_assigned_retry() -> None:
    tasks = [
        {
            "id": 6,
            "status": "assigned",
            "assigned_agent_id": 4,
            "failure_count": 1,
            "waiting_reason": "Manager requested one fix retry.",
        }
    ]
    agents = [{"id": 4, "status": "waiting", "current_task_id": None}]

    assert _task_launch_was_already_claimed(6, tasks, agents) is False


def test_startable_task_sort_key_prefers_runnable_backlog_before_waiting_on_paths() -> None:
    waiting_task = {"id": 4, "status": "waiting_on_paths", "priority": 11}
    backlog_task = {"id": 2, "status": "backlog", "priority": 20}

    ordered = sorted([waiting_task, backlog_task], key=_startable_task_sort_key)

    assert [task["id"] for task in ordered] == [2, 4]


def test_should_request_manager_recovery_only_for_stalled_nonterminal_state() -> None:
    stalled_tasks = [
        {"id": 2, "status": "blocked"},
        {"id": 3, "status": "backlog"},
    ]

    assert _should_request_manager_recovery(
        stalled_tasks,
        [],
        [],
        recovery_attempts_without_progress=0,
    ) is True
    assert _should_request_manager_recovery(
        stalled_tasks,
        [{"id": 1}],
        [],
        recovery_attempts_without_progress=0,
    ) is False
    assert _should_request_manager_recovery(
        stalled_tasks,
        [],
        [{"id": 1}],
        recovery_attempts_without_progress=0,
    ) is False
    assert _should_request_manager_recovery(
        [{"id": 9, "status": "done"}],
        [],
        [],
        recovery_attempts_without_progress=0,
    ) is False
    assert _should_request_manager_recovery(
        stalled_tasks,
        [],
        [],
        recovery_attempts_without_progress=2,
    ) is False


def test_should_enter_completion_grace_only_for_recent_active_work() -> None:
    tasks = [{"id": 3, "status": "working", "assigned_agent_id": 4}]
    agents = [{"id": 4, "status": "working", "current_task_id": 3}]
    task_statuses = {3: "working"}

    assert _should_enter_completion_grace(
        tasks,
        agents,
        task_statuses,
        [],
        [],
        recent_progress_age=5,
        idle_timeout_seconds=60,
    ) is True
    assert _should_enter_completion_grace(
        tasks,
        agents,
        task_statuses,
        [{"id": 1}],
        [],
        recent_progress_age=5,
        idle_timeout_seconds=60,
    ) is False
    assert _should_enter_completion_grace(
        tasks,
        agents,
        task_statuses,
        [],
        [],
        recent_progress_age=120,
        idle_timeout_seconds=30,
    ) is False


def test_should_enter_completion_grace_excludes_dependency_blocked_assigned_tasks() -> None:
    tasks = [
        {
            "id": 2,
            "status": "blocked",
            "assigned_agent_id": 4,
        },
        {
            "id": 3,
            "status": "assigned",
            "assigned_agent_id": 6,
            "dependencies_json": [2],
            "waiting_reason": "Waiting for task dependencies to finish.",
        },
    ]
    agents = [{"id": 6, "status": "waiting", "current_task_id": None}]
    task_statuses = {2: "blocked", 3: "assigned"}

    assert _should_enter_completion_grace(
        tasks,
        agents,
        task_statuses,
        [],
        [],
        recent_progress_age=5,
        idle_timeout_seconds=60,
    ) is False


def test_completion_grace_seconds_is_bounded() -> None:
    fast = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root="out",
        run_label="fast",
        idle_timeout_seconds=5,
    )
    slow = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root="out",
        run_label="slow",
        idle_timeout_seconds=600,
    )
    extended = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root="out",
        run_label="extended",
        idle_timeout_seconds=600,
        task_timeout_seconds=1320,
    )

    assert _completion_grace_seconds(fast) == 30.0
    assert _completion_grace_seconds(slow) == 450.0
    assert _completion_grace_seconds(extended) == 600.0


def test_should_run_post_poll_validation_skips_timeout_without_patch() -> None:
    assert _should_run_post_poll_validation(timed_out=True, patch_applied=False) is False
    assert _should_run_post_poll_validation(timed_out=True, patch_applied=True) is True
    assert _should_run_post_poll_validation(timed_out=False, patch_applied=False) is True


def test_worker_subprocess_timeout_seconds_includes_recovery_slack() -> None:
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root="out",
        run_label="timeout-slack",
        task_timeout_seconds=300,
        validation_timeout_seconds=60,
    )

    assert _worker_subprocess_timeout_seconds(config) == 600


def test_should_stop_for_evaluator_convergence_only_when_fix_is_done_and_open_work_is_validation() -> None:
    converged_tasks = [
        {
            "id": 1,
            "status": "done",
            "title": "Implement the smallest safe code fix",
            "goal": "Correct the confirmed failing behavior with the least invasive code change.",
            "agent_role": "Service Flow Builder",
        },
        {
            "id": 2,
            "status": "working",
            "title": "Re-run focused validation and prepare an honest handoff",
            "goal": "Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            "agent_role": "Validation Specialist",
        },
    ]
    assert _should_stop_for_evaluator_convergence(converged_tasks, [], []) is True

    no_fix_done = [
        {
            "id": 1,
            "status": "working",
            "title": "Implement the smallest safe code fix",
            "goal": "Correct the confirmed failing behavior with the least invasive code change.",
            "agent_role": "Service Flow Builder",
        },
        {
            "id": 2,
            "status": "working",
            "title": "Re-run focused validation and prepare an honest handoff",
            "goal": "Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            "agent_role": "Validation Specialist",
        },
    ]
    assert _should_stop_for_evaluator_convergence(no_fix_done, [], []) is False

    extra_open_fix_lane = [
        {
            "id": 1,
            "status": "done",
            "title": "Implement the smallest safe code fix",
            "goal": "Correct the confirmed failing behavior with the least invasive code change.",
            "agent_role": "Service Flow Builder",
        },
        {
            "id": 2,
            "status": "working",
            "title": "Re-run focused validation and prepare an honest handoff",
            "goal": "Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
            "agent_role": "Validation Specialist",
        },
        {
            "id": 3,
            "status": "backlog",
            "title": "Implement an alternative patch",
            "goal": "Try another code fix.",
            "agent_role": "Service Flow Builder",
        },
    ]
    assert _should_stop_for_evaluator_convergence(extra_open_fix_lane, [], []) is False

    post_validation_retry = [
        {
            "id": 1,
            "status": "done",
            "title": "Implement the smallest safe code fix",
            "goal": "Correct the confirmed failing behavior with the least invasive code change.",
            "agent_role": "Service Flow Builder",
            "milestone": "Milestone 2 - Fix the code",
        },
        {
            "id": 4,
            "status": "working",
            "title": "Implement a fix for duplicate order by clause detection",
            "goal": "Rework implement a fix for duplicate order by clause detection as a surgical patch inside the existing scoped paths. Last blocker to overcome: No verified workspace file changes were produced for a task that requires a concrete fix.",
            "scope": "Resolve a blocker or error before the main flow can continue.",
            "agent_role": "Execution Planner",
            "milestone": "Milestone 3 - Validate and hand off",
        },
    ]
    assert _should_stop_for_evaluator_convergence(post_validation_retry, [], []) is True
    assert _should_stop_for_evaluator_convergence(converged_tasks, [{"id": "pending"}], []) is False


def test_select_decision_option_requests_changes_for_implementation_review() -> None:
    decision = {
        "decision_type": "handoff_review",
        "title": "Review required: Focused retry: Implement the smallest safe code fix",
        "message": "Task needs review before Mission Control can continue.",
        "recommended_option": "approve",
    }
    options = [
        {"id": "approve", "label": "Approve"},
        {"id": "request_changes", "label": "Request changes"},
    ]
    option_by_id = {item["id"]: item for item in options}

    selected = _select_decision_option(decision, option_by_id, options)

    assert selected["id"] == "request_changes"


def test_select_decision_option_requests_changes_for_unverified_validation_review() -> None:
    decision = {
        "decision_type": "handoff_review",
        "title": "Review required: Re-run focused validation and prepare an honest handoff",
        "message": "Task needs review before Mission Control can continue.",
        "recommended_option": "approve",
    }
    options = [
        {"id": "approve", "label": "Approve"},
        {"id": "request_changes", "label": "Request changes"},
    ]
    option_by_id = {item["id"]: item for item in options}

    selected = _select_decision_option(decision, option_by_id, options)

    assert selected["id"] == "request_changes"


def test_select_decision_option_requests_changes_for_rejected_edit_review() -> None:
    decision = {
        "decision_type": "handoff_review",
        "title": "Review required: Focused retry: Implement the smallest safe code fix",
        "message": (
            "Mission Control rejected or could not apply one or more proposed edits. "
            "Mission Control rejected this as a no-change review gate because the task requires verified changed files."
        ),
        "recommended_option": "approve",
    }
    options = [
        {"id": "approve", "label": "Approve"},
        {"id": "request_changes", "label": "Request changes"},
    ]
    option_by_id = {item["id"]: item for item in options}

    selected = _select_decision_option(decision, option_by_id, options)

    assert selected["id"] == "request_changes"


def test_select_decision_option_keeps_recommended_option_for_verified_validation_review() -> None:
    decision = {
        "decision_type": "handoff_review",
        "title": "Review required: Re-run focused validation and prepare an honest handoff",
        "message": "Focused validation passed and the handoff is ready for approval.",
        "recommended_option": "approve",
    }
    options = [
        {"id": "approve", "label": "Approve"},
        {"id": "request_changes", "label": "Request changes"},
    ]
    option_by_id = {item["id"]: item for item in options}

    selected = _select_decision_option(decision, option_by_id, options)

    assert selected["id"] == "approve"


def test_poll_run_requests_manager_recovery_before_deadlock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="recovery-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=5,
        idle_timeout_seconds=2,
        poll_interval_seconds=0,
    )
    state = {"phase": "stalled", "post_recovery_task_polls": 0}
    manager_calls: list[str] = []

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/manager/next-step":
            manager_calls.append(path)
            state["phase"] = "recovered"
            return {"decision_type": "request_fix", "summary_markdown": "Recover the blocked follow-up."}
        if method == "GET" and path == "/api/projects/1/tasks":
            if state["phase"] == "stalled":
                return [
                    {"id": 2, "status": "blocked", "failure_count": 1, "dependencies_json": []},
                    {
                        "id": 3,
                        "status": "backlog",
                        "failure_count": 0,
                        "dependencies_json": [2],
                        "waiting_reason": "Waiting for task dependencies to finish.",
                    },
                ]
            state["post_recovery_task_polls"] += 1
            if state["post_recovery_task_polls"] == 1:
                return [
                    {"id": 6, "status": "working", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": []},
                    {"id": 2, "status": "blocked", "failure_count": 1, "dependencies_json": []},
                    {"id": 3, "status": "backlog", "failure_count": 0, "dependencies_json": [6]},
                ]
            return [
                {"id": 6, "status": "done", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": []},
                {"id": 2, "status": "done", "failure_count": 1, "dependencies_json": []},
                {"id": 3, "status": "done", "failure_count": 0, "dependencies_json": [6]},
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            if state["phase"] == "stalled":
                return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 1}]
            if state["post_recovery_task_polls"] <= 1:
                return [{"id": 4, "status": "working", "current_task_id": 6, "failure_count": 1}]
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 1}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["phase"] == "stalled":
                return []
            if state["post_recovery_task_polls"] <= 1:
                return [{"event_type": "manager.worker_decision"}]
            return [{"event_type": "manager.worker_decision"}, {"event_type": "runner.item.completed"}]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert manager_calls == ["/api/projects/1/manager/next-step"]
    assert poll_result["deadlock_reason"] is None
    assert [task["status"] for task in poll_result["tasks"]] == ["done", "done", "done"]


def test_poll_run_restarts_task_returned_to_backlog_after_review_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="review-retry-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=5,
        idle_timeout_seconds=2,
        poll_interval_seconds=0,
    )
    state = {"phase": "initial"}
    start_calls: list[int] = []

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/tasks/5/start":
            start_calls.append(5)
            if len(start_calls) == 1:
                state["phase"] = "needs_retry"
            else:
                state["phase"] = "completed"
            return {"ok": True}
        if method == "GET" and path == "/api/projects/1/tasks":
            if state["phase"] == "initial":
                return [{"id": 5, "status": "backlog", "failure_count": 0, "dependencies_json": []}]
            if state["phase"] == "needs_retry":
                return [
                    {
                        "id": 5,
                        "status": "backlog",
                        "assigned_agent_id": None,
                        "failure_count": 0,
                        "dependencies_json": [],
                        "waiting_reason": "Review requested changes before Mission Control can continue.",
                    }
                ]
            return [{"id": 5, "status": "done", "failure_count": 0, "dependencies_json": []}]
        if method == "GET" and path == "/api/projects/1/agents":
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 0}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["phase"] == "completed":
                return [{"event_type": "runner.item.completed"}]
            return []
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert start_calls == [5, 5]
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"] == [{"id": 5, "status": "done", "failure_count": 0, "dependencies_json": []}]


def test_poll_run_allows_restart_of_same_task_after_unique_start_budget_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="unique-start-budget-retry-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=5,
        idle_timeout_seconds=2,
        poll_interval_seconds=0,
        max_auto_task_starts=1,
    )
    state = {"phase": "initial"}
    start_calls: list[int] = []

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/tasks/5/start":
            start_calls.append(5)
            if len(start_calls) == 1:
                state["phase"] = "retry-ready"
            else:
                state["phase"] = "completed"
            return {"ok": True}
        if method == "GET" and path == "/api/projects/1/tasks":
            if state["phase"] == "initial":
                return [{"id": 5, "status": "backlog", "failure_count": 0, "dependencies_json": []}]
            if state["phase"] == "retry-ready":
                return [
                    {
                        "id": 5,
                        "status": "backlog",
                        "assigned_agent_id": None,
                        "failure_count": 1,
                        "dependencies_json": [],
                        "waiting_reason": "Review requested changes before Mission Control can continue.",
                    }
                ]
            return [{"id": 5, "status": "done", "failure_count": 1, "dependencies_json": []}]
        if method == "GET" and path == "/api/projects/1/agents":
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 0}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["phase"] == "completed":
                return [{"event_type": "runner.item.completed"}]
            return []
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert start_calls == [5, 5]
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"] == [{"id": 5, "status": "done", "failure_count": 1, "dependencies_json": []}]


def test_poll_run_prefers_backlog_retry_over_waiting_on_paths_follow_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="path-wait-priority-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=5,
        idle_timeout_seconds=2,
        poll_interval_seconds=0,
    )
    state = {"phase": "initial"}
    start_calls: list[int] = []

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/tasks/2/start":
            start_calls.append(2)
            state["phase"] = "completed"
            return {"ok": True}
        if method == "POST" and path == "/api/projects/1/tasks/4/start":
            start_calls.append(4)
            raise AssertionError("The harness should prioritize the backlog retry before the path-blocked follow-up.")
        if method == "GET" and path == "/api/projects/1/tasks":
            if state["phase"] == "initial":
                return [
                    {
                        "id": 4,
                        "status": "waiting_on_paths",
                        "priority": 11,
                        "failure_count": 0,
                        "dependencies_json": [],
                        "waiting_reason": "Service Flow Builder owns django/db/models/sql",
                    },
                    {
                        "id": 2,
                        "status": "backlog",
                        "priority": 20,
                        "assigned_agent_id": None,
                        "failure_count": 2,
                        "dependencies_json": [],
                        "waiting_reason": "Blocked task had no recorded blocker and no active owning run; Mission Control returned it to backlog.",
                    },
                ]
            return [
                {
                    "id": 4,
                    "status": "done",
                    "priority": 11,
                    "failure_count": 0,
                    "dependencies_json": [],
                },
                {
                    "id": 2,
                    "status": "done",
                    "priority": 20,
                    "assigned_agent_id": 4,
                    "failure_count": 2,
                    "dependencies_json": [],
                },
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 2}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["phase"] == "completed":
                return [{"event_type": "runner.item.completed"}]
            return []
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert start_calls == [2]
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"][1]["status"] == "done"


def test_poll_run_uses_completion_grace_for_recent_active_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="completion-grace-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=0.1,
        idle_timeout_seconds=60,
        poll_interval_seconds=0,
    )
    state = {"task_polls": 0}

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "GET" and path == "/api/projects/1/tasks":
            state["task_polls"] += 1
            if state["task_polls"] == 1:
                return [{"id": 3, "status": "working", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": []}]
            return [{"id": 3, "status": "done", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": []}]
        if method == "GET" and path == "/api/projects/1/agents":
            if state["task_polls"] == 1:
                return [{"id": 4, "status": "working", "current_task_id": 3, "failure_count": 0}]
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 0}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["task_polls"] == 1:
                return [{"event_type": "runner.turn.started"}]
            return [{"event_type": "runner.turn.started"}, {"event_type": "runner.item.completed"}]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    tick = {"value": 0.0}

    def fake_monotonic() -> float:
        tick["value"] += 0.2
        return tick["value"]

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(harness_script.time, "monotonic", fake_monotonic)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert poll_result["timed_out"] is False
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"] == [{"id": 3, "status": "done", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": []}]


def test_poll_run_stops_early_for_evaluator_convergence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="evaluator-convergence-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=60,
        idle_timeout_seconds=60,
        poll_interval_seconds=0,
    )
    call_counts = {"tasks": 0}

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "GET" and path == "/api/projects/1/tasks":
            call_counts["tasks"] += 1
            return [
                {
                    "id": 1,
                    "status": "done",
                    "title": "Implement the smallest safe code fix",
                    "goal": "Correct the confirmed failing behavior with the least invasive code change.",
                    "agent_role": "Service Flow Builder",
                    "failure_count": 0,
                    "dependencies_json": [],
                },
                {
                    "id": 2,
                    "status": "working",
                    "assigned_agent_id": 5,
                    "title": "Re-run focused validation and prepare an honest handoff",
                    "goal": "Verify the fix outcome and leave truthful run instructions, limitations, and next steps.",
                    "agent_role": "Validation Specialist",
                    "failure_count": 2,
                    "dependencies_json": [1],
                },
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            return [{"id": 5, "status": "working", "current_task_id": 2, "failure_count": 2}]
        if method == "GET" and path == "/api/projects/1/events":
            return [{"event_type": "worker.report.received"}]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert call_counts["tasks"] >= 1
    assert poll_result["timed_out"] is False
    assert "only validation/handoff lanes remained open" in str(poll_result["early_exit_reason"] or "").lower()
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"][1]["status"] == "working"


def test_poll_run_stops_early_for_post_validation_retry_convergence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="post-validation-retry-convergence-run",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=60,
        idle_timeout_seconds=60,
        poll_interval_seconds=0,
    )

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "GET" and path == "/api/projects/1/tasks":
            return [
                {
                    "id": 1,
                    "status": "done",
                    "title": "Implement the smallest safe code fix",
                    "goal": "Correct the confirmed failing behavior with the least invasive code change.",
                    "agent_role": "Service Flow Builder",
                    "milestone": "Milestone 2 - Fix the code",
                    "failure_count": 0,
                    "dependencies_json": [],
                },
                {
                    "id": 4,
                    "status": "working",
                    "assigned_agent_id": 2,
                    "title": "Implement a fix for duplicate order by clause detection",
                    "goal": "Rework implement a fix for duplicate order by clause detection as a surgical patch inside the existing scoped paths. Last blocker to overcome: No verified workspace file changes were produced for a task that requires a concrete fix.",
                    "scope": "Resolve a blocker or error before the main flow can continue.",
                    "agent_role": "Execution Planner",
                    "milestone": "Milestone 3 - Validate and hand off",
                    "failure_count": 7,
                    "dependencies_json": [],
                },
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            return [{"id": 2, "status": "working", "current_task_id": 4, "failure_count": 7}]
        if method == "GET" and path == "/api/projects/1/events":
            return [{"event_type": "worker.report.received"}]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert poll_result["timed_out"] is False
    assert "only validation/handoff lanes remained open" in str(poll_result["early_exit_reason"] or "").lower()
    assert poll_result["tasks"][1]["status"] == "working"


def test_poll_run_starts_newly_unblocked_task_during_completion_grace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="completion-grace-unblocks-follow-up",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=0.1,
        idle_timeout_seconds=60,
        poll_interval_seconds=0,
    )
    state = {
        "task_polls": 0,
        "task3_started": False,
        "start_calls": [],
    }

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/tasks/3/start":
            state["start_calls"].append(3)
            state["task3_started"] = True
            return {"ok": True, "message": "Task started.", "run_id": 9}
        if method == "GET" and path == "/api/projects/1/tasks":
            state["task_polls"] += 1
            if state["task_polls"] == 1:
                return [
                    {"id": 2, "status": "working", "assigned_agent_id": 4, "failure_count": 1, "dependencies_json": [1]},
                    {
                        "id": 3,
                        "status": "backlog",
                        "assigned_agent_id": None,
                        "failure_count": 1,
                        "dependencies_json": [2],
                        "waiting_reason": "Waiting for task dependencies to finish.",
                        "priority": 30,
                    },
                ]
            if not state["task3_started"]:
                return [
                    {"id": 2, "status": "done", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": [1]},
                    {
                        "id": 3,
                        "status": "backlog",
                        "assigned_agent_id": None,
                        "failure_count": 1,
                        "dependencies_json": [2],
                        "waiting_reason": "Waiting for task dependencies to finish.",
                        "priority": 30,
                    },
                ]
            return [
                {"id": 2, "status": "done", "assigned_agent_id": 4, "failure_count": 0, "dependencies_json": [1]},
                {
                    "id": 3,
                    "status": "done",
                    "assigned_agent_id": 5,
                    "failure_count": 1,
                    "dependencies_json": [2],
                    "waiting_reason": None,
                    "priority": 30,
                },
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            if state["task_polls"] == 1:
                return [{"id": 4, "status": "working", "current_task_id": 2, "failure_count": 1}]
            if not state["task3_started"]:
                return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 0}]
            return [{"id": 5, "status": "waiting", "current_task_id": None, "failure_count": 1}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["task_polls"] == 1:
                return [{"event_type": "runner.turn.started"}]
            if not state["task3_started"]:
                return [{"event_type": "runner.turn.started"}, {"event_type": "runner.item.completed"}]
            return [
                {"event_type": "runner.turn.started"},
                {"event_type": "runner.item.completed"},
                {"event_type": "runner.turn.completed"},
            ]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    tick = {"value": 0.0}

    def fake_monotonic() -> float:
        tick["value"] += 0.2
        return tick["value"]

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(harness_script.time, "monotonic", fake_monotonic)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert state["start_calls"] == [3]
    assert poll_result["timed_out"] is False
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"][1]["status"] == "done"


def test_poll_run_restarts_assigned_retry_task_when_worker_is_idle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trajectory_path = tmp_path / "trajectory.jsonl"
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="assigned-retry-restart",
        model="qwen2.5-coder:7b",
        task_timeout_seconds=1,
        idle_timeout_seconds=60,
        poll_interval_seconds=0,
    )
    state = {
        "task_polls": 0,
        "start_calls": [],
        "retry_started": False,
    }

    def fake_call_api(client, method, path, trajectory_path, *, params=None, json_body=None):
        if method == "POST" and path == "/api/projects/1/tasks/2/start":
            state["start_calls"].append(2)
            state["retry_started"] = True
            return {"ok": True, "message": "Task started.", "run_id": 12}
        if method == "GET" and path == "/api/projects/1/tasks":
            state["task_polls"] += 1
            if state["task_polls"] == 1:
                return [
                    {
                        "id": 2,
                        "status": "working",
                        "assigned_agent_id": 4,
                        "failure_count": 0,
                        "dependencies_json": [],
                        "priority": 20,
                    }
                ]
            if state["task_polls"] == 2:
                return [
                    {
                        "id": 2,
                        "status": "assigned",
                        "assigned_agent_id": 4,
                        "failure_count": 1,
                        "dependencies_json": [],
                        "priority": 20,
                        "waiting_reason": "Manager requested one fix retry.",
                    }
                ]
            return [
                {
                    "id": 2,
                    "status": "done",
                    "assigned_agent_id": 4,
                    "failure_count": 0,
                    "dependencies_json": [],
                    "priority": 20,
                }
            ]
        if method == "GET" and path == "/api/projects/1/agents":
            if state["task_polls"] == 1:
                return [{"id": 4, "status": "working", "current_task_id": 2, "failure_count": 0}]
            if state["retry_started"]:
                return [{"id": 4, "status": "working", "current_task_id": 2, "failure_count": 1}]
            return [{"id": 4, "status": "waiting", "current_task_id": None, "failure_count": 1}]
        if method == "GET" and path == "/api/projects/1/events":
            if state["task_polls"] == 1:
                return [{"event_type": "runner.turn.started"}]
            if state["task_polls"] == 2:
                return [{"event_type": "runner.turn.started"}, {"event_type": "worker.report.received"}]
            return [
                {"event_type": "runner.turn.started"},
                {"event_type": "worker.report.received"},
                {"event_type": "runner.turn.completed"},
            ]
        if method == "GET" and path in {
            "/api/projects/1/pending-decisions",
            "/api/projects/1/approvals/pending",
        }:
            return []
        raise AssertionError(f"Unexpected API call: {method} {path}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)
    monkeypatch.setattr(harness_script.time, "sleep", lambda *_args, **_kwargs: None)

    poll_result = _poll_run(
        client=object(),
        project_id=1,
        config=config,
        trajectory_path=trajectory_path,
    )

    assert state["start_calls"] == [2]
    assert poll_result["timed_out"] is False
    assert poll_result["deadlock_reason"] is None
    assert poll_result["tasks"] == [
        {
            "id": 2,
            "status": "done",
            "assigned_agent_id": 4,
            "failure_count": 0,
            "dependencies_json": [],
            "priority": 20,
        }
    ]


def test_fetch_project_state_persists_latest_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload_by_suffix = {
        "/tasks": [{"id": 1, "status": "done"}],
        "/agents": [{"id": 2, "status": "waiting"}],
        "/events": [{"event_type": "worker.report.received"}],
        "/pending-decisions": [],
        "/approvals/pending": [],
    }

    def fake_call_api(_client, method: str, route: str, _trajectory_path: Path, json_body=None):
        assert method == "GET"
        for suffix, payload in payload_by_suffix.items():
            if route.endswith(suffix):
                return payload
        raise AssertionError(f"Unexpected route: {route}")

    monkeypatch.setattr(harness_script, "_call_api", fake_call_api)

    state = _fetch_project_state(
        object(),
        7,
        tmp_path / "trajectory.jsonl",
        snapshot_dir=tmp_path / "snapshots",
        started_task_ids={1, 3},
        deadlock_reason="none",
    )

    assert state["tasks"] == [{"id": 1, "status": "done"}]
    assert state["agents"] == [{"id": 2, "status": "waiting"}]
    assert json.loads((tmp_path / "snapshots" / "latest-tasks.json").read_text(encoding="utf-8")) == state["tasks"]
    assert json.loads((tmp_path / "snapshots" / "latest-agents.json").read_text(encoding="utf-8")) == state["agents"]
    meta = json.loads((tmp_path / "snapshots" / "latest-meta.json").read_text(encoding="utf-8"))
    assert meta["started_task_ids"] == [1, 3]
    assert meta["deadlock_reason"] == "none"


def test_task_is_restartable_after_prior_start_when_it_returns_to_backlog_unassigned() -> None:
    task = {
        "id": 2,
        "status": "backlog",
        "assigned_agent_id": None,
        "failure_count": 0,
        "waiting_reason": None,
    }

    assert _task_is_restartable_after_prior_start(task, {2}) is True


def test_detect_local_setup_blocker_flags_missing_compiler_for_extension_repo(tmp_path: Path) -> None:
    bootstrap_stdout = tmp_path / "bootstrap.stdout.txt"
    bootstrap_stderr = tmp_path / "bootstrap.stderr.txt"
    probe_stderr = tmp_path / "probe.stderr.txt"
    bootstrap_stdout.write_text("", encoding="utf-8")
    bootstrap_stderr.write_text("error: command 'cl.exe' failed: None", encoding="utf-8")
    probe_stderr.write_text(
        "ImportError: You appear to be trying to import astropy from within a source checkout or from an editable installation without building the extension modules first.",
        encoding="utf-8",
    )

    blocker = _detect_local_setup_blocker(
        {
            "results": [
                {
                    "stdout_path": bootstrap_stdout.as_posix(),
                    "stderr_path": bootstrap_stderr.as_posix(),
                }
            ]
        },
        {
            "probe_results": [
                {
                    "stdout_path": "",
                    "stderr_path": probe_stderr.as_posix(),
                }
            ]
        },
    )

    assert blocker is not None
    assert "compiled extension modules" in blocker.lower()


def test_wrap_command_for_windows_cpp_toolchain_only_wraps_build_ext() -> None:
    vcvars = Path("C:/VS/VC/Auxiliary/Build/vcvars64.bat")

    wrapped = _wrap_command_for_windows_cpp_toolchain(
        "python setup.py build_ext --inplace --build-temp build-temp --build-lib build-lib",
        vcvars64_bat=vcvars,
    )

    assert _command_needs_windows_cpp_toolchain("python setup.py build_ext --inplace") is True
    assert _command_needs_windows_cpp_toolchain("python -m pytest astropy/modeling/tests/test_separable.py -q") is False
    assert wrapped == (
        f'call "{vcvars}" && '
        "python setup.py build_ext --inplace --build-temp build-temp --build-lib build-lib"
    )
    assert _wrap_command_for_windows_cpp_toolchain(
        "python setup.py egg_info",
        vcvars64_bat=vcvars,
    ) == "python setup.py egg_info"


def test_detect_local_setup_blocker_flags_windows_sdk_resource_failure(tmp_path: Path) -> None:
    bootstrap_stderr = tmp_path / "bootstrap.stderr.txt"
    probe_stderr = tmp_path / "probe.stderr.txt"
    bootstrap_stderr.write_text("LINK : fatal error LNK1158: cannot run 'rc.exe'", encoding="utf-8")
    probe_stderr.write_text(
        "ImportError: You appear to be trying to import astropy from within a source checkout or from an editable installation without building the extension modules first.",
        encoding="utf-8",
    )

    blocker = _detect_local_setup_blocker(
        {
            "results": [
                {
                    "stdout_path": "",
                    "stderr_path": bootstrap_stderr.as_posix(),
                }
            ]
        },
        {
            "probe_results": [
                {
                    "stdout_path": "",
                    "stderr_path": probe_stderr.as_posix(),
                }
            ]
        },
    )

    assert blocker is not None
    assert "lnk1158" in blocker.lower()


def test_detect_local_setup_blocker_flags_dependency_drift(tmp_path: Path) -> None:
    bootstrap_stderr = tmp_path / "bootstrap.stderr.txt"
    bootstrap_stderr.write_text(
        "C:\\Users\\mike\\AppData\\Roaming\\Python\\Python310\\site-packages\\numpy\\__init__.pxd:781:79: Syntax error in ctypedef statement",
        encoding="utf-8",
    )

    blocker = _detect_local_setup_blocker(
        {
            "results": [
                {
                    "stdout_path": "",
                    "stderr_path": bootstrap_stderr.as_posix(),
                }
            ]
        },
        {"probe_results": []},
    )

    assert blocker is not None
    assert "dependency stack" in blocker.lower()


def test_analyze_task_execution_ignores_superseded_waiting_tasks() -> None:
    analysis = analyze_task_execution(
        tasks=[
            {
                "id": 6,
                "title": "Clarify the Failing Behavior",
                "status": "waiting_on_paths",
                "waiting_reason": "Superseded after Mission Control accepted downstream completed task #3.",
                "failure_count": 1,
            }
        ],
        agents=[],
        events=[],
    )

    assert analysis["active_task_count"] == 0
    assert all("active task" not in note.lower() for note in analysis["notes"])


def test_load_task_manifest_resolves_relative_repo_paths_against_manifest_location(tmp_path: Path) -> None:
    repo_root = tmp_path / "repos" / "django-case"
    repo_root.mkdir(parents=True)
    manifest = tmp_path / "manifests" / "tasks.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "instance_id": "django__relative",
                        "problem_statement": "Fix the regression.",
                        "repo_path": "../repos/django-case",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    tasks = load_task_manifest(manifest)

    assert tasks[0].repo_path == repo_root.resolve().as_posix()


def test_load_task_manifest_resolves_upstream_style_records_from_prepared_repos_root(tmp_path: Path) -> None:
    prepared_repos_root = tmp_path / "prepared"
    repo_root = prepared_repos_root / "django__django"
    repo_root.mkdir(parents=True)
    manifest = tmp_path / "swebench-lite.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "instance_id": "django__12345",
                "repo": "django/django",
                "base_commit": "abc123",
                "problem_statement": "Fix the queryset regression.",
                "FAIL_TO_PASS": ["tests/queries/test_bug.py::test_regression"],
            }
        ),
        encoding="utf-8",
    )

    tasks = load_task_manifest(manifest, prepared_repos_root=prepared_repos_root)

    assert tasks[0].repo_name == "django/django"
    assert tasks[0].base_commit == "abc123"
    assert tasks[0].repo_path == repo_root.resolve().as_posix()


def test_load_task_manifest_prefers_repo_map_for_upstream_style_records(tmp_path: Path) -> None:
    mapped_repo = tmp_path / "mapped" / "sympy"
    mapped_repo.mkdir(parents=True)
    manifest = tmp_path / "swebench-lite.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "instance_id": "sympy__67890",
                        "repo": "sympy/sympy",
                        "problem_statement": "Fix the symbolic regression.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    repo_map = tmp_path / "repo-map.json"
    repo_map.write_text(
        json.dumps({"repos": {"sympy/sympy": "./mapped/sympy"}}),
        encoding="utf-8",
    )

    tasks = load_task_manifest(manifest, repo_map_path=repo_map)

    assert tasks[0].repo_path == mapped_repo.resolve().as_posix()


def test_load_task_manifest_supports_swe_bench_parquet_directory(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    data_root = tmp_path / "SWE-bench_Lite" / "data"
    data_root.mkdir(parents=True)
    table = pyarrow.table(
        {
            "repo": ["astropy/astropy"],
            "instance_id": ["astropy__astropy-1"],
            "base_commit": ["abc123"],
            "patch": ["gold"],
            "test_patch": ["gold-test"],
            "problem_statement": ["Fix the regression."],
            "hints_text": [""],
            "created_at": ["2026-01-01T00:00:00Z"],
            "version": ["1.0"],
            "FAIL_TO_PASS": ['["tests/test_bug.py::test_regression"]'],
            "PASS_TO_PASS": ['["tests/test_ok.py::test_ok"]'],
            "environment_setup_commit": ["def456"],
        }
    )
    pq.write_table(table, data_root / "test-00000-of-00001.parquet")

    tasks = load_task_manifest(tmp_path / "SWE-bench_Lite", dataset_split="test", prepared_repos_root=tmp_path / "repos")

    assert len(tasks) == 1
    assert tasks[0].instance_id == "astropy__astropy-1"
    assert tasks[0].repo_name == "astropy/astropy"
    assert tasks[0].repo_path.endswith("/repos/astropy__astropy")
    assert tasks[0].metadata["environment_setup_commit"] == "def456"
    assert tasks[0].test_patch == "gold-test"
    assert "patch" not in tasks[0].metadata
    assert "test_patch" not in tasks[0].metadata
    assert "test_patch" not in tasks[0].to_dict()


def test_detect_validation_commands_prefers_explicit_and_falls_back_to_pytest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    assert detect_validation_commands(repo, ["python -m pytest tests/test_bug.py"]) == [
        "python -m pytest tests/test_bug.py"
    ]
    assert detect_validation_commands(
        repo,
        [],
        fail_to_pass=["tests/test_bug.py::test_regression"],
        pass_to_pass=["tests/test_ok.py::test_ok"],
    ) == ["python -m pytest tests/test_bug.py tests/test_ok.py -q"]
    assert detect_validation_commands(repo, []) == ["python -m pytest"]


def test_detect_validation_commands_uses_django_runtests_for_unittest_style_targets(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")

    commands = detect_validation_commands(
        repo,
        [],
        fail_to_pass=["test_override_file_upload_permissions (test_utils.tests.OverrideSettingsTests)"],
        pass_to_pass=["test_override_media_root (test_utils.tests.OverrideSettingsTests)"],
    )

    assert commands == [
        "python tests/runtests.py --settings=test_sqlite "
        "test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions "
        "test_utils.tests.OverrideSettingsTests.test_override_media_root"
    ]


def test_detect_validation_commands_falls_back_to_django_class_target_when_method_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
                "",
                "class ReprTests:",
                "    def test_expressions(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    commands = detect_validation_commands(
        repo,
        [],
        fail_to_pass=[
            "test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)",
            "test_order_of_operations (expressions.tests.BasicExpressionsTests)",
        ],
        pass_to_pass=["test_expressions (expressions.tests.ReprTests)"],
    )

    assert commands == [
        "python tests/runtests.py --settings=test_sqlite "
        "expressions.tests.BasicExpressionsTests expressions.tests.ReprTests.test_expressions"
    ]


def test_detect_validation_commands_normalizes_explicit_django_runtests_command_when_method_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    commands = detect_validation_commands(
        repo,
        [
            "python tests/runtests.py --settings=test_sqlite "
            "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
            "expressions.tests.BasicExpressionsTests.test_order_of_operations"
        ],
    )

    assert commands == [
        "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"
    ]


def test_apply_solver_test_patch_enables_exact_django_fail_to_pass_command(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__solver-test-patch",
        repo_name="django/django",
        problem_statement="Expose the benchmark regression test to the solver workspace.",
        repo_path=repo.as_posix(),
        fail_to_pass=[
            "test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)",
            "test_order_of_operations (expressions.tests.BasicExpressionsTests)",
        ],
        pass_to_pass=[],
        test_patch=(
            "diff --git a/tests/expressions/tests.py b/tests/expressions/tests.py\n"
            "--- a/tests/expressions/tests.py\n"
            "+++ b/tests/expressions/tests.py\n"
            "@@ -1,3 +1,6 @@\n"
            " class BasicExpressionsTests:\n"
            "+    def test_order_by_multiline_sql(self):\n"
            "+        assert True\n"
            "+\n"
            "     def test_order_of_operations(self):\n"
            "         assert True\n"
        ),
    )

    report = apply_solver_test_patch(task, repo, tmp_path / "artifacts")

    assert report is not None
    assert report["applied"] is True
    assert detect_validation_commands(
        repo,
        [],
        fail_to_pass=task.fail_to_pass,
        pass_to_pass=[],
    ) == [
        "python tests/runtests.py --settings=test_sqlite "
        "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
        "expressions.tests.BasicExpressionsTests.test_order_of_operations"
    ]


def test_detect_setup_commands_prefers_explicit_and_falls_back_to_editable_install(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    assert detect_setup_commands(repo, ["python -m pip install demo"]) == ["python -m pip install demo"]
    assert detect_setup_commands(repo, []) == [
        'python -m pip install --disable-pip-version-check --no-input --no-index --no-build-isolation -e ".[test]"',
        'python -m pip install --disable-pip-version-check --no-input --no-index --no-build-isolation -e "."',
    ]


def test_build_manager_issue_prompt_includes_repo_constraints_and_repo_context(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo_root / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "instance_id": "django__1",
                        "problem_statement": "Fix the failing ORM test.",
                        "repo_path": repo_root.as_posix(),
                        "repo": "django/django",
                        "hints_text": "The failure is in queryset evaluation.",
                        "FAIL_TO_PASS": ["tests/test_math_utils.py::test_add"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    task = load_task_manifest(manifest)[0]
    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_math_utils.py -q"])

    prompt = build_manager_issue_prompt(task, ["python -m pytest tests/test_math_utils.py -q"], repo_context)

    assert "No internet access" in prompt
    assert "django/django" in prompt
    assert "python -m pytest tests/test_math_utils.py -q" in prompt
    assert "manager-led plan" in prompt
    assert "Workspace clues:" in prompt
    assert "tests/test_math_utils.py" in prompt
    assert "src/math_utils.py" in prompt


def test_build_manager_issue_prompt_sanitizes_urls_and_summarizes_large_target_sets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "django" / "conf").mkdir(parents=True)
    (repo_root / "tests" / "test_utils").mkdir(parents=True)
    (repo_root / "docs" / "ref").mkdir(parents=True)
    (repo_root / "django" / "conf" / "global_settings.py").write_text(
        "FILE_UPLOAD_PERMISSIONS = None\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_utils" / "tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "ref" / "settings.txt").write_text(
        "FILE_UPLOAD_PERMISSIONS documentation\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__1",
        repo_name="django/django",
        problem_statement="Set default FILE_UPLOAD_PERMISSION to 0o644. See https://example.com/ticket for context.",
        repo_path=repo_root.as_posix(),
        hints_text="Adjust settings docs and release notes. https://example.com/discussion",
        fail_to_pass=["test_override_file_upload_permissions (test_utils.tests.OverrideSettingsTests)"],
        pass_to_pass=[f"test_extra_{index} (test_utils.tests.OverrideSettingsTests)" for index in range(20)],
    )

    repo_context = build_repo_context(
        task,
        repo_root,
        ["python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions"],
    )
    prompt = build_manager_issue_prompt(
        task,
        ["python tests/runtests.py --settings=test_sqlite " + " ".join(f"test_utils.tests.OverrideSettingsTests.test_extra_{index}" for index in range(20))],
        repo_context,
    )

    assert "https://example.com" not in prompt
    assert "[url omitted]" in prompt
    assert "Focused reproduction commands:" in prompt
    assert "Broader validation commands after a fix:" in prompt
    assert "... and 8 more target(s)." in prompt


def test_build_manager_issue_prompt_redacts_local_absolute_paths_from_retry_hints(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "astropy" / "modeling" / "tests").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "separable.py").write_text(
        "def separability_matrix(transform):\n    return transform\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "modeling" / "tests" / "test_separable.py").write_text(
        "def test_separable():\n    assert True\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__prompt_path_redaction",
        repo_name="astropy/astropy",
        problem_statement="Fix separability_matrix for nested CompoundModels.",
        repo_path=repo_root.as_posix(),
        hints_text=(
            "Validation failure excerpt:\n"
            "ImportError from "
            "(C:\\Users\\mike\\AppData\\Local\\Temp\\mc-swe-eval\\9461592234\\ws\\astropy\\modeling\\separable.py)\n"
            "See /Users/mike/AppData/Local/Temp/mc-swe-eval/9461592234/ws/astropy/modeling/separable.py too."
        ),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest astropy/modeling/tests/test_separable.py -q"])
    prompt = build_manager_issue_prompt(task, ["python -m pytest astropy/modeling/tests/test_separable.py -q"], repo_context)

    assert "C:\\Users\\mike\\AppData\\Local\\Temp" not in prompt
    assert "/Users/mike/AppData/Local/Temp" not in prompt
    assert "[local path omitted]" in prompt


def test_build_manager_issue_prompt_includes_exact_repo_matches_for_issue_snippets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "math_utils.py").write_text(
        "\n".join(
            [
                "def adjust(value):",
                "    total = normalize(value)",
                "    helper = 1",
                "    total = normalize(value)",
                "    return total",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_math_utils.py").write_text("def test_adjust():\n    assert True\n", encoding="utf-8")
    task = BenchmarkTaskSpec(
        instance_id="demo__code_search",
        repo_name="demo/repo",
        problem_statement="Fix src/math_utils.py where `total = normalize(value)` still appears in both logic paths.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_math_utils.py::test_adjust"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_math_utils.py -q"])
    prompt = build_manager_issue_prompt(task, ["python -m pytest tests/test_math_utils.py -q"], repo_context)

    assert repo_context["code_search_hits"] == [
        "src/math_utils.py:2: total = normalize(value)",
        "src/math_utils.py:4: total = normalize(value)",
    ]
    assert "Exact repo matches for issue snippets:" in prompt
    assert "src/math_utils.py:2: total = normalize(value)" in prompt
    assert "src/math_utils.py:4: total = normalize(value)" in prompt


def test_build_manager_issue_prompt_normalizes_stale_explicit_django_targets(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__stale_prompt_targets",
        repo_name="django/django",
        problem_statement="Fix the broken order_by handling for multiline RawSQL.",
        repo_path=repo.as_posix(),
        fail_to_pass=[
            "test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)",
            "test_order_of_operations (expressions.tests.BasicExpressionsTests)",
        ],
    )
    stale_command = (
        "python tests/runtests.py --settings=test_sqlite "
        "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
        "expressions.tests.BasicExpressionsTests.test_order_of_operations"
    )

    prompt = build_manager_issue_prompt(
        task,
        [stale_command],
        {"focused_validation_commands": [stale_command]},
    )

    assert "Focused reproduction commands:" in prompt
    assert "Broader validation commands after a fix:" in prompt
    assert "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests" in prompt
    assert "test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations" not in prompt


def test_build_project_issue_context_normalizes_stale_explicit_django_targets(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__stale_issue_context",
        repo_name="django/django",
        problem_statement="Fix the broken order_by handling for multiline RawSQL.",
        repo_path=repo.as_posix(),
        fail_to_pass=[
            "test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)",
            "test_order_of_operations (expressions.tests.BasicExpressionsTests)",
        ],
    )
    stale_command = (
        "python tests/runtests.py --settings=test_sqlite "
        "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
        "expressions.tests.BasicExpressionsTests.test_order_of_operations"
    )

    issue_context = build_project_issue_context(
        task,
        [stale_command],
        {"focused_validation_commands": [stale_command]},
    )

    assert "Focused reproduction commands:" in issue_context
    assert "Broader validation commands after a fix:" in issue_context
    assert "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests" in issue_context
    assert "test_order_by_multiline_sql expressions.tests.BasicExpressionsTests.test_order_of_operations" not in issue_context


def test_build_project_issue_context_prioritizes_focused_command_before_long_issue_text(tmp_path: Path) -> None:
    repo = tmp_path / "django-repo"
    (repo / "tests" / "expressions").mkdir(parents=True)
    (repo / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__project_seed_priority",
        repo_name="django/django",
        problem_statement=("Long issue text. " * 400).strip(),
        repo_path=repo.as_posix(),
        hints_text=("Long hint text. " * 200).strip(),
        fail_to_pass=[
            "test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)",
            "test_order_of_operations (expressions.tests.BasicExpressionsTests)",
        ],
    )
    stale_command = (
        "python tests/runtests.py --settings=test_sqlite "
        "expressions.tests.BasicExpressionsTests.test_order_by_multiline_sql "
        "expressions.tests.BasicExpressionsTests.test_order_of_operations"
    )

    issue_context = build_project_issue_context(
        task,
        [stale_command],
        {"focused_validation_commands": [stale_command]},
    )

    assert issue_context.startswith("Focused reproduction commands:")
    assert "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests" in issue_context
    assert len(issue_context) < 4000


def test_build_project_issue_context_includes_repo_clues_and_exact_hits(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "math_utils.py").write_text(
        "\n".join(
            [
                "def adjust(value):",
                "    total = normalize(value)",
                "    return total",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_math_utils.py").write_text("def test_adjust():\n    assert True\n", encoding="utf-8")
    task = BenchmarkTaskSpec(
        instance_id="demo__project_issue_context",
        repo_name="demo/repo",
        problem_statement="Fix src/math_utils.py because `total = normalize(value)` is wrong.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_math_utils.py::test_adjust"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_math_utils.py -q"])
    issue_context = build_project_issue_context(task, ["python -m pytest tests/test_math_utils.py -q"], repo_context)

    assert "Workspace clues:" in issue_context
    assert "Files to inspect first: src/math_utils.py, tests/test_math_utils.py" in issue_context
    assert "Exact repo matches for issue snippets:" in issue_context
    assert "src/math_utils.py:2: total = normalize(value)" in issue_context
    assert "FAIL_TO_PASS targets:" in issue_context
    assert "tests/test_math_utils.py::test_adjust" in issue_context


def test_build_workspace_diff_reports_changed_files() -> None:
    diff, changed = build_workspace_diff(
        {"src/math_utils.py": "def add(a, b):\n    return a - b\n"},
        {"src/math_utils.py": "def add(a, b):\n    return a + b\n", "README.md": "# Demo\n"},
    )

    assert "src/math_utils.py" in diff
    assert "README.md" in diff
    assert changed == ["README.md", "src/math_utils.py"]


def test_build_meaningful_workspace_diff_ignores_harness_artifacts() -> None:
    diff, changed = build_meaningful_workspace_diff(
        {
            "mission-control/benchmark-protected-paths.json": '{"protected_paths": ["tests/test_math_utils.py"]}\n',
            "src/math_utils.py": "def add(a, b):\n    return a - b\n",
            "tests/test_math_utils.py": "def test_add():\n    assert True\n",
        },
        {
            "src/math_utils.py": "def add(a, b):\n    return a + b\n",
            "tests/test_math_utils.py": "def test_add():\n    assert False\n",
        },
    )

    assert "mission-control/benchmark-protected-paths.json" not in diff
    assert changed == ["src/math_utils.py", "tests/test_math_utils.py"]


def test_finalize_workspace_diff_restores_protected_files_before_writing_diff(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "mission-control").mkdir()
    protected_path = workspace / "tests" / "test_math_utils.py"
    protected_path.write_text("def test_add():\n    assert True\n", encoding="utf-8")
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    manifest_path = workspace / "mission-control" / "benchmark-protected-paths.json"
    manifest_path.write_text('{"protected_paths": ["tests/test_math_utils.py"]}\n', encoding="utf-8")
    before_snapshot = {
        "mission-control/benchmark-protected-paths.json": manifest_path.read_text(encoding="utf-8"),
        "src/math_utils.py": "def add(a, b):\n    return a - b\n",
        "tests/test_math_utils.py": "def test_add():\n    assert True\n",
    }
    protected_path.unlink()
    manifest_path.unlink()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    diff_text, changed_files, skipped_protected_files, restore_report = _finalize_workspace_diff(
        workspace,
        before_snapshot,
        (
            "diff --git a/tests/test_math_utils.py b/tests/test_math_utils.py\n"
            "--- a/tests/test_math_utils.py\n"
            "+++ b/tests/test_math_utils.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+pass\n"
        ),
    )

    assert skipped_protected_files == ["tests/test_math_utils.py"]
    assert restore_report == {
        "restored_files": ["tests/test_math_utils.py"],
        "deleted_files": [],
    }
    assert protected_path.read_text(encoding="utf-8") == "def test_add():\n    assert True\n"
    assert "tests/test_math_utils.py" not in diff_text
    assert "mission-control/benchmark-protected-paths.json" not in diff_text
    assert changed_files == ["src/math_utils.py"]


def test_meaningful_patch_paths_filters_generated_artifacts() -> None:
    paths = meaningful_patch_paths(
        [
            ".pytest_cache/README.md",
            "mission-control/TASK_BOARD.md",
            "src/math_utils.py",
            "tests/test_math_utils.py",
        ]
    )

    assert paths == ["src/math_utils.py", "tests/test_math_utils.py"]


def test_unwrap_nested_result_payload_and_extract_task_summary() -> None:
    payload, repaired = unwrap_nested_result_payload(
        {
            "result": """```json
            {
              "report": {
                "status": "done",
                "message": "Applied the smallest safe code fix."
              },
              "validation_commands": ["python -m pytest tests/test_bug.py -q"]
            }
            ```"""
        }
    )

    summary = extract_task_summary(
        [
            {
                "role": "manager",
                "content_markdown": json.dumps(
                    {
                        "result": json.dumps(
                            {
                                "report": {
                                    "status": "done",
                                    "message": "Applied the smallest safe code fix.",
                                }
                            }
                        )
                    }
                ),
            }
        ]
    )

    assert repaired is True
    assert payload is not None
    assert payload["report"]["message"] == "Applied the smallest safe code fix."
    assert summary == "Applied the smallest safe code fix."


def test_analyze_task_execution_and_classify_retry_exhaustion() -> None:
    analysis = analyze_task_execution(
        tasks=[
            {"title": "Implement fix", "status": "done", "failure_count": 1},
            {"title": "Unblock: Implement fix", "status": "done", "failure_count": 1},
            {"title": "Unblock: Unblock: Implement fix", "status": "done", "failure_count": 1},
        ],
        events=[
            {"event_type": "manager.parse_failed"},
            {"event_type": "manager.mode.fallback"},
            {"event_type": "manager.mode.fallback"},
        ],
        agents=[{"failure_count": 2}],
    )

    failure_category = classify_failure_category(
        timed_out=False,
        setup_failed=False,
        patch_applied=False,
        runner_failed=False,
        validation_attempted=False,
        validation_succeeded=False,
        pending_approvals=0,
        pending_decisions=0,
        tasks_generated=3,
        task_statuses=["done", "done", "done"],
        manager_parse_failures=analysis["manager_parse_failures"],
        retry_count=analysis["retry_count"],
        unblock_task_count=analysis["unblock_task_count"],
    )

    assert analysis["retry_count"] == 3
    assert analysis["unblock_task_count"] == 2
    assert analysis["manager_parse_failures"] == 1
    assert failure_category == "manager_contract_failed"


def test_classify_failure_category_prefers_orchestration_deadlock_over_runner_failure() -> None:
    failure_category = classify_failure_category(
        timed_out=False,
        setup_failed=False,
        orchestration_deadlocked=True,
        patch_applied=False,
        runner_failed=True,
        validation_attempted=False,
        validation_succeeded=False,
        pending_approvals=0,
        pending_decisions=0,
        tasks_generated=3,
        task_statuses=["blocked", "backlog"],
    )

    assert failure_category == "orchestration_deadlock"


def test_classify_failure_category_prefers_validation_failure_after_patch_over_runner_failure() -> None:
    failure_category = classify_failure_category(
        timed_out=False,
        setup_failed=False,
        orchestration_deadlocked=False,
        patch_applied=True,
        runner_failed=True,
        validation_attempted=True,
        validation_succeeded=False,
        pending_approvals=0,
        pending_decisions=0,
        tasks_generated=3,
        task_statuses=["blocked", "done"],
        retry_count=2,
        unblock_task_count=0,
    )

    assert failure_category == "validation_failed"


def test_classify_failure_category_prefers_validation_failure_after_patch_over_deadlock() -> None:
    failure_category = classify_failure_category(
        timed_out=False,
        setup_failed=False,
        orchestration_deadlocked=True,
        patch_applied=True,
        runner_failed=False,
        validation_attempted=True,
        validation_succeeded=False,
        pending_approvals=0,
        pending_decisions=0,
        tasks_generated=3,
        task_statuses=["blocked", "working"],
        retry_count=6,
        unblock_task_count=0,
    )

    assert failure_category == "validation_failed"


def test_recover_timeout_task_result_uses_runtime_snapshots(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    task_output_dir = tmp_path / "task-output"
    snapshot_dir = task_output_dir / "runtime-snapshots"
    snapshot_dir.mkdir(parents=True)
    _task = BenchmarkTaskSpec(
        instance_id="demo__1",
        repo_name="demo/repo",
        problem_statement="Fix the regression.",
        repo_path=workspace.as_posix(),
        validation_commands=["python -m pytest tests/test_bug.py -q"],
    )
    (task_output_dir / "workspace").mkdir(parents=True)
    for source in workspace.iterdir():
        if source.is_file():
            (task_output_dir / "workspace" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=task_output_dir / "workspace", check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=task_output_dir / "workspace", check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=task_output_dir / "workspace", check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "module.py"], cwd=task_output_dir / "workspace", check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=task_output_dir / "workspace", check=True, capture_output=True, text=True)

    (snapshot_dir / "latest-tasks.json").write_text(
        json.dumps(
            [
                {"id": 1, "status": "done", "title": "Investigate", "failure_count": 0},
                {"id": 2, "status": "backlog", "title": "Fix", "failure_count": 1},
            ]
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-agents.json").write_text(
        json.dumps([{"id": 1, "failure_count": 0, "status": "waiting"}]),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-events.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-decisions.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-approvals.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-meta.json").write_text(json.dumps({"deadlock_reason": "No runnable tasks remained."}), encoding="utf-8")

    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="demo-run",
        model="qwen2.5-coder:7b",
    )

    recovered = recover_timeout_task_result(_task, config, task_output_dir)

    assert recovered is not None
    assert recovered.failure_category == "orchestration_deadlock"
    assert recovered.status == "orchestration_deadlock"
    assert recovered.attempted is True
    assert any("Recovered partial task state" in note for note in recovered.notes)


def test_recover_timeout_task_result_does_not_keep_deadlock_after_completed_flow(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    task_output_dir = tmp_path / "task-output-complete"
    snapshot_dir = task_output_dir / "runtime-snapshots"
    snapshot_dir.mkdir(parents=True)
    _task = BenchmarkTaskSpec(
        instance_id="demo__2",
        repo_name="demo/repo",
        problem_statement="Fix the regression.",
        repo_path=workspace.as_posix(),
        validation_commands=["python -m pytest tests/test_bug.py -q"],
    )
    staged_workspace = task_output_dir / "workspace"
    staged_workspace.mkdir(parents=True)
    for source in workspace.iterdir():
        if source.is_file():
            (staged_workspace / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=staged_workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=staged_workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=staged_workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "module.py"], cwd=staged_workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=staged_workspace, check=True, capture_output=True, text=True)
    (staged_workspace / "module.py").write_text("VALUE = 3\n", encoding="utf-8")

    (snapshot_dir / "latest-tasks.json").write_text(
        json.dumps(
            [
                {"id": 1, "status": "done", "title": "Investigate", "failure_count": 0},
                {"id": 2, "status": "done", "title": "Fix", "failure_count": 0},
                {"id": 3, "status": "superseded", "title": "Validate", "failure_count": 0},
            ]
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-agents.json").write_text(
        json.dumps([{"id": 1, "failure_count": 0, "status": "waiting"}]),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-events.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-decisions.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-approvals.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-meta.json").write_text(json.dumps({"deadlock_reason": "No runnable tasks remained."}), encoding="utf-8")

    validation_dir = task_output_dir / "validation"
    validation_dir.mkdir(parents=True)
    stdout_path = validation_dir / "validation-1.stdout.txt"
    stderr_path = validation_dir / "validation-1.stderr.txt"
    stdout_path.write_text("ok\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    (task_output_dir / "validation-results.json").write_text(
        json.dumps(
            [
                {
                    "command": "python -m pytest tests/test_bug.py -q",
                    "returncode": 0,
                    "timed_out": False,
                    "runtime_seconds": 1.0,
                    "stdout_path": stdout_path.as_posix(),
                    "stderr_path": stderr_path.as_posix(),
                }
            ]
        ),
        encoding="utf-8",
    )

    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="demo-run",
        model="qwen2.5-coder:7b",
    )

    recovered = recover_timeout_task_result(_task, config, task_output_dir)

    assert recovered is not None
    assert recovered.completed is True
    assert recovered.patch_applied is True
    assert recovered.validation_succeeded is True
    assert recovered.failure_category is None
    assert recovered.status == "resolved"
    assert all("deadlock" not in note.lower() for note in recovered.notes)


def test_recover_timeout_task_result_does_not_count_validation_success_without_patch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace-no-patch"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Codex"], cwd=workspace, check=True, capture_output=True, text=True)
    (workspace / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "module.py"], cwd=workspace, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workspace, check=True, capture_output=True, text=True)

    task_output_dir = tmp_path / "task-output-no-patch"
    snapshot_dir = task_output_dir / "runtime-snapshots"
    snapshot_dir.mkdir(parents=True)
    task = BenchmarkTaskSpec(
        instance_id="demo__no_patch",
        repo_name="demo/repo",
        problem_statement="Fix the regression.",
        repo_path=workspace.as_posix(),
        validation_commands=["python -m pytest tests/test_bug.py -q"],
    )
    staged_workspace = task_output_dir / "workspace"
    stage_workspace_snapshot(workspace, staged_workspace)

    (snapshot_dir / "latest-tasks.json").write_text(
        json.dumps(
            [
                {"id": 1, "status": "done", "title": "Investigate", "failure_count": 0},
                {"id": 2, "status": "done", "title": "Validate", "failure_count": 0},
            ]
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-agents.json").write_text(
        json.dumps([{"id": 1, "failure_count": 0, "status": "waiting"}]),
        encoding="utf-8",
    )
    (snapshot_dir / "latest-events.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-decisions.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-pending-approvals.json").write_text(json.dumps([]), encoding="utf-8")
    (snapshot_dir / "latest-meta.json").write_text(json.dumps({}), encoding="utf-8")

    validation_dir = task_output_dir / "validation"
    validation_dir.mkdir(parents=True)
    stdout_path = validation_dir / "validation-1.stdout.txt"
    stderr_path = validation_dir / "validation-1.stderr.txt"
    stdout_path.write_text("ok\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    (task_output_dir / "validation-results.json").write_text(
        json.dumps(
            [
                {
                    "command": "python -m pytest tests/test_bug.py -q",
                    "returncode": 0,
                    "timed_out": False,
                    "runtime_seconds": 1.0,
                    "stdout_path": stdout_path.as_posix(),
                    "stderr_path": stderr_path.as_posix(),
                }
            ]
        ),
        encoding="utf-8",
    )

    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="demo-run",
        model="qwen2.5-coder:7b",
    )

    recovered = recover_timeout_task_result(task, config, task_output_dir)

    assert recovered is not None
    assert recovered.patch_applied is False
    assert recovered.validation_succeeded is False
    assert recovered.failure_category == "no_patch_applied"
    assert any("not counted as candidate validation success" in note for note in recovered.notes)


def test_task_flow_completed_requires_done_like_statuses_only() -> None:
    assert task_flow_terminal(["done", "completed", "superseded"]) is True
    assert task_flow_terminal(["done", "blocked"]) is False
    assert task_flow_terminal(["done", "needs_review"]) is False
    assert task_flow_completed(["done", "completed", "superseded"], timed_out=False) is True
    assert task_flow_completed(["done", "blocked"], timed_out=False) is False
    assert task_flow_completed(["done", "needs_review"], timed_out=False) is False
    assert task_flow_completed(["done"], timed_out=True) is False


def test_summarize_results_rolls_up_metrics_and_persists_report(tmp_path: Path) -> None:
    results = [
        BenchmarkTaskResult(
            instance_id="ok-1",
            repo_name="demo/ok",
            status="resolved",
            attempted=True,
            completed=True,
            resolved=True,
            patch_applied=True,
            validation_succeeded=True,
            failure_category=None,
            runtime_seconds=12.5,
            changed_files=["src/app.py"],
            validation_commands=["python -m pytest"],
            validation_results=[
                ValidationCommandResult(
                    command="python -m pytest",
                    returncode=0,
                    timed_out=False,
                    runtime_seconds=3.2,
                    stdout_path="stdout.txt",
                    stderr_path="stderr.txt",
                )
            ],
            model_settings={"provider": "ollama"},
            retry_count=1,
            manager_parse_failures=2,
        ),
        BenchmarkTaskResult(
            instance_id="bad-1",
            repo_name="demo/bad",
            status="resolved_with_open_tasks",
            attempted=True,
            completed=False,
            resolved=True,
            patch_applied=True,
            validation_succeeded=True,
            failure_category=None,
            runtime_seconds=20.0,
            changed_files=["src/app.py"],
            validation_commands=["python -m pytest"],
            validation_results=[],
            model_settings={"provider": "ollama"},
            retry_count=3,
            unblock_task_count=2,
        ),
    ]

    summary = summarize_results(results, run_label="sample-run", generated_at="2026-06-28T00:00:00Z")
    paths = persist_summary(tmp_path, summary)

    assert summary["resolved_tasks"] == 2
    assert summary["attempted_tasks"] == 2
    assert summary["patch_apply_rate"] == 1.0
    assert summary["validation_success_rate"] == 1.0
    assert summary["resolved_with_open_tasks_count"] == 1
    assert summary["total_retry_count"] == 4
    assert summary["total_unblock_task_count"] == 2
    assert summary["total_manager_parse_failures"] == 2
    assert summary["failure_categories"] == {}
    assert Path(paths["summary_path"]).exists()
    assert Path(paths["report_path"]).exists()
    assert "Resolved %" in Path(paths["report_path"]).read_text(encoding="utf-8")
    assert "Resolved with open tasks" in Path(paths["report_path"]).read_text(encoding="utf-8")


def test_run_validation_commands_captures_stdout_and_returncode(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    results = run_validation_commands(
        workspace,
        ['python -c "print(\'ok\')"'],
        tmp_path / "validation",
        timeout_seconds=30,
    )

    assert len(results) == 1
    assert results[0].returncode == 0
    assert results[0].timed_out is False
    assert Path(results[0].stdout_path).read_text(encoding="utf-8").strip() == "ok"


def test_run_validation_commands_adds_workspace_to_pythonpath(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "demo_pkg").mkdir(parents=True)
    (workspace / "tests").mkdir(parents=True)
    (workspace / "demo_pkg" / "__init__.py").write_text("VALUE = 7\n", encoding="utf-8")
    (workspace / "tests" / "check_import.py").write_text(
        "from demo_pkg import VALUE\nprint(VALUE)\n",
        encoding="utf-8",
    )

    results = run_validation_commands(
        workspace,
        ["python tests/check_import.py"],
        tmp_path / "validation-pythonpath",
        timeout_seconds=30,
    )

    assert len(results) == 1
    assert results[0].returncode == 0
    assert Path(results[0].stdout_path).read_text(encoding="utf-8").strip() == "7"


def test_run_validation_commands_disables_user_site(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    results = run_validation_commands(
        workspace,
        ['python -c "import os, site, sys; print(os.environ.get(\'PYTHONNOUSERSITE\')); print(site.ENABLE_USER_SITE); print(site.USER_SITE in sys.path)"'],
        tmp_path / "validation-user-site",
        timeout_seconds=30,
    )

    output_lines = Path(results[0].stdout_path).read_text(encoding="utf-8").strip().splitlines()

    assert output_lines == ["1", "False", "False"]


def test_checkout_workspace_commit_preserves_untracked_files_when_clean_is_false(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "bench@example.com"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Bench Harness"], cwd=source_repo, check=True, capture_output=True, text=True)
    target_file = source_repo / "app.py"
    target_file.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=source_repo, check=True, capture_output=True, text=True)
    target_file.write_text("value = 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=source_repo, check=True, capture_output=True, text=True)
    head_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    destination = tmp_path / "workspace-copy"
    stage_workspace_snapshot(source_repo, destination)
    artifact = destination / "build-artifact.txt"
    artifact.write_text("keep me\n", encoding="utf-8")

    notes = checkout_workspace_commit(destination, head_commit, clean=False)

    assert (destination / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert artifact.read_text(encoding="utf-8") == "keep me\n"
    assert any("checkout --force" in note for note in notes)


def test_build_repo_context_discovers_related_implementation_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo_root / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")
    task = BenchmarkTaskSpec(
        instance_id="demo__1",
        repo_name="demo/demo",
        problem_statement="Fix tests/test_math_utils.py so the focused pytest target passes.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_math_utils.py::test_add"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_math_utils.py -q"])

    assert "src/" in repo_context["top_level_entries"]
    assert "tests/" in repo_context["top_level_entries"]
    assert repo_context["existing_focus_paths"] == ["tests/test_math_utils.py"]
    assert "src/math_utils.py" in repo_context["related_files"]


def test_build_repo_context_uses_identifier_matches_for_related_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "django" / "conf").mkdir(parents=True)
    (repo_root / "docs" / "ref").mkdir(parents=True)
    (repo_root / "tests" / "test_utils").mkdir(parents=True)
    (repo_root / "django" / "conf" / "global_settings.py").write_text(
        "FILE_UPLOAD_PERMISSIONS = None\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "ref" / "settings.txt").write_text(
        "FILE_UPLOAD_PERMISSIONS controls uploaded file permissions.\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_utils" / "tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__1",
        repo_name="django/django",
        problem_statement="Set default FILE_UPLOAD_PERMISSION to 0o644 for FileSystemStorage uploads.",
        repo_path=repo_root.as_posix(),
        hints_text="Adjust FILE_UPLOAD_PERMISSIONS docs and release note wording.",
        fail_to_pass=["test_override_file_upload_permissions (test_utils.tests.OverrideSettingsTests)"],
    )

    repo_context = build_repo_context(
        task,
        repo_root,
        ["python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions"],
    )

    assert "django/conf/global_settings.py" in repo_context["related_files"]
    assert "docs/ref/settings.txt" in repo_context["related_files"]


def test_build_repo_context_prefers_inferred_source_files_over_tests_and_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "astropy" / "modeling" / "tests").mkdir(parents=True)
    (repo_root / "astropy" / "io" / "misc" / "asdf" / "tags" / "transform" / "tests").mkdir(parents=True)
    (repo_root / "astropy" / "io" / "misc" / "asdf" / "tags" / "transform").mkdir(parents=True, exist_ok=True)
    (repo_root / "astropy.egg-info").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "tests" / "test_separable.py").write_text(
        "from astropy.modeling.separable import separability_matrix\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "modeling" / "separable.py").write_text(
        "def separability_matrix(model):\n    return model\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "io" / "misc" / "asdf" / "tags" / "transform" / "tests" / "test_transform.py").write_text(
        "from astropy.modeling.separable import separability_matrix\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "io" / "misc" / "asdf" / "tags" / "transform" / "polynomial.py").write_text(
        "class Polynomial:\n    pass\n",
        encoding="utf-8",
    )
    (repo_root / "astropy.egg-info" / "SOURCES.txt").write_text(
        "astropy/modeling/separable.py\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__12907",
        repo_name="astropy/astropy",
        problem_statement="Fix separability_matrix for nested CompoundModels.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest astropy/modeling/tests/test_separable.py -q"])

    assert repo_context["existing_focus_paths"] == ["astropy/modeling/tests/test_separable.py"]
    assert repo_context["related_files"][0] == "astropy/modeling/separable.py"
    assert "astropy/io/misc/asdf/tags/transform/tests/test_transform.py" not in repo_context["related_files"]
    assert "astropy.egg-info/SOURCES.txt" not in repo_context["related_files"]


def test_build_repo_context_filters_retry_log_noise_from_paths_and_identifiers(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "astropy" / "modeling" / "tests").mkdir(parents=True)
    (repo_root / "mission-control").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "tests" / "test_separable.py").write_text(
        "from astropy.modeling.separable import separability_matrix\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "modeling" / "separable.py").write_text(
        "def separability_matrix(transform):\n    return transform\n",
        encoding="utf-8",
    )
    (repo_root / "mission-control" / "benchmark-protected-paths.json").write_text(
        '{"protected_paths":["astropy/modeling/tests/test_separable.py"]}\n',
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__retry_noise_filter",
        repo_name="astropy/astropy",
        problem_statement=(
            "Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels."
        ),
        repo_path=repo_root.as_posix(),
        hints_text=(
            "Retry feedback for attempt 2.\n"
            "Validation failure excerpt:\n"
            "ERROR astropy/modeling/tests/test_separable.py - ImportError: cannot import name '_coord_matrix' from "
            "'astropy.modeling.separable' "
            "(C:\\Users\\mike\\AppData\\Local\\Temp\\mc-swe-eval\\9461592234\\ws\\astropy\\modeling\\separable.py)\n"
            "Prior patch excerpt:\n"
            "-# Licensed under a 3-clause BSD style license - see LICENSE.rst\n"
            "Also mentioned: /Users/mike/AppData/Local/Temp/mc-swe-eval/9461592234/ws/astropy/modeling/separable.py"
        ),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest astropy/modeling/tests/test_separable.py -q"])

    assert "astropy/modeling/separable.py" in repo_context["related_files"]
    assert all("AppData" not in path for path in repo_context["focus_paths"])
    assert all(not path.startswith("/") for path in repo_context["focus_paths"])
    assert "ERROR" not in repo_context["identifier_terms"]
    assert "LICENSE" not in repo_context["identifier_terms"]
    assert "AppData" not in repo_context["identifier_terms"]
    assert "ImportError" not in repo_context["identifier_terms"]
    assert "separability_matrix" in repo_context["identifier_terms"]
    assert all("mission-control/" not in item for item in repo_context["related_files"])
    assert all("mission-control/" not in item for item in repo_context["implementation_anchors"])


def test_build_repo_context_includes_django_test_file_from_unittest_style_targets(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "tests" / "expressions").mkdir(parents=True)
    (repo_root / "django" / "db" / "models" / "sql").mkdir(parents=True)
    (repo_root / "tests" / "runtests.py").write_text("print('stub')\n", encoding="utf-8")
    (repo_root / "tests" / "expressions" / "tests.py").write_text(
        "\n".join(
            [
                "class BasicExpressionsTests:",
                "    def test_order_of_operations(self):",
                "        assert True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "django" / "db" / "models" / "sql" / "compiler.py").write_text(
        "class SQLCompiler:\n    pass\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="django__11001",
        repo_name="django/django",
        problem_statement="Incorrect removal of order_by clause created as multiline RawSQL.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["test_order_by_multiline_sql (expressions.tests.BasicExpressionsTests)"],
        pass_to_pass=[],
    )

    repo_context = build_repo_context(task, repo_root, ["python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"])

    assert "tests/expressions/tests.py" in repo_context["existing_focus_paths"]


def test_build_repo_context_collects_exact_code_search_hits_from_related_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "math_utils.py").write_text(
        "\n".join(
            [
                "def adjust(value):",
                "    total = normalize(value)",
                "    if value:",
                "        total = normalize(value)",
                "    return total",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_math_utils.py").write_text("def test_adjust():\n    assert True\n", encoding="utf-8")
    task = BenchmarkTaskSpec(
        instance_id="demo__code_search_context",
        repo_name="demo/repo",
        problem_statement="Fix src/math_utils.py because `total = normalize(value)` is still duplicated.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_math_utils.py::test_adjust"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_math_utils.py -q"])

    assert repo_context["existing_focus_paths"] == ["src/math_utils.py", "tests/test_math_utils.py"]
    assert "total = normalize(value)" in repo_context["code_search_needles"]
    assert repo_context["code_search_hits"] == [
        "src/math_utils.py:2: total = normalize(value)",
        "src/math_utils.py:4: total = normalize(value)",
    ]


def test_build_repo_context_prioritizes_source_code_search_hits_over_test_imports(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "separable.py").write_text(
        "\n".join(
            [
                "def separability_matrix(model):",
                "    return [[True]]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_separable.py").write_text(
        "\n".join(
            [
                "from src.separable import separability_matrix",
                "",
                "def test_separable():",
                "    assert separability_matrix(None) == [[True]]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="demo__source_first",
        repo_name="demo/repo",
        problem_statement="Fix src/separable.py because `def separability_matrix(model):` still has the wrong behavior.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_separable.py -q"])

    assert repo_context["related_files"][0] == "src/separable.py"
    assert repo_context["code_search_hits"][0].startswith("src/separable.py:")
    assert not repo_context["code_search_hits"][0].startswith("tests/test_separable.py:")
    assert any(item.startswith("src/separable.py:1: def separability_matrix(model):") for item in repo_context["implementation_anchors"])


def test_build_repo_context_drops_test_only_code_search_hits_when_source_candidates_exist(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "separable.py").write_text(
        "\n".join(
            [
                "def separability_matrix(model):",
                "    return [[True]]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_separable.py").write_text(
        "\n".join(
            [
                "from src.separable import separability_matrix",
                "",
                "def test_matrix():",
                "    assert separability_matrix(None) == [[True]]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="demo__drop_test_only_hits",
        repo_name="demo/repo",
        problem_statement=(
            "The issue mentions `from src.separable import separability_matrix`, but the real fix belongs in src/separable.py."
        ),
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_separable.py::test_matrix"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_separable.py -q"])

    assert repo_context["related_files"][0] == "src/separable.py"
    assert repo_context["code_search_hits"] == []
    assert any(item.startswith("src/separable.py:1: def separability_matrix(model):") for item in repo_context["implementation_anchors"])


def test_build_repo_context_prioritizes_function_definition_anchor_over_docstring_mentions(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "astropy" / "modeling").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "separable.py").write_text(
        "\n".join(
            [
                '"""Utilities for separability_matrix handling."""',
                "__all__ = ['is_separable', 'separability_matrix']",
                "",
                "def helper():",
                "    return 'separability_matrix helper'",
                "",
                "def separability_matrix(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "modeling" / "tests").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "tests" / "test_separable.py").write_text(
        "def test_separable():\n    assert True\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest astropy/modeling/tests/test_separable.py -q"])

    assert repo_context["implementation_anchors"][0].startswith(
        "astropy/modeling/separable.py:7: def separability_matrix(transform):"
    )
    assert any(
        item.startswith("astropy/modeling/separable.py:4: def helper():")
        for item in repo_context["implementation_anchors"]
    )


def test_build_repo_context_includes_neighbor_same_file_definitions_for_primary_anchor(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "astropy" / "modeling" / "tests").mkdir(parents=True)
    (repo_root / "astropy" / "modeling" / "separable.py").write_text(
        "\n".join(
            [
                "__all__ = ['is_separable', 'separability_matrix']",
                "",
                "def is_separable(transform):",
                "    return transform",
                "",
                "def separability_matrix(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "astropy" / "modeling" / "tests" / "test_separable.py").write_text(
        "def test_separable():\n    assert True\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest astropy/modeling/tests/test_separable.py -q"])

    assert any(
        item.startswith("astropy/modeling/separable.py:3: def is_separable(transform):")
        for item in repo_context["implementation_anchors"]
    )
    assert any(
        item.startswith("astropy/modeling/separable.py:6: def separability_matrix(transform):")
        for item in repo_context["implementation_anchors"]
    )


def test_build_repo_context_finds_equivalent_call_fragment_when_issue_snippet_uses_older_syntax(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "tests").mkdir()
    (repo_root / "src" / "compiler.py").write_text(
        "\n".join(
            [
                "def dedupe(sql):",
                "    without_ordering = self.ordering_parts.search(sql)[1]",
                "    return without_ordering",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "tests" / "test_compiler.py").write_text("def test_dedupe():\n    assert True\n", encoding="utf-8")
    task = BenchmarkTaskSpec(
        instance_id="demo__equivalent_syntax",
        repo_name="demo/repo",
        problem_statement="The issue is around `without_ordering = self.ordering_parts.search(sql).group(1)` in src/compiler.py.",
        repo_path=repo_root.as_posix(),
        fail_to_pass=["tests/test_compiler.py::test_dedupe"],
    )

    repo_context = build_repo_context(task, repo_root, ["python -m pytest tests/test_compiler.py -q"])

    assert "self.ordering_parts.search(sql)" in repo_context["code_search_needles"]
    assert "src/compiler.py:2: without_ordering = self.ordering_parts.search(sql)[1]" in repo_context["code_search_hits"]


def test_stage_workspace_snapshot_resets_to_requested_base_commit(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "bench@example.com"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Bench Harness"], cwd=source_repo, check=True, capture_output=True, text=True)
    target_file = source_repo / "app.py"
    target_file.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=source_repo, check=True, capture_output=True, text=True)
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target_file.write_text("value = 2\n", encoding="utf-8")
    (source_repo / "scratch.tmp").write_text("remove me\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=source_repo, check=True, capture_output=True, text=True)

    destination = tmp_path / "workspace-copy"
    notes = stage_workspace_snapshot(source_repo, destination, base_commit=base_commit)

    assert (destination / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not (destination / "scratch.tmp").exists()
    assert any("git clone --local" in note for note in notes)
    assert any("checkout --force" in note for note in notes)


def test_stage_workspace_snapshot_copies_non_git_workspace_as_is(tmp_path: Path) -> None:
    source_workspace = tmp_path / "plain-workspace"
    source_workspace.mkdir()
    (source_workspace / "module.py").write_text("value = 1\n", encoding="utf-8")

    destination = tmp_path / "workspace-copy"
    notes = stage_workspace_snapshot(source_workspace, destination)

    assert (destination / "module.py").read_text(encoding="utf-8") == "value = 1\n"
    assert notes == []


def test_run_evaluator_validation_replays_candidate_patch_and_applies_test_patch(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "bench@example.com"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Bench Harness"], cwd=source_repo, check=True, capture_output=True, text=True)
    (source_repo / "module.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "module.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=source_repo, check=True, capture_output=True, text=True)
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    candidate_workspace = tmp_path / "candidate-workspace"
    stage_workspace_snapshot(source_repo, candidate_workspace, base_commit=base_commit)
    (candidate_workspace / "module.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    task = BenchmarkTaskSpec(
        instance_id="demo__eval",
        repo_name="demo/repo",
        problem_statement="Fix add().",
        repo_path=source_repo.as_posix(),
        base_commit=base_commit,
        validation_commands=["python -m pytest tests/test_module.py -q"],
        fail_to_pass=["tests/test_module.py::test_add"],
        test_patch=(
            "diff --git a/tests/test_module.py b/tests/test_module.py\n"
            "new file mode 100644\n"
            "index 0000000..73791fa\n"
            "--- /dev/null\n"
            "+++ b/tests/test_module.py\n"
            "@@ -0,0 +1,4 @@\n"
            "+from module import add\n"
            "+\n"
            "+def test_add():\n"
            "+    assert add(1, 2) == 3\n"
        ),
    )

    evaluator = run_evaluator_validation(
        task,
        candidate_workspace,
        ["module.py"],
        tmp_path / "evaluator",
        timeout_seconds=60,
    )

    assert evaluator.attempted is True
    assert evaluator.succeeded is True
    assert evaluator.test_patch_applied is True
    assert evaluator.commands == ["python -m pytest tests/test_module.py -q"]
    assert Path(evaluator.artifact_paths["workspace_path"]).joinpath("tests", "test_module.py").exists()
    assert Path(evaluator.artifact_paths["authoritative_workspace_path"]).name == "auth"


def test_run_evaluator_validation_ignores_candidate_edits_that_overlap_test_patch(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-repo"
    source_repo.mkdir()
    subprocess.run(["git", "init"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "bench@example.com"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Bench Harness"], cwd=source_repo, check=True, capture_output=True, text=True)
    (source_repo / "module.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "module.py"], cwd=source_repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=source_repo, check=True, capture_output=True, text=True)
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    candidate_workspace = tmp_path / "candidate-workspace"
    stage_workspace_snapshot(source_repo, candidate_workspace, base_commit=base_commit)
    (candidate_workspace / "module.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (candidate_workspace / "tests").mkdir(parents=True, exist_ok=True)
    (candidate_workspace / "tests" / "test_module.py").write_text(
        "def test_add():\n    assert False\n",
        encoding="utf-8",
    )

    task = BenchmarkTaskSpec(
        instance_id="demo__eval_protected",
        repo_name="demo/repo",
        problem_statement="Fix add().",
        repo_path=source_repo.as_posix(),
        base_commit=base_commit,
        validation_commands=["python -m pytest tests/test_module.py -q"],
        fail_to_pass=["tests/test_module.py::test_add"],
        test_patch=(
            "diff --git a/tests/test_module.py b/tests/test_module.py\n"
            "new file mode 100644\n"
            "index 0000000..73791fa\n"
            "--- /dev/null\n"
            "+++ b/tests/test_module.py\n"
            "@@ -0,0 +1,4 @@\n"
            "+from module import add\n"
            "+\n"
            "+def test_add():\n"
            "+    assert add(1, 2) == 3\n"
        ),
    )

    evaluator = run_evaluator_validation(
        task,
        candidate_workspace,
        ["module.py", "tests/test_module.py"],
        tmp_path / "evaluator-protected",
        timeout_seconds=60,
    )

    replay_report = json.loads((tmp_path / "evaluator-protected" / "candidate-change-replay.json").read_text(encoding="utf-8"))

    assert evaluator.attempted is True
    assert evaluator.succeeded is True
    assert replay_report["replayed_files"] == ["module.py"]
    assert replay_report["skipped_protected_files"] == ["tests/test_module.py"]


def test_filter_benchmark_protected_changed_files_ignores_solver_test_patch_overlap() -> None:
    kept, skipped = filter_benchmark_protected_changed_files(
        ["django/db/models/sql/compiler.py", "tests/expressions/tests.py"],
        (
            "diff --git a/tests/expressions/tests.py b/tests/expressions/tests.py\n"
            "--- a/tests/expressions/tests.py\n"
            "+++ b/tests/expressions/tests.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+pass\n"
        ),
    )

    assert kept == ["django/db/models/sql/compiler.py"]
    assert skipped == ["tests/expressions/tests.py"]


def test_audit_task_readiness_flags_missing_base_commit_and_missing_validation(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "bench@example.com"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Bench Harness"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo_root, check=True, capture_output=True, text=True)

    audit = audit_task_readiness(
        [
            BenchmarkTaskSpec(
                instance_id="demo__1",
                repo_name="demo/demo",
                problem_statement="Fix the regression.",
                repo_path=repo_root.as_posix(),
                base_commit="deadbeef",
            )
        ]
    )

    assert audit["ready"] is False
    assert audit["missing_base_commit_count"] == 1
    assert audit["no_validation_count"] == 1
    assert "missing_base_commit:demo__1" in audit["blockers"]
    assert "no_validation_detected" in audit["tasks"][0]["notes"]


def test_benchmark_preflight_blocks_missing_exact_ollama_model(tmp_path: Path) -> None:
    manifest = tmp_path / "tasks.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "instance_id": "demo__1",
                "problem_statement": "Fix the regression.",
                "repo_path": tmp_path.as_posix(),
            }
        ),
        encoding="utf-8",
    )
    config = HarnessRunConfig(
        tasks_path=manifest.as_posix(),
        output_root="Tests/swe-bench-lite-runs",
        run_label="sample",
        model="qwen2.5-coder:7b",
        provider="ollama",
        strict_model=True,
    )

    preflight = benchmark_preflight(config, available_models=["qwen2.5:7b", "gpt-oss:20b"])

    assert preflight["ready"] is False
    assert preflight["blockers"] == ["missing_exact_model:qwen2.5-coder:7b"]


def test_benchmark_preflight_includes_manifest_task_audit(tmp_path: Path) -> None:
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "instance_id": "missing__repo",
                        "problem_statement": "Fix the regression.",
                        "repo_path": "./does-not-exist",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config = HarnessRunConfig(
        tasks_path=manifest.as_posix(),
        output_root="Tests/swe-bench-lite-runs",
        run_label="sample",
        model="qwen2.5-coder:7b",
        provider="ollama",
        strict_model=True,
    )

    preflight = benchmark_preflight(config, available_models=["qwen2.5-coder:7b"])

    assert preflight["ready"] is False
    assert "missing_repo:missing__repo" in preflight["blockers"]
    assert preflight["task_audit"]["missing_repo_count"] == 1
    assert preflight["task_audit"]["tasks"][0]["repo_exists"] is False


def test_select_tasks_supports_chunking_and_exact_ids() -> None:
    tasks = [
        type("Task", (), {"instance_id": "a"})(),
        type("Task", (), {"instance_id": "b"})(),
        type("Task", (), {"instance_id": "c"})(),
        type("Task", (), {"instance_id": "d"})(),
    ]

    sliced = select_tasks(tasks, start_index=1, max_tasks=2)
    filtered = select_tasks(tasks, task_ids=["d", "b", "missing"])
    combined = select_tasks(tasks, start_index=1, max_tasks=1, task_ids=["b", "c", "d"])

    assert [task.instance_id for task in sliced] == ["b", "c"]
    assert [task.instance_id for task in filtered] == ["b", "d"]
    assert [task.instance_id for task in combined] == ["c"]


def test_harness_run_config_round_trips_chunking_fields() -> None:
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root="Tests/swe-bench-lite-runs",
        run_label="chunked",
        dataset_split="dev",
        model="qwen2.5-coder:7b",
        provider="ollama",
        strict_model=True,
        max_task_attempts=3,
        start_index=7,
        max_tasks=25,
        task_ids=["django__1", "sympy__2"],
        prepared_repos_root="C:/bench/prepared",
        repo_map_path="C:/bench/repo-map.json",
        repo_cache_root="C:/bench/repo-cache",
        auto_prepare_repos=True,
    )

    restored = HarnessRunConfig.from_dict(config.to_dict())

    assert restored.start_index == 7
    assert restored.max_tasks == 25
    assert restored.task_ids == ["django__1", "sympy__2"]
    assert restored.dataset_split == "dev"
    assert restored.max_task_attempts == 3
    assert restored.prepared_repos_root == "C:/bench/prepared"
    assert restored.repo_map_path == "C:/bench/repo-map.json"
    assert restored.repo_cache_root == "C:/bench/repo-cache"
    assert restored.auto_prepare_repos is True


def test_run_single_task_retries_failed_validated_patch_with_local_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_root = tmp_path / "task-run"
    diff_path = tmp_path / "attempt-01.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "@@ -1,3 +1,4 @@",
                "+if isinstance(transform, CompoundModel) and transform.has_nested_compound_models:",
                "+    return _separable(transform.left, transform.right)",
            ]
        ),
        encoding="utf-8",
    )
    stdout_path = tmp_path / "attempt-01.stdout.txt"
    stderr_path = tmp_path / "attempt-01.stderr.txt"
    stdout_path.write_text("FAILED astropy/modeling/tests/test_separable.py::test_regression\n", encoding="utf-8")
    stderr_path.write_text("AttributeError: 'CompoundModel' object has no attribute 'has_nested_compound_models'\n", encoding="utf-8")

    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_regression"],
    )
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="retry-task",
        model="qwen2.5-coder:7b",
        max_task_attempts=2,
    )
    observed_hints: list[str | None] = []

    def fake_run_single_task_attempt(current_task, current_config, attempt_output_dir):
        observed_hints.append(current_task.hints_text)
        if len(observed_hints) == 1:
            assert attempt_output_dir.name == "attempt-01"
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="validation_failed",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=True,
                validation_succeeded=False,
                failure_category="validation_failed",
                runtime_seconds=12.0,
                changed_files=["astropy/modeling/separable.py"],
                validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                validation_results=[
                    ValidationCommandResult(
                        command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                        returncode=1,
                        timed_out=False,
                        runtime_seconds=2.0,
                        stdout_path=stdout_path.as_posix(),
                        stderr_path=stderr_path.as_posix(),
                    )
                ],
                artifact_paths={
                    "task_output_dir": attempt_output_dir.as_posix(),
                    "diff_path": diff_path.as_posix(),
                },
            )
        assert attempt_output_dir.name == "attempt-02"
        retry_hints = current_task.hints_text or ""
        assert "failed authoritative validation" in retry_hints
        assert "astropy/modeling/separable.py" in retry_hints
        assert "AttributeError" in retry_hints
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="resolved",
            attempted=True,
            completed=True,
            resolved=True,
            patch_applied=True,
            validation_succeeded=True,
            failure_category=None,
            runtime_seconds=8.0,
            changed_files=["astropy/modeling/separable.py"],
            validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            validation_results=[],
            artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
        )

    monkeypatch.setattr(harness_script, "_run_single_task_attempt", fake_run_single_task_attempt)

    result = harness_script._run_single_task(task, config, task_root)

    attempts_payload = json.loads((task_root / "attempts.json").read_text(encoding="utf-8"))
    assert len(observed_hints) == 2
    assert observed_hints[0] is None
    assert result.resolved is True
    assert result.model_settings["attempt_count"] == 2
    assert result.model_settings["max_task_attempts"] == 2
    assert result.artifact_paths["task_output_dir"] == task_root.as_posix()
    assert result.artifact_paths["final_attempt_dir"].endswith("attempt-02")
    assert len(attempts_payload) == 2
    assert attempts_payload[0]["failure_category"] == "validation_failed"
    assert any("Ran 2 benchmark attempts" in note for note in result.notes)


def test_validation_failure_excerpt_includes_error_signatures_from_stdout(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "\n".join(
            [
                "....FFFF",
                "Traceback (most recent call last):",
                "  File \"astropy/modeling/separable.py\", line 68, in separability_matrix",
                "AttributeError: Attribute \"components\" not found",
                "FAILED astropy/modeling/tests/test_separable.py::test_regression",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = ValidationCommandResult(
        command="python -m pytest astropy/modeling/tests/test_separable.py -q",
        returncode=1,
        timed_out=False,
        runtime_seconds=1.0,
        stdout_path=stdout_path.as_posix(),
        stderr_path=None,
    )

    excerpt = harness_script._validation_failure_excerpt([result], max_chars=900)

    assert excerpt is not None
    assert "Error signatures:" in excerpt
    assert "Traceback (most recent call last):" in excerpt
    assert 'AttributeError: Attribute "components" not found' in excerpt


def test_build_retry_feedback_flags_same_file_sibling_anchor_from_failing_assertion(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "\n".join(
            [
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]",
                "    assert_allclose(is_separable(compound_model), result[0])",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -98,7 +98,7 @@",
                "-    separable_matrix = np.where(separable_matrix != 0, True, False)",
                "+    separable_matrix = (separable_matrix != 0).astype(bool)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    repo_context_path = tmp_path / "repo-context.json"
    repo_context_path.write_text(
        json.dumps(
            {
                "implementation_anchors": [
                    "astropy/modeling/separable.py:27: def is_separable(transform):",
                    "astropy/modeling/separable.py:66: def separability_matrix(transform):",
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={
            "diff_path": diff_path.as_posix(),
            "repo_context_path": repo_context_path.as_posix(),
        },
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "remaining failing assertion still centers on `is_separable`" in feedback
    assert "previous patch targeted `separability_matrix`" in feedback


def test_build_retry_feedback_flags_syntax_or_runtime_breakage_direction(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "\n".join(
            [
                "Traceback (most recent call last):",
                "IndentationError: expected an indented block after 'if' statement on line 100",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "introduced a direct syntax/runtime error" in feedback
    assert "IndentationError" in feedback
    assert "keep the original control flow and function structure intact" in feedback


def test_build_retry_feedback_flags_output_coercion_only_patch_direction(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -59,7 +59,7 @@",
                "-    is_separable = np.where(is_separable != 1, False, True)",
                "+    is_separable = is_separable.astype(bool)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "only changed the final boolean coercion for `is_separable`" in feedback
    assert "Inspect the upstream calculation or earlier helper" in feedback


def test_build_retry_feedback_flags_invented_helper_signature_rewrite(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "\n".join(
            [
                "Traceback (most recent call last):",
                "TypeError: _compute_n_outputs() missing 1 required positional argument: 'right'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -97,7 +97,7 @@",
                "-    separable_matrix = _separable(transform)",
                "+    separable_matrix = _compute_n_outputs(_arith_oper(transform, transform))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "invented an internal helper-call rewrite" in feedback
    assert "_compute_n_outputs() missing 1 required positional argument" in feedback
    assert "Do not replace the existing core expression with a new helper-call chain" in feedback


def test_build_retry_feedback_prioritizes_fresh_retry_evidence_over_older_hints(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -59,7 +59,7 @@",
                "-    is_separable = np.where(is_separable != 1, False, True)",
                "+    is_separable = is_separable.astype(bool)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
        hints_text="OLDER STATIC HINTS " * 80,
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert feedback.startswith("Retry feedback for attempt 2:")
    assert "Highest-priority correction cues:" in feedback
    assert "only changed the final boolean coercion for `is_separable`" in feedback
    assert "Earlier hints (lower priority than the fresh failure evidence above):" in feedback


def test_build_retry_feedback_flags_new_regressions_outside_expected_targets(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "\n".join(
            [
                "FAILED astropy/modeling/tests/test_separable.py::test_regression",
                "FAILED astropy/modeling/tests/test_separable.py::test_unrelated_regression",
            ]
        ),
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "@@ -59,7 +59,7 @@",
                "-    is_separable = np.where(is_separable != 1, False, True)",
                "+    is_separable = np.any(is_separable != 0, axis=1)",
            ]
        ),
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_regression"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=10.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path="",
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    retry_feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "introduced additional failing targets outside the original benchmark regression set" in retry_feedback
    assert "test_unrelated_regression" in retry_feedback
    assert "Revert that direction and preserve unrelated behavior" in retry_feedback


def test_build_retry_feedback_flags_multiline_equivalent_output_normalization_patch(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -59,7 +59,8 @@",
                "-    separable_matrix = np.where(separable_matrix != 0, True, False)",
                "+    separable_matrix[separable_matrix == 0] = False",
                "+    separable_matrix[separable_matrix != 0] = True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "only changed the final boolean coercion for `separable_matrix`" in feedback
    assert "equivalent output-normalization tweak" in feedback


def test_build_retry_feedback_flags_sibling_source_boolean_coercion_patch(tmp_path: Path) -> None:
    stdout_path = tmp_path / "validation.stdout.txt"
    stdout_path.write_text(
        "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model0-result0]\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "workspace.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -98,7 +98,7 @@",
                "-    separable_matrix = np.where(separable_matrix != 0, True, False)",
                "+    separable_matrix = separability_matrix.astype(bool)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
        fail_to_pass=["astropy/modeling/tests/test_separable.py::test_separable[compound_model0-result0]"],
    )
    previous_result = BenchmarkTaskResult(
        instance_id=task.instance_id,
        repo_name=task.repo_name,
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    feedback = harness_script._build_retry_feedback(task, previous_result, attempt_number=2)

    assert "only changed the final boolean coercion for `separable_matrix`" in feedback
    assert "equivalent output-normalization tweak" in feedback


def test_attempt_selection_score_demotes_equivalent_output_normalization_patch(tmp_path: Path) -> None:
    strong_diff_path = tmp_path / "substantive.diff"
    strong_diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -97,7 +97,7 @@",
                "-    return _separable(transform.left) & _separable(transform.right)",
                "+    return _separable(transform.left) | _separable(transform.right)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    low_value_diff_path = tmp_path / "low-value.diff"
    low_value_diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -59,7 +59,8 @@",
                "-    separable_matrix = np.where(separable_matrix != 0, True, False)",
                "+    separable_matrix[separable_matrix == 0] = False",
                "+    separable_matrix[separable_matrix != 0] = True",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    substantive_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=None,
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": strong_diff_path.as_posix()},
    )
    low_value_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=None,
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": low_value_diff_path.as_posix()},
    )

    assert harness_script._attempt_selection_score(substantive_result) > harness_script._attempt_selection_score(
        low_value_result
    )


def test_attempt_selection_score_demotes_boolean_reduction_rewrite(tmp_path: Path) -> None:
    strong_diff_path = tmp_path / "substantive.diff"
    strong_diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -97,7 +97,7 @@",
                "-    return _separable(transform.left) & _separable(transform.right)",
                "+    return _separable(transform.left) | _separable(transform.right)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    low_value_diff_path = tmp_path / "low-value-any.diff"
    low_value_diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -59,7 +59,7 @@",
                "-    is_separable = np.where(is_separable != 1, False, True)",
                "+    is_separable = np.any(separable_matrix, axis=1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    substantive_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=None,
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": strong_diff_path.as_posix()},
    )
    low_value_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=None,
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": low_value_diff_path.as_posix()},
    )

    assert harness_script._attempt_selection_score(substantive_result) > harness_script._attempt_selection_score(
        low_value_result
    )


def test_attempt_selection_score_prefers_fewer_remaining_validation_failures(tmp_path: Path) -> None:
    better_stdout_path = tmp_path / "better.stdout.txt"
    better_stdout_path.write_text(
        "\n".join(
            [
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model0-result0]",
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model1-result1]",
                "2 failed, 13 passed in 0.25s",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    worse_stdout_path = tmp_path / "worse.stdout.txt"
    worse_stdout_path.write_text(
        "\n".join(
            [
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model0-result0]",
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model1-result1]",
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model2-result2]",
                "FAILED astropy/modeling/tests/test_separable.py::test_separable[compound_model3-result3]",
                "4 failed, 11 passed in 0.25s",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    diff_path = tmp_path / "substantive.diff"
    diff_path.write_text(
        "\n".join(
            [
                "diff --git a/astropy/modeling/separable.py b/astropy/modeling/separable.py",
                "--- a/astropy/modeling/separable.py",
                "+++ b/astropy/modeling/separable.py",
                "@@ -97,7 +97,7 @@",
                "-    return _separable(transform.left) & _separable(transform.right)",
                "+    return _separable(transform.left) | _separable(transform.right)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    better_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=better_stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )
    worse_result = BenchmarkTaskResult(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        status="validation_failed",
        attempted=True,
        completed=False,
        resolved=False,
        patch_applied=True,
        validation_succeeded=False,
        failure_category="validation_failed",
        runtime_seconds=5.0,
        changed_files=["astropy/modeling/separable.py"],
        validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
        validation_results=[
            ValidationCommandResult(
                command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                returncode=1,
                timed_out=False,
                runtime_seconds=1.0,
                stdout_path=worse_stdout_path.as_posix(),
                stderr_path=None,
            )
        ],
        artifact_paths={"diff_path": diff_path.as_posix()},
    )

    assert harness_script._attempt_selection_score(better_result) > harness_script._attempt_selection_score(
        worse_result
    )


def test_run_single_task_keeps_best_attempt_when_later_retry_regresses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
    )
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="retry-task-best-attempt",
        model="qwen2.5-coder:7b",
        max_task_attempts=2,
    )

    def fake_run_single_task_attempt(_current_task, _current_config, attempt_output_dir):
        if attempt_output_dir.name == "attempt-01":
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="validation_failed",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=True,
                validation_succeeded=False,
                failure_category="validation_failed",
                runtime_seconds=12.0,
                changed_files=["astropy/modeling/separable.py"],
                validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                validation_results=[
                    ValidationCommandResult(
                        command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                        returncode=1,
                        timed_out=False,
                        runtime_seconds=2.0,
                        stdout_path=None,
                        stderr_path=None,
                    )
                ],
                artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
            )
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="runner_failed",
            attempted=True,
            completed=False,
            resolved=False,
            patch_applied=False,
            validation_succeeded=False,
            failure_category="runner_failed",
            runtime_seconds=8.0,
            changed_files=[],
            validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            validation_results=[],
            artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
        )

    monkeypatch.setattr(harness_script, "_run_single_task_attempt", fake_run_single_task_attempt)

    result = harness_script._run_single_task(task, config, task_root)

    assert result.patch_applied is True
    assert result.failure_category == "validation_failed"
    assert result.changed_files == ["astropy/modeling/separable.py"]
    assert result.model_settings["attempt_count"] == 2
    assert result.artifact_paths["final_attempt_dir"].endswith("attempt-01")
    assert result.artifact_paths["last_attempt_dir"].endswith("attempt-02")
    assert any("Selected attempt 1 as the benchmark result" in note for note in result.notes)


def test_run_single_task_carries_forward_patch_apply_evidence_from_earlier_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
    )
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="retry-task-carry-forward-patch-evidence",
        model="qwen2.5-coder:7b",
        max_task_attempts=2,
    )

    def fake_run_single_task_attempt(_current_task, _current_config, attempt_output_dir):
        if attempt_output_dir.name == "attempt-01":
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="validation_failed",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=True,
                validation_succeeded=False,
                failure_category="validation_failed",
                runtime_seconds=12.0,
                changed_files=["astropy/modeling/separable.py"],
                validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                validation_results=[],
                artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
            )
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="runner_failed",
            attempted=True,
            completed=False,
            resolved=False,
            patch_applied=False,
            validation_succeeded=False,
            failure_category="runner_failed",
            runtime_seconds=8.0,
            changed_files=[],
            validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            validation_results=[
                ValidationCommandResult(
                    command="python -m pytest astropy/modeling/tests/test_separable.py -q",
                    returncode=1,
                    timed_out=False,
                    runtime_seconds=1.0,
                    stdout_path=None,
                    stderr_path=None,
                )
            ],
            artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
        )

    monkeypatch.setattr(harness_script, "_run_single_task_attempt", fake_run_single_task_attempt)

    result = harness_script._run_single_task(task, config, task_root)

    assert result.failure_category == "runner_failed"
    assert result.patch_applied is True
    assert result.changed_files == ["astropy/modeling/separable.py"]
    assert any("Earlier attempts produced candidate patches" in note for note in result.notes)


def test_run_single_task_retries_against_last_patch_validation_failure_after_no_patch_regression(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_root = tmp_path / "task"
    task_root.mkdir(parents=True)
    task = BenchmarkTaskSpec(
        instance_id="astropy__astropy-12907",
        repo_name="astropy/astropy",
        problem_statement="Fix the regression in separability_matrix for nested CompoundModels.",
        repo_path=tmp_path.as_posix(),
    )
    config = HarnessRunConfig(
        tasks_path="tasks.jsonl",
        output_root=tmp_path.as_posix(),
        run_label="retry-task-preserve-patch-feedback",
        model="qwen2.5-coder:7b",
        max_task_attempts=3,
    )
    seen_hints: list[str] = []

    def fake_run_single_task_attempt(current_task, _current_config, attempt_output_dir):
        seen_hints.append(str(current_task.hints_text or ""))
        if attempt_output_dir.name == "attempt-01":
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="validation_failed",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=True,
                validation_succeeded=False,
                failure_category="validation_failed",
                runtime_seconds=12.0,
                changed_files=["astropy/modeling/separable.py"],
                validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                validation_results=[],
                artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
            )
        if attempt_output_dir.name == "attempt-02":
            return BenchmarkTaskResult(
                instance_id=task.instance_id,
                repo_name=task.repo_name,
                status="runner_failed",
                attempted=True,
                completed=False,
                resolved=False,
                patch_applied=False,
                validation_succeeded=False,
                failure_category="runner_failed",
                runtime_seconds=8.0,
                changed_files=[],
                validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
                validation_results=[],
                artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
            )
        return BenchmarkTaskResult(
            instance_id=task.instance_id,
            repo_name=task.repo_name,
            status="runner_failed",
            attempted=True,
            completed=False,
            resolved=False,
            patch_applied=False,
            validation_succeeded=False,
            failure_category="runner_failed",
            runtime_seconds=7.0,
            changed_files=[],
            validation_commands=["python -m pytest astropy/modeling/tests/test_separable.py -q"],
            validation_results=[],
            artifact_paths={"task_output_dir": attempt_output_dir.as_posix()},
        )

    monkeypatch.setattr(harness_script, "_run_single_task_attempt", fake_run_single_task_attempt)

    result = harness_script._run_single_task(task, config, task_root)

    attempts_payload = json.loads((task_root / "attempts.json").read_text(encoding="utf-8"))
    assert len(attempts_payload) == 3
    assert "applied a candidate patch but failed authoritative validation" in seen_hints[1]
    assert "continue iterating from the most recent authoritative patch-validation attempt" in seen_hints[2]
    assert result.model_settings["attempt_count"] == 3


def test_benchmark_task_spec_round_trips_lowercase_validation_targets() -> None:
    original = BenchmarkTaskSpec(
        instance_id="demo__1",
        problem_statement="Fix the regression.",
        repo_path="C:/bench/demo",
        fail_to_pass=["tests/test_bug.py::test_regression"],
        pass_to_pass=["tests/test_ok.py::test_ok"],
        setup_commands=["python -m pip install -e ."],
        metadata={"environment_setup_commit": "def456"},
    )

    restored = BenchmarkTaskSpec.from_record(original.to_dict())

    assert restored.fail_to_pass == ["tests/test_bug.py::test_regression"]
    assert restored.pass_to_pass == ["tests/test_ok.py::test_ok"]
    assert restored.setup_commands == ["python -m pip install -e ."]
    assert restored.metadata["environment_setup_commit"] == "def456"
