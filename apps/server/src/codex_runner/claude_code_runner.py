from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_cli_path import claude_command_path
from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle, RunnerSettings
from config import RUNTIME_LOGS_ROOT
from prompts import worker_task_prompt
from provider_support import default_label
from usage_tracking import build_prompt_usage_estimate


def _permission_mode(settings: RunnerSettings) -> str | None:
    if settings.sandbox_mode == "read-only":
        return "plan"
    if settings.approval_policy == "never":
        return "bypassPermissions"
    return "default"


@dataclass
class ClaudeRunState:
    process: asyncio.subprocess.Process | None = None
    status: str = "starting"
    events: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    logs_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    final_text: str | None = None
    session_ref: str | None = None
    reader_task: asyncio.Task | None = None
    exit_code: int | None = None
    cli_version: str | None = None
    effective_settings: dict[str, Any] = field(default_factory=dict)


class ClaudeCodeRunner(BaseCodexRunner):
    runner_type = "claude_code_cli"

    def __init__(self) -> None:
        self.runs: dict[str, ClaudeRunState] = {}
        self.last_cli_version: str | None = None

    async def handshake(self, settings: RunnerSettings | None = None) -> bool:
        cli_path = claude_command_path()
        if cli_path is None:
            self.last_cli_version = None
            return False
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **self.quiet_subprocess_kwargs(),
            )
        except OSError:
            self.last_cli_version = None
            return False
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            self.last_cli_version = (stdout or stderr).decode("utf-8", errors="ignore").strip() or None
        return process.returncode == 0

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = await asyncio.to_thread(
            worker_task_prompt,
            context.project,
            context.agent,
            context.task,
            context.docs_path,
            context.plan_markdown,
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        return await self._start_process(context, prompt, resume=False)

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        return await self._start_process(context, message, resume=True)

    async def stop_run(self, run_id: str) -> None:
        state = self.runs.get(run_id)
        if not state or not state.process:
            return
        state.process.terminate()
        state.status = "stopped"

    async def read_events(self, run_id: str) -> list[dict[str, Any]]:
        state = self.runs.get(run_id)
        if not state:
            return []
        events = state.events[state.cursor :]
        state.cursor = len(state.events)
        return events

    async def get_status(self, run_id: str) -> str:
        state = self.runs.get(run_id)
        return state.status if state else "error"

    def build_exec_args(self, context: RunnerContext, *, resume: bool) -> list[str]:
        cli_path = claude_command_path()
        if cli_path is None:
            raise RuntimeError("Claude Code CLI executable could not be resolved.")
        args = [
            cli_path,
            "-p",
            "Read the full Mission Control task instructions from standard input and follow them exactly. Return only the format requested in those instructions.",
            "--output-format",
            "json",
        ]
        permission_mode = _permission_mode(context.settings)
        if permission_mode:
            args.extend(["--permission-mode", permission_mode])
        if context.settings.model:
            args.extend(["--model", context.settings.model])
        if resume and context.agent.session_ref:
            args.extend(["--resume", context.agent.session_ref])
        return args

    async def _start_process(self, context: RunnerContext, prompt: str, resume: bool) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("Claude Code CLI is not available.")
        run_id = f"claude-{uuid.uuid4().hex}"
        initial_usage = build_prompt_usage_estimate(prompt)
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        effective_label = default_label(context.settings.provider)
        state = ClaudeRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            cli_version=self.last_cli_version,
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or effective_label,
                "reasoning_effort": context.settings.reasoning_effort or effective_label,
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
            },
        )
        self.runs[run_id] = state
        state.events.append({"type": "thread.started", "thread_id": run_id})
        state.events.append({"type": "turn.started", "effective_settings": state.effective_settings})
        workdir = self.effective_workspace_path(context)
        args = self.build_exec_args(context, resume=resume)
        state.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            **self.quiet_subprocess_kwargs(),
        )
        assert state.process.stdin is not None
        state.process.stdin.write(prompt.encode("utf-8"))
        await state.process.stdin.drain()
        state.process.stdin.close()
        state.reader_task = asyncio.create_task(self._consume_process(run_id))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            initial_usage=initial_usage,
        )

    async def _consume_process(self, run_id: str) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        try:
            stdout_bytes, stderr_bytes = await state.process.communicate()
            state.exit_code = state.process.returncode
            stdout_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
            parsed, repaired = self.try_parse_json_payload(stdout_text)
            if parsed:
                session_ref = parsed.get("session_id") or parsed.get("sessionId")
                if isinstance(session_ref, str) and session_ref:
                    state.session_ref = session_ref
                result_text = parsed.get("result")
                if not isinstance(result_text, str):
                    result_text = json.dumps(parsed)
                state.final_text = result_text
                state.status = "done" if state.exit_code == 0 else "error"
                state.events.append(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": result_text},
                        "effective_settings": state.effective_settings,
                        "repaired_json": repaired,
                    }
                )
                state.events.append({"type": "turn.completed" if state.status == "done" else "turn.failed"})
            else:
                state.final_text = stdout_text or stderr_text or "Claude Code returned no output."
                state.status = "done" if state.exit_code == 0 else "error"
                state.events.append(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": state.final_text},
                        "effective_settings": state.effective_settings,
                    }
                )
                state.events.append({"type": "turn.completed" if state.status == "done" else "turn.failed"})

            Path(state.logs_path or "").write_text(
                "\n".join(
                    [
                        f"command: {' '.join(self.build_exec_args_placeholder(state.effective_settings))}",
                        "",
                        stdout_text,
                        "",
                        stderr_text,
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            Path(state.stdout_path or "").write_text(stdout_text, encoding="utf-8")
            Path(state.stderr_path or "").write_text(stderr_text, encoding="utf-8")
            Path(state.event_log_path or "").write_text("\n".join(json.dumps(event) for event in state.events), encoding="utf-8")
        finally:
            self.finalize_subprocess_state(state)

    @staticmethod
    def build_exec_args_placeholder(effective_settings: dict[str, Any]) -> list[str]:
        args = ["claude", "-p", "<mission-control-stdin-prompt>", "--output-format", "json"]
        permission_mode = "plan" if effective_settings.get("sandbox_mode") == "read-only" else (
            "bypassPermissions" if effective_settings.get("approval_policy") == "never" else "default"
        )
        args.extend(["--permission-mode", permission_mode])
        model = effective_settings.get("model")
        if model and "default" not in str(model).lower():
            args.extend(["--model", str(model)])
        return args
