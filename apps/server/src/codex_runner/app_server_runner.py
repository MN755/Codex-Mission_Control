from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle
from codex_runner.events import parse_json_line
from config import RUNTIME_LOGS_ROOT
from prompts import app_server_input_items, worker_task_prompt
from provider_support import default_label


@dataclass
class AppServerRunState:
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


class AppServerCodexRunner(BaseCodexRunner):
    runner_type = "app_server"

    def __init__(self) -> None:
        self.runs: dict[str, AppServerRunState] = {}

    async def handshake(self, settings=None) -> bool:
        run_id = f"appsvr-handshake-{uuid.uuid4().hex}"
        try:
            process = await asyncio.create_subprocess_exec(
                "codex",
                "app-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **self.quiet_subprocess_kwargs(),
            )
        except OSError:
            return False
        except PermissionError:
            return False
        try:
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(
                (json.dumps({"method": "initialize", "id": 0, "params": {"clientInfo": {"name": "mission_control", "title": "Codex Mission Control", "version": "0.1.0"}}}) + "\n").encode("utf-8")
            )
            process.stdin.write((json.dumps({"method": "initialized", "params": {}}) + "\n").encode("utf-8"))
            await process.stdin.drain()
            line = await asyncio.wait_for(process.stdout.readline(), timeout=5)
            parsed = parse_json_line(line.decode("utf-8", errors="ignore"))
            return bool(parsed and parsed.get("id") == 0)
        except Exception:
            return False
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            transport = getattr(process, "_transport", None)
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = worker_task_prompt(
            context.project,
            context.agent,
            context.task,
            context.docs_path,
            context.plan_markdown,
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        return await self._start_turn(context, prompt, resume=False)

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        return await self._start_turn(context, message, resume=True)

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

    async def _start_turn(self, context: RunnerContext, prompt: str, resume: bool) -> RunnerHandle:
        run_id = f"appsvr-{uuid.uuid4().hex}"
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = AppServerRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
        )
        self.runs[run_id] = state
        process = await asyncio.create_subprocess_exec(
            "codex",
            "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **self.quiet_subprocess_kwargs(),
        )
        state.process = process
        state.reader_task = asyncio.create_task(self._run_protocol(run_id, context, prompt, resume))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
        )

    async def _run_protocol(self, run_id: str, context: RunnerContext, prompt: str, resume: bool) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        process = state.process
        assert process.stdin is not None and process.stdout is not None
        log_lines: list[str] = []
        event_lines: list[str] = []

        async def send(payload: dict) -> None:
            line = json.dumps(payload)
            log_lines.append(f"> {line}")
            process.stdin.write((line + "\n").encode("utf-8"))
            await process.stdin.drain()

        await send(
            {
                "method": "initialize",
                "id": 0,
                "params": {
                    "clientInfo": {
                        "name": "mission_control",
                        "title": "Codex Mission Control",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": False},
                },
            }
        )
        await send({"method": "initialized", "params": {}})

        workdir = context.agent.workspace_path or context.project.workspace_path
        if resume and context.agent.session_ref:
            await send({"method": "thread/resume", "id": 1, "params": {"threadId": context.agent.session_ref, "cwd": workdir}})
        else:
            params = {
                "cwd": workdir,
                "approvalPolicy": "onRequest" if context.settings.approval_policy == "on-request" else context.settings.approval_policy,
                "sandbox": "workspaceWrite" if context.settings.sandbox_mode == "workspace-write" else "readOnly",
                "serviceName": "codex_mission_control",
            }
            if context.settings.model:
                params["model"] = context.settings.model
            await send(
                {
                    "method": "thread/start",
                    "id": 1,
                    "params": params,
                }
            )

        thread_id: str | None = None
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore")
                log_lines.append(f"< {text.rstrip()}")
                parsed = parse_json_line(text)
                if not parsed:
                    continue
                state.events.append(parsed)
                event_lines.append(str(parsed))
                if parsed.get("id") == 1 and parsed.get("result", {}).get("thread", {}).get("id"):
                    thread_id = parsed["result"]["thread"]["id"]
                    state.session_ref = thread_id
                    await send(
                        {
                            "method": "turn/start",
                            "id": 2,
                            "params": {
                                "threadId": thread_id,
                                "input": app_server_input_items(prompt),
                                "cwd": workdir,
                                "metadata": {
                                    "provider": context.settings.provider,
                                    "model": context.settings.model or default_label(context.settings.provider),
                                    "reasoning_effort": context.settings.reasoning_effort or default_label(context.settings.provider),
                                },
                            },
                        }
                    )
                    state.status = "working"
                method = parsed.get("method")
                if method == "item/completed":
                    item = parsed.get("params", {}).get("item", {})
                    if item.get("type") == "agentMessage":
                        state.final_text = item.get("text")
                if method == "turn/completed":
                    turn = parsed.get("params", {}).get("turn", {})
                    state.status = "done" if turn.get("status") == "completed" else "error"
                    break
            returncode = await process.wait()
            state.exit_code = returncode
            if returncode != 0 and state.status not in {"done", "stopped"}:
                state.status = "error"
            Path(state.logs_path or "").write_text("\n".join(log_lines), encoding="utf-8")
            Path(state.stdout_path or "").write_text("\n".join(line[2:] for line in log_lines if line.startswith("< ")), encoding="utf-8")
            Path(state.stderr_path or "").write_text("", encoding="utf-8")
            Path(state.event_log_path or "").write_text("\n".join(event_lines), encoding="utf-8")
        finally:
            self.finalize_subprocess_state(state)
