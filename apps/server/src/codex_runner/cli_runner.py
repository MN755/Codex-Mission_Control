from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle
from codex_runner.events import parse_json_line
from codex_cli_path import codex_command_path
from config import RUNTIME_LOGS_ROOT
from prompts import worker_task_prompt
from provider_support import default_label


@dataclass
class CliRunState:
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
    login_status: str | None = None
    effective_settings: dict[str, Any] = field(default_factory=dict)


class CliCodexRunner(BaseCodexRunner):
    runner_type = "codex_cli"

    def __init__(self) -> None:
        self.runs: dict[str, CliRunState] = {}
        self.last_cli_version: str | None = None
        self.last_login_status: str | None = None
        self.last_cli_path: str | None = None

    async def handshake(self, settings=None) -> bool:
        cli_path = codex_command_path()
        self.last_cli_path = cli_path
        if cli_path is None:
            self.last_cli_version = None
            return False
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return False
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            self.last_cli_version = (stdout or stderr).decode("utf-8", errors="ignore").strip() or None
        await self._refresh_login_status()
        return process.returncode == 0

    async def _refresh_login_status(self) -> None:
        cli_path = self.last_cli_path or codex_command_path()
        self.last_cli_path = cli_path
        if cli_path is None:
            self.last_login_status = "Unavailable"
            return
        try:
            process = await asyncio.create_subprocess_exec(
                cli_path,
                "login",
                "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            self.last_login_status = "Unavailable"
            return
        stdout, stderr = await process.communicate()
        self.last_login_status = (stdout or stderr).decode("utf-8", errors="ignore").strip() or "Unavailable"

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = worker_task_prompt(context.project, context.agent, context.task, context.docs_path, context.plan_markdown)
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
        workdir = context.agent.workspace_path or context.project.workspace_path
        cli_path = self.last_cli_path or codex_command_path()
        if cli_path is None:
            raise RuntimeError("Codex CLI resolved path is unavailable.")
        self.last_cli_path = cli_path
        base_args = [cli_path, "exec"]
        if resume and context.agent.session_ref:
            base_args.extend(["resume", context.agent.session_ref])
        base_args.extend(["--json", "--skip-git-repo-check"])
        if context.settings.sandbox_mode:
            base_args.extend(["--sandbox", context.settings.sandbox_mode])
        if context.settings.approval_policy:
            base_args.extend(["-a", context.settings.approval_policy])
        if context.settings.model:
            base_args.extend(["-m", context.settings.model])
        if context.settings.reasoning_effort:
            base_args.extend(["-c", f'model_reasoning_effort="{context.settings.reasoning_effort}"'])
        base_args.extend(["-C", workdir, "-"])
        return base_args

    async def _start_process(self, context: RunnerContext, prompt: str, resume: bool) -> RunnerHandle:
        if not await self.handshake():
            raise RuntimeError("Codex CLI is not available on PATH.")
        run_id = f"cli-{uuid.uuid4().hex}"
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = CliRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            cli_version=self.last_cli_version,
            login_status=self.last_login_status,
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or default_label(context.settings.provider),
                "reasoning_effort": context.settings.reasoning_effort or default_label(context.settings.provider),
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
            },
        )
        self.runs[run_id] = state

        base_args = self.build_exec_args(context, resume=resume)

        state.process = await asyncio.create_subprocess_exec(
            *base_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
        )

    async def _consume_process(self, run_id: str) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        stdout = state.process.stdout
        stderr = state.process.stderr
        log_lines: list[str] = []
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        event_lines: list[str] = []
        if stdout is not None:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore")
                stdout_lines.append(text.rstrip())
                log_lines.append(text.rstrip())
                parsed = parse_json_line(text)
                if not parsed:
                    continue
                event_lines.append(json.dumps(parsed))
                event_type = parsed.get("type", "unknown")
                if event_type == "thread.started":
                    state.session_ref = parsed.get("thread_id")
                if event_type == "turn.started":
                    state.status = "working"
                    parsed["effective_settings"] = state.effective_settings
                if event_type == "turn.completed":
                    state.status = "done"
                if event_type == "turn.failed" or event_type == "error":
                    state.status = "error"
                item = parsed.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    state.final_text = item.get("text")
                state.events.append(parsed)
        stderr_text = ""
        if stderr is not None:
            stderr_text = (await stderr.read()).decode("utf-8", errors="ignore")
            if stderr_text.strip():
                stderr_lines.append(stderr_text.strip())
                log_lines.append(stderr_text.strip())

        returncode = await state.process.wait()
        state.exit_code = returncode
        if state.status == "starting":
            state.status = "done" if returncode == 0 else "error"
        if returncode != 0 and state.status != "stopped":
            state.status = "error"
        Path(state.logs_path or "").write_text("\n".join(log_lines), encoding="utf-8")
        Path(state.stdout_path or "").write_text("\n".join(stdout_lines), encoding="utf-8")
        Path(state.stderr_path or "").write_text("\n".join(stderr_lines), encoding="utf-8")
        Path(state.event_log_path or "").write_text("\n".join(event_lines), encoding="utf-8")
