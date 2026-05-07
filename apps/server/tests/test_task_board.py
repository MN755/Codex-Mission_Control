from types import SimpleNamespace

from task_board import can_assign_task, paths_conflict


def test_paths_conflict_when_root_path_is_shared() -> None:
    assert paths_conflict(["."], ["src"])
    assert paths_conflict(["src"], ["src"])
    assert not paths_conflict(["frontend"], ["tests"])


def test_non_git_workspace_prevents_overlapping_writer_assignment() -> None:
    agent = SimpleNamespace(id=1)
    task = SimpleNamespace(status="backlog", allowed_paths_json=["src"])
    other_busy_agent = SimpleNamespace(id=2, status="working", locked_paths_json=["src"])
    assert not can_assign_task(agent, task, [other_busy_agent], is_git_workspace=False)
    assert can_assign_task(agent, task, [other_busy_agent], is_git_workspace=True)

