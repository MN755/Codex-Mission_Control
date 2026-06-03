import asyncio
import sys
from pathlib import Path

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerSettings
from codex_runner.claude_code_runner import ClaudeCodeRunner
from codex_runner.cli_runner import CliCodexRunner
from codex_runner.dry_run_runner import DryRunRunner
from codex_runner.external_adapter_runner import ExternalAdapterRunner, ExternalAdapterRunState
from codex_runner.events import parse_json_line
from manager import RunnerRegistry
from models import Agent, Project, Task
from project_settings import ResolvedRunSettings
from system_status import assess_model_advisories, detect_system_status


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

    assert args[:3] == ["C:/tools/codex.exe", "exec", "resume"]
    assert "--json" in args
    assert "--skip-git-repo-check" in args
    assert "-m" in args and "gpt-5.5" in args
    assert "session-123" in args
    assert "--sandbox" not in args
    assert "-a" not in args
    assert "-C" not in args


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
