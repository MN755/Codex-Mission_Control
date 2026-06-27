import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from codex_runner.app_server_runner import AppServerCodexRunner
from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle, RunnerSettings
from codex_runner.claude_code_runner import ClaudeCodeRunner
from codex_runner.cli_runner import CliCodexRunner, CliRunState
from codex_runner.dry_run_runner import DryRunRunner
from codex_runner.external_adapter_runner import ExternalAdapterRunner, ExternalAdapterRunState
from codex_runner.remote_adapter_runner import RemoteAdapterRunner
from codex_runner.events import parse_json_line
from manager import RunnerRegistry
from models import Agent, Project, Task
from project_settings import ResolvedRunSettings
from system_status import assess_model_advisories, detect_system_status


def _runner_context(
    *,
    workspace_path: str = "C:/demo",
    provider: str = "codex",
    model: str | None = None,
    reasoning_effort: str | None = None,
    adapter_command: str | None = None,
    adapter_args: list[str] | None = None,
) -> RunnerContext:
    project = Project(id=1, name="Demo", idea="Idea", workspace_path=workspace_path, status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=workspace_path)
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
    return RunnerContext(
        project=project,
        agent=agent,
        task=task,
        docs_path=f"{workspace_path}/mission-control",
        settings=RunnerSettings(
            provider=provider,
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model=model,
            reasoning_effort=reasoning_effort,
            adapter_command=adapter_command,
            adapter_args=adapter_args or [],
        ),
    )


def test_base_runner_manager_turn_times_out_and_stops_stuck_run() -> None:
    class StuckRunner(BaseCodexRunner):
        runner_type = "stuck"
        manager_turn_timeout_seconds = 0.02
        manager_turn_poll_interval_seconds = 0.01

        def __init__(self) -> None:
            self.stopped_run_ids: list[str] = []

        async def handshake(self, settings=None) -> bool:
            return True

        async def start_task(self, context: RunnerContext) -> RunnerHandle:
            raise NotImplementedError

        async def stop_run(self, run_id: str) -> None:
            self.stopped_run_ids.append(run_id)

        async def read_events(self, run_id: str) -> list[dict[str, object]]:
            return []

        async def get_status(self, run_id: str) -> str:
            return "working"

        async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
            return RunnerHandle(id="stuck-run", runner_type=self.runner_type, logs_path=None)

    runner = StuckRunner()
    context = _runner_context()

    async def run_test() -> None:
        try:
            await runner.run_manager_turn(context, "manager prompt")
        except TimeoutError as exc:
            assert "manager turn exceeded" in str(exc)
        else:
            raise AssertionError("Expected manager turn timeout for a non-terminating run.")

    asyncio.run(run_test())

    assert runner.stopped_run_ids == ["stuck-run"]


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
        provider_endpoint=None,
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
        provider_endpoint=None,
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


def test_runner_registry_selects_external_adapter_when_configured(monkeypatch) -> None:
    registry = RunnerRegistry()

    async def fake_handshake(settings=None) -> bool:
        return bool(settings and settings.adapter_command == "custom-adapter")

    monkeypatch.setattr(registry.runners["external_adapter"], "handshake", fake_handshake)
    resolved = ResolvedRunSettings(
        provider="custom",
        provider_label="Custom provider",
        provider_endpoint=None,
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="custom-model",
        reasoning_effort="high",
        adapter_command="custom-adapter",
        adapter_args=["--project", "demo"],
        effective_model_label="custom-model",
        effective_reasoning_label="high",
    )
    runner = asyncio.run(registry.get_runner_for_settings(resolved))
    assert runner.runner_type == "external_adapter"


def test_runner_registry_selects_openai_api_adapter_when_configured(monkeypatch) -> None:
    registry = RunnerRegistry()

    async def fake_handshake(settings=None) -> bool:
        return bool(settings and settings.provider == "openai_api" and settings.adapter_command == "python")

    monkeypatch.setattr(registry.runners["external_adapter"], "handshake", fake_handshake)
    resolved = ResolvedRunSettings(
        provider="openai_api",
        provider_label="OpenAI API",
        provider_endpoint=None,
        runner_mode="auto",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-4o-mini",
        reasoning_effort=None,
        adapter_command="python",
        adapter_args=["scripts/api_provider_adapter.py"],
        effective_model_label="gpt-4o-mini",
        effective_reasoning_label="OpenAI API default",
    )
    runner = asyncio.run(registry.get_runner_for_settings(resolved))
    assert runner.runner_type == "external_adapter"


def test_runner_registry_retries_negative_codex_cli_cache(monkeypatch) -> None:
    registry = RunnerRegistry()
    attempts = {"count": 0}

    async def fake_handshake(settings=None) -> bool:
        attempts["count"] += 1
        return attempts["count"] >= 2

    monkeypatch.setattr(registry.runners["codex_cli"], "handshake", fake_handshake)

    assert asyncio.run(registry.codex_cli_available()) is False
    assert asyncio.run(registry.codex_cli_available()) is True
    assert attempts["count"] == 2


def test_try_parse_json_payload_repairs_fenced_trailing_comma_json() -> None:
    payload, repaired = BaseCodexRunner.try_parse_json_payload(
        """```json
{"status":"done","summary":"ok",}
```"""
    )
    assert repaired is True
    assert payload == {"status": "done", "summary": "ok"}


def test_try_parse_result_envelope_unwraps_nested_result_string() -> None:
    nested = {
        "status": "completed",
        "runner_type": "external_adapter",
        "summary": "Fixed a real bug.",
        "report": {
            "agent": "Worker",
            "task_id": "42",
            "status": "done",
            "summary": "Fixed a real bug.",
            "files_changed": ["src/example.py"],
            "tests_run": ["pytest -q"],
            "blockers": [],
            "risks": [],
        },
    }

    envelope = BaseCodexRunner.try_parse_result_envelope(json.dumps({"result": json.dumps(nested)}))

    assert envelope is not None
    assert envelope["runner_type"] == "external_adapter"
    assert envelope["report"]["status"] == "done"


def test_try_parse_result_envelope_unwraps_stringified_report() -> None:
    envelope = BaseCodexRunner.try_parse_result_envelope(
        json.dumps(
            {
                "status": "completed",
                "runner_type": "codex_cli",
                "summary": "Fixed a real bug.",
                "report": json.dumps(
                    {
                        "agent": "Worker",
                        "task_id": "42",
                        "status": "done",
                        "summary": "Fixed a real bug.",
                        "files_changed": ["src/example.py"],
                        "tests_run": ["pytest -q"],
                        "blockers": [],
                        "risks": [],
                    }
                ),
            }
        )
    )

    assert envelope is not None
    assert envelope["runner_type"] == "codex_cli"
    assert envelope["report"]["files_changed"] == ["src/example.py"]


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


def test_cli_runner_start_task_builds_prompt_off_thread(monkeypatch) -> None:
    async def run_test() -> None:
        runner = CliCodexRunner()
        context = _runner_context(model="gpt-5.5", reasoning_effort="high")
        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-cli-prompt"

        async def fake_start_process(context_arg, prompt, resume):
            assert prompt == "threaded-cli-prompt"
            assert resume is False
            return RunnerHandle(id="cli-threaded", runner_type="codex_cli", logs_path="C:/logs/cli-threaded.log")

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(runner, "_start_process", fake_start_process)

        handle = await runner.start_task(context)

        assert handle.runner_type == "codex_cli"
        assert calls == ["worker_task_prompt"]

    asyncio.run(run_test())


def test_app_server_runner_start_task_builds_prompt_off_thread(monkeypatch) -> None:
    async def run_test() -> None:
        runner = AppServerCodexRunner()
        context = _runner_context(model="gpt-5.5")
        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-app-server-prompt"

        async def fake_start_turn(context_arg, prompt, resume):
            assert prompt == "threaded-app-server-prompt"
            assert resume is False
            return RunnerHandle(id="app-server-threaded", runner_type="app_server", logs_path="C:/logs/app-server-threaded.log")

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(runner, "_start_turn", fake_start_turn)

        handle = await runner.start_task(context)

        assert handle.runner_type == "app_server"
        assert calls == ["worker_task_prompt"]

    asyncio.run(run_test())


def test_claude_runner_start_task_builds_prompt_off_thread(monkeypatch) -> None:
    async def run_test() -> None:
        runner = ClaudeCodeRunner()
        context = _runner_context(provider="claude_code", model="sonnet")
        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-claude-prompt"

        async def fake_start_process(context_arg, prompt, resume):
            assert prompt == "threaded-claude-prompt"
            assert resume is False
            return RunnerHandle(id="claude-threaded", runner_type="claude_code_cli", logs_path="C:/logs/claude-threaded.log")

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(runner, "_start_process", fake_start_process)

        handle = await runner.start_task(context)

        assert handle.runner_type == "claude_code_cli"
        assert calls == ["worker_task_prompt"]

    asyncio.run(run_test())


def test_external_adapter_runner_start_task_builds_prompt_off_thread(monkeypatch) -> None:
    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        context = _runner_context(
            provider="openai_api",
            model="gpt-4o-mini",
            adapter_command=sys.executable,
            adapter_args=["adapter.py"],
        )
        calls: list[str] = []

        async def fake_to_thread(func, *args, **kwargs):
            calls.append(func.__name__)
            return "threaded-adapter-prompt"

        async def fake_start_process(context_arg, prompt):
            assert prompt == "threaded-adapter-prompt"
            return RunnerHandle(id="adapter-threaded", runner_type="external_adapter", logs_path="C:/logs/adapter-threaded.log")

        monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
        monkeypatch.setattr(runner, "_start_process", fake_start_process)

        handle = await runner.start_task(context)

        assert handle.runner_type == "external_adapter"
        assert calls == ["_build_adapter_prompt"]

    asyncio.run(run_test())


def test_external_adapter_prompt_includes_remote_execution_contract() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="openai_api",
        model="gpt-4o-mini",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.settings.remote_execution = {
        "selected_target": {
            "id": "edge-box",
            "label": "Edge Box",
            "transport": "tailscale_ssh",
            "host": "edge-box.tailnet.ts.net",
            "workspace_root": "/srv/shadow-repo",
        },
        "artifact_contract": {
            "sync_enabled": True,
            "local_artifact_paths": ["artifacts/model.onnx"],
            "blocking_reasons": [],
        },
        "connector_contract": {
            "available_families": ["source_control"],
            "blocking_reasons": [],
        },
    }

    prompt = runner._build_adapter_prompt(context)

    assert "Remote execution context:" in prompt
    assert "Edge Box" in prompt
    assert "artifacts/model.onnx" in prompt
    assert "source_control" in prompt


def test_cli_build_exec_args_include_model_and_reasoning_when_set() -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

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
    original = cli_module.codex_command_path
    cli_module.codex_command_path = lambda: "C:/tools/codex.exe"
    try:
        args = runner.build_exec_args(context, resume=False)
    finally:
        cli_module.codex_command_path = original
    assert args[:9] == [
        "C:/tools/codex.exe",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "tool_suggest",
        "-a",
        "on-request",
    ]
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert "-m" in args
    assert "gpt-5.5" in args
    assert any('model_reasoning_effort="high"' == value for value in args)


def test_cli_build_exec_args_omit_model_when_unset() -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

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
    original = cli_module.codex_command_path
    cli_module.codex_command_path = lambda: "C:/tools/codex.exe"
    try:
        args = runner.build_exec_args(context, resume=False)
    finally:
        cli_module.codex_command_path = original
    assert "-m" not in args
    assert not any("model_reasoning_effort" in value for value in args)


def test_cli_subprocess_cwd_uses_ready_agent_workspace(tmp_path) -> None:
    runner = CliCodexRunner()
    project_root = tmp_path / "project-root"
    agent_root = tmp_path / "agent-root"
    project_root.mkdir()
    agent_root.mkdir()
    (agent_root / "README.md").write_text("ready\n", encoding="utf-8")
    project = Project(id=1, name="Demo", idea="Idea", workspace_path=project_root.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=agent_root.as_posix())
    context = RunnerContext(project=project, agent=agent, task=None, docs_path=(project_root / "mission-control").as_posix())

    assert runner.subprocess_cwd(context) == agent_root.as_posix()


def test_cli_subprocess_cwd_falls_back_to_project_workspace() -> None:
    runner = CliCodexRunner()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/project-root", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=None)
    context = RunnerContext(project=project, agent=agent, task=None, docs_path="C:/demo/mission-control")

    assert runner.subprocess_cwd(context) == "C:/project-root"


def test_cli_subprocess_cwd_ignores_unprovisioned_agent_workspace(tmp_path) -> None:
    runner = CliCodexRunner()
    project_root = tmp_path / "project-root"
    agent_root = tmp_path / "agent-root"
    project_root.mkdir()
    agent_root.mkdir()
    (project_root / "README.md").write_text("project\n", encoding="utf-8")
    (agent_root / "Microsoft").mkdir()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path=project_root.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=agent_root.as_posix())
    context = RunnerContext(project=project, agent=agent, task=None, docs_path=(project_root / "mission-control").as_posix())

    assert runner.subprocess_cwd(context) == project_root.as_posix()


def test_cli_effective_sandbox_mode_preserves_read_only(monkeypatch) -> None:
    runner = CliCodexRunner()
    monkeypatch.delenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CODEX_SHELL", raising=False)
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/project-root", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/agent-root")
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(sandbox_mode="read-only", approval_policy="on-request"),
    )

    assert runner.effective_sandbox_mode(context) == "read-only"


def test_cli_effective_sandbox_mode_escalates_nested_workspace_write(monkeypatch) -> None:
    runner = CliCodexRunner()
    monkeypatch.setenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "Codex Desktop")
    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/project-root", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path="C:/agent-root")
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path="C:/demo/mission-control",
        settings=RunnerSettings(sandbox_mode="workspace-write", approval_policy="on-request"),
    )

    assert runner.effective_sandbox_mode(context) == "danger-full-access"


def test_cli_build_subprocess_env_uses_runtime_profile_and_mirrors_auth(monkeypatch, tmp_path) -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    for name in ("auth.json", ".credentials.json", "installation_id"):
        (source_codex_home / name).write_text(name, encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))
    if os.name == "nt":
        monkeypatch.setenv("MISSION_CONTROL_SOURCE_USERPROFILE", r"C:\Users\real-user")
        monkeypatch.setenv("MISSION_CONTROL_SOURCE_HOME", r"C:\Users\real-user")
        monkeypatch.setenv("USERPROFILE", str(runtime_root / "daemon-profile"))
        monkeypatch.setenv("HOME", str(runtime_root / "daemon-profile"))
        monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
        monkeypatch.setenv(
            "Path",
            r"%USERPROFILE%\AppData\Local\Microsoft\WindowsApps;%ProgramFiles%\Git\cmd",
        )
        monkeypatch.setenv("PATH", r"%USERPROFILE%\AppData\Local\Microsoft\WindowsApps;%ProgramFiles%\Git\cmd")
    else:
        monkeypatch.setenv("PATH", "from-path")
        monkeypatch.setenv("Path", "from-Path")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-123")
    monkeypatch.setenv("UNRELATED_SECRET", "do-not-copy")

    env = runner.build_subprocess_env()

    profile_root = runtime_root / "codex-profile"
    codex_home = profile_root / ".codex"
    assert env["HOME"] == str(profile_root)
    assert env["CODEX_HOME"] == str(codex_home)
    assert env["MISSION_CONTROL_CODEX_HOME"] == str(codex_home)
    assert env["MISSION_CONTROL_SOURCE_CODEX_HOME"] == str(source_codex_home)
    assert "CODEX_THREAD_ID" not in env
    assert "UNRELATED_SECRET" not in env
    if os.name == "nt":
        path_entries = env["Path"].split(os.pathsep)
        assert path_entries[2:4] == [
            r"C:\Users\real-user\AppData\Local\Microsoft\WindowsApps",
            r"C:\Program Files\Git\cmd",
        ]
        assert env["PATH"] == env["Path"]
        assert env["USERPROFILE"] == str(profile_root)
        assert env["MISSION_CONTROL_SOURCE_USERPROFILE"] == r"C:\Users\real-user"
        assert env["MISSION_CONTROL_SOURCE_HOME"] == r"C:\Users\real-user"
    else:
        assert env["PATH"] == "from-path"
    for name in ("auth.json", ".credentials.json", "installation_id"):
        assert (codex_home / name).read_text(encoding="utf-8") == name


def test_cli_build_subprocess_env_augmentes_sparse_windows_path_with_required_tool_dirs(monkeypatch, tmp_path) -> None:
    if os.name != "nt":
        pytest.skip("Windows-specific PATH hardening")
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    runtime_root = tmp_path / "runtime"
    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("WINDIR", r"C:\Windows")
    monkeypatch.setenv("Path", r"C:\custom\bin")
    monkeypatch.setenv("PATH", r"C:\custom\bin")
    monkeypatch.setattr(
        cli_module.shutil,
        "which",
        lambda command: {
            "git.exe": r"C:\Program Files\Git\cmd\git.exe",
            "python.exe": r"C:\Users\mike\AppData\Local\Programs\Python\Python310\python.exe",
            "py.exe": r"C:\Users\mike\AppData\Local\Programs\Python\Launcher\py.exe",
            "node.exe": r"C:\Program Files\nodejs\node.exe",
            "npm.cmd": r"C:\Program Files\nodejs\npm.cmd",
            "rg.exe": r"C:\Users\mike\AppData\Local\OpenAI\Codex\bin\rg.exe",
            "where.exe": r"C:\Windows\System32\where.exe",
            "powershell.exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        }.get(command),
    )
    monkeypatch.setattr(cli_module, "codex_command_path", lambda: r"C:\Users\mike\AppData\Local\OpenAI\Codex\bin\codex.exe")

    env = runner.build_subprocess_env()

    path_entries = env["Path"].split(os.pathsep)
    assert path_entries[2] == r"C:\custom\bin"
    assert r"C:\Windows\System32" in path_entries
    assert r"C:\Windows" in path_entries
    assert r"C:\Windows\System32\WindowsPowerShell\v1.0" in path_entries
    assert r"C:\Program Files\Git\cmd" in path_entries
    assert r"C:\Users\mike\AppData\Local\Programs\Python\Python310" in path_entries
    assert r"C:\Users\mike\AppData\Local\Programs\Python\Launcher" in path_entries
    assert r"C:\Program Files\nodejs" in path_entries
    assert r"C:\Users\mike\AppData\Local\OpenAI\Codex\bin" in path_entries
    assert env["PATH"] == env["Path"]


def test_cli_build_subprocess_env_creates_windows_tool_shims(monkeypatch, tmp_path) -> None:
    if os.name != "nt":
        pytest.skip("Windows-specific PATH hardening")
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    runtime_root = tmp_path / "runtime"
    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_USERPROFILE", r"C:\Users\mike")
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_HOME", r"C:\Users\mike")
    monkeypatch.setenv("USERPROFILE", str(runtime_root / "daemon-profile"))
    monkeypatch.setenv("HOME", str(runtime_root / "daemon-profile"))
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    monkeypatch.setenv("WINDIR", r"C:\Windows")
    monkeypatch.setenv("Path", r"C:\custom\bin")
    monkeypatch.setenv("PATH", r"C:\custom\bin")
    monkeypatch.setattr(
        cli_module.shutil,
        "which",
        lambda command: {
            "git.exe": r"C:\Program Files\Git\cmd\git.exe",
            "python.exe": r"C:\Users\mike\AppData\Local\Programs\Python\Python310\python.exe",
            "py.exe": r"C:\Users\mike\AppData\Local\Programs\Python\Launcher\py.exe",
            "node.exe": r"C:\Program Files\nodejs\node.exe",
            "npm.cmd": r"C:\Program Files\nodejs\npm.cmd",
            "rg.exe": r"C:\Users\mike\AppData\Local\OpenAI\Codex\bin\rg.exe",
            "where.exe": r"C:\Windows\System32\where.exe",
            "powershell.exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        }.get(command),
    )

    env = runner.build_subprocess_env()

    profile_root = runtime_root / "codex-profile"
    shim_dir = profile_root / "tool-bin"
    windowsapps_dir = profile_root / "AppData" / "Local" / "Microsoft" / "WindowsApps"
    path_entries = env["Path"].split(os.pathsep)
    assert path_entries[0] == str(shim_dir)
    assert path_entries[1] == str(windowsapps_dir)
    assert (shim_dir / "git.cmd").read_text(encoding="utf-8").endswith('"C:\\Program Files\\Git\\cmd\\git.exe" %*\n')
    assert (shim_dir / "python.cmd").read_text(encoding="utf-8").endswith('"C:\\Users\\mike\\AppData\\Local\\Programs\\Python\\Python310\\python.exe" %*\n')
    assert (shim_dir / "npm.cmd").read_text(encoding="utf-8").endswith('call "C:\\Program Files\\nodejs\\npm.cmd" %*\n')
    assert (windowsapps_dir / "rg.cmd").exists()


def test_cli_build_subprocess_env_creates_windows_tool_shims_from_explicit_fallback_paths(monkeypatch, tmp_path) -> None:
    if os.name != "nt":
        pytest.skip("Windows-specific PATH hardening")
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    runtime_root = tmp_path / "runtime"
    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    local_app_data = tmp_path / "LocalAppData"
    program_files = tmp_path / "ProgramFiles"
    system_root = tmp_path / "Windows"

    python_path = local_app_data / "Programs" / "Python" / "Python310" / "python.exe"
    py_launcher_path = local_app_data / "Programs" / "Python" / "Launcher" / "py.exe"
    codex_path = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
    rg_path = local_app_data / "OpenAI" / "Codex" / "bin" / "ada252862d154cdd" / "rg.exe"
    git_path = program_files / "Git" / "cmd" / "git.exe"
    node_path = program_files / "nodejs" / "node.exe"
    npm_path = program_files / "nodejs" / "npm.cmd"
    where_path = system_root / "System32" / "where.exe"
    powershell_path = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

    for file_path in [
        python_path,
        py_launcher_path,
        codex_path,
        rg_path,
        git_path,
        node_path,
        npm_path,
        where_path,
        powershell_path,
    ]:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("shim target\n", encoding="utf-8")

    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_USERPROFILE", r"C:\Users\mike")
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_HOME", r"C:\Users\mike")
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.setenv("USERPROFILE", str(runtime_root / "daemon-profile"))
    monkeypatch.setenv("HOME", str(runtime_root / "daemon-profile"))
    monkeypatch.setenv("SystemRoot", str(system_root))
    monkeypatch.setenv("WINDIR", str(system_root))
    monkeypatch.setenv("Path", r"C:\custom\bin")
    monkeypatch.setenv("PATH", r"C:\custom\bin")
    monkeypatch.setattr(cli_module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(cli_module, "codex_command_path", lambda: str(codex_path))

    env = runner.build_subprocess_env()

    profile_root = runtime_root / "codex-profile"
    shim_dir = profile_root / "tool-bin"
    windowsapps_dir = profile_root / "AppData" / "Local" / "Microsoft" / "WindowsApps"
    path_entries = env["Path"].split(os.pathsep)

    assert path_entries[0] == str(shim_dir)
    assert path_entries[1] == str(windowsapps_dir)
    assert (shim_dir / "git.cmd").read_text(encoding="utf-8").endswith(f'"{git_path}" %*\n')
    assert (shim_dir / "python.cmd").read_text(encoding="utf-8").endswith(f'"{python_path}" %*\n')
    assert (shim_dir / "py.cmd").read_text(encoding="utf-8").endswith(f'"{py_launcher_path}" %*\n')
    assert (shim_dir / "node.cmd").read_text(encoding="utf-8").endswith(f'"{node_path}" %*\n')
    assert (shim_dir / "npm.cmd").read_text(encoding="utf-8").endswith(f'call "{npm_path}" %*\n')
    assert (windowsapps_dir / "rg.cmd").read_text(encoding="utf-8").endswith(f'"{rg_path}" %*\n')


def test_cli_build_subprocess_env_strips_parent_codex_desktop_session_vars(monkeypatch, tmp_path) -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))
    monkeypatch.setenv("CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "Codex Desktop")
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-123")
    monkeypatch.setenv("CODEX_SHELL", "1")

    env = runner.build_subprocess_env()

    assert "CODEX_INTERNAL_ORIGINATOR_OVERRIDE" not in env
    assert "CODEX_THREAD_ID" not in env
    assert "CODEX_SHELL" not in env


def test_cli_build_context_subprocess_env_uses_agent_scoped_runtime_profile(monkeypatch, tmp_path) -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    source_codex_home = tmp_path / "source-codex"
    source_codex_home.mkdir()
    for name in ("auth.json", ".credentials.json", "installation_id"):
        (source_codex_home / name).write_text(name, encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(cli_module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setenv("MISSION_CONTROL_SOURCE_CODEX_HOME", str(source_codex_home))

    context = _runner_context(workspace_path="C:/demo-a")
    other_context = _runner_context(workspace_path="C:/demo-b")
    other_context.agent.id = 99
    other_context.agent.name = "Second Worker"

    env = runner.build_context_subprocess_env(context)
    other_env = runner.build_context_subprocess_env(other_context)

    shared_profile_root = runtime_root / "codex-profile"
    assert env["HOME"].startswith(str(shared_profile_root))
    assert other_env["HOME"].startswith(str(shared_profile_root))
    assert env["HOME"] != str(shared_profile_root)
    assert env["HOME"] != other_env["HOME"]
    assert env["CODEX_HOME"] != other_env["CODEX_HOME"]
    for target in (Path(env["CODEX_HOME"]), Path(other_env["CODEX_HOME"])):
        for name in ("auth.json", ".credentials.json", "installation_id"):
            assert (target / name).read_text(encoding="utf-8") == name


def test_cli_filter_stderr_lines_suppresses_known_startup_noise_only_for_success() -> None:
    lines = [
        "Reading additional input from stdin...",
        "2026-06-09T05:06:04Z ERROR codex_models_manager::manager: failed to refresh available models: stream disconnected",
        "2026-06-09T05:06:07Z WARN codex_analytics::client: failed to send events request: nope",
        "actual stderr that matters",
    ]

    assert CliCodexRunner._filter_stderr_lines(lines, status="done") == ["actual stderr that matters"]
    assert CliCodexRunner._filter_stderr_lines(lines, status="error") == lines


def test_cli_read_stdout_stream_handles_very_long_lines_without_readline_limit() -> None:
    class FakeStream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    async def run_test() -> None:
        runner = CliCodexRunner()
        state = CliRunState()
        stdout_lines: list[str] = []
        log_lines: list[str] = []
        event_lines: list[str] = []
        oversized = "x" * 70000
        payload = f"{oversized}\n" + json.dumps({"type": "turn.completed"}) + "\n"
        stream = FakeStream([payload[:20000].encode("utf-8"), payload[20000:].encode("utf-8")])

        await runner._read_stdout_stream(state, stream, stdout_lines, log_lines, event_lines)

        assert stdout_lines[0] == oversized
        assert stdout_lines[1] == '{"type": "turn.completed"}'
        assert state.status == "working"
        assert state.events[0]["type"] == "raw.output"
        assert state.events[1]["type"] == "turn.completed"

    asyncio.run(run_test())


def test_cli_consume_process_synthesizes_failure_envelope_for_provider_errors(tmp_path) -> None:
    class FakeStream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self) -> None:
            payload = "\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-123"}',
                    '{"type":"turn.started"}',
                    '{"type":"error","message":"You\\u2019ve hit your usage limit. Try again later."}',
                    '{"type":"turn.failed","error":{"message":"You\\u2019ve hit your usage limit. Try again later."}}',
                ]
            ) + "\n"
            self.stdout = FakeStream([payload.encode("utf-8")])
            self.stderr = FakeStream([])
            self.returncode = 1
            self._transport = None

        async def wait(self) -> int:
            return self.returncode

    async def run_test() -> None:
        runner = CliCodexRunner()
        run_id = "cli-failure-envelope"
        state = CliRunState(
            process=FakeProcess(),
            logs_path=str(tmp_path / "combined.log"),
            stdout_path=str(tmp_path / "stdout.log"),
            stderr_path=str(tmp_path / "stderr.log"),
            event_log_path=str(tmp_path / "events.jsonl"),
            effective_settings={"provider": "codex", "model": "gpt-5.5", "reasoning_effort": "high"},
            agent_name="Worker",
            task_id="42",
        )
        runner.runs[run_id] = state

        await runner._consume_process(run_id)

        assert state.status == "error"
        envelope = BaseCodexRunner.try_parse_result_envelope(state.final_text)
        assert envelope is not None
        assert envelope["failure_classification"] == "transient"
        assert envelope["status"] == "blocked"
        assert envelope["report"]["status"] == "blocked"
        assert envelope["report"]["agent"] == "Worker"
        assert envelope["report"]["task_id"] == "42"
        assert any(event.get("type") == "item.completed" for event in state.events)

    asyncio.run(run_test())


def test_cli_consume_process_marks_successful_structured_runs_done(tmp_path) -> None:
    class FakeStream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self) -> None:
            envelope = {
                "status": "completed",
                "runner_type": "codex",
                "summary": "Fixed a real bug.",
                "report": {
                    "agent": "Worker",
                    "task_id": "42",
                    "status": "done",
                    "summary": "Fixed a real bug.",
                    "files_changed": ["src/example.py"],
                    "tests_run": ["pytest -q"],
                    "blockers": [],
                    "risks": [],
                },
            }
            payload = "\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-123"}',
                    '{"type":"turn.started"}',
                    '{"type":"turn.completed"}',
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(envelope)}}),
                ]
            ) + "\n"
            self.stdout = FakeStream([payload.encode("utf-8")])
            self.stderr = FakeStream([])
            self.returncode = 0
            self._transport = None

        async def wait(self) -> int:
            return self.returncode

    async def run_test() -> None:
        runner = CliCodexRunner()
        run_id = "cli-success-envelope"
        state = CliRunState(
            process=FakeProcess(),
            logs_path=str(tmp_path / "combined.log"),
            stdout_path=str(tmp_path / "stdout.log"),
            stderr_path=str(tmp_path / "stderr.log"),
            event_log_path=str(tmp_path / "events.jsonl"),
            effective_settings={"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "high"},
            agent_name="Worker",
            task_id="42",
        )
        runner.runs[run_id] = state

        await runner._consume_process(run_id)

        assert state.exit_code == 0
        assert state.status == "done"
        assert state.final_text is not None
        envelope = BaseCodexRunner.try_parse_result_envelope(state.final_text)
        assert envelope is not None
        assert envelope["report"]["status"] == "done"

    asyncio.run(run_test())


def test_cli_consume_process_marks_successful_manager_decision_runs_done_without_synthetic_failure(tmp_path) -> None:
    class FakeStream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self) -> None:
            decision = {
                "decision_type": "wait",
                "summary_markdown": "All safe worker lanes are already occupied.",
                "task_id": 183,
                "assign_to_agent_id": 32,
                "follow_up_title": "Wait For Active Worker Completion",
                "follow_up_goal": "Preserve safe throughput until one active worker completes.",
                "escalation_message": "",
            }
            payload = "\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-123"}',
                    '{"type":"turn.started"}',
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(decision)}}),
                    '{"type":"turn.completed"}',
                ]
            ) + "\n"
            self.stdout = FakeStream([payload.encode("utf-8")])
            self.stderr = FakeStream([])
            self.returncode = 0
            self._transport = None

        async def wait(self) -> int:
            return self.returncode

    async def run_test() -> None:
        runner = CliCodexRunner()
        run_id = "cli-manager-decision"
        state = CliRunState(
            process=FakeProcess(),
            logs_path=str(tmp_path / "combined.log"),
            stdout_path=str(tmp_path / "stdout.log"),
            stderr_path=str(tmp_path / "stderr.log"),
            event_log_path=str(tmp_path / "events.jsonl"),
            effective_settings={"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "high"},
            agent_name="Manager AI",
        )
        runner.runs[run_id] = state

        await runner._consume_process(run_id)

        assert state.exit_code == 0
        assert state.status == "done"
        payload = BaseCodexRunner.try_parse_structured_message_payload(state.final_text)
        assert payload is not None
        assert payload["decision_type"] == "wait"
        agent_messages = [
            event
            for event in state.events
            if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message"
        ]
        assert len(agent_messages) == 1

    asyncio.run(run_test())


def test_cli_consume_process_marks_successful_manager_plan_runs_done_without_synthetic_failure(tmp_path) -> None:
    class FakeStream:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _size: int) -> bytes:
            if not self._chunks:
                return b""
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self) -> None:
            plan = {
                "summary_markdown": "Keep worker context compact and current.",
                "milestones": ["Reset benchmark state", "Stabilize worker context"],
                "tasks": [
                    {
                        "title": "Compact Benchmark Worker Context Repair",
                        "goal": "Keep worker context current and minimal.",
                        "scope": "Tighten compact worker-context packing.",
                        "agent_role": "feature",
                        "milestone": "Stabilize worker context",
                        "priority": 9,
                        "allowed_paths": ["apps/server/**"],
                        "forbidden_paths": ["apps/dashboard/**"],
                        "validation_steps": ["Inspect emitted worker context."],
                        "success_criteria": ["Workers receive current context only."],
                        "estimated_complexity": "medium",
                        "dependencies": [],
                        "status": "backlog",
                    }
                ],
            }
            payload = "\n".join(
                [
                    '{"type":"thread.started","thread_id":"thread-456"}',
                    '{"type":"turn.started"}',
                    json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(plan)}}),
                    '{"type":"turn.completed"}',
                ]
            ) + "\n"
            self.stdout = FakeStream([payload.encode("utf-8")])
            self.stderr = FakeStream([])
            self.returncode = 0
            self._transport = None

        async def wait(self) -> int:
            return self.returncode

    async def run_test() -> None:
        runner = CliCodexRunner()
        run_id = "cli-manager-plan"
        state = CliRunState(
            process=FakeProcess(),
            logs_path=str(tmp_path / "combined.log"),
            stdout_path=str(tmp_path / "stdout.log"),
            stderr_path=str(tmp_path / "stderr.log"),
            event_log_path=str(tmp_path / "events.jsonl"),
            effective_settings={"provider": "codex", "model": "gpt-5.4", "reasoning_effort": "high"},
            agent_name="Manager AI",
        )
        runner.runs[run_id] = state

        await runner._consume_process(run_id)

        assert state.exit_code == 0
        assert state.status == "done"
        payload = BaseCodexRunner.try_parse_structured_message_payload(state.final_text)
        assert payload is not None
        assert payload["tasks"][0]["title"] == "Compact Benchmark Worker Context Repair"
        agent_messages = [
            event
            for event in state.events
            if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message"
        ]
        assert len(agent_messages) == 1

    asyncio.run(run_test())


def test_remote_adapter_runner_persists_runtime_manifest_and_remote_execution_settings(monkeypatch, tmp_path) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.buffer = bytearray()
            self.closed = False

        def write(self, data: bytes) -> None:
            self.buffer.extend(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None
            self.returncode = 0
            self._transport = None

        async def communicate(self) -> tuple[bytes, bytes]:
            envelope = {
                "status": "completed",
                "runner_type": "remote_adapter",
                "lane": "test_execution",
                "summary": "Remote browser validation completed.",
                "report": {
                    "agent": "Worker",
                    "task_id": "3",
                    "status": "done",
                    "summary": "Remote browser validation completed.",
                    "files_changed": ["artifacts/screenshots/boot.png"],
                    "tests_run": ["playwright test"],
                    "blockers": [],
                    "risks": [],
                    "recommended_next_task": "",
                },
                "commands_attempted": ["playwright test"],
                "evidence": [],
                "diagnostics": ["artifacts/logs/run.log"],
                "approvals_requested": [],
                "recovery_plan": [],
                "edits": [],
                "failure_classification": None,
                "needs_approval": False,
                "metadata_json": {},
            }
            return json.dumps(envelope).encode("utf-8"), b""

    async def fake_exec(*args, **kwargs):
        return FakeProcess()

    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)
    monkeypatch.setattr(
        "codex_runner.remote_adapter_runner.build_remote_launch_plan",
        lambda **kwargs: {
            "preflight_ready": True,
            "target_id": "browser-box",
            "target_label": "Browser Box",
            "transport": "tailscale_ssh",
            "host": "browser-box.tailnet.ts.net",
            "remote_workspace_root": "/srv/browser-work",
            "allowed_relative_paths": ["artifacts", "tests"],
            "allowed_remote_paths": ["/srv/browser-work/artifacts", "/srv/browser-work/tests"],
            "allowed_repo_roots": ["/srv/browser-work"],
            "remote_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"],
            "connector_families": ["source_control"],
            "session_recording_required": True,
            "session_recording_enabled": True,
            "session_recording_artifact_paths": [
                "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
            "remote_session_recording_artifact_paths": [
                "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
            ],
            "command_preview": "tailscale ssh browser-box tailnet command",
            "exec_args": ["python", "adapter.py"],
            "blocking_reasons": [],
        },
    )

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote validation",
        goal="Collect brokered browser evidence.",
        scope="Do not edit code.",
        agent_role="Validation",
        milestone="Milestone 2",
        allowed_paths_json=["artifacts", "tests"],
        forbidden_paths_json=[],
        validation_steps_json=["playwright test"],
        success_criteria_json=["Evidence captured."],
        estimated_complexity="small",
        dependencies_json=[],
        status="assigned",
        priority=10,
    )
    context = RunnerContext(
        project=project,
        agent=agent,
        task=task,
        docs_path=(tmp_path / "mission-control").as_posix(),
        settings=RunnerSettings(
            provider="openai_api",
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model="gpt-4.1-mini",
            reasoning_effort="medium",
            remote_execution={
                "policy": {"enabled": True, "required_runner_family": "external_adapter"},
                "selected_target": {
                    "id": "browser-box",
                    "transport": "tailscale_ssh",
                    "host": "browser-box.tailnet.ts.net",
                    "adapter_command": "python",
                },
                "artifact_contract": {"remote_workspace_artifact_paths": ["/srv/browser-work/artifacts/screenshots/boot.png"]},
                "connector_contract": {"available_families": ["source_control"]},
                "broker_contract": {"require_session_recording": True, "session_recording_enabled": True},
                "result_contract": {
                    "expected_evidence_categories": ["logs", "screenshots", "traces"],
                    "normalized_summary_artifact": "artifacts/remote-execution-governance/normalized-execution-summary.json",
                    "session_recording_artifact_paths": [
                        "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                    "remote_session_recording_artifact_paths": [
                        "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
                    ],
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        handle = await runner._start_process(context, "Run the remote validation.")
        state = runner.runs[handle.id]
        assert state.reader_task is not None
        await state.reader_task

        manifest_path = tmp_path / "artifacts" / "remote-execution-governance" / "runtime" / f"{handle.id}-launch-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert state.effective_settings["remote_execution"]["selected_target"]["id"] == "browser-box"
        assert state.effective_settings["remote_artifact_paths"] == ["/srv/browser-work/artifacts/screenshots/boot.png"]
        assert state.effective_settings["session_recording_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert manifest["target_id"] == "browser-box"
        assert manifest["expected_evidence_categories"] == ["logs", "screenshots", "traces"]
        assert manifest["normalized_summary_artifact"] == "artifacts/remote-execution-governance/normalized-execution-summary.json"
        assert manifest["session_recording_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert manifest["remote_session_recording_artifact_paths"] == [
            "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert manifest["status"] == "done"
        assert manifest["report"]["summary"] == "Remote browser validation completed."
        assert manifest["result_envelope"]["status"] == "completed"

    asyncio.run(run_test())


def test_remote_adapter_runner_blocks_when_launch_package_approval_is_pending(monkeypatch, tmp_path) -> None:
    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote mutation",
        goal="Run a brokered remote task that mutates state.",
        scope="Requires explicit approval.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Task launched only after approval."],
        estimated_complexity="small",
        dependencies_json=[],
        status="assigned",
        priority=10,
    )
    context = RunnerContext(
        project=project,
        agent=agent,
        task=task,
        docs_path=(tmp_path / "mission-control").as_posix(),
        settings=RunnerSettings(
            provider="openai_api",
            sandbox_mode="workspace-write",
            approval_policy="on-request",
            model="gpt-4.1-mini",
            reasoning_effort="medium",
            remote_execution={
                "policy": {"enabled": True, "required_runner_family": "external_adapter"},
                "selected_target": {
                    "id": "gpu-box",
                    "transport": "tailscale_ssh",
                    "host": "gpu-box.tailnet.ts.net",
                    "adapter_command": "python",
                },
                "launch_package": {
                    "approval_required": True,
                    "approval_id": 77,
                    "approval_status": "pending",
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        with pytest.raises(RuntimeError, match="requires approval"):
            await runner._start_process(context, "Run the remote mutation.")

    asyncio.run(run_test())


def test_cli_build_exec_args_resume_uses_resume_subcommand_without_shell_flags() -> None:
    runner = CliCodexRunner()
    from codex_runner import cli_runner as cli_module

    project = Project(id=1, name="Demo", idea="Idea", workspace_path="C:/demo", status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(
        id=2,
        project_id=1,
        name="Manager",
        role="Project orchestration",
        kind="manager",
        status="idle",
        workspace_path="C:/demo",
        session_ref="session-123",
    )
    context = RunnerContext(
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
    original = cli_module.codex_command_path
    cli_module.codex_command_path = lambda: "C:/tools/codex.exe"
    try:
        args = runner.build_exec_args(context, resume=True)
    finally:
        cli_module.codex_command_path = original

    assert args[:13] == [
        "C:/tools/codex.exe",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "tool_suggest",
        "-a",
        "on-request",
        "--sandbox",
        "danger-full-access",
        "exec",
        "resume",
    ]
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert "--json" in args
    assert "--skip-git-repo-check" in args
    assert "-m" in args and "gpt-5.5" in args
    assert "session-123" in args
    assert "-C" not in args


def test_cli_start_process_launches_in_target_workspace(monkeypatch, tmp_path) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.buffer = bytearray()
            self.closed = False

        def write(self, data: bytes) -> None:
            self.buffer.extend(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None

    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProcess()

    runner = CliCodexRunner()
    monkeypatch.setattr(runner, "handshake", lambda: asyncio.sleep(0, result=True))
    monkeypatch.setattr(runner, "build_exec_args", lambda context, resume: ["C:/tools/codex.exe", "exec"])
    monkeypatch.setattr(runner, "build_subprocess_env", lambda: {"CODEX_HOME": str(tmp_path / ".codex")})
    monkeypatch.setattr("codex_runner.cli_runner.workspace_git_env", lambda workspace_path, base_env=None: {**(base_env or {}), "GIT_CONFIG_GLOBAL": str(tmp_path / "workspace.gitconfig")})
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    project_root = tmp_path / "project-root"
    agent_root = tmp_path / "agent-root"
    project_root.mkdir()
    agent_root.mkdir()
    (agent_root / "README.md").write_text("ready\n", encoding="utf-8")
    project = Project(id=1, name="Demo", idea="Idea", workspace_path=project_root.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Manager", role="Project orchestration", kind="manager", status="idle", workspace_path=agent_root.as_posix())
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path=(project_root / "mission-control").as_posix(),
        settings=RunnerSettings(sandbox_mode="workspace-write", approval_policy="on-request"),
    )

    async def run_test() -> None:
        handle = await runner.resume_or_continue(context, "manager prompt")
        assert handle.runner_type == "codex_cli"
        assert captured["kwargs"]["cwd"] == agent_root.as_posix()
        assert captured["kwargs"]["env"]["GIT_CONFIG_GLOBAL"] == str(tmp_path / "workspace.gitconfig")

    asyncio.run(run_test())


def test_cli_start_process_falls_back_from_unprovisioned_agent_workspace(monkeypatch, tmp_path) -> None:
    class FakeStdin:
        def __init__(self) -> None:
            self.buffer = bytearray()
            self.closed = False

        def write(self, data: bytes) -> None:
            self.buffer.extend(data)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None

    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["kwargs"] = kwargs
        return FakeProcess()

    runner = CliCodexRunner()
    monkeypatch.setattr(runner, "handshake", lambda: asyncio.sleep(0, result=True))
    monkeypatch.setattr(runner, "build_exec_args", lambda context, resume: ["C:/tools/codex.exe", "exec"])
    monkeypatch.setattr(runner, "build_subprocess_env", lambda: {"CODEX_HOME": str(tmp_path / ".codex")})
    monkeypatch.setattr(
        "codex_runner.cli_runner.workspace_git_env",
        lambda workspace_path, base_env=None: {
            **(base_env or {}),
            "GIT_CONFIG_GLOBAL": str(tmp_path / "workspace.gitconfig"),
            "WORKSPACE_SEEN": workspace_path,
        },
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    project_root = tmp_path / "project-root"
    agent_root = tmp_path / "agent-root"
    project_root.mkdir()
    agent_root.mkdir()
    (project_root / "README.md").write_text("project\n", encoding="utf-8")
    (agent_root / "Microsoft").mkdir()
    project = Project(id=1, name="Demo", idea="Idea", workspace_path=project_root.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Manager", role="Project orchestration", kind="manager", status="idle", workspace_path=agent_root.as_posix())
    context = RunnerContext(
        project=project,
        agent=agent,
        task=None,
        docs_path=(project_root / "mission-control").as_posix(),
        settings=RunnerSettings(sandbox_mode="workspace-write", approval_policy="on-request"),
    )

    async def run_test() -> None:
        handle = await runner.resume_or_continue(context, "manager prompt")
        assert handle.runner_type == "codex_cli"
        assert captured["kwargs"]["cwd"] == project_root.as_posix()
        assert captured["kwargs"]["env"]["WORKSPACE_SEEN"] == project_root.as_posix()

    asyncio.run(run_test())


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
    from codex_runner import claude_code_runner as claude_module

    original = claude_module.claude_command_path
    claude_module.claude_command_path = lambda: "C:/tools/claude.cmd"
    try:
        args = runner.build_exec_args(context, resume=False)
    finally:
        claude_module.claude_command_path = original
    assert "--model" in args
    assert "sonnet" in args
    assert "--output-format" in args
    assert args[0] == "C:/tools/claude.cmd"


def test_claude_runner_handshake_uses_resolved_claude_path(monkeypatch) -> None:
    runner = ClaudeCodeRunner()

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (b"claude 1.2.3", b"")

    captured: list[str] = []

    async def fake_exec(*args, **kwargs):
        captured.extend(args)
        return FakeProcess()

    monkeypatch.setattr("codex_runner.claude_code_runner.claude_command_path", lambda: "/opt/homebrew/bin/claude")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    assert asyncio.run(runner.handshake()) is True
    assert captured[0] == "/opt/homebrew/bin/claude"


def test_launcher_scripts_exist() -> None:
    root = Path(__file__).resolve().parents[3]
    scripts = root / "scripts"
    assert (scripts / "start-mission-control.ps1").exists()
    assert (scripts / "start-mission-control.bat").exists()
    assert (scripts / "start-mission-control.sh").exists()
    assert (scripts / "stop-mission-control.sh").exists()
    assert (scripts / "create-desktop-shortcut.ps1").exists()
    assert (scripts / "stop-mission-control.ps1").exists()
    assert (scripts / "mission-control-headless-health.sh").exists()
    assert (scripts / "mission-control-support-bundle.py").exists()
    assert (scripts / "mission-control-support-bundle.ps1").exists()
    assert (scripts / "mission-control-support-bundle.sh").exists()
    assert (scripts / "package-desktop.ps1").exists()
    assert (scripts / "package-desktop.sh").exists()
    assert (scripts / "package-desktop.py").exists()
    assert (root / "apps" / "desktop" / "src" / "mission_control_desktop" / "app.py").exists()
    assert (root / ".github" / "workflows" / "package-desktop.yml").exists()
    assert (root / "apps" / "desktop" / "assets" / "mission-control-logo.png").exists()
    assert (root / "apps" / "dashboard" / "public" / "mission-control-mark.png").exists()
    config_text = (scripts / "mission-control.config.json").read_text(encoding="utf-8")
    assert '"backendPort": 8010' in config_text
    assert '"frontendPort": 5173' in config_text


def test_cli_runner_build_exec_args_use_resolved_codex_path(monkeypatch) -> None:
    runner = CliCodexRunner()
    monkeypatch.setattr("codex_runner.cli_runner.codex_command_path", lambda: "C:/tools/codex.exe")
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
    assert args[0] == "C:/tools/codex.exe"


def test_system_status_includes_provider_matrix() -> None:
    status = detect_system_status(selected_provider="claude_code")
    assert status["selected_provider"] == "claude_code"
    assert any(provider["provider"] == "codex" for provider in status["provider_statuses"])
    assert any(provider["provider"] == "claude_code" for provider in status["provider_statuses"])


def test_external_adapter_runner_handshake_uses_path_lookup_without_direct_path_probe(monkeypatch) -> None:
    runner = ExternalAdapterRunner()
    monkeypatch.setattr(
        "codex_runner.external_adapter_runner.Path",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Path should not be used during adapter handshake")),
    )
    monkeypatch.setattr("codex_runner.external_adapter_runner.shutil.which", lambda command: "/safe/bin/custom-adapter" if command == "custom-adapter" else None)

    available = asyncio.run(
        runner.handshake(
            RunnerSettings(
                provider="custom",
                sandbox_mode="workspace-write",
                approval_policy="on-request",
                adapter_command="custom-adapter",
                adapter_args=["--project", "demo"],
            )
        )
    )

    assert available is True


def test_assess_model_advisories_flags_weak_ollama_model() -> None:
    advisories = assess_model_advisories(
        provider="ollama",
        manager_model="qwen2.5:7b",
        worker_model="qwen2.5:7b",
        available_models=["qwen2.5:7b", "gpt-oss:20b", "gemma3:12b"],
    )
    assert advisories
    assert any(item["severity"] == "warning" for item in advisories)
    assert any("weaker local model" in item["summary"] for item in advisories)


def test_external_adapter_runner_applies_allowed_file_edits(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_apply.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the requested code fix.',",
                "    'files_changed': [],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/math_utils.py', 'content': 'def add(a, b):\\n    return a + b\\n'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix tests", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal="Correct the broken behavior.",
            scope="Update the src implementation.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run tests"],
            success_criteria_json=["Behavior is corrected"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        context = RunnerContext(
            project=project,
            agent=agent,
            task=task,
            docs_path=(workspace / "mission-control").as_posix(),
            settings=RunnerSettings(
                provider="ollama",
                sandbox_mode="workspace-write",
                approval_policy="on-request",
                model="qwen2.5:7b",
                adapter_command=sys.executable,
                adapter_args=[adapter_script.as_posix()],
            ),
        )
        handle = await runner.start_task(context)
        for _ in range(20):
            await asyncio.sleep(0.2)
            if await runner.get_status(handle.id) == "done":
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == ["src/math_utils.py"]
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

    asyncio.run(run_test())


def test_external_adapter_runner_rejects_out_of_scope_edits(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_reject.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Tried to modify an out-of-scope file.',",
                "    'files_changed': [],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Review the rejected edit.'",
                "  },",
                "  'edits': [",
                "    {'path': '../outside.py', 'content': 'print(1)\\n'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix tests", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal="Correct the broken behavior.",
            scope="Update the src implementation.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run tests"],
            success_criteria_json=["Behavior is corrected"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        context = RunnerContext(
            project=project,
            agent=agent,
            task=task,
            docs_path=(workspace / "mission-control").as_posix(),
            settings=RunnerSettings(
                provider="ollama",
                sandbox_mode="workspace-write",
                approval_policy="on-request",
                model="qwen2.5:7b",
                adapter_command=sys.executable,
                adapter_args=[adapter_script.as_posix()],
            ),
        )
        handle = await runner.start_task(context)
        for _ in range(20):
            await asyncio.sleep(0.2)
            if await runner.get_status(handle.id) in {"done", "needs_review"}:
                break
        assert await runner.get_status(handle.id) == "needs_review"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["status"] == "needs_review"
        assert any("Rejected edit outside" in risk for risk in report["risks"])
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"

    asyncio.run(run_test())


def test_external_adapter_runner_rejects_sibling_prefix_workspace_escape(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    sibling = tmp_path / "workspace-evil"
    workspace.mkdir()
    sibling.mkdir()
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["."],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [{"path": "../workspace-evil/pwned.py", "content": "print('nope')\n"}],
    )

    assert applied == []
    assert any("outside workspace root" in issue for issue in issues)
    assert not (sibling / "pwned.py").exists()


def test_external_adapter_runner_rejects_no_op_edits(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_noop.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Fixed the implementation.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/math_utils.py', 'content': 'def add(a, b):\\n    return a - b\\n'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix tests", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal="Correct the broken behavior.",
            scope="Update the src implementation.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Run tests"],
            success_criteria_json=["Behavior is corrected"],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=20,
        )
        context = RunnerContext(
            project=project,
            agent=agent,
            task=task,
            docs_path=(workspace / "mission-control").as_posix(),
            settings=RunnerSettings(
                provider="ollama",
                sandbox_mode="workspace-write",
                approval_policy="on-request",
                model="qwen2.5:7b",
                adapter_command=sys.executable,
                adapter_args=[adapter_script.as_posix()],
            ),
        )
        handle = await runner.start_task(context)
        for _ in range(20):
            await asyncio.sleep(0.2)
            if await runner.get_status(handle.id) in {"done", "needs_review"}:
                break
        assert await runner.get_status(handle.id) == "needs_review"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert any("Rejected no-op edit" in risk for risk in report["risks"])
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"

    asyncio.run(run_test())
