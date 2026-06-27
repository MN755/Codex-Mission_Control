from __future__ import annotations

import asyncio
import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models import Agent, Project, Task
from usage_tracking import merge_usage_snapshots, usage_snapshot_from_event


@dataclass
class RunnerSettings:
    provider: str = "codex"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "on-request"
    model: str | None = None
    reasoning_effort: str | None = None
    provider_endpoint: str | None = None
    adapter_command: str | None = None
    adapter_args: list[str] = field(default_factory=list)
    remote_execution: dict[str, Any] | None = None


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
    initial_usage: dict[str, Any] | None = None
    latest_usage: dict[str, Any] | None = None


class BaseCodexRunner(ABC):
    runner_type = "base"
    manager_turn_timeout_seconds = 90.0
    manager_turn_poll_interval_seconds = 0.5
    workspace_ignored_entries = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
            ".DS_Store",
            "Thumbs.db",
            "__pycache__",
            "node_modules",
            ".venv",
            "venv",
            ".claude",
            ".codex",
            "mission-control",
            "Microsoft",
        }
    )
    workspace_repo_signals = frozenset(
        {
            ".git",
            "README",
            "README.md",
            "pyproject.toml",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "apps",
            "src",
            "docs",
            "tests",
            "scripts",
        }
    )

    @staticmethod
    def quiet_subprocess_kwargs() -> dict[str, Any]:
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        return {}

    @classmethod
    def _workspace_looks_ready(cls, workspace_path: str | None) -> bool:
        if not workspace_path:
            return False
        root = Path(workspace_path)
        if not root.exists() or not root.is_dir():
            return False
        try:
            entries = list(root.iterdir())
        except OSError:
            return False
        if any(entry.name in cls.workspace_repo_signals for entry in entries):
            return True
        return any(entry.name not in cls.workspace_ignored_entries for entry in entries)

    @classmethod
    def effective_workspace_path(cls, context: RunnerContext) -> str:
        project_workspace = context.project.workspace_path
        agent_workspace = context.agent.workspace_path
        if not agent_workspace:
            return project_workspace
        try:
            if Path(agent_workspace).resolve() == Path(project_workspace).resolve():
                return agent_workspace
        except OSError:
            pass
        if cls._workspace_looks_ready(agent_workspace):
            return agent_workspace
        return project_workspace

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
        deadline = asyncio.get_running_loop().time() + max(
            float(self.manager_turn_timeout_seconds),
            float(self.manager_turn_poll_interval_seconds),
            0.01,
        )
        while True:
            await asyncio.sleep(self.manager_turn_poll_interval_seconds)
            events = await self.read_events(handle.id)
            for event in events:
                if event.get("type") == "thread.started":
                    handle.session_ref = event.get("thread_id")
                usage_snapshot = usage_snapshot_from_event(event)
                if usage_snapshot:
                    handle.latest_usage = merge_usage_snapshots(handle.latest_usage, usage_snapshot)
                if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message":
                    last_payload = event
                elif "text" in event:
                    last_payload = event
            status = await self.get_status(handle.id)
            if status in {"done", "blocked", "needs_review", "error", "stopped"}:
                break
            if asyncio.get_running_loop().time() >= deadline:
                try:
                    await self.stop_run(handle.id)
                except Exception:
                    pass
                raise TimeoutError(
                    f"{self.runner_type} manager turn exceeded {self.manager_turn_timeout_seconds:.0f}s without reaching a terminal status."
                )
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
    def try_parse_result_envelope(cls, text: str | None) -> dict[str, Any] | None:
        payload, _ = cls.try_parse_json_payload(text)
        if not isinstance(payload, dict):
            return None
        candidate = dict(payload)
        nested_result = candidate.get("result")
        if isinstance(nested_result, str):
            nested_payload, _ = cls.try_parse_json_payload(nested_result)
            if isinstance(nested_payload, dict):
                candidate = nested_payload
        report = candidate.get("report")
        if isinstance(report, str):
            parsed_report, _ = cls.try_parse_json_payload(report)
            if isinstance(parsed_report, dict):
                candidate["report"] = parsed_report
                report = parsed_report
        if isinstance(report, dict) and "status" in candidate and "runner_type" in candidate:
            return candidate
        return None

    @classmethod
    def try_parse_report(cls, text: str | None) -> dict[str, Any] | None:
        envelope = cls.try_parse_result_envelope(text)
        if isinstance(envelope, dict) and isinstance(envelope.get("report"), dict):
            return envelope["report"]
        payload, _ = cls.try_parse_json_payload(text)
        if isinstance(payload, dict) and "status" in payload and "summary" in payload:
            return payload
        return None

    @classmethod
    def try_parse_structured_message_payload(cls, text: str | None) -> dict[str, Any] | None:
        payload, _ = cls.try_parse_json_payload(text)
        return payload if isinstance(payload, dict) else None
