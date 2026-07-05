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

    @staticmethod
    def _first_present_int(*values: Any) -> int | None:
        for value in values:
            if value is None or value == "":
                continue
            try:
                normalized = int(value)
            except (TypeError, ValueError):
                continue
            if normalized > 0:
                return normalized
        return None

    def _resolve_remote_quota_contract(
        self,
        *,
        execution_request: dict[str, Any],
        launch_package: dict[str, Any],
        launch_plan: dict[str, Any],
        broker_contract: dict[str, Any],
    ) -> dict[str, int | None]:
        return {
            "minimum_command_runtime_seconds": self._first_present_int(
                execution_request.get("minimum_command_runtime_seconds"),
                launch_package.get("minimum_command_runtime_seconds"),
                launch_plan.get("minimum_command_runtime_seconds"),
                broker_contract.get("minimum_command_runtime_seconds"),
            ),
            "minimum_file_transfer_quota_mb": self._first_present_int(
                execution_request.get("minimum_file_transfer_quota_mb"),
                launch_package.get("minimum_file_transfer_quota_mb"),
                launch_plan.get("minimum_file_transfer_quota_mb"),
                broker_contract.get("minimum_file_transfer_quota_mb"),
            ),
            "target_command_runtime_seconds": self._first_present_int(
                execution_request.get("target_command_runtime_seconds"),
                launch_package.get("target_command_runtime_seconds"),
                launch_plan.get("target_command_runtime_seconds"),
                broker_contract.get("target_command_runtime_seconds"),
            ),
            "target_file_transfer_quota_mb": self._first_present_int(
                execution_request.get("target_file_transfer_quota_mb"),
                launch_package.get("target_file_transfer_quota_mb"),
                launch_plan.get("target_file_transfer_quota_mb"),
                broker_contract.get("target_file_transfer_quota_mb"),
            ),
        }

    def _validate_remote_quota_contract(self, quota_contract: dict[str, int | None]) -> list[str]:
        blocking_reasons: list[str] = []
        minimum_command_runtime_seconds = quota_contract.get("minimum_command_runtime_seconds")
        target_command_runtime_seconds = quota_contract.get("target_command_runtime_seconds")
        minimum_file_transfer_quota_mb = quota_contract.get("minimum_file_transfer_quota_mb")
        target_file_transfer_quota_mb = quota_contract.get("target_file_transfer_quota_mb")
        if minimum_command_runtime_seconds is not None and (
            target_command_runtime_seconds is None or target_command_runtime_seconds < minimum_command_runtime_seconds
        ):
            blocking_reasons.append("remote_command_runtime_quota_mismatch")
        if minimum_file_transfer_quota_mb is not None and (
            target_file_transfer_quota_mb is None or target_file_transfer_quota_mb < minimum_file_transfer_quota_mb
        ):
            blocking_reasons.append("remote_file_transfer_quota_mismatch")
        return blocking_reasons

    @staticmethod
    def _effective_adapter_command(settings) -> str | None:
        remote_execution = dict(getattr(settings, "remote_execution", None) or {})
        execution_request = dict(remote_execution.get("execution_request") or {})
        launch_package = dict(remote_execution.get("launch_package") or {})
        selected_target = dict(remote_execution.get("selected_target") or {})
        return (
            str(execution_request.get("runner_command") or "").strip()
            or str(launch_package.get("runner_command") or "").strip()
            or str(selected_target.get("runner_command") or "").strip()
            or str(execution_request.get("adapter_command") or "").strip()
            or str(launch_package.get("adapter_command") or "").strip()
            or str(selected_target.get("adapter_command") or "").strip()
            or str(getattr(settings, "adapter_command", None) or "").strip()
            or None
        )

    @staticmethod
    def _effective_adapter_args(settings) -> list[str]:
        remote_execution = dict(getattr(settings, "remote_execution", None) or {})
        execution_request = dict(remote_execution.get("execution_request") or {})
        launch_package = dict(remote_execution.get("launch_package") or {})
        selected_target = dict(remote_execution.get("selected_target") or {})
        raw = (
            list(execution_request.get("runner_args") or [])
            or list(launch_package.get("runner_args") or [])
            or list(selected_target.get("runner_args") or [])
            or list(execution_request.get("adapter_args") or [])
            or list(launch_package.get("adapter_args") or [])
            or list(selected_target.get("adapter_args") or [])
            or list(getattr(settings, "adapter_args", None) or [])
        )
        return [str(item) for item in raw if str(item).strip()]

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
        adapter_command = self._effective_adapter_command(settings)
        if not adapter_command:
            return False
        return remote_transport_client_available(str(selected_target.get("transport") or "ssh"))

    async def _start_process(self, context: RunnerContext, prompt: str) -> RunnerHandle:
        if not await self.handshake(context.settings):
            raise RuntimeError("Remote adapter execution is not configured with a reachable target and adapter command.")
        remote_execution = dict(context.settings.remote_execution or {})
        launch_package = dict(remote_execution.get("launch_package") or {})
        execution_request = dict(remote_execution.get("execution_request") or {})
        selected_target = dict(remote_execution.get("selected_target") or {})
        broker_contract = dict(remote_execution.get("broker_contract") or {})
        selected_target_id = str(selected_target.get("id") or "").strip() or None
        adapter_command = self._effective_adapter_command(context.settings) or ""
        adapter_args = self._effective_adapter_args(context.settings)
        target_id = selected_target_id or str(execution_request.get("target_id") or "remote-target")
        approval_required = bool(launch_package.get("approval_required"))
        approval_status = str(launch_package.get("approval_status") or "").strip().lower()
        if approval_required and approval_status not in {"approved_once", "allowed_for_project"}:
            raise RuntimeError(
                "Remote adapter launch package still requires approval before execution can start."
            )
        request_status = str(execution_request.get("request_status") or "").strip().lower()
        request_target_id = str(execution_request.get("target_id") or "").strip() or None
        launch_target_id = str(launch_package.get("target_id") or "").strip() or None
        if launch_package and not execution_request:
            raise RuntimeError(
                "Remote adapter execution requires a brokered execution request before dispatch can start."
            )
        if request_target_id and selected_target_id and request_target_id != selected_target_id:
            raise RuntimeError("Remote execution request target no longer matches the selected remote target.")
        if request_target_id and launch_target_id and request_target_id != launch_target_id:
            raise RuntimeError("Remote execution request target drifted away from the approved launch package.")
        if execution_request and request_status != "ready":
            raise RuntimeError("Remote execution request is not ready for dispatch.")
        if str(execution_request.get("transport_mode_adapter_status") or "").strip().lower() == "blocked":
            raise RuntimeError(
                "Remote execution request transport mode is not supported by the selected adapter contracts."
            )
        if str(execution_request.get("result_collection_contract_status") or "").strip().lower() == "blocked":
            raise RuntimeError("Remote execution request result collection contract is blocked.")
        if str(execution_request.get("transfer_quota_status") or "").strip().lower() == "blocked":
            raise RuntimeError("Remote execution transfer bundle exceeds the governed file-transfer quota.")
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
        quota_contract = self._resolve_remote_quota_contract(
            execution_request=execution_request,
            launch_package=launch_package,
            launch_plan=launch_plan,
            broker_contract=broker_contract,
        )
        quota_blocking_reasons = self._validate_remote_quota_contract(quota_contract)
        if quota_blocking_reasons:
            raise RuntimeError(
                "Remote adapter quota contract is inconsistent: " + ", ".join(quota_blocking_reasons)
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
                "runner_command": adapter_command,
                "runner_args": adapter_args,
                "adapter_command": adapter_command,
                "adapter_args": adapter_args,
                "remote_workspace_root": launch_plan.get("remote_workspace_root"),
                "remote_allowed_paths": list(launch_plan.get("allowed_relative_paths") or []),
                "remote_artifact_paths": list(launch_plan.get("remote_artifact_paths") or []),
                "remote_connector_families": list(launch_plan.get("connector_families") or []),
                "remote_launch_package": launch_package,
                "remote_execution_request": execution_request,
                "remote_launch_approval_required": approval_required,
                "remote_launch_approval_status": approval_status or None,
                "remote_execution_request_id": execution_request.get("request_id"),
                "remote_execution_request_status": request_status or None,
                "remote_execution_request_path": execution_request.get("execution_request_path"),
                "remote_execution_result_bundle_path": execution_request.get("result_bundle_path"),
                "remote_execution_transfer_bundle_path": execution_request.get("transfer_bundle_path"),
                "remote_execution_availability_diagnostics": dict(
                    execution_request.get("availability_diagnostics") or {}
                ),
                "remote_execution_selected_target_requirement_gaps": dict(
                    execution_request.get("selected_target_requirement_gaps") or {}
                ),
                "remote_execution_selected_target_rejected_reasons": list(
                    execution_request.get("selected_target_rejected_reasons") or []
                ),
                "remote_execution_dispatch_status": execution_request.get("dispatch_status"),
                "remote_execution_dispatch_recorded_at": execution_request.get("dispatch_recorded_at"),
                "transport_mode": execution_request.get("transport_mode"),
                "transport_mode_adapter_status": execution_request.get("transport_mode_adapter_status"),
                "selected_adapter_shipping_modes": list(
                    execution_request.get("selected_adapter_shipping_modes") or []
                ),
                "common_adapter_shipping_modes": list(
                    execution_request.get("common_adapter_shipping_modes") or []
                ),
                "transport_mode_supported_adapter_contract_ids": list(
                    execution_request.get("transport_mode_supported_adapter_contract_ids") or []
                ),
                "transport_mode_unsupported_adapter_contract_ids": list(
                    execution_request.get("transport_mode_unsupported_adapter_contract_ids") or []
                ),
                "transport_mode_undeclared_adapter_contract_ids": list(
                    execution_request.get("transport_mode_undeclared_adapter_contract_ids") or []
                ),
                "result_collection_contract_status": execution_request.get("result_collection_contract_status"),
                "result_collection_blocking_reasons": list(
                    execution_request.get("result_collection_blocking_reasons") or []
                ),
                "brokered_result_collection_supported": execution_request.get(
                    "brokered_result_collection_supported"
                ),
                "minimum_command_runtime_seconds": quota_contract.get("minimum_command_runtime_seconds"),
                "minimum_file_transfer_quota_mb": quota_contract.get("minimum_file_transfer_quota_mb"),
                "target_command_runtime_seconds": quota_contract.get("target_command_runtime_seconds"),
                "target_file_transfer_quota_mb": quota_contract.get("target_file_transfer_quota_mb"),
                "estimated_outbound_transfer_bytes": launch_plan.get("estimated_outbound_transfer_bytes"),
                "estimated_outbound_transfer_mb": launch_plan.get("estimated_outbound_transfer_mb"),
                "estimated_total_known_transfer_bytes": launch_plan.get("estimated_total_known_transfer_bytes"),
                "estimated_total_known_transfer_mb": launch_plan.get("estimated_total_known_transfer_mb"),
                "estimated_transfer_within_quota": launch_plan.get("estimated_transfer_within_quota"),
                "result_collection_contract": dict(launch_plan.get("result_collection_contract") or {}),
                "staged_outbound_transfer_bytes": execution_request.get("staged_outbound_transfer_bytes"),
                "staged_outbound_transfer_mb": execution_request.get("staged_outbound_transfer_mb"),
                "staged_outbound_transfer_path_count": execution_request.get("staged_outbound_transfer_path_count"),
                "transfer_quota_status": execution_request.get("transfer_quota_status"),
                "session_recording_required": bool(launch_plan.get("session_recording_required")),
                "session_recording_enabled": bool(launch_plan.get("session_recording_enabled")),
                "session_recording_artifact_paths": list(launch_plan.get("session_recording_artifact_paths") or []),
                "remote_session_recording_artifact_paths": list(
                    launch_plan.get("remote_session_recording_artifact_paths") or []
                ),
            },
        )
        state.process_timeout_seconds = (
            float(quota_contract["target_command_runtime_seconds"])
            if quota_contract.get("target_command_runtime_seconds") is not None
            else None
        )
        state.timeout_summary = (
            f"Remote adapter execution on `{target_id}` exceeded the governed runtime ceiling of "
            f"{quota_contract['target_command_runtime_seconds']}s and was terminated by Mission Control."
            if quota_contract.get("target_command_runtime_seconds") is not None
            else None
        )
        state.quota_contract = {key: value for key, value in quota_contract.items() if value is not None}
        state.quota_enforcement_status = "armed" if state.quota_contract else "not_applicable"
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
            "selected_target_probe_status": execution_request.get("selected_target_probe_status")
            or launch_plan.get("selected_target_probe_status"),
            "availability_diagnostics": dict(execution_request.get("availability_diagnostics") or {}),
            "selected_target_requirement_gaps": dict(
                execution_request.get("selected_target_requirement_gaps") or {}
            ),
            "selected_target_rejected_reasons": list(
                execution_request.get("selected_target_rejected_reasons") or []
            ),
            "runner_command": launch_plan.get("runner_command") or launch_plan.get("adapter_command") or adapter_command,
            "runner_args": list(launch_plan.get("runner_args") or launch_plan.get("adapter_args") or adapter_args),
            "allowed_relative_paths": list(launch_plan.get("allowed_relative_paths") or []),
            "allowed_remote_paths": list(launch_plan.get("allowed_remote_paths") or []),
            "allowed_repo_roots": list(launch_plan.get("allowed_repo_roots") or []),
            "remote_artifact_paths": list(launch_plan.get("remote_artifact_paths") or []),
            "connector_families": list(launch_plan.get("connector_families") or []),
            "minimum_command_runtime_seconds": quota_contract.get("minimum_command_runtime_seconds"),
            "minimum_file_transfer_quota_mb": quota_contract.get("minimum_file_transfer_quota_mb"),
            "target_command_runtime_seconds": quota_contract.get("target_command_runtime_seconds"),
            "target_file_transfer_quota_mb": quota_contract.get("target_file_transfer_quota_mb"),
            "estimated_outbound_transfer_bytes": launch_plan.get("estimated_outbound_transfer_bytes"),
            "estimated_outbound_transfer_mb": launch_plan.get("estimated_outbound_transfer_mb"),
            "estimated_total_known_transfer_bytes": launch_plan.get("estimated_total_known_transfer_bytes"),
            "estimated_total_known_transfer_mb": launch_plan.get("estimated_total_known_transfer_mb"),
            "estimated_transfer_within_quota": launch_plan.get("estimated_transfer_within_quota"),
            "result_collection_contract": dict(launch_plan.get("result_collection_contract") or {}),
            "staged_outbound_transfer_bytes": execution_request.get("staged_outbound_transfer_bytes"),
            "staged_outbound_transfer_mb": execution_request.get("staged_outbound_transfer_mb"),
            "staged_outbound_transfer_path_count": execution_request.get("staged_outbound_transfer_path_count"),
            "transfer_quota_status": execution_request.get("transfer_quota_status"),
            "quota_enforcement_status": state.quota_enforcement_status,
            "launch_approval_required": approval_required,
            "launch_approval_status": approval_status or None,
            "execution_request_id": execution_request.get("request_id"),
            "execution_request_status": request_status or None,
            "execution_request_path": execution_request.get("execution_request_path"),
            "approval_binding_path": execution_request.get("approval_binding_path"),
            "result_bundle_path": execution_request.get("result_bundle_path"),
            "transfer_bundle_path": execution_request.get("transfer_bundle_path"),
            "dispatch_status": execution_request.get("dispatch_status"),
            "dispatch_recorded_at": execution_request.get("dispatch_recorded_at"),
            "transport_mode": execution_request.get("transport_mode"),
            "selected_adapter_shipping_modes": list(execution_request.get("selected_adapter_shipping_modes") or []),
            "common_adapter_shipping_modes": list(execution_request.get("common_adapter_shipping_modes") or []),
            "transport_mode_adapter_status": execution_request.get("transport_mode_adapter_status"),
            "transport_mode_supported_adapter_contract_ids": list(
                execution_request.get("transport_mode_supported_adapter_contract_ids") or []
            ),
            "transport_mode_unsupported_adapter_contract_ids": list(
                execution_request.get("transport_mode_unsupported_adapter_contract_ids") or []
            ),
            "transport_mode_undeclared_adapter_contract_ids": list(
                execution_request.get("transport_mode_undeclared_adapter_contract_ids") or []
            ),
            "result_collection_contract_status": execution_request.get("result_collection_contract_status"),
            "result_collection_blocking_reasons": list(
                execution_request.get("result_collection_blocking_reasons") or []
            ),
            "brokered_result_collection_supported": execution_request.get(
                "brokered_result_collection_supported"
            ),
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
        if execution_request:
            state.events.append(
                {
                    "type": "remote.execution.request",
                    "request": {
                        "request_id": execution_request.get("request_id"),
                        "request_status": request_status or None,
                        "target_id": request_target_id or target_id,
                        "execution_request_path": execution_request.get("execution_request_path"),
                        "approval_binding_path": execution_request.get("approval_binding_path"),
                        "result_bundle_path": execution_request.get("result_bundle_path"),
                        "transfer_bundle_path": execution_request.get("transfer_bundle_path"),
                        "dispatch_status": execution_request.get("dispatch_status"),
                        "dispatch_recorded_at": execution_request.get("dispatch_recorded_at"),
                        "availability_diagnostics": dict(
                            execution_request.get("availability_diagnostics") or {}
                        ),
                        "selected_target_requirement_gaps": dict(
                            execution_request.get("selected_target_requirement_gaps") or {}
                        ),
                        "selected_target_rejected_reasons": list(
                            execution_request.get("selected_target_rejected_reasons") or []
                        ),
                        "transport_mode": execution_request.get("transport_mode"),
                        "transport_mode_adapter_status": execution_request.get(
                            "transport_mode_adapter_status"
                        ),
                        "selected_adapter_shipping_modes": list(
                            execution_request.get("selected_adapter_shipping_modes") or []
                        ),
                        "common_adapter_shipping_modes": list(
                            execution_request.get("common_adapter_shipping_modes") or []
                        ),
                        "result_collection_contract_status": execution_request.get(
                            "result_collection_contract_status"
                        ),
                        "result_collection_blocking_reasons": list(
                            execution_request.get("result_collection_blocking_reasons") or []
                        ),
                        "brokered_result_collection_supported": execution_request.get(
                            "brokered_result_collection_supported"
                        ),
                        "staged_outbound_transfer_bytes": execution_request.get("staged_outbound_transfer_bytes"),
                        "transfer_quota_status": execution_request.get("transfer_quota_status"),
                        "declared_result_collection_count": int(
                            dict(launch_plan.get("result_collection_contract") or {}).get("declared_item_count") or 0
                        ),
                    },
                }
            )
        state.events.append(
            {
                "type": "remote.launch.plan",
                "plan": {
                    "target_id": launch_plan.get("target_id"),
                    "remote_workspace_root": launch_plan.get("remote_workspace_root"),
                    "allowed_relative_paths": list(launch_plan.get("allowed_relative_paths") or []),
                    "allowed_repo_roots": list(launch_plan.get("allowed_repo_roots") or []),
                    "quota_contract": dict(state.quota_contract or {}),
                    "estimated_outbound_transfer_bytes": launch_plan.get("estimated_outbound_transfer_bytes"),
                    "estimated_total_known_transfer_bytes": launch_plan.get("estimated_total_known_transfer_bytes"),
                    "estimated_transfer_within_quota": launch_plan.get("estimated_transfer_within_quota"),
                    "quota_enforcement_status": state.quota_enforcement_status,
                    "launch_approval_required": approval_required,
                    "launch_approval_status": approval_status or None,
                    "result_collection_contract": dict(launch_plan.get("result_collection_contract") or {}),
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
