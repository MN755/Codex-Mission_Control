import asyncio
from pathlib import Path

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerSettings
from codex_runner.claude_code_runner import ClaudeCodeRunner
from codex_runner.cli_runner import CliCodexRunner
from codex_runner.dry_run_runner import DryRunRunner
from codex_runner.events import parse_json_line
from manager import RunnerRegistry
from models import Agent, Project, Task
from project_settings import ResolvedRunSettings
from system_status import detect_system_status


def test_parse_json_line_handles_structured_and_raw_output() -> None:
    assert parse_json_line('{"type":"thread.started","thread_id":"abc"}') == {"type": "thread.started", "thread_id": "abc"}
    assert parse_json_line("plain text") == {"type": "raw.output", "text": "plain text"}


def test_runner_registry_auto_falls_back_to_codex_cli(monkeypatch) -> None:
    registry = RunnerRegistry()
    monkeypatch.setattr(registry, "app_server_available", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setattr(registry, "codex_cli_available", lambda: asyncio.sleep(0, result=True))
    resolved = ResolvedRunSettings(
        provider="codex",
        provider_label="Codex",
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model=None,
        reasoning_effort=None,
        adapter_command=None,
        adapter_args=[],
        effective_model_label="Codex default",
        effective_reasoning_label="Codex default",
    )
    runner = asyncio.run(registry.get_runner_for_settings(resolved))
    assert runner.runner_type == "codex_cli"


def test_runner_registry_selects_claude_cli(monkeypatch) -> None:
    registry = RunnerRegistry()
    monkeypatch.setattr(registry, "claude_cli_available", lambda: asyncio.sleep(0, result=True))
    resolved = ResolvedRunSettings(
        provider="claude_code",
        provider_label="Claude Code",
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="sonnet",
        reasoning_effort=None,
        adapter_command=None,
        adapter_args=[],
        effective_model_label="sonnet",
        effective_reasoning_label="Claude Code default",
    )
    runner = asyncio.run(registry.get_runner_for_settings(resolved))
    assert runner.runner_type == "claude_code_cli"


def test_try_parse_json_payload_repairs_fenced_trailing_comma_json() -> None:
    payload, repaired = BaseCodexRunner.try_parse_json_payload(
        """```json
{"status":"done","summary":"ok",}
```"""
    )
    assert repaired is True
    assert payload == {"status": "done", "summary": "ok"}


def test_dry_run_runner_reaches_done_state() -> None:
    async def run_test() -> None:
        runner = DryRunRunner()
        project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="dry_run", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/demo")
        task = Task(
            id=3,
            project_id=1,
            title="Simulated task",
            goal="Goal",
            scope="Scope",
            agent_role="Primary implementation",
            milestone="Milestone 1",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["step"],
            success_criteria_json=["done"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=10,
        )
        context = RunnerContext(project=project, agent=agent, task=task, docs_path="C:/demo/mission-control")
        handle = await runner.start_task(context)
        for _ in range(8):
            await asyncio.sleep(0.5)
            if await runner.get_status(handle.id) == "done":
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        assert any(event.get("type") == "turn.completed" for event in events)

    asyncio.run(run_test())


def test_cli_build_exec_args_include_model_and_reasoning_when_set() -> None:
    runner = CliCodexRunner()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/demo")
    task = Task(
        id=3,
        project_id=1,
        title="Task",
        goal="Goal",
        scope="Scope",
        agent_role="Primary implementation",
        milestone="Milestone 1",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["step"],
        success_criteria_json=["done"],
        estimated_complexity="small",
        dependencies_json=[],
        status="backlog",
        priority=10,
    )
    context = RunnerContext(
        project=project,
        agent=agent,
        task=task,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model="gpt-5.5",
            reasoning_effort="high",
        ),
    )
    args = runner.build_exec_args(context, resume=False)
    assert "-m" in args
    assert "gpt-5.5" in args
    assert any('model_reasoning_effort="high"' == value for value in args)


def test_cli_build_exec_args_omit_model_when_unset() -> None:
    runner = CliCodexRunner()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/demo")
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model=None,
            reasoning_effort=None,
        ),
    )
    args = runner.build_exec_args(context, resume=False)
    assert "-m" not in args
    assert not any("model_reasoning_effort" in value for value in args)


def test_claude_build_exec_args_include_model_when_set() -> None:
    runner = ClaudeCodeRunner()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/demo")
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(
            provider="claude_code",
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model="sonnet",
            reasoning_effort=None,
        ),
    )
    args = runner.build_exec_args(context, resume=False)
    assert "--model" in args
    assert "sonnet" in args
    assert "--output-format" in args


def test_launcher_scripts_exist() -> None:
    root = Path(__file__).resolve().parents[3]
    scripts = root / "scripts"
    assert (scripts / "start-mission-control.ps1").exists()
    assert (scripts / "start-mission-control.bat").exists()
    assert (scripts / "start-mission-control.sh").exists()
    assert (scripts / "create-desktop-shortcut.ps1").exists()
    assert (scripts / "stop-mission-control.ps1").exists()
    assert (scripts / "package-desktop.ps1").exists()
    assert (scripts / "package-desktop.sh").exists()
    assert (scripts / "package-desktop.py").exists()
    assert (root / "apps" / "desktop" / "src" / "mission_control_desktop" / "app.py").exists()
    assert (root / ".github" / "workflows" / "package-desktop.yml").exists()
    assert (root / "apps" / "desktop" / "assets" / "mission-control.svg").exists()
    config_text = (scripts / "mission-control.config.json").read_text(encoding="utf-8")
    assert '"backendPort": 8000' in config_text
    assert '"frontendPort": 5173' in config_text


def test_system_status_includes_provider_matrix() -> None:
    status = detect_system_status(selected_provider="claude_code")
    assert status["selected_provider"] == "claude_code"
    assert any(provider["provider"] == "codex" for provider in status["provider_statuses"])
    assert any(provider["provider"] == "claude_code" for provider in status["provider_statuses"])
