from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerSettings
from codex_runner.cli_runner import CliCodexRunner
from models import Agent, Project


def _context(*, session_ref: str | None = None) -> RunnerContext:
    project = Project(
        id=1,
        name="Demo",
        idea="Idea",
        workspace_path="C:/demo",
        status="building",
        runner_mode="cli",
        manager_mode="auto",
    )
    agent = Agent(
        id=2,
        project_id=1,
        name="Worker",
        role="Implementation",
        kind="worker",
        status="idle",
        workspace_path="C:/demo",
        session_ref=session_ref,
    )
    return RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model="gpt-5.5",
            reasoning_effort="high",
        ),
    )


def test_quiet_subprocess_kwargs_are_empty_or_creationflags() -> None:
    kwargs = BaseCodexRunner.quiet_subprocess_kwargs()
    assert set(kwargs).issubset({"creationflags"})


def test_cli_resume_args_do_not_include_initial_exec_only_flags(monkeypatch) -> None:
    monkeypatch.setattr("codex_runner.cli_runner.codex_command_path", lambda: "C:/tools/codex.exe")
    args = CliCodexRunner().build_exec_args(_context(session_ref="thread-123"), resume=True)

    assert args[:4] == ["C:/tools/codex.exe", "exec", "resume", "--json"]
    assert "thread-123" in args
    assert "--sandbox" not in args
    assert "-a" not in args
    assert "-C" not in args


def test_cli_initial_exec_args_keep_workspace_and_approval_flags(monkeypatch) -> None:
    monkeypatch.setattr("codex_runner.cli_runner.codex_command_path", lambda: "C:/tools/codex.exe")
    args = CliCodexRunner().build_exec_args(_context(), resume=False)

    assert args[:3] == ["C:/tools/codex.exe", "exec", "--json"]
    assert "--sandbox" in args
    assert "-a" in args
    assert "-C" in args
