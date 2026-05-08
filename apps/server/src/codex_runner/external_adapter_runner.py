from __future__ import annotations

import asyncio
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle, RunnerSettings
from config import RUNTIME_LOGS_ROOT
from prompts import worker_task_prompt
from provider_support import default_label


@dataclass
class ExternalAdapterRunState:
    process: asyncio.subprocess.Process | None = None
    status: str = "starting"
    events: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    logs_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    final_text: str | None = None
    reader_task: asyncio.Task | None = None
    exit_code: int | None = None
    effective_settings: dict[str, Any] = field(default_factory=dict)


class ExternalAdapterRunner(BaseCodexRunner):
    runner_type = "external_adapter"

    def __init__(self) -> None:
        self.runs: dict[str, ExternalAdapterRunState] = {}

    async def handshake(self, settings: RunnerSettings | None = None) -> bool:
        if settings is None or not settings.adapter_command:
            return False
        command = settings.adapter_command.strip()
        return bool(command and shutil.which(command))

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = worker_task_prompt(context.project, context.agent, context.task, context.docs_path, context.plan_markdown)
        return await self._start_process(context, prompt)

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        return await self._start_process(context, message)

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

    async def _start_process(self, context: RunnerContext, prompt: str) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("The external adapter command is not configured or is not available on PATH.")
        command = context.settings.adapter_command or ""
        args = [command, *(context.settings.adapter_args or [])]
        run_id = f"adapter-{uuid.uuid4().hex}"
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        effective_label = default_label(context.settings.provider)
        state = ExternalAdapterRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or effective_label,
                "reasoning_effort": context.settings.reasoning_effort or effective_label,
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
                "adapter_command": command,
            },
        )
        self.runs[run_id] = state
        state.events.append({"type": "thread.started", "thread_id": run_id})
        state.events.append({"type": "turn.started", "effective_settings": state.effective_settings})
        workdir = context.agent.workspace_path or context.project.workspace_path
        env = {
            **os.environ.copy(),
            "MISSION_CONTROL_MODEL": context.settings.model or "",
            "MISSION_CONTROL_REASONING_EFFORT": context.settings.reasoning_effort or "",
            "MISSION_CONTROL_SANDBOX_MODE": context.settings.sandbox_mode,
            "MISSION_CONTROL_APPROVAL_POLICY": context.settings.approval_policy,
            "MISSION_CONTROL_PROVIDER": context.settings.provider,
            "MISSION_CONTROL_DOCS_PATH": context.docs_path,
            "MISSION_CONTROL_PROJECT_NAME": context.project.name,
            "MISSION_CONTROL_PROJECT_WORKSPACE": context.project.workspace_path,
            "MISSION_CONTROL_AGENT_NAME": context.agent.name,
            "MISSION_CONTROL_AGENT_ROLE": context.agent.role,
            "MISSION_CONTROL_TASK_ID": str(context.task.id if context.task else ""),
        }
        state.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
            env=env,
        )
        assert state.process.stdin is not None
        state.process.stdin.write(prompt.encode("utf-8"))
        await state.process.stdin.drain()
        state.process.stdin.close()
        state.reader_task = asyncio.create_task(self._consume_process(run_id, args))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
        )

    async def _consume_process(self, run_id: str, args: list[str]) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        stdout_bytes, stderr_bytes = await state.process.communicate()
        state.exit_code = state.process.returncode
        stdout_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
        parsed, repaired = self.try_parse_json_payload(stdout_text)
        if parsed:
            result_text = parsed.get("result")
            if not isinstance(result_text, str):
                result_text = json.dumps(parsed)
            state.final_text = result_text
        else:
            state.final_text = stdout_text or stderr_text or "External adapter returned no output."
        state.status = "done" if state.exit_code == 0 else "error"
        state.events.append(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": state.final_text},
                "effective_settings": state.effective_settings,
                "repaired_json": repaired,
            }
        )
        state.events.append({"type": "turn.completed" if state.status == "done" else "turn.failed"})
        Path(state.logs_path or "").write_text(
            "\n".join(
                [
                    f"command: {' '.join(args)}",
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
