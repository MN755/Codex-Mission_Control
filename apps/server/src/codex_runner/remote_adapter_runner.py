from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from config import RUNTIME_LOGS_ROOT
from remote_execution import build_remote_launch_plan, remote_transport_client_available

from codex_runner.base import RunnerContext, RunnerHandle
from codex_runner.external_adapter_runner import ExternalAdapterRunState, ExternalAdapterRunner
from usage_tracking import build_prompt_usage_estimate


class RemoteAdapterRunner(ExternalAdapterRunner):
    runner_type = "remote_adapter"

    async def handshake(self, settings=None) -> bool:
        remote_execution = dict(getattr(settings, "remote_execution", None) or {})
        if not remote_execution:
            return False
        selection = dict(remote_execution.get("selection") or {})
        if selection and not bool(selection.get("preflight_ready")):
            return False
        selected_target = remote_execution.get("selected_target") or {}
        if not isinstance(selected_target, dict) or not selected_target:
            return False
        adapter_command = str(selected_target.get("adapter_command") or "").strip()
        if not adapter_command:
            return False
        return remote_transport_client_available(str(selected_target.get("transport") or "ssh"))

    async def _start_process(self, context: RunnerContext, prompt: str) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("Remote adapter execution is not configured with a reachable target and adapter command.")
        remote_execution = dict(context.settings.remote_execution or {})
        launch_package = dict(remote_execution.get("launch_package") or {})
        selected_target = dict(remote_execution.get("selected_target") or {})
        adapter_command = str(selected_target.get("adapter_command") or "").strip()
        adapter_args = list(selected_target.get("adapter_args") or [])
        target_id = str(selected_target.get("id") or "remote-target")
        approval_required = bool(launch_package.get("approval_required"))
        approval_status = str(launch_package.get("approval_status") or "").strip().lower()
        if approval_required and approval_status not in {"approved_once", "allowed_for_project"}:
            raise RuntimeError(
                "Remote adapter launch package still requires approval before execution can start."
            )
        launch_plan = build_remote_launch_plan(
            selected_target=selected_target,
            policy_payload=remote_execution.get("policy"),
            adapter_command=adapter_command,
            adapter_args=adapter_args,
            broker_contract=remote_execution.get("broker_contract"),
            artifact_contract=remote_execution.get("artifact_contract"),
            connector_contract=remote_execution.get("connector_contract"),
            result_contract=remote_execution.get("result_contract"),
            workspace_path=self.effective_workspace_path(context),
            allowed_paths=list(context.task.allowed_paths_json or []) if context.task else None,
            forbidden_paths=list(context.task.forbidden_paths_json or []) if context.task else None,
        )
        if not bool(launch_plan.get("preflight_ready")):
            raise RuntimeError(
                "Remote adapter launch plan is blocked: "
                + ", ".join(str(item) for item in list(launch_plan.get("blocking_reasons") or [])[:6])
            )
        run_id = f"remote-adapter-{uuid.uuid4().hex}"
        initial_usage = build_prompt_usage_estimate(prompt)
        logs_path = RUNTIME_LOGS_ROOT / f"{run_id}.log"
        stdout_path = RUNTIME_LOGS_ROOT / f"{run_id}.stdout.log"
        stderr_path = RUNTIME_LOGS_ROOT / f"{run_id}.stderr.log"
        event_log_path = RUNTIME_LOGS_ROOT / f"{run_id}.events.jsonl"
        self.ensure_log_parent(logs_path)
        state = ExternalAdapterRunState(
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            workspace_path=self.effective_workspace_path(context),
            allowed_paths=list(context.task.allowed_paths_json or []) if context.task else [],
            forbidden_paths=list(context.task.forbidden_paths_json or []) if context.task else [],
            effective_settings={
                "provider": context.settings.provider,
                "model": context.settings.model,
                "reasoning_effort": context.settings.reasoning_effort,
                "sandbox_mode": context.settings.sandbox_mode,
                "approval_policy": context.settings.approval_policy,
                "remote_execution": remote_execution,
                "remote_target_id": target_id,
                "remote_transport": selected_target.get("transport"),
                "remote_host": selected_target.get("host"),
                "adapter_command": adapter_command,
                "adapter_args": adapter_args,
                "remote_workspace_root": launch_plan.get("remote_workspace_root"),
                "remote_allowed_paths": list(launch_plan.get("allowed_relative_paths") or []),
                "remote_artifact_paths": list(launch_plan.get("remote_artifact_paths") or []),
                "remote_connector_families": list(launch_plan.get("connector_families") or []),
                "remote_launch_package": launch_package,
                "remote_launch_approval_required": approval_required,
                "remote_launch_approval_status": approval_status or None,
                "session_recording_required": bool(launch_plan.get("session_recording_required")),
                "session_recording_enabled": bool(launch_plan.get("session_recording_enabled")),
                "session_recording_artifact_paths": list(launch_plan.get("session_recording_artifact_paths") or []),
                "remote_session_recording_artifact_paths": list(
                    launch_plan.get("remote_session_recording_artifact_paths") or []
                ),
            },
        )
        workspace_root = Path(self.effective_workspace_path(context))
        runtime_manifest_path = (
            workspace_root
            / "artifacts"
            / "remote-execution-governance"
            / "runtime"
            / f"{run_id}-launch-manifest.json"
        )
        result_contract = dict(remote_execution.get("result_contract") or {})
        state.runtime_manifest_path = str(runtime_manifest_path)
        state.runtime_manifest_payload = {
            "run_id": run_id,
            "target_id": launch_plan.get("target_id"),
            "target_label": launch_plan.get("target_label"),
            "transport": launch_plan.get("transport"),
            "host": launch_plan.get("host"),
            "remote_workspace_root": launch_plan.get("remote_workspace_root"),
            "allowed_relative_paths": list(launch_plan.get("allowed_relative_paths") or []),
            "allowed_remote_paths": list(launch_plan.get("allowed_remote_paths") or []),
            "allowed_repo_roots": list(launch_plan.get("allowed_repo_roots") or []),
            "remote_artifact_paths": list(launch_plan.get("remote_artifact_paths") or []),
            "connector_families": list(launch_plan.get("connector_families") or []),
            "launch_approval_required": approval_required,
            "launch_approval_status": approval_status or None,
            "session_recording_required": bool(launch_plan.get("session_recording_required")),
            "session_recording_enabled": bool(launch_plan.get("session_recording_enabled")),
            "session_recording_artifact_paths": list(launch_plan.get("session_recording_artifact_paths") or []),
            "remote_session_recording_artifact_paths": list(
                launch_plan.get("remote_session_recording_artifact_paths") or []
            ),
            "expected_evidence_categories": list(result_contract.get("expected_evidence_categories") or []),
            "normalized_summary_artifact": result_contract.get("normalized_summary_artifact"),
            "command_preview": launch_plan.get("command_preview"),
        }
        self._persist_runtime_manifest(state)
        self.runs[run_id] = state
        state.events.append({"type": "thread.started", "thread_id": run_id})
        state.events.append({"type": "turn.started", "effective_settings": state.effective_settings})
        state.events.append(
            {
                "type": "remote.launch.plan",
                "plan": {
                    "target_id": launch_plan.get("target_id"),
                    "remote_workspace_root": launch_plan.get("remote_workspace_root"),
                    "allowed_relative_paths": list(launch_plan.get("allowed_relative_paths") or []),
                    "allowed_repo_roots": list(launch_plan.get("allowed_repo_roots") or []),
                    "launch_approval_required": approval_required,
                    "launch_approval_status": approval_status or None,
                    "session_recording_required": bool(launch_plan.get("session_recording_required")),
                    "session_recording_enabled": bool(launch_plan.get("session_recording_enabled")),
                    "session_recording_artifact_paths": list(
                        launch_plan.get("session_recording_artifact_paths") or []
                    ),
                    "remote_session_recording_artifact_paths": list(
                        launch_plan.get("remote_session_recording_artifact_paths") or []
                    ),
                },
            }
        )
        exec_args = list(launch_plan.get("exec_args") or [])
        env = os.environ.copy()
        state.process = await asyncio.create_subprocess_exec(
            *exec_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            **self.quiet_subprocess_kwargs(),
        )
        assert state.process.stdin is not None
        state.process.stdin.write(prompt.encode("utf-8"))
        await state.process.stdin.drain()
        state.process.stdin.close()
        state.reader_task = asyncio.create_task(self._consume_process(run_id, exec_args))
        return RunnerHandle(
            id=run_id,
            runner_type=self.runner_type,
            logs_path=str(logs_path),
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            event_log_path=str(event_log_path),
            session_ref=target_id,
            initial_usage=initial_usage,
        )
