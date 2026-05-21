from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models import Agent, Project, Task


@dataclass
class RunnerSettings:
    provider: str = "codex"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "on-request"
    model: str | None = None
    reasoning_effort: str | None = None
    adapter_command: str | None = None
    adapter_args: list[str] = field(default_factory=list)


@dataclass
class RunnerContext:
    project: Project
    agent: Agent
    task: Task | None
    docs_path: str
    plan_markdown: str | None = None
    context_pack_markdown: str | None = None
    settings: RunnerSettings = field(default_factory=RunnerSettings)


@dataclass
class RunnerHandle:
    id: str
    runner_type: str
    logs_path: str | None
    stdout_path: str | None = None
    stderr_path: str | None = None
    event_log_path: str | None = None
    session_ref: str | None = None


class BaseCodexRunner(ABC):
    runner_type = "base"

    @abstractmethod
    async def handshake(self, settings: RunnerSettings | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        raise NotImplementedError

    @abstractmethod
    async def stop_run(self, run_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def read_events(self, run_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_status(self, run_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def resume_or_continue(self, context: RunnerContext, message: str) -> RunnerHandle:
        raise NotImplementedError

    async def run_manager_turn(self, context: RunnerContext, message: str) -> tuple[RunnerHandle, dict[str, Any] | None]:
        handle = await self.resume_or_continue(context, message)
        last_payload = None
        while True:
            await asyncio.sleep(0.5)
            events = await self.read_events(handle.id)
            for event in events:
                if event.get("type") == "thread.started":
                    handle.session_ref = event.get("thread_id")
                if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message":
                    last_payload = event
                elif "text" in event:
                    last_payload = event
            status = await self.get_status(handle.id)
            if status in {"done", "blocked", "needs_review", "error", "stopped"}:
                break
        return handle, last_payload

    @staticmethod
    def ensure_log_parent(log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def finalize_subprocess_state(state: Any) -> None:
        process = getattr(state, "process", None)
        if process is not None:
            transport = getattr(process, "_transport", None)
            if transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass
        if hasattr(state, "process"):
            state.process = None
        if hasattr(state, "reader_task"):
            state.reader_task = None

    @staticmethod
    def try_parse_json_payload(text: str | None) -> tuple[dict[str, Any] | None, bool]:
        if not text:
            return None, False
        text = text.strip()
        if not text:
            return None, False
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else None, False
        except json.JSONDecodeError:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            match = re.search(r"\{[\s\S]*\}", cleaned)
            candidate = match.group(0) if match else cleaned
            candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
            try:
                payload = json.loads(candidate)
                return payload if isinstance(payload, dict) else None, True
            except json.JSONDecodeError:
                return None, True

    @classmethod
    def try_parse_report(cls, text: str | None) -> dict[str, Any] | None:
        payload, _ = cls.try_parse_json_payload(text)
        return payload
