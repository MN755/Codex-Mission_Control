from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_runner.base import BaseCodexRunner, RunnerContext, RunnerHandle
from config import RUNTIME_LOGS_ROOT
from prompts import worker_task_prompt


@dataclass
class DryRunState:
    status: str = "starting"
    events: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0
    logs_path: str | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    final_text: str | None = None
    task: asyncio.Task | None = None
    exit_code: int | None = None


class DryRunRunner(BaseCodexRunner):
    runner_type = "dry_run"

    def __init__(self) -> None:
        self.runs: dict[str, DryRunState] = {}

    async def handshake(self) -> bool:
        return True

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        run_id = f"dry-{uuid.uuid4().hex}"
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = DryRunState(logs_path=str(logs_path), stdout_path=str(stdout_path), stderr_path=str(stderr_path), event_log_path=str(event_log_path))
        self.runs[run_id] = state
        state.task = asyncio.create_task(self._simulate_task(run_id, context))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
        )

    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        run_id = f"dry-manager-{uuid.uuid4().hex}"
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = DryRunState(logs_path=str(logs_path), stdout_path=str(stdout_path), stderr_path=str(stderr_path), event_log_path=str(event_log_path))
        self.runs[run_id] = state
        state.task = asyncio.create_task(self._simulate_manager(run_id, context, message))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
        )

    async def stop_run(self, run_id: str) -> None:
        state = self.runs.get(run_id)
        if not state:
            return
        if state.task:
            state.task.cancel()
        state.status = "stopped"
        state.events.append({"type": "turn.stopped", "text": "Dry-run task stopped."})

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

    async def _simulate_task(self, run_id: str, context: RunnerContext) -> None:
        state = self.runs[run_id]
        prompt_preview = worker_task_prompt(context.project, context.agent, context.task, context.docs_path, context.plan_markdown) if context.task else ""
        Path(state.logs_path or "").write_text(prompt_preview, encoding="utf-8")
        state.events.append({"type": "thread.started", "thread_id": run_id})
        await asyncio.sleep(0.4)
        state.status = "working"
        state.events.append(
            {
                "type": "turn.started",
                "message": "Dry-run worker started.",
                "effective_settings": {
                    "model": context.settings.model or "Codex default",
                    "reasoning_effort": context.settings.reasoning_effort or "Codex default",
                    "sandbox_mode": context.settings.sandbox_mode,
                    "approval_policy": context.settings.approval_policy,
                },
            }
        )
        await asyncio.sleep(0.8)
        state.events.append({"type": "item.completed", "item": {"type": "agent_message", "text": f"{context.agent.name} is working on {context.task.title if context.task else 'manager turn'}."}})
        await asyncio.sleep(1.1)
        report = {
            "agent": context.agent.name,
            "task_id": str(context.task.id if context.task else "manager"),
            "status": "done",
            "summary": f"Simulated completion for {context.task.title if context.task else 'manager task'}.",
            "files_changed": [],
            "tests_run": ["dry-run simulation"],
            "blockers": [],
            "risks": ["Simulated result only"],
            "recommended_next_task": "Move the next backlog item into working state.",
        }
        state.final_text = json.dumps(report)
        state.status = "done"
        state.exit_code = 0
        state.events.append({"type": "item.completed", "item": {"type": "agent_message", "text": state.final_text}})
        state.events.append({"type": "turn.completed", "usage": {"simulated": True}})
        Path(state.logs_path or "").write_text(
            f"{prompt_preview}\n\nFinal:\n{state.final_text}\n",
            encoding="utf-8",
        )
        Path(state.stdout_path or "").write_text(state.final_text, encoding="utf-8")
        Path(state.stderr_path or "").write_text("", encoding="utf-8")
        Path(state.event_log_path or "").write_text("\n".join(json.dumps(event) for event in state.events), encoding="utf-8")

    async def _simulate_manager(self, run_id: str, context: RunnerContext, message: str) -> None:
        state = self.runs[run_id]
        Path(state.logs_path or "").write_text(message, encoding="utf-8")
        state.events.append({"type": "thread.started", "thread_id": run_id})
        await asyncio.sleep(0.3)
        state.status = "working"
        state.events.append(
            {
                "type": "turn.started",
                "effective_settings": {
                    "model": context.settings.model or "Codex default",
                    "reasoning_effort": context.settings.reasoning_effort or "Codex default",
                    "sandbox_mode": context.settings.sandbox_mode,
                    "approval_policy": context.settings.approval_policy,
                },
            }
        )
        await asyncio.sleep(0.7)
        final = {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": f"Dry-run manager response: {message[:400]}",
            },
        }
        state.events.append(final)
        state.final_text = final["item"]["text"]
        state.status = "done"
        state.exit_code = 0
        state.events.append({"type": "turn.completed", "usage": {"simulated": True}})
        Path(state.stdout_path or "").write_text(state.final_text, encoding="utf-8")
        Path(state.stderr_path or "").write_text("", encoding="utf-8")
        Path(state.event_log_path or "").write_text("\n".join(json.dumps(event) for event in state.events), encoding="utf-8")
