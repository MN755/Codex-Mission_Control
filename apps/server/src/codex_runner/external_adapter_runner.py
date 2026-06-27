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
from prompts import RUNNER_RESULT_ENVELOPE_SCHEMA, WORKER_REPORT_SCHEMA, worker_task_prompt
from provider_support import default_label
from usage_tracking import build_prompt_usage_estimate


ADAPTER_EDIT_RESPONSE_SCHEMA = {
    **RUNNER_RESULT_ENVELOPE_SCHEMA,
    "edits": [
        {
            "path": "relative/path/from/workspace",
            "content": "full updated file content",
            "summary": "why this edit exists",
        }
    ],
}


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
    workspace_path: str | None = None
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    applied_edits: list[str] = field(default_factory=list)
    edit_issues: list[str] = field(default_factory=list)
    runtime_manifest_path: str | None = None
    runtime_manifest_payload: dict[str, Any] = field(default_factory=dict)


class ExternalAdapterRunner(BaseCodexRunner):
    runner_type = "external_adapter"

    def __init__(self) -> None:
        self.runs: dict[str, ExternalAdapterRunState] = {}

    @staticmethod
    def _command_available(command: str | None) -> bool:
        normalized = str(command or "").strip()
        if not normalized:
            return False
        return shutil.which(normalized) is not None

    async def handshake(self, settings: RunnerSettings | None = None) -> bool:
        if settings is None or not settings.adapter_command:
            return False
        return self._command_available(settings.adapter_command)

    async def start_task(self, context: RunnerContext) -> RunnerHandle:
        prompt = await asyncio.to_thread(self._build_adapter_prompt, context)
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

    @staticmethod
    def _model_specific_adapter_note(model: str | None) -> str:
        lowered = (model or "").lower()
        if any(marker in lowered for marker in ("qwen", "llama", "gemma", "deepseek-r1")):
            return (
                "Model-specific reminder: weak local models often explain edits in prose instead of emitting them. "
                "Do not do that here. If you report a finished implementation step, include edits[]."
            )
        if "gpt-oss" in lowered or "coder" in lowered or "codestral" in lowered:
            return "Model-specific reminder: prefer a single minimal edit set over speculative cleanup."
        return "Model-specific reminder: stay literal and match the schema exactly."

    @staticmethod
    def _adapter_examples() -> str:
        return (
            "Valid example for a reproduce-or-validate task with no file edits:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Validation Specialist",\n'
            '    "task_id": "1",\n'
            '    "status": "done",\n'
            '    "summary": "Reproduced the failure in tests/test_math_utils.py and isolated src/math_utils.py as the broken path.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": ["pytest tests/test_math_utils.py"],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Implement the smallest safe code fix."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n\n'
            "Valid example when you really changed a file:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "done",\n'
            '    "summary": "Fixed the add function and kept the change scoped.",\n'
            '    "files_changed": ["src/math_utils.py"],\n'
            '    "tests_run": ["pytest tests/test_math_utils.py"],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Re-run focused validation."\n'
            '  },\n'
            '  "edits": [\n'
            '    {\n'
            '      "path": "src/math_utils.py",\n'
            '      "content": "def add(a, b):\\n    return a + b\\n"\n'
            '    }\n'
            '  ]\n'
            '}\n\n'
            "Valid example when you cannot safely complete the task:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "needs_review",\n'
            '    "summary": "I could not determine a safe edit from the available workspace evidence.",\n'
            '    "files_changed": [],\n'
            '    "tests_run": [],\n'
            '    "blockers": [],\n'
            '    "risks": ["Need clearer evidence before editing."],\n'
            '    "recommended_next_task": "Clarify the failing behavior or inspect more files."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n\n'
            "Invalid example that must be rejected:\n"
            '{\n'
            '  "report": {\n'
            '    "agent": "Service Flow Builder",\n'
            '    "task_id": "2",\n'
            '    "status": "done",\n'
            '    "summary": "Fixed the bug.",\n'
            '    "files_changed": ["src/math_utils.py"],\n'
            '    "tests_run": [],\n'
            '    "blockers": [],\n'
            '    "risks": [],\n'
            '    "recommended_next_task": "Run validation."\n'
            '  },\n'
            '  "edits": []\n'
            '}\n'
            "Why invalid: it claims a completed code change without any concrete edit payload."
        )

    def _build_adapter_prompt(self, context: RunnerContext) -> str:
        prompt = worker_task_prompt(
            context.project,
            context.agent,
            context.task,
            context.docs_path,
            context.plan_markdown,
            context.context_pack_markdown,
            provider=context.settings.provider,
            model=context.settings.model,
            reasoning_effort=context.settings.reasoning_effort,
        )
        workspace_snapshot = self._workspace_snapshot_markdown(context)
        model_note = self._model_specific_adapter_note(context.settings.model)
        editing_expected = "yes" if context.task and any(word in " ".join(filter(None, [context.task.title, context.task.goal, context.task.scope])).lower() for word in ("fix", "implement", "correct", "update", "change")) else "no"
        remote_execution_context = self._remote_execution_context_markdown(context)
        return (
            f"{prompt}\n\n"
            "External adapter execution rules:\n"
            "- You may propose file edits only inside the allowed files/areas.\n"
            "- For every changed file, return the full updated file contents.\n"
            "- If you cannot make a safe edit, return no edits and explain why in the report.\n"
            "- Do not claim a code fix unless your edits actually implement it.\n\n"
            f"Editing expected for this task: {editing_expected}\n"
            "- If editing expected is no, do not modify files and keep files_changed empty.\n"
            f"{model_note}\n\n"
            "Return only valid JSON matching this schema exactly:\n"
            f"{json.dumps(ADAPTER_EDIT_RESPONSE_SCHEMA, indent=2)}\n\n"
            f"{self._adapter_examples()}\n\n"
            f"{remote_execution_context}\n\n"
            f"{workspace_snapshot}"
        )

    def _remote_execution_context_markdown(self, context: RunnerContext) -> str:
        remote_execution = dict(getattr(context.settings, "remote_execution", None) or {})
        if not remote_execution:
            return "Remote execution context:\n- Not using a remote execution target for this run."
        selected_target = dict(remote_execution.get("selected_target") or {})
        artifact_contract = dict(remote_execution.get("artifact_contract") or {})
        connector_contract = dict(remote_execution.get("connector_contract") or {})
        broker_contract = dict(remote_execution.get("broker_contract") or {})
        if not selected_target:
            blocking_reasons = list(remote_execution.get("selection", {}).get("blocking_reasons") or [])
            blocking_summary = ", ".join(str(item) for item in blocking_reasons) if blocking_reasons else "no selected target"
            return (
                "Remote execution context:\n"
                "- Remote execution policy is present, but no target is ready for this run.\n"
                f"- Blocking reasons: {blocking_summary}"
            )
        target_label = str(selected_target.get("label") or selected_target.get("id") or "remote-target")
        target_host = str(selected_target.get("host") or "unknown-host")
        target_transport = str(selected_target.get("transport") or "ssh")
        workspace_root = str(selected_target.get("workspace_root") or "").strip()
        artifact_paths = list(artifact_contract.get("local_artifact_paths") or [])
        connector_families = list(connector_contract.get("available_families") or [])
        broker_command_families = list(broker_contract.get("target_command_families") or [])
        broker_toolchains = list(broker_contract.get("target_toolchains") or [])
        broker_path_prefixes = list(broker_contract.get("target_path_prefixes") or [])
        broker_repo_roots = list(broker_contract.get("target_repo_roots") or [])
        lines = [
            "Remote execution context:",
            f"- Target: {target_label} ({target_transport} -> {target_host})",
            f"- Remote workspace root: {workspace_root or 'not declared'}",
            f"- Artifact sync enabled: {'yes' if artifact_contract.get('sync_enabled') else 'no'}",
            f"- Artifact paths discovered locally: {', '.join(str(item) for item in artifact_paths[:6]) if artifact_paths else 'none'}",
            f"- Connector families usable in this lane: {', '.join(str(item) for item in connector_families[:6]) if connector_families else 'none'}",
            f"- Broker command families: {', '.join(str(item) for item in broker_command_families[:6]) if broker_command_families else 'none declared'}",
            f"- Broker toolchains: {', '.join(str(item) for item in broker_toolchains[:6]) if broker_toolchains else 'none declared'}",
            f"- Allowed repo roots: {', '.join(str(item) for item in broker_repo_roots[:6]) if broker_repo_roots else 'none declared'}",
            f"- Allowed path prefixes: {', '.join(str(item) for item in broker_path_prefixes[:6]) if broker_path_prefixes else 'none declared'}",
            f"- Session recording required/enabled: {'yes' if broker_contract.get('require_session_recording') else 'no'}/{'yes' if broker_contract.get('session_recording_enabled') else 'no'}",
        ]
        artifact_blockers = list(artifact_contract.get("blocking_reasons") or [])
        connector_blockers = list(connector_contract.get("blocking_reasons") or [])
        broker_blockers = list(broker_contract.get("blocking_reasons") or [])
        if artifact_blockers:
            lines.append(f"- Artifact blockers: {', '.join(str(item) for item in artifact_blockers)}")
        if connector_blockers:
            lines.append(f"- Connector blockers: {', '.join(str(item) for item in connector_blockers)}")
        if broker_blockers:
            lines.append(f"- Broker blockers: {', '.join(str(item) for item in broker_blockers)}")
        lines.append("- Honor the remote target contract. Do not assume extra artifact roots or connector access beyond what is listed here.")
        return "\n".join(lines)

    def _workspace_snapshot_markdown(self, context: RunnerContext) -> str:
        task = context.task
        if task is None:
            return "Editable workspace snapshot:\n- No task file context was provided."
        root = Path(context.project.workspace_path).resolve()
        allowed = list(task.allowed_paths_json or [])
        if not allowed:
            allowed = ["."]
        lines = ["Editable workspace snapshot:"]
        file_count = 0
        total_chars = 0
        max_files = 12
        max_chars = 32000
        for relative in allowed:
            candidate = (root / relative).resolve() if relative not in {"", "."} else root
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            if not candidate.exists():
                continue
            files = [candidate] if candidate.is_file() else sorted(path for path in candidate.rglob("*") if path.is_file())
            for file_path in files:
                if any(part in {"__pycache__", ".git", "node_modules", ".venv", "venv", "mission-control"} for part in file_path.parts):
                    continue
                try:
                    raw = file_path.read_bytes()
                except OSError:
                    continue
                if b"\x00" in raw:
                    continue
                text = raw.decode("utf-8", errors="ignore")
                if not text.strip():
                    continue
                rel_path = file_path.relative_to(root).as_posix()
                snippet = text[:4000]
                projected = total_chars + len(snippet)
                if file_count >= max_files or projected > max_chars:
                    lines.append("- Additional editable files omitted for brevity.")
                    return "\n".join(lines)
                suffix = "..." if len(text) > len(snippet) else ""
                lines.append(f"\nFILE: {rel_path}\n```text\n{snippet}{suffix}\n```")
                file_count += 1
                total_chars = projected
        if file_count == 0:
            lines.append("- No readable files were found in the allowed paths.")
        return "\n".join(lines)

    @staticmethod
    def _is_worker_report_payload(payload: dict[str, Any] | None) -> bool:
        if not isinstance(payload, dict):
            return False
        return "status" in payload and "summary" in payload

    def _normalize_adapter_payload(self, stdout_text: str) -> tuple[dict[str, Any] | None, bool]:
        outer, repaired = self.try_parse_json_payload(stdout_text)
        if outer is None:
            return None, repaired
        candidate = outer
        result_text = outer.get("result")
        if isinstance(result_text, str):
            inner, repaired_inner = self.try_parse_json_payload(result_text)
            if inner is not None:
                candidate = inner
                repaired = repaired or repaired_inner
        if isinstance(candidate, dict) and self._is_worker_report_payload(candidate.get("report")):
            edits = candidate.get("edits")
            if not isinstance(edits, list):
                edits = []
            normalized = dict(candidate)
            normalized["edits"] = edits
            normalized.setdefault("runner_type", self.runner_type)
            normalized.setdefault("lane", "implementation")
            normalized.setdefault("summary", str(candidate["report"].get("summary") or "Adapter completed."))
            normalized.setdefault("status", "completed" if candidate["report"].get("status") == "done" else "failed")
            normalized.setdefault("files_changed", list(candidate["report"].get("files_changed") or []))
            normalized.setdefault("tests_run", list(candidate["report"].get("tests_run") or []))
            normalized.setdefault("commands_attempted", [])
            normalized.setdefault("evidence", [])
            normalized.setdefault("risks", list(candidate["report"].get("risks") or []))
            normalized.setdefault("blockers", list(candidate["report"].get("blockers") or []))
            normalized.setdefault("diagnostics", [])
            normalized.setdefault("approvals_requested", [])
            normalized.setdefault("recovery_plan", [])
            normalized.setdefault("needs_approval", False)
            normalized.setdefault("metadata_json", {})
            return normalized, repaired
        if self._is_worker_report_payload(candidate):
            return {
                "status": "completed" if candidate.get("status") == "done" else "failed",
                "runner_type": self.runner_type,
                "lane": "implementation",
                "summary": str(candidate.get("summary") or "Adapter completed."),
                "report": candidate,
                "files_changed": list(candidate.get("files_changed") or []),
                "tests_run": list(candidate.get("tests_run") or []),
                "commands_attempted": [],
                "evidence": [],
                "risks": list(candidate.get("risks") or []),
                "blockers": list(candidate.get("blockers") or []),
                "diagnostics": [],
                "approvals_requested": [],
                "recovery_plan": [],
                "edits": [],
                "failure_classification": None,
                "needs_approval": False,
                "metadata_json": {},
            }, repaired
        return None, repaired

    @staticmethod
    def _path_is_allowed(path: str, allowed_paths: list[str], forbidden_paths: list[str]) -> bool:
        normalized = path.strip("/").lower()
        if not normalized:
            return False
        allowed = [item.strip("/").lower() for item in allowed_paths if item.strip()]
        forbidden = [item.strip("/").lower() for item in forbidden_paths if item.strip()]
        if forbidden and any(normalized == item or normalized.startswith(f"{item}/") for item in forbidden):
            return False
        if not allowed:
            return True
        return any(normalized == item or normalized.startswith(f"{item}/") or item == "." for item in allowed)

    def _apply_adapter_edits(self, state: ExternalAdapterRunState, edits: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
        workspace_root = Path(state.workspace_path or "").resolve()
        applied: list[str] = []
        issues: list[str] = []
        for edit in edits:
            if not isinstance(edit, dict):
                issues.append("Encountered a non-object edit entry.")
                continue
            relative_path = str(edit.get("path") or "").strip().replace("\\", "/")
            content = edit.get("content")
            if not relative_path or not isinstance(content, str):
                issues.append("Edit entries must include string path and content values.")
                continue
            if not self._path_is_allowed(relative_path, state.allowed_paths, state.forbidden_paths):
                issues.append(f"Rejected edit outside allowed paths: {relative_path}")
                continue
            target = (workspace_root / relative_path).resolve()
            try:
                target.relative_to(workspace_root)
            except ValueError:
                issues.append(f"Rejected edit outside workspace root: {relative_path}")
                continue
            existing_text: str | None = None
            if target.exists():
                try:
                    existing_text = target.read_text(encoding="utf-8")
                except OSError as exc:
                    issues.append(f"Failed to read existing content for {relative_path}: {exc}")
                    continue
                if existing_text == content:
                    issues.append(f"Rejected no-op edit with unchanged content: {relative_path}")
                    continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                applied.append(relative_path)
            except OSError as exc:
                issues.append(f"Failed to write {relative_path}: {exc}")
        return applied, issues

    def _persist_runtime_manifest(
        self,
        state: ExternalAdapterRunState,
        *,
        envelope_payload: dict[str, Any] | None = None,
        report_payload: dict[str, Any] | None = None,
    ) -> None:
        manifest_path = str(state.runtime_manifest_path or "").strip()
        if not manifest_path:
            return
        payload = dict(state.runtime_manifest_payload or {})
        payload.update(
            {
                "runner_type": self.runner_type,
                "status": state.status,
                "exit_code": state.exit_code,
                "applied_edit_count": len(state.applied_edits),
                "applied_edits": list(state.applied_edits),
                "edit_issue_count": len(state.edit_issues),
                "edit_issues": list(state.edit_issues),
            }
        )
        if isinstance(report_payload, dict):
            payload["report"] = {
                "status": report_payload.get("status"),
                "summary": report_payload.get("summary"),
                "files_changed": list(report_payload.get("files_changed") or []),
                "tests_run": list(report_payload.get("tests_run") or []),
                "blockers": list(report_payload.get("blockers") or []),
                "risks": list(report_payload.get("risks") or []),
            }
        if isinstance(envelope_payload, dict):
            payload["result_envelope"] = {
                "status": envelope_payload.get("status"),
                "summary": envelope_payload.get("summary"),
                "lane": envelope_payload.get("lane"),
                "failure_classification": envelope_payload.get("failure_classification"),
                "needs_approval": bool(envelope_payload.get("needs_approval")),
                "evidence_count": len(list(envelope_payload.get("evidence") or [])),
                "commands_attempted": list(envelope_payload.get("commands_attempted") or []),
                "diagnostics": list(envelope_payload.get("diagnostics") or []),
            }
        target = Path(manifest_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    async def _start_process(self, context: RunnerContext, prompt: str) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("The external adapter command is not configured or is not available on PATH.")
        command = context.settings.adapter_command or ""
        args = [command, *(context.settings.adapter_args or [])]
        run_id = f"adapter-{uuid.uuid4().hex}"
        initial_usage = build_prompt_usage_estimate(prompt)
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        effective_label = default_label(context.settings.provider)
        workdir = self.effective_workspace_path(context)
        state = ExternalAdapterRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            workspace_path=workdir,
            allowed_paths=list(context.task.allowed_paths_json or []) if context.task else [],
            forbidden_paths=list(context.task.forbidden_paths_json or []) if context.task else [],
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model or effective_label,
                "reasoning_effort": context.settings.reasoning_effort or effective_label,
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
                "provider_endpoint": context.settings.provider_endpoint,
                "adapter_command": command,
            },
        )
        self.runs[run_id] = state
        state.events.append({"type": "thread.started", "thread_id": run_id})
        state.events.append({"type": "turn.started", "effective_settings": state.effective_settings})
        env = {
            **os.environ.copy(),
            "MISSION_CONTROL_MODEL": context.settings.model or "",
            "MISSION_CONTROL_REASONING_EFFORT": context.settings.reasoning_effort or "",
            "MISSION_CONTROL_SANDBOX_MODE": context.settings.sandbox_mode,
            "MISSION_CONTROL_APPROVAL_POLICY": context.settings.approval_policy,
            "MISSION_CONTROL_PROVIDER": context.settings.provider,
            "MISSION_CONTROL_PROVIDER_ENDPOINT": context.settings.provider_endpoint or "",
            "MISSION_CONTROL_OLLAMA_ENDPOINT": context.settings.provider_endpoint or "",
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
            **self.quiet_subprocess_kwargs(),
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
            initial_usage=initial_usage,
        )

    async def _consume_process(self, run_id: str, args: list[str]) -> None:
        state = self.runs[run_id]
        assert state.process is not None
        try:
            stdout_bytes, stderr_bytes = await state.process.communicate()
            state.exit_code = state.process.returncode
            stdout_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
            stderr_text = stderr_bytes.decode("utf-8", errors="ignore").strip()
            parsed, repaired = self._normalize_adapter_payload(stdout_text)
            envelope_payload: dict[str, Any] | None = None
            report_payload: dict[str, Any] | None = None
            if parsed:
                envelope_payload = dict(parsed)
                report_payload = dict(envelope_payload.get("report") or {})
                edits = [item for item in (envelope_payload.get("edits") or []) if isinstance(item, dict)]
                applied, issues = self._apply_adapter_edits(state, edits)
                state.applied_edits = applied
                state.edit_issues = issues
                report_payload["files_changed"] = applied if applied or edits else list(report_payload.get("files_changed") or [])
                envelope_payload["files_changed"] = list(report_payload.get("files_changed") or [])
                if issues:
                    report_payload["risks"] = list(report_payload.get("risks") or []) + issues
                    if report_payload.get("status") == "done":
                        report_payload["status"] = "needs_review"
                    if envelope_payload.get("status") == "completed":
                        envelope_payload["status"] = "needs_review"
                    report_payload["summary"] = (
                        f"{report_payload.get('summary') or 'Adapter run completed.'} "
                        "Mission Control rejected or could not apply one or more proposed edits."
                    ).strip()
                envelope_payload["summary"] = str(report_payload.get("summary") or envelope_payload.get("summary") or "Adapter run completed.")
                envelope_payload["report"] = report_payload
                envelope_payload["risks"] = list(report_payload.get("risks") or [])
                envelope_payload["blockers"] = list(report_payload.get("blockers") or [])
                envelope_payload["tests_run"] = list(report_payload.get("tests_run") or [])
                state.final_text = json.dumps(envelope_payload)
            else:
                state.final_text = stdout_text or stderr_text or "External adapter returned no output."
            state.status = "done" if state.exit_code == 0 else "error"
            if report_payload and report_payload.get("status") in {"blocked", "needs_review", "error"}:
                state.status = str(report_payload.get("status"))
            self._persist_runtime_manifest(
                state,
                envelope_payload=envelope_payload,
                report_payload=report_payload,
            )
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
        finally:
            self.finalize_subprocess_state(state)
