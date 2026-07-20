import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_runner.app_server_runner import AppServerCodexRunner
from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle, RunnerSettings
from codex_runner.claude_code_runner import ClaudeCodeRunner
from codex_runner.cli_runner import CliCodexRunner, CliRunState
from codex_runner.dry_run_runner import DryRunRunner
from codex_runner.external_adapter_runner import ExternalAdapterRunner, ExternalAdapterRunState
from codex_runner.remote_adapter_runner import RemoteAdapterRunner
from codex_runner.events import parse_json_line
from benchmark_harness import restore_workspace_files_from_snapshot, write_benchmark_protected_paths_manifest
from manager import RunnerRegistry
from models import Agent, Project, Task
from project_settings import ResolvedRunSettings
from system_status import assess_model_advisories, detect_system_status


def test_external_adapter_identifier_extraction_stays_fast_on_adversarial_camel_case() -> None:
    adversarial = "Aa" + ("A0" * 4_000) + "_ SAFE_CONST valid_name FooBar"

    started_at = time.perf_counter()
    terms = ExternalAdapterRunner._extract_identifier_terms(adversarial)
    elapsed_seconds = time.perf_counter() - started_at

    assert terms == ["SAFE_CONST", "valid_name", "FooBar"]
    assert elapsed_seconds < 2.0


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


def test_external_adapter_runner_detects_same_file_helper_bypass_normalization_edit() -> None:
    query_text = "\n".join(
        [
            "Task",
            "Scope",
            "Same-file helper anchors: astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):; astropy/modeling/separable.py:27: def is_separable(transform):.",
        ]
    )

    flagged = ExternalAdapterRunner._is_same_file_helper_bypass_normalization_edit(
        relative_path="astropy/modeling/separable.py",
        existing_text=(
            "def separability_matrix(transform):\n"
            "    separable_matrix = _separable(transform)\n"
            "    return separable_matrix\n"
            "\n"
            "def _separable(transform):\n"
            "    return transform\n"
        ),
        search="separable_matrix = np.where(separable_matrix != 0, True, False)",
        replace="separable_matrix = separable_matrix.astype(bool)",
        content=None,
        query_text=query_text,
    )

    assert flagged is True


def test_external_adapter_runner_allows_helper_touch_when_same_file_anchor_exists() -> None:
    query_text = "\n".join(
        [
            "Task",
            "Scope",
            "Same-file helper anchors: astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):; astropy/modeling/separable.py:27: def is_separable(transform):.",
        ]
    )

    flagged = ExternalAdapterRunner._is_same_file_helper_bypass_normalization_edit(
        relative_path="astropy/modeling/separable.py",
        existing_text=(
            "def separability_matrix(transform):\n"
            "    separable_matrix = _separable(transform)\n"
            "    return separable_matrix\n"
            "\n"
            "def _compute_n_outputs(left, right):\n"
            "    return left.n_outputs + right.n_outputs\n"
        ),
        search="def _compute_n_outputs(left, right):\n    return left.n_outputs + right.n_outputs",
        replace="def _compute_n_outputs(left, right):\n    return _compute_n_outputs(left.left, left.right) + right.n_outputs",
        content=None,
        query_text=query_text,
    )

    assert flagged is False


def test_external_adapter_runner_allows_normalization_edit_inside_anchored_symbol_block() -> None:
    query_text = "\n".join(
        [
            "Task",
            "Scope",
            "Same-file helper anchors: astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):; astropy/modeling/separable.py:27: def is_separable(transform):.",
        ]
    )

    flagged = ExternalAdapterRunner._is_same_file_helper_bypass_normalization_edit(
        relative_path="astropy/modeling/separable.py",
        existing_text=(
            "def separability_matrix(transform):\n"
            "    separable_matrix = _separable(transform)\n"
            "    return separable_matrix\n"
            "\n"
            "def is_separable(transform):\n"
            "    separable_matrix = separability_matrix(transform)\n"
            "    return (separable_matrix == 0).all(axis=1)\n"
            "\n"
            "def _compute_n_outputs(left, right):\n"
            "    return left.n_outputs + right.n_outputs\n"
        ),
        search="(separable_matrix == 0).all(axis=1)",
        replace="(separable_matrix != 0).all(axis=1)",
        content=None,
        query_text=query_text,
    )

    assert flagged is False


def test_external_adapter_runner_rejects_anchored_normalization_edit_when_retry_requires_helper_callees_first() -> None:
    query_text = "\n".join(
        [
            "Task",
            "Scope",
            "Same-file helper anchors: astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):; astropy/modeling/separable.py:27: def is_separable(transform):.",
            "Start from this live symbol first if it exists in the scoped file: `separability_matrix`. Inspect its same-file helper callees or upstream return path before changing downstream wrappers or final normalization.",
        ]
    )

    flagged = ExternalAdapterRunner._is_same_file_helper_bypass_normalization_edit(
        relative_path="astropy/modeling/separable.py",
        existing_text=(
            "def separability_matrix(transform):\n"
            "    separable_matrix = _separable(transform)\n"
            "    separable_matrix = np.where(separable_matrix != 0, True, False)\n"
            "    return separable_matrix\n"
            "\n"
            "def _separable(transform):\n"
            "    return transform\n"
        ),
        search="separable_matrix = np.where(separable_matrix != 0, True, False)",
        replace="separable_matrix = (separable_matrix != 0)",
        content=None,
        query_text=query_text,
    )

    assert flagged is True


def test_external_adapter_runner_does_not_count_unchanged_helper_mentions_in_full_file_edit_as_helper_touch() -> None:
    query_text = "\n".join(
        [
            "Task",
            "Scope",
            "Same-file helper anchors: astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):; astropy/modeling/separable.py:27: def is_separable(transform):.",
            "Start from this live symbol first if it exists in the scoped file: `separability_matrix`. Inspect its same-file helper callees or upstream return path before changing downstream wrappers or final normalization.",
        ]
    )

    existing_text = (
        "def separability_matrix(transform):\n"
        "    separable_matrix = _separable(transform)\n"
        "    separable_matrix = np.where(separable_matrix != 0, True, False)\n"
        "    return separable_matrix\n"
        "\n"
        "def _separable(transform):\n"
        "    return transform\n"
    )
    updated_text = (
        "def separability_matrix(transform):\n"
        "    separable_matrix = _separable(transform)\n"
        "    separable_matrix[separable_matrix == 0] = False\n"
        "    separable_matrix[separable_matrix > 0] = True\n"
        "    return separable_matrix\n"
        "\n"
        "def _separable(transform):\n"
        "    return transform\n"
    )

    flagged = ExternalAdapterRunner._is_same_file_helper_bypass_normalization_edit(
        relative_path="astropy/modeling/separable.py",
        existing_text=existing_text,
        search=None,
        replace=None,
        content=updated_text,
        query_text=query_text,
    )

    assert flagged is True


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


def test_external_adapter_runner_start_task_does_not_block_on_prompt_stdin_drain(monkeypatch) -> None:
    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        context = _runner_context(
            provider="ollama",
            model="qwen2.5-coder:7b",
            adapter_command=sys.executable,
            adapter_args=["adapter.py"],
        )
        drain_released = asyncio.Event()
        stdin_closed = asyncio.Event()
        prompt = "retry prompt\n" * 20000

        class FakeStdin:
            def __init__(self) -> None:
                self.buffer = bytearray()
                self.closed = False

            def write(self, data: bytes) -> None:
                self.buffer.extend(data)

            async def drain(self) -> None:
                await drain_released.wait()

            def close(self) -> None:
                self.closed = True
                stdin_closed.set()

        class FakeProcess:
            def __init__(self) -> None:
                self.stdin = FakeStdin()
                self.stdout = None
                self.stderr = None
                self.returncode = 0

            async def communicate(self) -> tuple[bytes, bytes]:
                await stdin_closed.wait()
                return (
                    json.dumps(
                        {
                            "status": "completed",
                            "runner_type": "external_adapter",
                            "summary": "done",
                            "report": {
                                "agent": "Worker",
                                "task_id": "1",
                                "status": "done",
                                "summary": "done",
                                "files_changed": [],
                                "tests_run": [],
                                "blockers": [],
                                "risks": [],
                            },
                            "edits": [],
                        }
                    ).encode("utf-8"),
                    b"",
                )

        async def fake_exec(*args, **kwargs):
            return FakeProcess()

        monkeypatch.setattr(runner, "handshake", lambda settings=None: asyncio.sleep(0, result=True))
        monkeypatch.setattr(runner, "_build_adapter_prompt", lambda context_arg: prompt)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

        start_task = asyncio.create_task(runner.start_task(context))
        await asyncio.sleep(0.05)

        assert start_task.done() is True
        handle = await start_task
        state = runner.runs[handle.id]
        assert state.stdin_writer_task is not None
        assert state.process is not None
        assert state.process.stdin is not None
        stdin = state.process.stdin
        assert stdin.closed is False

        drain_released.set()
        assert state.reader_task is not None
        await state.reader_task
        assert stdin.closed is True
        assert stdin.buffer.decode("utf-8") == prompt

    asyncio.run(run_test())


def test_external_adapter_examples_do_not_anchor_math_utils_paths() -> None:
    examples = ExternalAdapterRunner._adapter_examples()

    assert "math_utils" not in examples
    assert "<allowed/code/path>" in examples
    assert "<relevant/test/path>" in examples
    assert '"search": "if old_flag:\\n    return legacy_value\\nreturn fallback_value"' in examples
    assert "placeholders only" in examples
    assert "full updated file contents go here" not in examples


def test_external_adapter_prompt_requires_unique_search_replace_snippets() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")

    prompt = runner._build_adapter_prompt(context)

    assert "make it unique within that file" in prompt
    assert "expand it with surrounding lines" in prompt


def test_external_adapter_prompt_omits_placeholder_example_paths_for_weak_local_models() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")

    prompt = runner._build_adapter_prompt(context)

    assert "Compact local-model JSON reminders:" in prompt
    assert "src/target.py" not in prompt
    assert "tests/test_target.py" not in prompt


def test_external_adapter_prompt_includes_scoped_live_file_focus_for_weak_local_models(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "target.py").write_text(
        "\n".join(
            [
                "def helper():",
                "    return None",
                "",
                "def build_target(value):",
                "    return value.strip()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = ExternalAdapterRunner()
    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
    )
    context.project.idea = (
        "Implementation anchors:\n"
        "- src/target.py:4: def build_target(value):\n"
    )
    context.task.scope = "Stay inside src/target.py."
    context.task.allowed_paths_json = ["src/target.py"]

    prompt = runner._build_adapter_prompt(context)

    assert "Scoped live file focus:" in prompt
    assert "FILE: src/target.py" in prompt
    assert "def build_target(value):" in prompt


def test_external_adapter_prompt_uses_compact_response_schema_for_weak_local_models() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")

    prompt = runner._build_adapter_prompt(context)

    assert "Compact local worker task:" in prompt
    assert '"report": {' in prompt
    assert '"edits": [' in prompt
    assert '"recommended_next_task": "next concrete step"' in prompt


def test_external_adapter_prompt_rejects_expected_behavior_dismissals_for_failing_benchmarks() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")

    prompt = runner._build_adapter_prompt(context)

    assert "Do not claim the current failing benchmark behavior is already correct, expected, or needs no action" in prompt


def test_external_adapter_prompt_requires_search_replace_only_for_large_single_file_weak_local_tasks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "large_module.py").write_text(
        "".join(f"line_{index} = {index}\n" for index in range(160)),
        encoding="utf-8",
    )
    runner = ExternalAdapterRunner()
    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
    )
    context.task.allowed_paths_json = ["src/large_module.py"]
    context.task.scope = "Update only src/large_module.py."

    prompt = runner._build_adapter_prompt(context)

    assert "Return search/replace edits only for this task. Do not return full-file content." in prompt
    assert '"search": "exact existing text to replace"' in prompt
    assert '"replace": "updated text for the matched block"' in prompt
    assert '"content": "full updated file content"' not in prompt


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
        "execution_request": {
            "request_id": "remote-exec-123",
            "request_status": "ready",
            "execution_request_path": "artifacts/remote-execution-requests/remote-exec-123/execution-request.json",
        },
    }

    prompt = runner._build_adapter_prompt(context)

    assert "Remote execution context:" in prompt
    assert "Edge Box" in prompt
    assert "artifacts/model.onnx" in prompt
    assert "source_control" in prompt
    assert "remote-exec-123" in prompt
    assert "execution-request.json" in prompt


def test_external_adapter_workspace_snapshot_includes_read_only_scope_references(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:14b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.scope = "Fix src/math_utils.py using evidence from tests/test_math_utils.py."
    context.task.validation_steps_json = ["python -m pytest tests/test_math_utils.py -q"]

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: src/math_utils.py" in snapshot
    assert "Read-only support context:" in snapshot
    assert "REFERENCE FILE (read-only): tests/test_math_utils.py" in snapshot


def test_external_adapter_workspace_snapshot_skips_read_only_support_for_weak_local_implementation(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["src/math_utils.py"]
    context.task.scope = "Fix src/math_utils.py using evidence from tests/test_math_utils.py."
    context.task.validation_steps_json = ["python -m pytest tests/test_math_utils.py -q"]

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: src/math_utils.py" in snapshot
    assert "Read-only support context:" not in snapshot
    assert "REFERENCE FILE (read-only): tests/test_math_utils.py" not in snapshot


def test_external_adapter_workspace_snapshot_includes_full_single_allowed_file_for_weak_local_implementation(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    large_body = "".join(f"VALUE_{index} = {index}\n" for index in range(260))
    (workspace / "src" / "math_utils.py").write_text(large_body, encoding="utf-8")

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["src/math_utils.py"]
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Correct the broken behavior."
    context.task.agent_role = "Service Flow Builder"
    context.task.scope = "Patch only src/math_utils.py."

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: src/math_utils.py" in snapshot
    assert "VALUE_0 = 0" in snapshot
    assert "VALUE_259 = 259" in snapshot
    assert "[targeted excerpt selected from a larger file]" not in snapshot


def test_external_adapter_workspace_snapshot_expands_globbed_allowed_paths(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["tests/*"]

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: tests/test_math_utils.py" in snapshot
    assert ExternalAdapterRunner._path_is_allowed("tests/test_math_utils.py", ["tests/*"], []) is True


def test_external_adapter_workspace_snapshot_prioritizes_identifier_matched_files(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "django" / "conf").mkdir(parents=True)
    (workspace / "tests" / "test_utils").mkdir(parents=True)
    (workspace / "tests" / "aaa_irrelevant").mkdir(parents=True)
    (workspace / "django" / "conf" / "global_settings.py").write_text(
        "FILE_UPLOAD_PERMISSIONS = None\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "test_utils" / "tests.py").write_text(
        "def test_override_file_upload_permissions():\n    assert True\n",
        encoding="utf-8",
    )
    (workspace / "tests" / "aaa_irrelevant" / "test_noise.py").write_text(
        "def test_noise():\n    assert True\n",
        encoding="utf-8",
    )

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["tests", "django/conf"]
    context.task.goal = "Fix FILE_UPLOAD_PERMISSIONS default handling."
    context.task.scope = "Inspect django.conf.global_settings and the failing test_utils.tests.OverrideSettingsTests case."
    context.task.validation_steps_json = [
        "python tests/runtests.py --settings=test_sqlite test_utils.tests.OverrideSettingsTests.test_override_file_upload_permissions"
    ]

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: django/conf/global_settings.py" in snapshot
    assert "FILE: tests/test_utils/tests.py" in snapshot


def test_external_adapter_prompt_compacts_large_benchmark_context_for_weak_ollama_model(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    workspace.mkdir(parents=True)
    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    pass_to_pass_targets = " ".join(f"- test_pass_{index}" for index in range(180))
    long_validation_command = "python tests/runtests.py --settings=test_sqlite " + " ".join(
        f"expressions.tests.GeneratedCase.test_{index}" for index in range(220)
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "Instance ID: django__django-11001 "
        "Repository: django/django "
        "Base commit: ef082ebb84f00e38af4e8880d04e8365c2766d34 "
        "Issue: Incorrect removal of order_by clause created as multiline RawSQL "
        "Description Hi. The SQLCompiler is ripping off one of my order by clauses because multiline RawSQL lines collide. "
        "Workspace clues: "
        "Files to inspect first: tests/expressions/tests.py, tests/runtests.py "
        "Likely related implementation files: django/db/models/sql/compiler.py, django/db/models/expressions.py "
        "Exact repo matches for issue snippets: "
        "django/db/models/sql/compiler.py:356: without_ordering = self.ordering_parts.search(sql).group(1) "
        "django/db/models/sql/compiler.py:369: without_ordering = self.ordering_parts.search(sql).group(1) "
        f"Focused reproduction commands: - {long_validation_command} "
        "FAIL_TO_PASS targets: - test_order_by_multiline_sql - test_order_of_operations "
        f"PASS_TO_PASS targets: {pass_to_pass_targets} "
        "Required behavior: - Produce the smallest safe patch and validate honestly."
    )
    context.task.goal = "Implement the smallest safe code fix. " + ("Keep the change narrow. " * 80)
    context.task.scope = "Update only the validated implementation paths. " + ("Stay inside the scoped files. " * 60)
    context.task.validation_steps_json = [long_validation_command] * 4
    context.context_pack_markdown = "# Worker Context\n\n## Validation\n" + "\n".join(
        f"- {long_validation_command}" for _ in range(4)
    )

    prompt = runner._build_adapter_prompt(context)

    assert "Benchmark task brief:" in prompt
    assert "Exact repo matches for issue snippets:" in prompt
    assert "django/db/models/sql/compiler.py:356:" in prompt
    assert "omitted for compact local worker context" in prompt
    assert "PASS_TO_PASS targets:" not in prompt
    assert len(prompt) < 14000


def test_external_adapter_workspace_snapshot_prioritizes_exact_repo_match_snippet(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    compiler_dir = workspace / "django" / "db" / "models" / "sql"
    compiler_dir.mkdir(parents=True)
    large_prefix = "".join(f"# filler {index}\n" for index in range(700))
    target_block = (
        "class SQLCompiler:\n"
        "    def get_order_by(self):\n"
        "        sql = \"SELECT 1\\nDESC\"\n"
        "        without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        return without_ordering\n"
    )
    large_suffix = "".join(f"# tail {index}\n" for index in range(700))
    (compiler_dir / "compiler.py").write_text(large_prefix + target_block + large_suffix, encoding="utf-8")
    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["django/db/models/sql"]
    context.task.goal = "Implement the smallest safe code fix."
    context.task.scope = "Update django/db/models/sql/compiler.py."
    context.project.idea = (
        "Instance ID: django__django-11001\n"
        "Exact repo matches for issue snippets:\n"
        "django/db/models/sql/compiler.py:356: without_ordering = self.ordering_parts.search(sql).group(1)\n"
    )

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: django/db/models/sql/compiler.py" in snapshot
    assert "def get_order_by(self):" in snapshot
    assert "without_ordering = self.ordering_parts.search(sql).group(1)" in snapshot


def test_external_adapter_required_validation_commands_extracts_embedded_django_command_from_sentence() -> None:
    task = Task(
        id=3,
        project_id=1,
        title="Implement the smallest safe code fix",
        goal="Correct the confirmed failing behavior with the least invasive code change.",
        scope="Update the validated implementation path only.",
        agent_role="Service Flow Builder",
        milestone="Milestone 2 - Fix the code",
        allowed_paths_json=["django/db/models/sql"],
        forbidden_paths_json=[],
        validation_steps_json=[
            "Use the focused validation command as the implementation anchor: "
            "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests",
            "Keep the change scoped to the validated failure",
        ],
        success_criteria_json=["The implementation matches the expected behavior"],
        estimated_complexity="small",
        dependencies_json=[],
        status="assigned",
        priority=20,
    )

    commands = ExternalAdapterRunner._required_validation_commands(task)

    assert commands == [
        "python tests/runtests.py --settings=test_sqlite expressions.tests.BasicExpressionsTests"
    ]


def test_external_adapter_workspace_snapshot_uses_targeted_excerpt_for_large_late_match_files(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    (workspace / "django" / "db" / "models" / "sql").mkdir(parents=True)
    filler = ("HEAD_ONLY_SENTINEL = 'noise'\n" * 220)
    target_block = (
        "class SQLCompiler:\n"
        "    def get_order_by(self):\n"
        "        sql = \"SELECT 1\\nDESC\"\n"
        "        without_ordering = self.ordering_parts.search(sql)[1]\n"
        "        return without_ordering\n"
    )
    (workspace / "django" / "db" / "models" / "sql" / "compiler.py").write_text(
        filler + "\n" + target_block,
        encoding="utf-8",
    )

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Incorrect removal of order_by clause created as multiline RawSQL. "
        "The bug is located in SQLCompiler.get_order_by() near without_ordering."
    )
    context.task.allowed_paths_json = ["django/db/models/sql"]
    context.task.goal = "Fix SQLCompiler.get_order_by() for multiline RawSQL ordering clauses."
    context.task.scope = "Inspect django/db/models/sql/compiler.py and correct without_ordering handling."

    snapshot = runner._workspace_snapshot_markdown(context)

    assert "FILE: django/db/models/sql/compiler.py" in snapshot
    assert "def get_order_by(self):" in snapshot
    assert "without_ordering = self.ordering_parts.search(sql)[1]" in snapshot
    assert "HEAD_ONLY_SENTINEL" not in snapshot
    assert "[targeted excerpt selected from a larger file]" in snapshot


def test_external_adapter_prompt_surfaces_exact_live_edit_anchors_for_repo_match_snippets(tmp_path: Path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "repo"
    compiler_dir = workspace / "django" / "db" / "models" / "sql"
    compiler_dir.mkdir(parents=True)
    (compiler_dir / "compiler.py").write_text(
        "\n".join(
            [
                "class SQLCompiler:",
                "    def get_order_by(self):",
                "        sql = \"SELECT 1\\nDESC\"",
                "        without_ordering = self.ordering_parts.search(sql).group(1)",
                "        return without_ordering",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["django/db/models/sql"]
    context.task.goal = "Fix SQLCompiler.get_order_by() for multiline RawSQL ordering clauses."
    context.task.scope = "Update django/db/models/sql/compiler.py."
    context.project.idea = (
        "Instance ID: django__django-11001\n"
        "Exact repo matches for issue snippets:\n"
        "django/db/models/sql/compiler.py:356: without_ordering = self.ordering_parts.search(sql).group(1)\n"
    )

    prompt = runner._build_adapter_prompt(context)

    assert "Exact live edit anchors:" in prompt
    assert "Never shorten identifiers or invent abbreviated code such as `self.o`." in prompt
    assert "without_ordering = self.ordering_parts.search(sql).group(1)" in prompt
    assert "def get_order_by(self):" in prompt


def test_external_adapter_prompt_surfaces_issue_provided_fix_clues() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Incorrect removal of order_by clause created as multiline RawSQL.\n"
        "As a quick/temporal fix I can suggest making sql variable clean of newline characters, like this:\n"
        "sql_oneline = ' '.join(sql.split('\\n'))\n"
        "without_ordering = self.ordering_parts.search(sql_oneline).group(1)\n"
        "Note: beware of unicode and EOL dragons.\n"
    )
    context.task.goal = "Fix SQLCompiler.get_order_by() for multiline RawSQL ordering clauses."
    context.task.scope = "Update django/db/models/sql/compiler.py."

    prompt = runner._build_adapter_prompt(context)

    assert "Issue-provided fix clues:" in prompt
    assert "sql_oneline = ' '.join(sql.split('\\n'))" in prompt
    assert "without_ordering = self.ordering_parts.search(sql_oneline).group(1)" in prompt
    assert "Do not invent unrelated string-contains heuristics" in prompt


def test_external_adapter_prompt_uses_local_execution_language_when_remote_execution_is_disabled() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.settings.remote_execution = {
        "policy": {"enabled": False},
        "selection": {"blocking_reasons": ["remote_execution_disabled"]},
    }

    prompt = runner._build_adapter_prompt(context)

    assert "Remote execution is disabled for this run." in prompt
    assert "Use the local workspace and local commands only." in prompt
    assert "no target is ready" not in prompt.lower()


def test_external_adapter_prompt_requires_validation_commands_for_validation_specialist() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent.role = "Validation Specialist"
    context.task.agent_role = "Validation Specialist"
    context.task.title = "Run focused regression validation"
    context.task.goal = "Validate the behavior using the provided regression command."
    context.task.scope = "Run the exact test command and report the outcome without editing files."
    context.task.validation_steps_json = ["Run the focused validation command: python -m pytest tests/test_math_utils.py -q"]

    prompt = runner._build_adapter_prompt(context)

    assert "Editing expected for this task: no" in prompt
    assert "Validation execution contract:" in prompt
    assert "Do not return `needs_review` or ask for more evidence" in prompt
    assert "`python -m pytest tests/test_math_utils.py -q`" in prompt


def test_external_adapter_prompt_requires_validation_commands_for_implementation_retry_with_explicit_rerun() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent.role = "Backend specialist"
    context.task.agent_role = "Service Flow Builder"
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Reproduce and clear the failing validation command: python -m pytest tests/test_math_utils.py -q. "
        "Rerun focused validation before calling this done. Do not report success unless the rerun actually passes."
    )
    context.task.scope = "Make the smallest safe code fix and rerun the focused validation command."
    context.task.validation_steps_json = ["Keep the change scoped to the validated failure."]

    prompt = runner._build_adapter_prompt(context)

    assert "Editing expected for this task: yes" in prompt
    assert "Validation execution contract:" in prompt
    assert "`python -m pytest tests/test_math_utils.py -q`" in prompt


def test_external_adapter_benchmark_implementation_task_skips_local_required_command_enforcement() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6] "
        "PASS_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_coord_matrix "
        "Mission Control will use authoritative validation after the patch."
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Repair the scoped implementation and clear the focused validation command: "
        "python -m pytest astropy/modeling/tests/test_separable.py -q"
    )
    context.task.scope = "Update astropy/modeling/separable.py only."
    context.task.validation_steps_json = [
        "Focused reproduction command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    assert runner._requires_command_execution(context) is False


def test_external_adapter_benchmark_validation_task_requires_local_command_enforcement() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6] "
        "PASS_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_coord_matrix "
        "Mission Control will use authoritative validation after the patch."
    )
    context.agent.role = "Validation Specialist"
    context.task.agent_role = "Validation Specialist"
    context.task.title = "Run focused regression validation"
    context.task.goal = "Validate the benchmark behavior using python -m pytest astropy/modeling/tests/test_separable.py -q"
    context.task.scope = "Use the focused regression command as the benchmark evidence source."
    context.task.validation_steps_json = [
        "Run the focused validation command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    assert runner._requires_command_execution(context) is True


def test_external_adapter_prompt_uses_authoritative_benchmark_validation_contract_for_implementation_tasks() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6] "
        "PASS_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_coord_matrix "
        "Mission Control will use authoritative evaluator validation after the patch."
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Repair the implementation and clear the focused validation command: "
        "python -m pytest astropy/modeling/tests/test_separable.py -q"
    )
    context.task.scope = "Update astropy/modeling/separable.py only."
    context.task.validation_steps_json = [
        "Focused reproduction command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "Validation execution contract:" in prompt
    assert "authoritative benchmark evaluation" in prompt
    assert "do not spend the turn only rerunning a local command if the staged workspace hits import/build noise" in prompt
    assert "`python -m pytest astropy/modeling/tests/test_separable.py -q`" in prompt
    assert "Copy the executed command into both `report.tests_run` and `commands_attempted`." not in prompt


def test_external_adapter_prompt_requires_real_execution_for_benchmark_validation_tasks() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6] "
        "PASS_TO_PASS targets: - astropy/modeling/tests/test_coord_matrix "
        "Mission Control will use authoritative evaluator validation after the patch."
    )
    context.agent.role = "Validation Specialist"
    context.task.agent_role = "Validation Specialist"
    context.task.title = "Run focused regression validation"
    context.task.goal = "Validate the benchmark behavior using python -m pytest astropy/modeling/tests/test_separable.py -q"
    context.task.scope = "Use the focused regression command as the benchmark evidence source."
    context.task.validation_steps_json = [
        "Run the focused validation command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "must execute the required command below inside the staged workspace before you answer" in prompt
    assert "If the command fails, report the real failure output instead of claiming the issue is not reproducible" in prompt
    assert "Do not claim the benchmark already passes or is not reproducible unless the command actually ran and passed in this workspace" in prompt
    assert "Copy the executed command into both `report.tests_run` and `commands_attempted`." in prompt


def test_external_adapter_prompt_surfaces_issue_named_primary_symbol_for_benchmark_fix() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Repair `separability_matrix` in astropy/modeling/separable.py."
    context.task.scope = "Update astropy/modeling/separable.py only."

    prompt = runner._build_adapter_prompt(context)

    assert "Issue-named primary symbols:" in prompt
    assert "`separability_matrix`" in prompt
    assert "start there unless stronger same-file live evidence points to a sibling helper" in prompt


def test_external_adapter_prompt_surfaces_same_file_implementation_anchors_for_benchmark_fix() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:27: def is_separable(transform):\n"
        "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
        "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.\n"
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6]"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Repair `separability_matrix` in astropy/modeling/separable.py."
    context.task.scope = "Update astropy/modeling/separable.py only."

    prompt = runner._build_adapter_prompt(context)

    assert "Same-file implementation anchors:" in prompt
    assert "`astropy/modeling/separable.py:27: def is_separable(transform):`" in prompt
    assert "`astropy/modeling/separable.py:66: def separability_matrix(transform):`" in prompt
    assert "Treat task-provided `path:line:symbol` anchors as approximate locators" in prompt
    assert "If report.files_changed is non-empty, edits[] must include the exact attempted patch" in prompt
    assert "Do not guess helper arity or compose those helpers into a new call chain" in prompt


def test_external_adapter_prompt_surfaces_authoritative_live_symbol_presence_for_benchmark_fix(tmp_path) -> None:
    runner = ExternalAdapterRunner()
    workspace = tmp_path / "workspace"
    target = workspace / "astropy" / "modeling"
    target.mkdir(parents=True)
    (target / "separable.py").write_text(
        "\n".join(
            [
                "def is_separable(transform):",
                "    return True",
                "",
                "def separability_matrix(transform):",
                "    return _separable(transform)",
                "",
                "def _separable(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = _runner_context(
        workspace_path=workspace.as_posix(),
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:4: def separability_matrix(transform):\n"
        "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.\n"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Repair `separability_matrix` in astropy/modeling/separable.py."
    context.task.scope = "Update astropy/modeling/separable.py only."

    prompt = runner._build_adapter_prompt(context)

    assert "Authoritative live symbol presence:" in prompt
    assert "`astropy/modeling/separable.py` contains `def separability_matrix(transform):`" in prompt
    assert "a blocker that says it is missing is invalid" in prompt


def test_external_adapter_prompt_blocks_invented_helper_call_chains_for_benchmark_fix() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task.\n"
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
        "- astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):\n"
        "- astropy/modeling/separable.py:130: def _arith_oper(left, right):\n"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Repair the implementation and clear the focused validation command: "
        "python -m pytest astropy/modeling/tests/test_separable.py -q"
    )
    context.task.scope = "Update astropy/modeling/separable.py only."
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.task.validation_steps_json = [
        "Focused reproduction command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "Do not replace an existing core expression with a newly invented internal helper-call chain" in prompt
    assert "treat that final normalization as a downstream symptom by default" in prompt
    assert "do not make another output-normalization tweak on that same variable" in prompt
    assert "inspect the other same-file anchors before repeating the same logic" in prompt


def test_external_adapter_full_prompt_blocks_initial_boolean_normalization_detours() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="openai",
        model="gpt-4.1",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task.\n"
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
        "- astropy/modeling/separable.py:27: def is_separable(transform):\n"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Repair the implementation and clear the focused validation command: "
        "python -m pytest astropy/modeling/tests/test_separable.py -q"
    )
    context.task.scope = "Update astropy/modeling/separable.py only."
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.task.validation_steps_json = [
        "Focused reproduction command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "treat that final normalization as a downstream symptom by default" in prompt
    assert "Inspect and patch the upstream calculation or helper that produced the intermediate" in prompt


def test_external_adapter_prompt_prioritizes_named_same_file_helper_from_retry_evidence() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task.\n"
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:27: def is_separable(transform):\n"
        "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
        "- astropy/modeling/separable.py:105: def _compute_n_outputs(left, right):\n"
    )
    context.task.title = "Focused retry: Implement the smallest safe code fix"
    context.task.goal = (
        "Repair the implementation and clear the focused validation command: "
        "python -m pytest astropy/modeling/tests/test_separable.py -q. "
        "Prior retry hint: Update the _separable function to handle nested models correctly."
    )
    context.task.scope = "Update astropy/modeling/separable.py only."
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.task.validation_steps_json = [
        "Focused reproduction command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "same-file sibling helper or upstream function as the likely culprit" in prompt
    assert "inspect and patch that named helper before changing the downstream wrapper or final normalization step again" in prompt


def test_external_adapter_prompt_uses_authoritative_benchmark_validation_contract_for_validation_tasks() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Run this as a prepared local SWE-bench-style coding task. "
        "FAIL_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_separable[compound_model6-result6] "
        "PASS_TO_PASS targets: - astropy/modeling/tests/test_separable.py::test_coord_matrix "
        "Mission Control will use authoritative evaluator validation after the patch."
    )
    context.agent.role = "Validation Specialist"
    context.task.agent_role = "Validation Specialist"
    context.task.title = "Run focused regression validation"
    context.task.goal = "Validate the benchmark behavior using python -m pytest astropy/modeling/tests/test_separable.py -q"
    context.task.scope = "Use the focused regression command as the benchmark evidence source."
    context.task.validation_steps_json = [
        "Run the focused validation command: python -m pytest astropy/modeling/tests/test_separable.py -q"
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "Validation execution contract:" in prompt
    assert "This benchmark task uses authoritative validation outside the staged worker workspace" in prompt
    assert "do not burn the turn only rerunning it locally if the staged workspace hits import/build noise first" in prompt
    assert "`python -m pytest astropy/modeling/tests/test_separable.py -q`" in prompt


def test_external_adapter_prompt_requires_edits_before_validation_only_completion_for_implementation_tasks() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent.role = "Backend specialist"
    context.task.agent_role = "Service Flow Builder"
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = (
        "Reproduce and clear the failing validation command: python -m pytest tests/test_math_utils.py -q. "
        "Rerun focused validation before calling this done."
    )
    context.task.scope = "Update src/math_utils.py only."
    context.task.validation_steps_json = [
        "Use the focused validation command as the implementation anchor: python -m pytest tests/test_math_utils.py -q",
        "Keep the change scoped to the validated failure.",
    ]

    prompt = runner._build_adapter_prompt(context)

    assert "Inspect the allowed implementation files first and return at least one concrete edit in `edits[]`" in prompt
    assert "A failing assertion line inside a benchmark test file is evidence about source behavior" in prompt
    assert "Treat a known failing focused command as starting-state evidence" in prompt
    assert "do not spend the whole turn only rerunning an already-failing command" in prompt
    assert "Do not return `needs_review`, `done`, or `blocked` with empty `edits[]`" in prompt
    assert "supporting class or helper being defined elsewhere does not prove the scoped implementation file is wrong" in prompt
    assert "do not claim the symbol only exists in a test or other file unless you cite contradictory live repo evidence" in prompt
    assert "assume the allowed implementation file is the default edit target" in prompt
    assert "do not claim that file lacks the implementation symbol just because related classes live elsewhere" in prompt
    assert "a blocker that says the symbol only exists in a test file is invalid" in prompt
    assert "'the function already exists' or 'no changes are needed' is not an acceptable blocker" in prompt
    assert "patch inside that body" in prompt
    assert "Do not prepend a replacement implementation block ahead of an existing docstring" in prompt
    assert "Do not introduce a recursive self-call in the anchored function" in prompt
    assert "do not retarget the fix into a failing test file" in prompt
    assert "do not treat a pre-edit validation rerun stack trace as stronger evidence" in prompt
    assert "treat this turn as patch-first, then rerun focused validation" in prompt
    assert "do not spend the entire turn on validation-only output" in prompt


def test_external_adapter_prompt_surfaces_previous_edit_rejection_context() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent.last_report_summary = (
        "Mission Control rejected or could not apply one or more proposed edits. "
        "Rejected search/replace edit because the search text was not found in django/db/models/sql/compiler.py. "
        "Mission Control could not verify any workspace file changes for this claimed implementation step."
    )

    prompt = runner._build_adapter_prompt(context)

    assert "Previous attempt signals:" in prompt
    assert "do not repeat the same stale search/replace patch" in prompt
    assert "exact applicable edit or return blocked with concrete evidence" in prompt
    assert "Never rewrite a large framework file from scratch for a narrow bugfix" in prompt


def test_external_adapter_prompt_surfaces_previous_validation_failure_as_patch_first_retry() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent.last_report_summary = (
        "Mission Control executed the required validation command locally and it failed. "
        "Required validation command failed with exit code 1: python -m pytest tests/test_math_utils.py -q"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Repair the implementation and rerun the focused validation command."
    context.task.scope = "Update src/math_utils.py only."

    prompt = runner._build_adapter_prompt(context)

    assert "Previous attempt signals:" in prompt
    assert "The failure has already been reproduced." in prompt
    assert "patch-first, then rerun focused validation" in prompt


def test_external_adapter_prompt_marks_reproduce_only_retry_as_invalid() -> None:
    runner = ExternalAdapterRunner()

    prompt = runner._adapter_examples()

    assert "Also invalid for an implementation retry:" in prompt
    assert "Reproduced the failing test again and need more investigation." in prompt
    assert "returns no edit plus no exact scoped blocker evidence" in prompt


def test_external_adapter_prompt_tolerates_agent_without_optional_attempt_fields() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.agent = SimpleNamespace(
        id=2,
        project_id=1,
        name="Worker",
        role="Implementation",
        kind="worker",
        status="idle",
        workspace_path="C:/demo",
    )

    prompt = runner._build_adapter_prompt(context)

    assert "External adapter execution rules:" in prompt
    assert "Previous attempt signals:" not in prompt


def test_external_adapter_task_query_text_preserves_multiline_repo_anchors() -> None:
    context = _runner_context(
        provider="ollama",
        model="qwen2.5-coder:7b",
        adapter_command=sys.executable,
        adapter_args=["adapter.py"],
    )
    context.project.idea = (
        "Implementation anchors:\n"
        "- src/target.py:10: def build_target(value):\n"
        "- src/target.py:12: if should_wrap(value):"
    )
    context.task.title = "Implement the smallest safe code fix"
    context.task.goal = "Patch the scoped implementation."
    context.task.scope = "Stay inside src/target.py."

    query_text = ExternalAdapterRunner._task_query_text(context)
    snippets = ExternalAdapterRunner._exact_repo_match_snippets(query_text, "src/target.py")

    assert "src/target.py:10: def build_target(value):" in query_text
    assert snippets == ["def build_target(value):", "if should_wrap(value):"]


def test_external_adapter_compact_project_idea_preserves_implementation_anchor_section() -> None:
    long_issue = ("Issue details. " * 220).strip()
    compact = ExternalAdapterRunner._compact_project_idea(
        "\n".join(
            [
                "Instance ID: astropy__astropy-12907",
                "Repository: astropy/astropy",
                "Files to inspect first:",
                "- astropy/modeling/tests/test_separable.py",
                "Likely related implementation files:",
                "- astropy/modeling/separable.py",
                "Implementation anchors:",
                "- astropy/modeling/separable.py:66: def separability_matrix(transform):",
                "- astropy/modeling/separable.py:24: __all__ = [\"is_separable\", \"separability_matrix\"]",
                f"Issue: {long_issue}",
                "Focused reproduction commands:",
                "- python -m pytest astropy/modeling/tests/test_separable.py -q",
                "Required behavior:",
                "- Generate and apply the smallest safe patch you can justify.",
            ]
        )
    )

    assert "Implementation anchors:" in compact
    assert "astropy/modeling/separable.py:66: def separability_matrix(transform):" in compact


def test_external_adapter_compact_project_idea_preserves_retry_hints_section() -> None:
    long_issue = ("Issue details. " * 180).strip()
    compact = ExternalAdapterRunner._compact_project_idea(
        "\n".join(
            [
                "Instance ID: astropy__astropy-12907",
                "Repository: astropy/astropy",
                f"Issue: {long_issue}",
                "Hints:",
                "Retry feedback for attempt 2: the previous benchmark attempt applied a candidate patch but failed authoritative validation.",
                "Validation failure excerpt:",
                "Command: python -m pytest astropy/modeling/tests/test_separable.py -q",
                "Prior patch excerpt:",
                "@@ -59,7 +59,7 @@",
                "-    is_separable = np.where(is_separable != 1, False, True)",
                "+    is_separable = np.any(is_separable != 0, axis=1)",
            ]
        )
    )

    assert "Hints:" in compact
    assert "failed authoritative validation" in compact
    assert "Prior patch excerpt:" in compact


def test_external_adapter_recent_attempt_context_flags_expected_behavior_dismissal() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")
    context.agent.last_report_summary = (
        "The current failing benchmark behavior is expected behavior and no action needed."
    )

    retry_context = runner._recent_attempt_context_markdown(context)

    assert "tried to dismiss the benchmark regression as already correct" in retry_context


def test_external_adapter_recent_attempt_context_flags_no_changes_needed_dismissal() -> None:
    runner = ExternalAdapterRunner()
    context = _runner_context(provider="ollama", model="qwen2.5-coder:7b")
    context.agent.last_report_summary = (
        "The exact live anchors already show the target function inside the allowed file. No changes are needed."
    )

    retry_context = runner._recent_attempt_context_markdown(context)

    assert "tried to dismiss the benchmark regression as already correct" in retry_context


def test_external_adapter_ranked_excerpt_terms_prioritizes_lowercase_snake_case_repo_symbols() -> None:
    query_text = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
        "- astropy/modeling/separable.py:24: __all__ = [\"is_separable\", \"separability_matrix\"]\n"
        "Modify the `separability_matrix` function in `astropy/modeling/separable.py`.\n"
    )

    ranked_terms = ExternalAdapterRunner._ranked_excerpt_terms(query_text, "astropy/modeling/separable.py")

    assert "separability_matrix" in ranked_terms[:5]
    assert ranked_terms.index("separability_matrix") < ranked_terms.index("separable")


def test_external_adapter_relaxed_multiline_search_tolerates_extra_blank_lines() -> None:
    existing_text = (
        "def is_separable(transform):\n"
        "    is_separable = np.where(is_separable != 1, False, True)\n"
        "    return is_separable\n"
        "\n"
        "\n"
        "def separability_matrix(transform):\n"
        "    return transform\n"
    )
    search = (
        "is_separable = np.where(is_separable != 1, False, True)\n"
        "return is_separable\n"
        "\n"
        "def separability_matrix(transform):"
    )

    matches = ExternalAdapterRunner._search_multiline_positions_relaxed(existing_text, search)

    assert len(matches) == 1
    position, matched_text = matches[0]
    assert position == existing_text.index("is_separable = np.where")
    assert matched_text == (
        "is_separable = np.where(is_separable != 1, False, True)\n"
        "    return is_separable\n"
        "\n"
        "\n"
        "def separability_matrix(transform):"
    )


def test_external_adapter_scoped_live_file_focus_prefers_explicit_live_anchor(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "astropy" / "modeling"
    target.mkdir(parents=True)
    (target / "separable.py").write_text(
        "\n".join(
            [
                "def unrelated_helper():",
                "    return 'ignore me'",
                "",
                "FILLER_01 = 1",
                "FILLER_02 = 2",
                "FILLER_03 = 3",
                "FILLER_04 = 4",
                "FILLER_05 = 5",
                "FILLER_06 = 6",
                "FILLER_07 = 7",
                "FILLER_08 = 8",
                "FILLER_09 = 9",
                "FILLER_10 = 10",
                "",
                "def separability_matrix(transform):",
                "    matrix = _separable(transform)",
                "    return matrix",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = _runner_context(workspace_path=workspace.as_posix(), provider="ollama", model="qwen2.5-coder:7b")
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:15: def separability_matrix(transform):\n"
    )
    context.task.scope = (
        "Update the implementation only. "
        "Live implementation anchor: astropy/modeling/separable.py:15: def separability_matrix(transform):."
    )

    markdown = ExternalAdapterRunner()._scoped_live_file_focus_markdown(context)

    assert "Scoped live file focus:" in markdown
    assert "def separability_matrix(transform):" in markdown
    assert "matrix = _separable(transform)" in markdown
    assert "def unrelated_helper()" not in markdown


def test_external_adapter_scoped_live_file_focus_prefers_retry_named_same_file_helper(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "astropy" / "modeling"
    target.mkdir(parents=True)
    (target / "separable.py").write_text(
        "\n".join(
            [
                "def separability_matrix(transform):",
                "    matrix = _separable(transform)",
                "    return matrix",
                "",
                "def _separable(transform):",
                "    if transform.n_inputs == 1:",
                "        return transform",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = _runner_context(workspace_path=workspace.as_posix(), provider="ollama", model="qwen2.5-coder:7b")
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:1: def separability_matrix(transform):\n"
    )
    context.task.goal = "Patch this same-file helper first if it exists in the live scoped file: `_separable`."
    context.task.scope = "Update astropy/modeling/separable.py only."

    markdown = ExternalAdapterRunner()._scoped_live_file_focus_markdown(context)

    assert "same-file helper or function explicitly named in the retry context" in markdown
    assert "def _separable(transform):" in markdown
    assert "if transform.n_inputs == 1:" in markdown


def test_external_adapter_scoped_live_file_focus_surfaces_same_file_callee_from_anchor(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "astropy" / "modeling"
    target.mkdir(parents=True)
    (target / "separable.py").write_text(
        "\n".join(
            [
                "def separability_matrix(transform):",
                "    matrix = _separable(transform)",
                "    return matrix",
                "",
                "def _separable(transform):",
                "    if transform.n_inputs == 1:",
                "        return transform",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = _runner_context(workspace_path=workspace.as_posix(), provider="ollama", model="qwen2.5-coder:7b")
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:1: def separability_matrix(transform):\n"
    )
    context.task.goal = "Implement the smallest safe fix in astropy/modeling/separable.py."
    context.task.scope = "Update astropy/modeling/separable.py only."

    markdown = ExternalAdapterRunner()._scoped_live_file_focus_markdown(context)

    assert "same-file helper or function explicitly named in the retry context" in markdown
    assert "same-file helper `_separable`" in markdown
    assert "def _separable(transform):" in markdown


def test_external_adapter_live_symbol_presence_markdown_surfaces_verified_definition(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "astropy" / "modeling"
    target.mkdir(parents=True)
    (target / "separable.py").write_text(
        "\n".join(
            [
                "def is_separable(transform):",
                "    return True",
                "",
                "def separability_matrix(transform):",
                "    return _separable(transform)",
                "",
                "def _separable(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    context = _runner_context(workspace_path=workspace.as_posix(), provider="ollama", model="qwen2.5-coder:7b")
    context.task.allowed_paths_json = ["astropy/modeling/separable.py"]
    context.project.idea = (
        "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.\n"
        "Implementation anchors:\n"
        "- astropy/modeling/separable.py:4: def separability_matrix(transform):\n"
    )
    context.task.goal = "Repair `separability_matrix` in astropy/modeling/separable.py."
    context.task.scope = "Update astropy/modeling/separable.py only."

    markdown = ExternalAdapterRunner()._live_symbol_presence_markdown(context)

    assert "Authoritative live symbol presence:" in markdown
    assert "`astropy/modeling/separable.py` contains `def separability_matrix(transform):`" in markdown
    assert "a blocker that says it is missing is invalid" in markdown


def test_external_adapter_query_focus_symbol_names_ignores_exact_function_signatures_noise() -> None:
    symbols = ExternalAdapterRunner._query_focus_symbol_names(
        "Inspect the live workspace and provide an exact search/replace patch based on the actual function signatures and logic. "
        "Patch the `_separable` helper function instead."
    )

    assert "_separable" in symbols
    assert "exact" not in symbols


def test_external_adapter_query_focus_symbol_names_ignores_same_file_helper_prose_noise() -> None:
    symbols = ExternalAdapterRunner._query_focus_symbol_names(
        "Patch this same-file helper first if it exists in the live scoped file. "
        "Then patch the `_separable` helper function instead."
    )

    assert "_separable" in symbols
    assert "file" not in symbols


def test_external_adapter_query_focus_symbol_names_prefers_backticked_helper_with_arguments() -> None:
    symbols = ExternalAdapterRunner._query_focus_symbol_names(
        "Investigate and fix the logic in `_compute_n_outputs(left, right)` or `_arith_oper(left, right)` "
        "instead of patching `separability_matrix` again."
    )

    assert "_compute_n_outputs" in symbols
    assert "_arith_oper" in symbols


def test_external_adapter_query_focus_symbol_names_prioritizes_explicit_same_file_helper_over_issue_symbol() -> None:
    symbols = ExternalAdapterRunner._query_focus_symbol_names(
        "Issue: `separability_matrix` does not compute separability correctly for nested CompoundModels. "
        "Patch this same-file helper first if it exists in the live scoped file: `_separable`."
    )

    assert symbols[0] == "_separable"
    assert "separability_matrix" in symbols


def test_external_adapter_find_symbol_definition_line_ignores_preceding_blank_line() -> None:
    text = "\n".join(
        [
            "def is_separable(transform):",
            "    return True",
            "",
            "def separability_matrix(transform):",
            "    return _separable(transform)",
        ]
    )

    line_number = ExternalAdapterRunner._find_symbol_definition_line(text, "separability_matrix")

    assert line_number == 4


def test_external_adapter_runner_normalizes_error_only_payload_as_blocked_envelope() -> None:
    runner = ExternalAdapterRunner()

    payload, repaired = runner._normalize_adapter_payload(json.dumps({"result": "", "error": "TimeoutError: timed out"}))

    assert repaired is False
    assert payload is not None
    assert payload["status"] == "blocked"
    assert payload["failure_classification"] == "timeout"
    assert payload["report"]["status"] == "blocked"
    assert payload["report"]["summary"] == "TimeoutError: timed out"


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
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "target_command_runtime_seconds": 1200,
            "target_file_transfer_quota_mb": 1024,
            "session_recording_required": True,
            "session_recording_enabled": True,
            "result_collection_contract": {
                "declared_item_count": 2,
                "remote_collectible_item_count": 1,
                "items": [
                    {
                        "local_path": "artifacts/screenshots/boot.png",
                        "remote_path": "/srv/browser-work/artifacts/screenshots/boot.png",
                        "collection_stage": "remote_workspace_artifact",
                        "source_kind": "workspace_artifact",
                        "required": False,
                        "collection_mode": "pull_remote_artifact",
                        "bytes_at_dispatch": None,
                        "present_at_dispatch": False,
                    },
                    {
                        "local_path": "artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                        "remote_path": "/srv/browser-work/artifacts/remote-execution-governance/session-recordings/browser-box.cast",
                        "collection_stage": "remote_session_recording",
                        "source_kind": "session_recording",
                        "required": True,
                        "collection_mode": "pull_remote_artifact",
                        "bytes_at_dispatch": None,
                        "present_at_dispatch": False,
                    },
                ],
            },
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
                "broker_contract": {
                    "require_session_recording": True,
                    "session_recording_enabled": True,
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                    "target_command_runtime_seconds": 1200,
                    "target_file_transfer_quota_mb": 1024,
                },
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
                "execution_request": {
                    "request_id": "remote-exec-1700000000000",
                    "request_status": "ready",
                    "target_id": "browser-box",
                    "selected_target_probe_status": "ready",
                    "availability_diagnostics": {
                        "summary": "GPU Box is ready for governed browser validation.",
                        "has_blockers": False,
                    },
                    "selected_target_requirement_gaps": {},
                    "selected_target_rejected_reasons": [],
                    "transport_mode": "remote_artifact_root",
                    "transport_mode_adapter_status": "ready",
                    "selected_adapter_shipping_modes": [
                        "workspace_relative_sync",
                        "remote_artifact_root",
                        "brokered_sync",
                    ],
                    "common_adapter_shipping_modes": [
                        "workspace_relative_sync",
                        "remote_artifact_root",
                        "brokered_sync",
                    ],
                    "transport_mode_supported_adapter_contract_ids": ["browser_playwright_contract"],
                    "transport_mode_unsupported_adapter_contract_ids": [],
                    "transport_mode_undeclared_adapter_contract_ids": [],
                    "result_collection_contract_status": "ready",
                    "result_collection_blocking_reasons": [],
                    "brokered_result_collection_supported": True,
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                    "target_command_runtime_seconds": 1200,
                    "target_file_transfer_quota_mb": 1024,
                    "execution_request_path": "artifacts/remote-execution-requests/remote-exec-1700000000000/execution-request.json",
                    "approval_binding_path": "artifacts/remote-execution-requests/remote-exec-1700000000000/approval-binding.json",
                    "result_bundle_path": "artifacts/remote-execution-requests/remote-exec-1700000000000/result-bundle.json",
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
        assert state.effective_settings["remote_execution_request"]["request_id"] == "remote-exec-1700000000000"
        assert state.effective_settings["runner_command"] == "python"
        assert state.effective_settings["runner_args"] == []
        assert state.effective_settings["transport_mode"] == "remote_artifact_root"
        assert state.effective_settings["transport_mode_adapter_status"] == "ready"
        assert state.effective_settings["remote_execution_availability_diagnostics"]["summary"] == (
            "GPU Box is ready for governed browser validation."
        )
        assert state.effective_settings["remote_execution_selected_target_requirement_gaps"] == {}
        assert state.effective_settings["remote_execution_selected_target_rejected_reasons"] == []
        assert state.effective_settings["selected_adapter_shipping_modes"] == [
            "workspace_relative_sync",
            "remote_artifact_root",
            "brokered_sync",
        ]
        assert state.effective_settings["result_collection_contract_status"] == "ready"
        assert state.effective_settings["brokered_result_collection_supported"] is True
        assert state.effective_settings["minimum_command_runtime_seconds"] == 900
        assert state.effective_settings["minimum_file_transfer_quota_mb"] == 512
        assert state.effective_settings["target_command_runtime_seconds"] == 1200
        assert state.effective_settings["target_file_transfer_quota_mb"] == 1024
        assert state.effective_settings["remote_artifact_paths"] == ["/srv/browser-work/artifacts/screenshots/boot.png"]
        assert state.effective_settings["result_collection_contract"]["declared_item_count"] == 2
        assert state.effective_settings["session_recording_artifact_paths"] == [
            "artifacts/remote-execution-governance/session-recordings/browser-box.cast"
        ]
        assert state.effective_settings["remote_execution_request_path"] == (
            "artifacts/remote-execution-requests/remote-exec-1700000000000/execution-request.json"
        )
        assert state.quota_enforcement_status == "satisfied"
        assert manifest["target_id"] == "browser-box"
        assert manifest["selected_target_probe_status"] == "ready"
        assert manifest["availability_diagnostics"]["summary"] == (
            "GPU Box is ready for governed browser validation."
        )
        assert manifest["selected_target_requirement_gaps"] == {}
        assert manifest["selected_target_rejected_reasons"] == []
        assert manifest["runner_command"] == "python"
        assert manifest["runner_args"] == []
        assert manifest["minimum_command_runtime_seconds"] == 900
        assert manifest["minimum_file_transfer_quota_mb"] == 512
        assert manifest["target_command_runtime_seconds"] == 1200
        assert manifest["target_file_transfer_quota_mb"] == 1024
        assert manifest["quota_enforcement_status"] == "satisfied"
        assert manifest["result_collection_contract"]["remote_collectible_item_count"] == 1
        assert manifest["execution_request_id"] == "remote-exec-1700000000000"
        assert manifest["execution_request_status"] == "ready"
        assert manifest["transport_mode"] == "remote_artifact_root"
        assert manifest["transport_mode_adapter_status"] == "ready"
        assert manifest["selected_adapter_shipping_modes"] == [
            "workspace_relative_sync",
            "remote_artifact_root",
            "brokered_sync",
        ]
        assert manifest["result_collection_contract_status"] == "ready"
        assert manifest["result_collection_blocking_reasons"] == []
        assert manifest["brokered_result_collection_supported"] is True
        assert manifest["execution_request_path"] == (
            "artifacts/remote-execution-requests/remote-exec-1700000000000/execution-request.json"
        )
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
        assert any(event["type"] == "remote.execution.request" for event in state.events)

    asyncio.run(run_test())


def test_remote_adapter_runner_blocks_on_inconsistent_quota_contract(monkeypatch, tmp_path) -> None:
    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)
    monkeypatch.setattr(
        "codex_runner.remote_adapter_runner.build_remote_launch_plan",
        lambda **kwargs: {
            "preflight_ready": True,
            "target_id": "gpu-box",
            "target_label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "remote_workspace_root": "/srv/shadow",
            "runner_command": "python",
            "runner_args": [],
            "adapter_command": "python",
            "adapter_args": [],
            "allowed_relative_paths": ["src"],
            "allowed_remote_paths": ["/srv/shadow/src"],
            "allowed_repo_roots": ["/srv/shadow"],
            "remote_artifact_paths": [],
            "connector_families": [],
            "minimum_command_runtime_seconds": 900,
            "minimum_file_transfer_quota_mb": 512,
            "target_command_runtime_seconds": 300,
            "target_file_transfer_quota_mb": 128,
            "session_recording_required": False,
            "session_recording_enabled": False,
            "session_recording_artifact_paths": [],
            "remote_session_recording_artifact_paths": [],
            "exec_args": ["ssh", "gpu-box.tailnet.ts.net", "python"],
            "command_preview": "ssh gpu-box.tailnet.ts.net python",
            "blocking_reasons": [],
        },
    )

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote quota validation",
        goal="Stop inconsistent governed remote launches before dispatch.",
        scope="Enforce runtime and transfer ceilings at the runner boundary.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Runner refuses inconsistent quota contracts."],
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
                "broker_contract": {
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                    "target_command_runtime_seconds": 300,
                    "target_file_transfer_quota_mb": 128,
                },
                "launch_package": {
                    "approval_required": False,
                    "approval_status": None,
                    "target_id": "gpu-box",
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                    "target_command_runtime_seconds": 300,
                    "target_file_transfer_quota_mb": 128,
                },
                "execution_request": {
                    "request_id": "remote-exec-bad-quota",
                    "request_status": "ready",
                    "target_id": "gpu-box",
                    "minimum_command_runtime_seconds": 900,
                    "minimum_file_transfer_quota_mb": 512,
                    "target_command_runtime_seconds": 300,
                    "target_file_transfer_quota_mb": 128,
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        with pytest.raises(RuntimeError, match="quota contract is inconsistent"):
            await runner._start_process(context, "Run the governed remote task.")

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


def test_remote_adapter_runner_enforces_runtime_timeout_from_quota_contract(monkeypatch, tmp_path) -> None:
    class FakeStdin:
        def write(self, _data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.stdout = None
            self.stderr = None
            self.returncode = None
            self.terminated = False
            self.killed = False
            self._transport = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(0.05)
            return b"", b""

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            if self.returncode is None:
                self.returncode = -15
            return self.returncode

    spawned: list[FakeProcess] = []

    async def fake_exec(*args, **kwargs):
        process = FakeProcess()
        spawned.append(process)
        return process

    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)
    monkeypatch.setattr(
        "codex_runner.remote_adapter_runner.build_remote_launch_plan",
        lambda **kwargs: {
            "preflight_ready": True,
            "target_id": "gpu-box",
            "target_label": "GPU Box",
            "transport": "tailscale_ssh",
            "host": "gpu-box.tailnet.ts.net",
            "remote_workspace_root": "/srv/shadow",
            "runner_command": "python",
            "runner_args": [],
            "adapter_command": "python",
            "adapter_args": [],
            "allowed_relative_paths": ["src"],
            "allowed_remote_paths": ["/srv/shadow/src"],
            "allowed_repo_roots": ["/srv/shadow"],
            "remote_artifact_paths": [],
            "connector_families": [],
            "minimum_command_runtime_seconds": 1,
            "minimum_file_transfer_quota_mb": 128,
            "target_command_runtime_seconds": 1,
            "target_file_transfer_quota_mb": 256,
            "session_recording_required": False,
            "session_recording_enabled": False,
            "session_recording_artifact_paths": [],
            "remote_session_recording_artifact_paths": [],
            "expected_evidence_categories": [],
            "exec_args": ["ssh", "gpu-box.tailnet.ts.net", "python"],
            "command_preview": "ssh gpu-box.tailnet.ts.net python",
            "blocking_reasons": [],
        },
    )

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote timeout enforcement",
        goal="Terminate remote executions that exceed the governed runtime ceiling.",
        scope="Runner-side enforcement only.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Timed-out remote run is blocked and audited."],
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
                "broker_contract": {
                    "minimum_command_runtime_seconds": 1,
                    "minimum_file_transfer_quota_mb": 128,
                    "target_command_runtime_seconds": 1,
                    "target_file_transfer_quota_mb": 256,
                },
                "launch_package": {
                    "approval_required": False,
                    "approval_status": None,
                    "target_id": "gpu-box",
                    "target_command_runtime_seconds": 1,
                },
                "execution_request": {
                    "request_id": "remote-exec-timeout",
                    "request_status": "ready",
                    "target_id": "gpu-box",
                    "execution_request_path": "artifacts/remote-execution-requests/remote-exec-timeout/execution-request.json",
                    "result_bundle_path": "artifacts/remote-execution-requests/remote-exec-timeout/result-bundle.json",
                    "target_command_runtime_seconds": 1,
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        handle = await runner._start_process(context, "Run the long remote task.")
        state = runner.runs[handle.id]
        state.process_timeout_seconds = 0.01
        state.timeout_summary = "Remote governed runtime ceiling was exceeded."
        assert state.reader_task is not None
        await state.reader_task

        manifest_path = tmp_path / "artifacts" / "remote-execution-governance" / "runtime" / f"{handle.id}-launch-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)

        assert spawned and spawned[0].terminated is True
        assert state.status == "blocked"
        assert state.quota_enforcement_status == "blocked"
        assert "remote_command_runtime_exceeded" in state.quota_blocking_reasons
        assert report is not None
        assert report["status"] == "blocked"
        assert "runtime ceiling" in report["summary"].lower()
        assert manifest["quota_enforcement_status"] == "blocked"
        assert "remote_command_runtime_exceeded" in manifest["quota_blocking_reasons"]
        assert any(event.get("type") == "quota.enforced" for event in events)

    asyncio.run(run_test())


def test_remote_adapter_runner_requires_execution_request_after_launch_package_approval(monkeypatch, tmp_path) -> None:
    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote mutation",
        goal="Dispatch the already approved launch package.",
        scope="Requires an explicit execution request.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Task launched only through a governed execution request."],
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
                    "approval_status": "approved_once",
                    "target_id": "gpu-box",
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        with pytest.raises(RuntimeError, match="requires a brokered execution request"):
            await runner._start_process(context, "Run the approved remote mutation.")

    asyncio.run(run_test())


def test_remote_adapter_runner_blocks_when_execution_request_transport_mode_is_blocked(monkeypatch, tmp_path) -> None:
    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote transport-mode guard",
        goal="Stop dispatch when the request transport mode is blocked.",
        scope="Require explicit adapter shipping-mode support.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Runner refuses blocked transport-mode requests."],
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
                    "approval_required": False,
                    "approval_status": None,
                    "target_id": "gpu-box",
                },
                "execution_request": {
                    "request_id": "remote-exec-transport-mode-blocked",
                    "request_status": "ready",
                    "target_id": "gpu-box",
                    "transport_mode": "remote_artifact_root",
                    "transport_mode_adapter_status": "blocked",
                    "transport_mode_unsupported_adapter_contract_ids": ["linux_host_runtime"],
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        with pytest.raises(RuntimeError, match="transport mode is not supported"):
            await runner._start_process(context, "Run the governed remote task.")

    asyncio.run(run_test())


def test_remote_adapter_runner_blocks_when_execution_request_result_collection_contract_is_blocked(
    monkeypatch, tmp_path
) -> None:
    async def fake_handshake(self, _settings=None) -> bool:
        return True

    monkeypatch.setattr(RemoteAdapterRunner, "handshake", fake_handshake)

    project = Project(id=1, name="Demo", idea="Idea", workspace_path=tmp_path.as_posix(), status="building", runner_mode="cli", manager_mode="auto")
    agent = Agent(id=2, project_id=1, name="Worker", role="Implementation", kind="worker", status="idle", workspace_path=tmp_path.as_posix())
    task = Task(
        id=3,
        project_id=1,
        title="Remote result-collection guard",
        goal="Stop dispatch when the request result collection contract is blocked.",
        scope="Require brokered result pickup support before launch.",
        agent_role="Implementation",
        milestone="Milestone 2",
        allowed_paths_json=["src"],
        forbidden_paths_json=[],
        validation_steps_json=["pytest"],
        success_criteria_json=["Runner refuses blocked result collection contracts."],
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
                    "approval_required": False,
                    "approval_status": None,
                    "target_id": "gpu-box",
                },
                "execution_request": {
                    "request_id": "remote-exec-result-collection-blocked",
                    "request_status": "ready",
                    "target_id": "gpu-box",
                    "result_collection_contract_status": "blocked",
                    "result_collection_blocking_reasons": [
                        "selected_adapter_contract_missing_brokered_result_collection_support"
                    ],
                },
            },
        ),
    )

    async def run_test() -> None:
        runner = RemoteAdapterRunner()
        with pytest.raises(RuntimeError, match="result collection contract is blocked"):
            await runner._start_process(context, "Run the governed remote task.")

    asyncio.run(run_test())


def test_remote_adapter_runner_handshake_uses_project_adapter_command_fallback(monkeypatch) -> None:
    monkeypatch.setattr("codex_runner.external_adapter_runner.shutil.which", lambda command: "C:/Python/python.exe" if command == "python" else None)
    monkeypatch.setattr("codex_runner.remote_adapter_runner.remote_transport_client_available", lambda _transport: True)
    runner = RemoteAdapterRunner()
    settings = RunnerSettings(
        provider="openai_api",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-4.1-mini",
        reasoning_effort="medium",
        adapter_command="python",
        adapter_args=["adapter.py"],
        remote_execution={
            "policy": {"enabled": True, "required_runner_family": "windows_agent_runner"},
            "selection": {"preflight_ready": True},
            "selected_target": {
                "id": "win-agent",
                "transport": "tailscale_ssh",
                "host": "win-agent.tailnet.ts.net",
            },
        },
    )

    async def run_test() -> None:
        assert await runner.handshake(settings) is True

    asyncio.run(run_test())


def test_remote_adapter_runner_handshake_accepts_runner_command_alias(monkeypatch) -> None:
    monkeypatch.setattr("codex_runner.external_adapter_runner.shutil.which", lambda command: "C:/Python/python.exe" if command == "python" else None)
    monkeypatch.setattr("codex_runner.remote_adapter_runner.remote_transport_client_available", lambda _transport: True)
    runner = RemoteAdapterRunner()
    settings = RunnerSettings(
        provider="openai_api",
        sandbox_mode="workspace-write",
        approval_policy="on-request",
        model="gpt-4.1-mini",
        reasoning_effort="medium",
        remote_execution={
            "policy": {"enabled": True, "required_runner_family": "windows_agent_runner"},
            "selection": {"preflight_ready": True},
            "selected_target": {
                "id": "win-agent",
                "transport": "tailscale_ssh",
                "host": "win-agent.tailnet.ts.net",
                "runner_command": "python",
                "runner_args": ["adapter.py"],
            },
        },
    )

    async def run_test() -> None:
        assert await runner.handshake(settings) is True

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


def test_external_adapter_runner_normalizes_nested_legacy_payload() -> None:
    runner = ExternalAdapterRunner()
    payload, repaired = runner._normalize_adapter_payload(
        json.dumps(
            {
                "result": """```json
                {
                  "report": {
                    "agent": "Service Flow Builder",
                    "task_id": "2",
                    "status": "done",
                    "message": "Fixed src/math_utils.py and kept the change scoped.",
                    "edits": [
                      {
                        "file_path": "src/math_utils.py",
                        "content": "def add(a, b):\\n    return a + b\\n"
                      }
                    ]
                  },
                  "validation_commands": ["python -m pytest tests/test_math_utils.py -q"],
                  "task_status": "done"
                }
                ```"""
            }
        )
    )

    assert repaired is True
    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["report"]["status"] == "done"
    assert payload["report"]["summary"] == "Fixed src/math_utils.py and kept the change scoped."
    assert payload["files_changed"] == ["src/math_utils.py"]
    assert payload["tests_run"] == ["python -m pytest tests/test_math_utils.py -q"]
    assert payload["edits"][0]["path"] == "src/math_utils.py"


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


def test_external_adapter_runner_applies_search_replace_edit(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text("alpha\nbeta\ncharlie\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/large_module.py",
                "search": "beta\n",
                "replace": "beta_updated\n",
            }
        ],
    )

    assert applied == ["src/large_module.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == "alpha\nbeta_updated\ncharlie\n"


def test_external_adapter_runner_rejects_ambiguous_search_replace_edit(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text("repeat\nrepeat\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/large_module.py",
                "search": "repeat\n",
                "replace": "updated\n",
            }
        ],
    )

    assert applied == []
    assert any("matched 2 locations" in issue for issue in issues)
    assert target.read_text(encoding="utf-8") == "repeat\nrepeat\n"


def test_external_adapter_runner_rejects_python_syntax_error_edit(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "module.py"
    target.write_text(
        "def helper(value):\n    return value + 1\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/module.py",
                "search": "def helper(value):\n    return value + 1\n",
                "replace": "def helper(value):\nreturn value + 1\n",
            }
        ],
    )

    assert applied == []
    assert any("introduces a Python syntax error" in issue for issue in issues)
    assert target.read_text(encoding="utf-8") == "def helper(value):\n    return value + 1\n"


def test_external_adapter_runner_disambiguates_duplicate_guard_using_exact_repo_anchor(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text(
        "\n".join(
            [
                "def is_separable(transform):",
                "    if transform.n_inputs == 1 and transform.n_outputs > 1:",
                "        return False",
                "",
                "def separability_matrix(transform):",
                "    if transform.n_inputs == 1 and transform.n_outputs > 1:",
                "        return True",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
        task_query_text=(
            "Implementation anchors:\n"
            "- src/large_module.py:5: def separability_matrix(transform):\n"
            "- src/large_module.py:6: if transform.n_inputs == 1 and transform.n_outputs > 1:\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/large_module.py",
                "search": "if transform.n_inputs == 1 and transform.n_outputs > 1:",
                "replace": "if isinstance(transform, CompoundModel) or (transform.n_inputs == 1 and transform.n_outputs > 1):",
            }
        ],
    )

    assert applied == ["src/large_module.py"]
    assert issues == []
    updated = target.read_text(encoding="utf-8")
    assert "def is_separable(transform):\n    if transform.n_inputs == 1 and transform.n_outputs > 1:" in updated
    assert "def separability_matrix(transform):\n    if isinstance(transform, CompoundModel) or (transform.n_inputs == 1 and transform.n_outputs > 1):" in updated


def test_external_adapter_runner_rejects_same_file_helper_call_bypass_rewrite(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "astropy" / "modeling").mkdir(parents=True)
    target = workspace / "astropy" / "modeling" / "separable.py"
    target.write_text(
        "\n".join(
            [
                "def is_separable(transform):",
                "    separable_matrix = _separable(transform)",
                "    return separable_matrix.any()",
                "",
                "def separability_matrix(transform):",
                "    separable_matrix = _separable(transform)",
                "    return separable_matrix",
                "",
                "def _separable(transform):",
                "    return transform",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["astropy/modeling/separable.py"],
        forbidden_paths=[],
        task_query_text=(
            "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.\n"
            "Implementation anchors:\n"
            "- astropy/modeling/separable.py:66: def separability_matrix(transform):\n"
            "- astropy/modeling/separable.py:24: __all__ = [\"is_separable\", \"separability_matrix\"]\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "astropy/modeling/separable.py",
                "search": (
                    "def separability_matrix(transform):\n"
                    "    separable_matrix = _separable(transform)\n"
                    "    return separable_matrix"
                ),
                "replace": (
                    "def separability_matrix(transform):\n"
                    "    separable_matrix = _compute_separability(transform)\n"
                    "    return separable_matrix"
                ),
            }
        ],
    )

    assert applied == []
    assert any("bypasses same-file helper `_separable`" in issue for issue in issues)
    updated = target.read_text(encoding="utf-8")
    assert "def is_separable(transform):\n    separable_matrix = _separable(transform)" in updated
    assert "def separability_matrix(transform):\n    separable_matrix = _separable(transform)" in updated


def test_external_adapter_runner_rejects_renaming_exported_top_level_symbol(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "astropy" / "modeling").mkdir(parents=True)
    target = workspace / "astropy" / "modeling" / "separable.py"
    target.write_text(
        "\n".join(
            [
                "__all__ = [\"is_separable\", \"separability_matrix\"]",
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
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["astropy/modeling/separable.py"],
        forbidden_paths=[],
        task_query_text=(
            "Implementation anchors:\n"
            "- astropy/modeling/separable.py:3: def is_separable(transform):\n"
            "- astropy/modeling/separable.py:6: def separability_matrix(transform):\n"
            "- astropy/modeling/separable.py:1: __all__ = [\"is_separable\", \"separability_matrix\"]\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "astropy/modeling/separable.py",
                "search": "def is_separable(transform):",
                "replace": "def is_compute_separability(transform):",
            }
        ],
    )

    assert applied == []
    assert any("renames anchored or exported top-level symbol(s)" in issue for issue in issues)
    assert "def is_separable(transform):" in target.read_text(encoding="utf-8")


def test_external_adapter_runner_flags_invalid_missing_symbol_blocker_against_live_file(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "astropy" / "modeling").mkdir(parents=True)
    (workspace / "astropy" / "modeling" / "separable.py").write_text(
        "\n".join(
            [
                "def is_separable(transform):",
                "    return True",
                "",
                "def separability_matrix(transform):",
                "    return _separable(transform)",
                "",
                "def _separable(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    runner = ExternalAdapterRunner()
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["astropy/modeling/separable.py"],
        forbidden_paths=[],
        task_query_text=(
            "Issue: Modeling's `separability_matrix` does not compute separability correctly for nested CompoundModels.\n"
            "Implementation anchors:\n"
            "- astropy/modeling/separable.py:4: def separability_matrix(transform):\n"
        ),
    )
    envelope_payload = {
        "status": "blocked",
        "summary": "The target function 'separability_matrix' is missing from the specified path.",
        "blockers": ["The target function 'separability_matrix' is missing from the specified path."],
        "risks": [],
        "failure_classification": None,
    }
    report_payload = {
        "status": "blocked",
        "summary": "The target function 'separability_matrix' is missing from the specified path.",
        "files_changed": [],
        "tests_run": [],
        "blockers": ["The target function 'separability_matrix' is missing from the specified path."],
        "risks": [],
        "recommended_next_task": "Verify the correct path to the function.",
    }

    runner._enforce_live_symbol_presence_contract(state, envelope_payload, report_payload)

    assert any("Invalid missing-symbol blocker" in blocker for blocker in report_payload["blockers"])
    assert "def separability_matrix(transform):" in report_payload["summary"]
    assert report_payload["recommended_next_task"].startswith("Patch the verified live definition")
    assert envelope_payload["failure_classification"] == "invalid_worker_claim"


def test_external_adapter_runner_rejected_boolean_normalization_issue_names_live_helper(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "astropy" / "modeling").mkdir(parents=True)
    target = workspace / "astropy" / "modeling" / "separable.py"
    target.write_text(
        "\n".join(
            [
                "def separability_matrix(transform):",
                "    separable_matrix = _separable(transform)",
                "    separable_matrix = np.where(separable_matrix != 0, True, False)",
                "    return separable_matrix",
                "",
                "def _separable(transform):",
                "    return transform",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["astropy/modeling/separable.py"],
        forbidden_paths=[],
        task_query_text=(
            "Implementation anchors:\n"
            "- astropy/modeling/separable.py:1: def separability_matrix(transform):\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "astropy/modeling/separable.py",
                "search": "separable_matrix = np.where(separable_matrix != 0, True, False)",
                "replace": "separable_matrix = separable_matrix.astype(bool)",
            }
        ],
    )

    assert applied == []
    assert any("Patch the live same-file helper(s) first:" in issue and "`_separable`" in issue for issue in issues)


def test_external_adapter_runner_applies_identical_search_replace_for_bulleted_exact_repo_matches(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text("repeat\nrepeat\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
        task_query_text=(
            "- src/large_module.py:1: repeat\n"
            "- src/large_module.py:2: repeat\n"
            "Keep the replacement identical at both exact repo match sites."
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/large_module.py",
                "search": "repeat\n",
                "replace": "updated\n",
            }
        ],
    )

    assert applied == ["src/large_module.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == "updated\nupdated\n"


def test_external_adapter_runner_infers_benchmark_protected_paths_from_git_status(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "baseline"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
    )
    target.write_text("mutated\n", encoding="utf-8")
    docs_dir = workspace / "mission-control"
    docs_dir.mkdir(parents=True)
    (docs_dir / "TASK_BOARD.md").write_text("task board\n", encoding="utf-8")

    protected_paths = ExternalAdapterRunner._load_benchmark_protected_paths(workspace)

    assert protected_paths == ["tests/expressions/tests.py"]


def test_external_adapter_runner_does_not_recover_direct_edits_to_benchmark_protected_paths(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_order_by_multiline_sql():\n    return 'baseline'\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["tests"],
        forbidden_paths=[],
        scoped_workspace_baseline={
            "tests/expressions/tests.py": target.read_bytes(),
        },
        protected_paths=["tests/expressions/tests.py"],
    )
    target.write_text("def unrelated_change():\n    return 'mutated'\n", encoding="utf-8")

    synthesized, issues = ExternalAdapterRunner._synthesize_scoped_workspace_edits(state)

    assert synthesized == []
    assert any("benchmark-protected path" in issue for issue in issues)


def test_external_adapter_runner_restores_benchmark_protected_paths_from_baseline(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_order_by_multiline_sql():\n    return 'baseline'\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql"],
        forbidden_paths=[],
        scoped_workspace_baseline={
            "tests/expressions/tests.py": target.read_bytes(),
        },
        protected_paths=["tests/expressions/tests.py"],
    )
    target.write_text("def unrelated_change():\n    return 'mutated'\n", encoding="utf-8")

    restored = ExternalAdapterRunner._restore_scoped_workspace_baseline(state)

    assert "tests/expressions/tests.py" in restored
    assert target.read_text(encoding="utf-8") == "def test_order_by_multiline_sql():\n    return 'baseline'\n"


def test_external_adapter_runner_restores_benchmark_protected_paths_even_if_forbidden(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_order_by_multiline_sql():\n    return 'baseline'\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "baseline"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql/compiler.py"],
        forbidden_paths=["tests", "tests/expressions", "tests/expressions/tests.py"],
        scoped_workspace_baseline={
            "tests/expressions/tests.py": target.read_bytes(),
        },
        protected_paths=["tests/expressions/tests.py"],
    )
    target.write_text("def unrelated_change():\n    return 'mutated'\n", encoding="utf-8")

    restored = ExternalAdapterRunner._restore_scoped_workspace_baseline(state)

    assert "tests/expressions/tests.py" in restored
    assert target.read_text(encoding="utf-8") == "def test_order_by_multiline_sql():\n    return 'baseline'\n"


def test_external_adapter_runner_rejects_explicit_edits_to_benchmark_protected_paths(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("baseline\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["tests"],
        forbidden_paths=[],
        protected_paths=["tests/expressions/tests.py"],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "tests/expressions/tests.py",
                "content": "mutated\n",
            }
        ],
    )

    assert applied == []
    assert any("benchmark-protected path" in issue for issue in issues)
    assert target.read_text(encoding="utf-8") == "baseline\n"


def test_benchmark_harness_restores_protected_files_from_baseline_snapshot(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "tests" / "expressions" / "tests.py"
    target.parent.mkdir(parents=True)
    target.write_text("baseline\n", encoding="utf-8")
    patch_text = "\n".join(
        [
            "diff --git a/tests/expressions/tests.py b/tests/expressions/tests.py",
            "--- a/tests/expressions/tests.py",
            "+++ b/tests/expressions/tests.py",
            "@@ -1 +1 @@",
            "-baseline",
            "+baseline",
        ]
    )

    manifest_report = write_benchmark_protected_paths_manifest(workspace, patch_text)
    target.write_text("mutated\n", encoding="utf-8")
    restore_report = restore_workspace_files_from_snapshot(
        workspace,
        {"tests/expressions/tests.py": "baseline\n"},
        ["tests/expressions/tests.py"],
    )

    assert manifest_report["written"] is True
    assert manifest_report["protected_paths"] == ["tests/expressions/tests.py"]
    assert target.read_text(encoding="utf-8") == "baseline\n"
    assert restore_report["restored_files"] == ["tests/expressions/tests.py"]
    assert restore_report["deleted_files"] == []


def test_external_adapter_runner_applies_all_exact_repo_match_occurrences(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "django" / "db" / "models" / "sql").mkdir(parents=True)
    target = workspace / "django" / "db" / "models" / "sql" / "compiler.py"
    target.write_text(
        "\n".join(
            [
                "class SQLCompiler:",
                "    def get_order_by(self):",
                "        without_ordering = self.ordering_parts.search(sql).group(1)",
                "        return without_ordering",
                "",
                "    def get_extra_select(self, order_by, select):",
                "        without_ordering = self.ordering_parts.search(sql).group(1)",
                "        return without_ordering",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql"],
        forbidden_paths=[],
        task_query_text=(
            "Exact repo matches for issue snippets:\n"
            "django/db/models/sql/compiler.py:3: without_ordering = self.ordering_parts.search(sql).group(1)\n"
            "django/db/models/sql/compiler.py:7: without_ordering = self.ordering_parts.search(sql).group(1)\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "django/db/models/sql/compiler.py",
                "search": "without_ordering = self.ordering_parts.search(sql).group(1)",
                "replace": "sql_oneline = ' '.join(sql.split('\\n'))\nwithout_ordering = self.ordering_parts.search(sql_oneline).group(1)",
            }
        ],
    )

    assert applied == ["django/db/models/sql/compiler.py"]
    assert issues == []
    updated_text = target.read_text(encoding="utf-8")
    assert updated_text.count("sql_oneline = ' '.join(sql.split('\\n'))") == 2
    assert updated_text.count("without_ordering = self.ordering_parts.search(sql_oneline).group(1)") == 2


def test_external_adapter_runner_applies_all_exact_repo_match_partial_line_occurrences(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "django" / "db" / "models" / "sql").mkdir(parents=True)
    target = workspace / "django" / "db" / "models" / "sql" / "compiler.py"
    target.write_text(
        "\n".join(
            [
                "class SQLCompiler:",
                "    def get_order_by(self):",
                "        without_ordering = self.ordering_parts.search(sql).group(1)",
                "        return without_ordering",
                "",
                "    def get_extra_select(self, order_by, select):",
                "        without_ordering = self.ordering_parts.search(sql).group(1)",
                "        return without_ordering",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql"],
        forbidden_paths=[],
        task_query_text=(
            "Exact repo matches for issue snippets:\n"
            "django/db/models/sql/compiler.py:3: without_ordering = self.ordering_parts.search(sql).group(1)\n"
            "django/db/models/sql/compiler.py:7: without_ordering = self.ordering_parts.search(sql).group(1)\n"
        ),
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "django/db/models/sql/compiler.py",
                "search": "self.ordering_parts.search(sql).group(1)",
                "replace": "sql_oneline = ' '.join(sql.split('\\n'))\n        without_ordering = self.ordering_parts.search(sql_oneline).group(1)",
            }
        ],
    )

    assert applied == ["django/db/models/sql/compiler.py"]
    assert issues == []
    updated_text = target.read_text(encoding="utf-8")
    assert updated_text.count("sql_oneline = ' '.join(sql.split('\\n'))") == 2
    assert updated_text.count("without_ordering = self.ordering_parts.search(sql_oneline).group(1)") == 2


def test_external_adapter_runner_disambiguates_search_replace_using_query_context(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "django" / "db" / "models" / "sql").mkdir(parents=True)
    target = workspace / "django" / "db" / "models" / "sql" / "compiler.py"
    target.write_text(
        "\n".join(
            [
                "class SQLCompiler:",
                "    def get_order_by(self):",
                "        without_ordering = self.ordering_parts.search(sql)[1]",
                "        return without_ordering",
                "",
                "    def get_extra_select(self, order_by, select):",
                "        without_ordering = self.ordering_parts.search(sql)[1]",
                "        return without_ordering",
                "",
            ]
        ),
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql"],
        forbidden_paths=[],
        task_query_text="Fix SQLCompiler.get_order_by() so multiline RawSQL no longer breaks without_ordering dedupe.",
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "django/db/models/sql/compiler.py",
                "search": "without_ordering = self.ordering_parts.search(sql)[1]",
                "replace": "without_ordering = self.ordering_parts.search(sql_oneline)[1]",
            }
        ],
    )

    assert applied == ["django/db/models/sql/compiler.py"]
    assert issues == []
    updated_text = target.read_text(encoding="utf-8")
    assert "def get_order_by(self):\n        without_ordering = self.ordering_parts.search(sql_oneline)[1]" in updated_text
    assert "def get_extra_select(self, order_by, select):\n        without_ordering = self.ordering_parts.search(sql)[1]" in updated_text


def test_external_adapter_runner_preserves_indentation_for_multiline_search_replace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "module.py"
    target.write_text(
        "def fix(sql):\n"
        "    if sql:\n"
        "        without_ordering = self.ordering_parts.search(sql)[1]\n"
        "        return without_ordering\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/module.py",
                "search": "without_ordering = self.ordering_parts.search(sql)[1]",
                "replace": "sql_oneline = ' '.join(sql.split('\\n'))\nwithout_ordering = self.ordering_parts.search(sql_oneline)[1]",
            }
        ],
    )

    assert applied == ["src/module.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == (
        "def fix(sql):\n"
        "    if sql:\n"
        "        sql_oneline = ' '.join(sql.split('\\n'))\n"
        "        without_ordering = self.ordering_parts.search(sql_oneline)[1]\n"
        "        return without_ordering\n"
    )


def test_external_adapter_runner_normalizes_model_supplied_multiline_indentation(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "module.py"
    target.write_text(
        "def fix(sql):\n"
        "    if sql:\n"
        "        without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        params_hash = make_hashable(params)\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/module.py",
                "search": "without_ordering = self.ordering_parts.search(sql).group(1)",
                "replace": (
                    "if self.ordering_parts.search(sql):\n"
                    "            without_ordering = self.ordering_parts.search(sql).group(1)\n"
                    "        else:\n"
                    "            without_ordering = ''"
                ),
            }
        ],
    )

    assert applied == ["src/module.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == (
        "def fix(sql):\n"
        "    if sql:\n"
        "        if self.ordering_parts.search(sql):\n"
        "            without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        else:\n"
        "            without_ordering = ''\n"
        "        params_hash = make_hashable(params)\n"
    )


def test_external_adapter_runner_matches_multiline_search_replace_with_relaxed_followup_indentation(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "django" / "db" / "models" / "sql").mkdir(parents=True)
    target = workspace / "django" / "db" / "models" / "sql" / "compiler.py"
    target.write_text(
        "def get_order_by(expressions, params):\n"
        "    for expr, is_ref in expressions:\n"
        "        without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        params_hash = make_hashable(params)\n"
        "        result.append((without_ordering, params_hash))\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["django/db/models/sql"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "django/db/models/sql/compiler.py",
                "search": (
                    "without_ordering = self.ordering_parts.search(sql).group(1)\n"
                    "params_hash = make_hashable(params)"
                ),
                "replace": (
                    "if isinstance(sql, RawSQL):\n"
                    "    continue\n"
                    "without_ordering = self.ordering_parts.search(sql).group(1)\n"
                    "params_hash = make_hashable(params)"
                ),
            }
        ],
    )

    assert applied == ["django/db/models/sql/compiler.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == (
        "def get_order_by(expressions, params):\n"
        "    for expr, is_ref in expressions:\n"
        "        if isinstance(sql, RawSQL):\n"
        "            continue\n"
        "        without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        params_hash = make_hashable(params)\n"
        "        result.append((without_ordering, params_hash))\n"
    )


def test_external_adapter_runner_expands_partial_line_multiline_search_replace_to_full_line(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "module.py"
    target.write_text(
        "def fix(sql):\n"
        "    if sql:\n"
        "        without_ordering = self.ordering_parts.search(sql).group(1)\n"
        "        params_hash = make_hashable(params)\n",
        encoding="utf-8",
    )
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/module.py",
                "search": "self.ordering_parts.search(sql).group(1)",
                "replace": "sql_oneline = ' '.join(sql.split('\\n'))\nwithout_ordering = self.ordering_parts.search(sql_oneline).group(1)",
            }
        ],
    )

    assert applied == ["src/module.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == (
        "def fix(sql):\n"
        "    if sql:\n"
        "        sql_oneline = ' '.join(sql.split('\\n'))\n"
        "        without_ordering = self.ordering_parts.search(sql_oneline).group(1)\n"
        "        params_hash = make_hashable(params)\n"
    )


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


def test_external_adapter_runner_rejects_placeholder_full_file_edit(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "settings.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/settings.py",
                "content": "# updated header\n# Rest of the file content...\n",
            }
        ],
    )

    assert applied == []
    assert any("placeholder or truncated full-file edit" in issue for issue in issues)
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_external_adapter_runner_prefers_full_content_when_search_fields_are_blank(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "settings.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/settings.py",
                "content": "VALUE = 2\n",
                "search": "",
                "replace": "",
            }
        ],
    )

    assert applied == ["src/settings.py"]
    assert issues == []
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_external_adapter_runner_rejects_template_full_file_edit(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "settings.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/settings.py",
                "content": "# full updated file contents go here\n",
            }
        ],
    )

    assert applied == []
    assert any("placeholder or truncated full-file edit" in issue for issue in issues)
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"


def test_external_adapter_runner_rejects_suspiciously_destructive_full_file_rewrite(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text("".join(f"line_{index} = {index}\n" for index in range(220)), encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
    )

    applied, issues = ExternalAdapterRunner()._apply_adapter_edits(
        state,
        [
            {
                "path": "src/large_module.py",
                "content": "VALUE = 1\nprint(VALUE)\n",
            }
        ],
    )

    assert applied == []
    assert any("suspiciously destructive full-file rewrite" in issue for issue in issues)
    assert "line_219 = 219" in target.read_text(encoding="utf-8")


def test_external_adapter_runner_recovers_direct_workspace_edits_without_edit_payload(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_direct_edit_no_payload.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "target = pathlib.Path.cwd() / 'src' / 'math_utils.py'",
                "target.write_text('def add(a, b):\\n    return a + b\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change directly in the workspace.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': []",
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
            validation_steps_json=["Keep the change scoped."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == ["src/math_utils.py"]
        assert any("recovered 1 scoped workspace change" in risk.lower() for risk in report["risks"])
        updated = target.read_text(encoding="utf-8")
        assert "return a + b" in updated
        assert "return a - b" not in updated

    asyncio.run(run_test())


def test_external_adapter_runner_recovers_direct_workspace_edits_when_declared_edits_are_unusable(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_direct_edit_bad_payload.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "target = pathlib.Path.cwd() / 'src' / 'math_utils.py'",
                "target.write_text('def add(a, b):\\n    return a + b\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change directly in the workspace.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': [",
                "    {",
                "      'path': 'src/math_utils.py',",
                "      'search': 'return a ... [truncated] ...',",
                "      'replace': 'return a + b'",
                "    }",
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
            validation_steps_json=["Keep the change scoped."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == ["src/math_utils.py"]
        assert any("recovered 1 scoped workspace change" in risk.lower() for risk in report["risks"])
        assert any("returned unusable accepted edits[]" in risk.lower() for risk in report["risks"])
        assert any("search text was not found" in risk.lower() for risk in report["risks"])
        updated = target.read_text(encoding="utf-8")
        assert "return a + b" in updated
        assert "return a - b" not in updated

    asyncio.run(run_test())


def test_external_adapter_runner_restores_workspace_before_applying_accepted_edit_payload(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_direct_edit_with_patch.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "target = pathlib.Path.cwd() / 'src' / 'math_utils.py'",
                "target.write_text('def add(a, b):\\n    return a * b\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': ['python -m pytest tests/test_math_utils.py -q'],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/math_utils.py', 'search': 'return a - b', 'replace': 'return a + b'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "mission-control").mkdir(parents=True)
    (workspace / "mission-control" / "AGENTS.md").write_text("# guidance\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()
    target = workspace / "src" / "math_utils.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests" / "test_math_utils.py").write_text(
        "\n".join(
            [
                "from src.math_utils import add",
                "",
                "def test_add():",
                "    assert add(1, 2) == 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal=(
                "Reproduce and clear the failing validation command: python -m pytest tests/test_math_utils.py -q. "
                "Rerun focused validation before calling this done."
            ),
            scope="Make the smallest safe code fix and rerun the focused validation command.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
            success_criteria_json=["The implementation matches the expected behavior."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == ["src/math_utils.py"]
        assert any("discarded 1 unvetted direct workspace change" in risk.lower() for risk in report["risks"])
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

    asyncio.run(run_test())


def test_external_adapter_runner_reverts_destructive_direct_edit_when_full_file_rewrite_is_rejected(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_destructive_direct_rewrite.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "target = pathlib.Path.cwd() / 'src' / 'large_module.py'",
                "target.write_text('VALUE = 1\\nprint(VALUE)\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Fixed the implementation.',",
                "    'files_changed': ['src/large_module.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/large_module.py', 'content': 'VALUE = 1\\nprint(VALUE)\\n'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "large_module.py"
    target.write_text("".join(f"line_{index} = {index}\n" for index in range(220)), encoding="utf-8")

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
            validation_steps_json=["Keep the change scoped."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "needs_review"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == []
        assert any("suspiciously destructive full-file rewrite" in risk for risk in report["risks"])
        assert "line_219 = 219" in target.read_text(encoding="utf-8")

    asyncio.run(run_test())


def test_external_adapter_runner_reverts_forbidden_direct_git_edit_before_applying_allowed_edit(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_forbidden_git_edit.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "workspace = pathlib.Path.cwd()",
                "(workspace / 'tests' / 'expressions').mkdir(parents=True, exist_ok=True)",
                "(workspace / 'tests' / 'expressions' / 'tests.py').write_text('BROKEN = True\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the smallest safe fix.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/math_utils.py', 'search': 'return a - b', 'replace': 'return a + b'}",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding='utf-8',
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "tests" / "expressions").mkdir(parents=True)
    target = workspace / "src" / "math_utils.py"
    forbidden = workspace / "tests" / "expressions" / "tests.py"
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    forbidden.write_text("ORIGINAL = True\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Test Runner", "-c", "user.email=test@example.com", "commit", "-m", "baseline"],
        cwd=str(workspace),
        check=True,
        capture_output=True,
        text=True,
    )

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal="Correct the broken behavior.",
            scope="Update only the src implementation.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=["tests", "tests/expressions/tests.py"],
            validation_steps_json=["Keep the change scoped."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
        assert forbidden.read_text(encoding="utf-8") == "ORIGINAL = True\n"
        assert any("discarded 1 unvetted direct workspace change" in risk.lower() for risk in report["risks"])

    asyncio.run(run_test())


def test_external_adapter_runner_prefers_synthesized_workspace_content_when_accepted_edits_drift(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_drifted_edits.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "sys.stdin.read()",
                "target = pathlib.Path.cwd() / 'src' / 'math_utils.py'",
                "target.write_text('def add(a, b):\\n    return a + b\\n', encoding='utf-8')",
                "payload = {",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied a narrow implementation fix.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Re-run focused validation.'",
                "  },",
                "  'edits': [",
                "    {'path': 'src/math_utils.py', 'search': 'return a - b', 'replace': 'return a * b'}",
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
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
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
            validation_steps_json=["Keep the change scoped."],
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == ["src/math_utils.py"]
        assert any("final scoped workspace content" in risk.lower() for risk in report["risks"])
        updated_text = target.read_text(encoding="utf-8")
        assert "return a + b" in updated_text
        assert "return a * b" not in updated_text

    asyncio.run(run_test())


def test_external_adapter_runner_restore_scoped_workspace_baseline_preserves_prior_allowed_patch(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    tracked_allowed = workspace / "src" / "target.py"
    tracked_outside = workspace / "README.md"
    tracked_allowed.write_text("original\n", encoding="utf-8")
    tracked_outside.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "init"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=True,
    )

    # Simulate a previously accepted implementation patch that should survive later validation runs.
    tracked_allowed.write_text("accepted patch\n", encoding="utf-8")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
        scoped_workspace_baseline=ExternalAdapterRunner._capture_scoped_workspace_baseline(workspace, ["src"]),
    )

    # Simulate untrusted direct edits during the current run.
    tracked_allowed.write_text("rogue within scope\n", encoding="utf-8")
    tracked_outside.write_text("rogue outside scope\n", encoding="utf-8")

    restored = ExternalAdapterRunner._restore_scoped_workspace_baseline(state)

    assert tracked_allowed.read_text(encoding="utf-8") == "accepted patch\n"
    assert tracked_outside.read_text(encoding="utf-8") == "clean\n"
    assert restored == ["README.md", "src/target.py"]


def test_external_adapter_runner_synthesize_scoped_workspace_edits_ignores_ephemeral_runtime_artifacts(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    cache_dir = workspace / "src" / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "math_utils.cpython-312.pyc").write_bytes(b"compiled")
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        allowed_paths=["src"],
        forbidden_paths=[],
        scoped_workspace_baseline=ExternalAdapterRunner._capture_scoped_workspace_baseline(workspace, ["src"]),
    )

    (cache_dir / "math_utils.cpython-312.pyc").write_bytes(b"updated-compiled")

    synthesized, issues = ExternalAdapterRunner._synthesize_scoped_workspace_edits(state)

    assert synthesized == []
    assert issues == []


def test_external_adapter_runner_restore_out_of_scope_git_changes_ignores_ephemeral_runtime_artifacts(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "init"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=True,
    )
    cache_dir = workspace / "src" / "__pycache__"
    cache_dir.mkdir()
    cache_file = cache_dir / "math_utils.cpython-312.pyc"
    cache_file.write_bytes(b"compiled")

    restored, repo_available = ExternalAdapterRunner._restore_out_of_scope_git_changes(
        workspace,
        allowed_paths=["src/math_utils.py"],
        forbidden_paths=[],
    )

    assert repo_available is True
    assert restored == []
    assert not cache_file.exists()


def test_external_adapter_runner_restore_out_of_scope_git_changes_ignores_mission_control_runtime_artifacts(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(["git", "add", "."], cwd=str(workspace), capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Codex", "-c", "user.email=codex@example.com", "commit", "-m", "init"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        check=True,
    )
    task_board = workspace / "mission-control" / "TASK_BOARD.md"
    task_board.parent.mkdir(parents=True)
    task_board.write_text("runtime task board\n", encoding="utf-8")
    governance = workspace / "artifacts" / "remote-execution-governance" / "normalized-execution-summary.json"
    governance.parent.mkdir(parents=True)
    governance.write_text("{\"status\": \"runtime\"}\n", encoding="utf-8")

    restored, repo_available = ExternalAdapterRunner._restore_out_of_scope_git_changes(
        workspace,
        allowed_paths=["src/math_utils.py"],
        forbidden_paths=[],
    )

    assert repo_available is True
    assert restored == []
    assert not task_board.exists()
    assert not governance.exists()


def test_external_adapter_runner_does_not_flag_ephemeral_validation_cache_as_direct_workspace_edit(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_validation_report.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'report': {",
                "    'agent': 'Validation Specialist',",
                "    'task_id': '3',",
                "    'status': 'blocked',",
                "    'summary': 'Waiting for Mission Control validation.',",
                "    'files_changed': [],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Run the focused validation command.'",
                "  },",
                "  'edits': []",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "src" / "math_utils.py").write_text("VALUE = 1\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Validate the import", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Validation Specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Re-run focused validation and prepare an honest handoff",
            goal="Run the focused validation command and record the result honestly.",
            scope="Validate the current implementation without editing source files.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["src/math_utils.py"],
            forbidden_paths_json=[],
            validation_steps_json=['python -c "import src.math_utils"'],
            success_criteria_json=["Validation evidence is recorded truthfully."],
            estimated_complexity="small",
            dependencies_json=[],
            status="backlog",
            priority=30,
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
            if await runner.get_status(handle.id) in {"done", "needs_review", "blocked"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["files_changed"] == []
        assert all("discarded unvetted direct workspace edits" not in risk.lower() for risk in report["risks"])
        assert report["summary"] == "Mission Control executed the required validation command locally and it passed."

    asyncio.run(run_test())


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


def test_external_adapter_runner_executes_required_validation_command_when_adapter_omits_it(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_validation_skip.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'report': {",
                "    'agent': 'Validation Specialist',",
                "    'task_id': '3',",
                "    'status': 'needs_review',",
                "    'summary': 'Need clearer evidence before editing.',",
                "    'files_changed': [],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': ['Need clearer evidence before editing.'],",
                "    'recommended_next_task': 'Inspect more files.'",
                "  },",
                "  'edits': []",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_math_utils.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Validate the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Validation Specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Run focused regression validation",
            goal="Validate the behavior using the provided regression command.",
            scope="Run the exact test command and report the outcome without editing files.",
            agent_role="Validation Specialist",
            milestone="Milestone 3",
            allowed_paths_json=["tests"],
            forbidden_paths_json=[],
            validation_steps_json=["python -m pytest tests/test_math_utils.py -q"],
            success_criteria_json=["Focused validation command result is captured."],
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
            if await runner.get_status(handle.id) in {"done", "blocked", "needs_review"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["status"] == "done"
        assert report["tests_run"] == ["python -m pytest tests/test_math_utils.py -q"]
        assert report["recommended_next_task"] == "Prepare the final operator handoff."
        assert report["blockers"] == []
        envelope = BaseCodexRunner.try_parse_result_envelope(message)
        assert envelope is not None
        assert envelope["commands_attempted"] == ["python -m pytest tests/test_math_utils.py -q"]
        assert any(
            evidence.get("command") == "python -m pytest tests/test_math_utils.py -q"
            and evidence.get("status") == "passed"
            for evidence in list(envelope.get("evidence") or [])
        )

    asyncio.run(run_test())


def test_external_adapter_runner_required_validation_command_isolates_pythonpath_to_workspace(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    stale_path = tmp_path / "stale"
    stale_path.mkdir()
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        required_validation_commands=["python -m pytest tests/test_math_utils.py -q"],
    )
    envelope_payload: dict[str, object] = {}
    report_payload: dict[str, object] = {}
    observed: dict[str, object] = {}

    def fake_run(*args, **kwargs):
        observed["cwd"] = kwargs.get("cwd")
        observed["env"] = dict(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setenv("PYTHONPATH", stale_path.as_posix())
    monkeypatch.setattr("codex_runner.external_adapter_runner.subprocess.run", fake_run)

    executed = ExternalAdapterRunner._execute_required_validation_command(state, envelope_payload, report_payload)

    assert executed is True
    assert Path(str(observed["cwd"])).resolve() == workspace.resolve()
    env = observed["env"]
    assert isinstance(env, dict)
    assert Path(str(env.get("PYTHONPATH") or "")).resolve() == workspace.resolve()


def test_external_adapter_runner_includes_failure_excerpt_in_validation_retry_summary(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = ExternalAdapterRunState(
        workspace_path=workspace.as_posix(),
        required_validation_commands=["python -m pytest tests/test_math_utils.py -q"],
        editing_expected=True,
    )
    envelope_payload: dict[str, object] = {}
    report_payload: dict[str, object] = {"status": "done", "tests_run": [], "risks": []}

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="sqlite3.OperationalError: near ')': syntax error\nwhile compiling SQLCompiler.get_order_by()\n",
        )

    monkeypatch.setattr("codex_runner.external_adapter_runner.subprocess.run", fake_run)

    executed = ExternalAdapterRunner._execute_required_validation_command(state, envelope_payload, report_payload)

    assert executed is True
    assert report_payload["status"] == "blocked"
    assert "Observed failure excerpt:" in str(report_payload["summary"])
    assert "sqlite3.OperationalError: near ')': syntax error" in str(report_payload["summary"])


def test_external_adapter_runner_executes_required_validation_command_after_applying_edit(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_impl_validation_skip.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'status': 'completed',",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': []",
                "  },",
                "  'edits': [",
                "    {",
                "      'path': 'src/math_utils.py',",
                "      'search': 'return a - b',",
                "      'replace': 'return a + b'",
                "    }",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "mission-control").mkdir(parents=True)
    (workspace / "mission-control" / "AGENTS.md").write_text("# guidance\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_math_utils.py").write_text(
        "\n".join(
            [
                "from src.math_utils import add",
                "",
                "def test_add():",
                "    assert add(1, 2) == 3",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal=(
                "Reproduce and clear the failing validation command: python -m pytest tests/test_math_utils.py -q. "
                "Rerun focused validation before calling this done. Do not report success unless the rerun actually passes."
            ),
            scope="Make the smallest safe code fix and rerun the focused validation command.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure."],
            success_criteria_json=["The implementation matches the expected behavior."],
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
            if await runner.get_status(handle.id) in {"done", "blocked", "needs_review"}:
                break
        assert await runner.get_status(handle.id) == "done"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["status"] == "done"
        assert report["tests_run"] == ["python -m pytest tests/test_math_utils.py -q"]
        target = workspace / "src" / "math_utils.py"
        assert target.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
        envelope = BaseCodexRunner.try_parse_result_envelope(message)
        assert envelope is not None
        assert envelope["commands_attempted"] == ["python -m pytest tests/test_math_utils.py -q"]
        assert any(
            evidence.get("command") == "python -m pytest tests/test_math_utils.py -q"
            and evidence.get("status") == "passed"
            for evidence in list(envelope.get("evidence") or [])
        )

    asyncio.run(run_test())


def test_external_adapter_runner_rewrites_stale_dependency_hint_after_failed_validation_rerun(tmp_path) -> None:
    adapter_script = tmp_path / "adapter_impl_validation_bad_hint.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'status': 'completed',",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': [],",
                "    'recommended_next_task': 'Install missing dependencies and rerun validation.'",
                "  },",
                "  'edits': [",
                "    {",
                "      'path': 'src/math_utils.py',",
                "      'search': 'return a - b',",
                "      'replace': 'return a + b'",
                "    }",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "mission-control").mkdir(parents=True)
    (workspace / "mission-control" / "AGENTS.md").write_text("# guidance\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_math_utils.py").write_text(
        "\n".join(
            [
                "from src.math_utils import add",
                "",
                "def test_add():",
                "    assert add(1, 2) == 4",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal=(
                "Reproduce and clear the failing validation command: python -m pytest tests/test_math_utils.py -q. "
                "Rerun focused validation before calling this done. Do not report success unless the rerun actually passes."
            ),
            scope="Make the smallest safe code fix and rerun the focused validation command.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=["Keep the change scoped to the validated failure."],
            success_criteria_json=["The implementation matches the expected behavior."],
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
            if await runner.get_status(handle.id) in {"done", "blocked", "needs_review"}:
                break
        assert await runner.get_status(handle.id) == "blocked"
        events = await runner.read_events(handle.id)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        report = BaseCodexRunner.try_parse_report(message)
        assert report is not None
        assert report["status"] == "blocked"
        assert report["tests_run"] == ["python -m pytest tests/test_math_utils.py -q"]
        assert "exit code 1" in report["blockers"][0]
        assert report["recommended_next_task"] == (
            "Inspect the failed validation output, repair the implementation, and rerun the focused validation command."
        )

    asyncio.run(run_test())


def test_external_adapter_runner_converts_internal_reconciliation_errors_into_terminal_failure(tmp_path, monkeypatch) -> None:
    adapter_script = tmp_path / "adapter_internal_reconcile_error.py"
    adapter_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "sys.stdin.read()",
                "payload = {",
                "  'status': 'completed',",
                "  'report': {",
                "    'agent': 'Service Flow Builder',",
                "    'task_id': '3',",
                "    'status': 'done',",
                "    'summary': 'Applied the targeted implementation change.',",
                "    'files_changed': ['src/math_utils.py'],",
                "    'tests_run': [],",
                "    'blockers': [],",
                "    'risks': []",
                "  },",
                "  'edits': [",
                "    {",
                "      'path': 'src/math_utils.py',",
                "      'search': 'return a - b',",
                "      'replace': 'return a + b'",
                "    }",
                "  ]",
                "}",
                "print(json.dumps({'result': json.dumps(payload)}))",
            ]
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    (workspace / "mission-control").mkdir(parents=True)
    (workspace / "mission-control" / "AGENTS.md").write_text("# guidance\n", encoding="utf-8")
    (workspace / "src").mkdir()
    (workspace / "src" / "math_utils.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    async def run_test() -> None:
        runner = ExternalAdapterRunner()
        monkeypatch.setattr(
            runner,
            "_apply_adapter_edits",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("forced reconcile failure")),
        )
        project = Project(id=1, name="Demo", idea="Fix the regression", workspace_path=workspace.as_posix(), status="building", runner_mode="auto", manager_mode="auto")
        agent = Agent(id=2, project_id=1, name="Worker", role="Backend specialist", kind="worker", status="idle", workspace_path=workspace.as_posix())
        task = Task(
            id=3,
            project_id=1,
            title="Implement the smallest safe code fix",
            goal="Correct the broken behavior with the smallest safe code change.",
            scope="Update the implementation only.",
            agent_role="Service Flow Builder",
            milestone="Milestone 2",
            allowed_paths_json=["src"],
            forbidden_paths_json=[],
            validation_steps_json=[],
            success_criteria_json=["The implementation matches the expected behavior."],
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
            if await runner.get_status(handle.id) in {"done", "blocked", "needs_review", "error"}:
                break
        assert await runner.get_status(handle.id) == "error"
        events = await runner.read_events(handle.id)
        assert any(event.get("type") == "turn.failed" for event in events)
        message = next(event["item"]["text"] for event in events if event.get("type") == "item.completed")
        envelope = BaseCodexRunner.try_parse_result_envelope(message)
        assert envelope is not None
        assert envelope["status"] == "error"
        assert envelope["failure_classification"] == "runner_bug"
        assert "forced reconcile failure" in envelope["summary"]
        assert Path(handle.logs_path).exists()

    asyncio.run(run_test())
