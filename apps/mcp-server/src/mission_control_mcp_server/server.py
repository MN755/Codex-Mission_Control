from __future__ import annotations

import json
from typing import Any, Callable

from mission_control_mcp_server.catalog import prompt_entries, prompt_entry, resource_entries
from mission_control_mcp_server.client import MissionControlDaemonClient


def _object_schema(
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


GENERIC_OUTPUT_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": True}


class MissionControlMcpServer:
    def __init__(self, client: MissionControlDaemonClient | None = None) -> None:
        self.client = client or MissionControlDaemonClient()
        self._tools = self._build_tool_specs()
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "mission_control_attach_workspace": self._call_attach_workspace,
            "mission_control_start_task": self._call_start_task,
            "mission_control_get_status": self._call_get_status,
            "mission_control_get_pending_decisions": self._call_get_pending_decisions,
            "mission_control_answer_decision": self._call_answer_decision,
            "mission_control_pause": self._call_pause,
            "mission_control_resume": self._call_resume,
            "mission_control_get_handoff": self._call_get_handoff,
            "mission_control_import_existing_codebase": self._call_import_existing_codebase,
            "mission_control_plugin_health": self._call_plugin_health,
            "mission_control_enable_safe_mode": self._call_enable_safe_mode,
            "mission_control_get_event_digest": self._call_get_event_digest,
            "mission_control_get_handoff_summary": self._call_get_handoff_summary,
            "mission_control_generate_agents_md": self._call_generate_agents_md,
            "mission_control_request_snapshot": self._call_request_snapshot,
            "mission_control_request_recovery_plan": self._call_request_recovery_plan,
            "mission_control_get_orchestration_events": self._call_get_orchestration_events,
            "mission_control_get_codebase_map": self._call_get_codebase_map,
            "mission_control_get_codebase_understanding": self._call_get_codebase_understanding,
            "mission_control_set_import_interview_choice": self._call_set_import_interview_choice,
            "mission_control_get_diagnostics": self._call_get_diagnostics,
            "mission_control_get_workspace_tooling": self._call_get_workspace_tooling,
            "mission_control_search_codebase": self._call_search_codebase,
            "mission_control_get_webwright_status": self._call_get_webwright_status,
            "mission_control_get_nvidia_dynamo_status": self._call_get_nvidia_dynamo_status,
            "mission_control_get_nvidia_aiq_status": self._call_get_nvidia_aiq_status,
            "mission_control_run_nvidia_aiq_research": self._call_run_nvidia_aiq_research,
            "mission_control_get_nvidia_gpu_diagnostics": self._call_get_nvidia_gpu_diagnostics,
            "mission_control_get_swarm_plan": self._call_get_swarm_plan,
            "mission_control_update_swarm_preferences": self._call_update_swarm_preferences,
            "mission_control_generate_swarm_plan": self._call_generate_swarm_plan,
            "mission_control_approve_swarm_plan": self._call_approve_swarm_plan,
            "mission_control_get_project_settings": self._call_get_project_settings,
            "mission_control_update_project_settings": self._call_update_project_settings,
            "mission_control_get_import_safety": self._call_get_import_safety,
            "mission_control_update_import_safety": self._call_update_import_safety,
            "mission_control_get_tool_catalog": self._call_get_tool_catalog,
            "mission_control_set_tool_permission": self._call_set_tool_permission,
            "mission_control_get_agents_md_status": self._call_get_agents_md_status,
            "mission_control_propose_agents_md": self._call_propose_agents_md,
            "mission_control_request_recovery_options": self._call_request_recovery_options,
        }

    def _build_tool_specs(self) -> list[dict[str, Any]]:
        common_target = _object_schema(
            {
                "orchestration_id": {"type": "integer", "minimum": 1},
                "project_id": {"type": "integer", "minimum": 1},
            }
        )
        return [
            {
                "name": "mission_control_attach_workspace",
                "description": "Attach the current workspace to Mission Control and safely reuse or import it before orchestration.",
                "inputSchema": _object_schema(
                    {
                        "workspace_path": {"type": "string", "minLength": 1},
                        "project_name": {"type": "string", "minLength": 1},
                        "mode": {"type": "string", "enum": ["auto", "new_project", "existing_codebase"]},
                        "read_only_first": {"type": "boolean"},
                        "attach_policy": {"type": "string", "enum": ["reuse_existing", "create_new", "ask"]},
                    },
                    required=["workspace_path"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_start_task",
                "description": "Start or continue a background Mission Control task for an attached project.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "user_request": {"type": "string", "minLength": 1},
                        "source": {"type": "string", "minLength": 1},
                        "orchestration_id": {"type": "integer", "minimum": 1},
                    },
                    required=["project_id", "user_request"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_status",
                "description": "Get a compact orchestration status summary suitable for Codex chat polling.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_pending_decisions",
                "description": "List approvals and manager questions that still need a user answer.",
                "inputSchema": common_target,
                "outputSchema": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            {
                "name": "mission_control_answer_decision",
                "description": "Send the user's selected answer back to Mission Control so orchestration can continue safely.",
                "inputSchema": _object_schema(
                    {
                        "decision_id": {"type": "integer", "minimum": 1},
                        "project_id": {"type": "integer", "minimum": 1},
                        "option_id": {"type": "string", "minLength": 1},
                        "selected_text": {"type": "string", "minLength": 1},
                        "free_text": {"type": "string"},
                    },
                    required=["decision_id", "project_id", "option_id", "selected_text"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_pause",
                "description": "Pause a running Mission Control orchestration.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_resume",
                "description": "Resume a paused Mission Control orchestration.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_handoff",
                "description": "Fetch the latest Mission Control handoff summary when available.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_import_existing_codebase",
                "description": "Attach an existing repo or folder in existing-codebase mode and return the initial map and understanding summary.",
                "inputSchema": _object_schema(
                    {
                        "workspace_path": {"type": "string", "minLength": 1},
                        "project_name": {"type": "string", "minLength": 1},
                        "read_only_first": {"type": "boolean"},
                        "attach_policy": {"type": "string", "enum": ["reuse_existing", "create_new", "ask"]},
                    },
                    required=["workspace_path"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_plugin_health",
                "description": "Run the Mission Control plugin health doctor and return a bridge-safe summary.",
                "inputSchema": _object_schema({}),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_enable_safe_mode",
                "description": "Enable strict Mission Control safe mode for a project through daemon-backed policy updates.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_event_digest",
                "description": "Fetch a compact, redacted event digest for a project or orchestration.",
                "inputSchema": _object_schema(
                    {
                        "orchestration_id": {"type": "integer", "minimum": 1},
                        "project_id": {"type": "integer", "minimum": 1},
                        "window": {
                            "type": "string",
                            "enum": [
                                "last_5_minutes",
                                "last_15_minutes",
                                "since_last_user_interaction",
                                "since_orchestration_start",
                            ],
                        },
                    }
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_handoff_summary",
                "description": "Fetch a chat-native handoff summary for a project or orchestration.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_generate_agents_md",
                "description": "Generate a Mission Control-backed AGENTS.md proposal for user review.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_request_snapshot",
                "description": "Record a project snapshot request through the daemon without executing a restore.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "label": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "created_before_task_id": {"type": "integer", "minimum": 1},
                        "created_before_agent_id": {"type": "integer", "minimum": 1},
                    },
                    required=["project_id", "label", "description"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_request_recovery_plan",
                "description": "Create a daemon-backed recovery plan record for a stuck or failed Mission Control run.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "orchestration_id": {"type": "integer", "minimum": 1},
                        "trigger_type": {"type": "string", "minLength": 1},
                        "trigger_summary": {"type": "string", "minLength": 1},
                        "related_agent_id": {"type": "integer", "minimum": 1},
                        "related_task_id": {"type": "integer", "minimum": 1},
                        "suggested_actions_json": {"type": "array", "items": {"type": "string"}},
                    },
                    required=["trigger_summary"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_orchestration_events",
                "description": "Fetch recent safe orchestration events for debugging or progress summaries.",
                "inputSchema": _object_schema({"orchestration_id": {"type": "integer", "minimum": 1}}, required=["orchestration_id"]),
                "outputSchema": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            {
                "name": "mission_control_get_codebase_map",
                "description": "Fetch the current codebase map for an attached Mission Control project.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_codebase_understanding",
                "description": "Fetch Mission Control's compact understanding summary for an imported codebase.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_set_import_interview_choice",
                "description": "Tell Mission Control which import interview mode the user selected.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "choice": {"type": "string", "enum": ["skip", "quick_clarify", "full_interview", "manager_decides"]},
                    },
                    required=["project_id", "choice"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_diagnostics",
                "description": "Fetch bridge-safe diagnostics and plugin-health context for a Mission Control project or orchestration.",
                "inputSchema": common_target,
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_workspace_tooling",
                "description": "Fetch the project-scoped repo-native tooling summary covering intake, validation, and security helper lanes.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_search_codebase",
                "description": "Search the attached workspace with ripgrep when available, with a safe fallback if ripgrep is missing.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "pattern": {"type": "string", "minLength": 1},
                        "glob": {"type": "string", "minLength": 1},
                        "max_matches": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    required=["project_id", "pattern"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_webwright_status",
                "description": "Fetch the project-scoped Webwright readiness summary for browser-agent work.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_nvidia_dynamo_status",
                "description": "Fetch the project-scoped NVIDIA Dynamo readiness summary for GPU-backed Mission Control worker inference.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_nvidia_aiq_status",
                "description": "Fetch the project-scoped NVIDIA AI-Q readiness summary for deep research delegation.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_run_nvidia_aiq_research",
                "description": "Submit a deep research query to NVIDIA AI-Q and return the final structured report summary when available.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "query": {"type": "string", "minLength": 1},
                        "agent_type": {"type": "string", "minLength": 1},
                        "timeout_seconds": {"type": "integer", "minimum": 5},
                        "poll_interval_seconds": {"type": "number", "minimum": 0.2},
                        "expiry_seconds": {"type": "integer", "minimum": 60},
                        "endpoint_override": {"type": "string", "minLength": 1},
                    },
                    required=["project_id", "query"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_nvidia_gpu_diagnostics",
                "description": "Fetch NVIDIA GPU cluster diagnostics derived from Prometheus and DCGM-exporter metrics when configured.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_swarm_plan",
                "description": "Fetch the current or proposed Mission Control swarm plan.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_update_swarm_preferences",
                "description": "Update swarm preferences such as optimization mode, agent budget, or dynamic spawning posture.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "optimization_mode": {"type": "string"},
                        "swarm_aggressiveness": {"type": "string"},
                        "max_agents": {"type": "integer", "minimum": 1},
                        "require_approval_above_agent_count": {"type": "integer", "minimum": 1},
                        "allow_dynamic_spawning": {"type": "boolean"},
                        "allow_dynamic_retirement": {"type": "boolean"},
                        "docs_depth": {"type": "string"},
                        "testing_depth": {"type": "string"},
                    },
                    required=["project_id"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_generate_swarm_plan",
                "description": "Ask Mission Control to generate or refresh a swarm plan for the project.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "goal": {"type": "string"},
                        "milestone_id": {"type": "integer", "minimum": 1},
                    },
                    required=["project_id"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_approve_swarm_plan",
                "description": "Approve a pending Mission Control swarm plan after the user explicitly asks to proceed.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "swarm_plan_id": {"type": "integer", "minimum": 1},
                    },
                    required=["project_id", "swarm_plan_id"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_project_settings",
                "description": "Fetch the current project settings that affect runner mode, sandbox, and approval posture.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_update_project_settings",
                "description": "Update project settings such as approval policy or sandbox posture for safer Mission Control execution.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "provider": {"type": "string"},
                        "runner_mode": {"type": "string"},
                        "sandbox_mode": {"type": "string"},
                        "approval_policy": {"type": "string"},
                    },
                    required=["project_id"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_import_safety",
                "description": "Fetch the current imported-codebase safety posture for the project.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_update_import_safety",
                "description": "Update imported-codebase safety switches such as write permission or approval requirements.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "write_permission_status": {"type": "string"},
                        "require_snapshot_before_edits": {"type": "boolean"},
                        "require_approval_for_dependency_changes": {"type": "boolean"},
                        "require_approval_for_test_commands": {"type": "boolean"},
                        "require_approval_for_build_commands": {"type": "boolean"},
                        "require_approval_for_formatting": {"type": "boolean"},
                        "require_approval_for_package_file_changes": {"type": "boolean"},
                        "destructive_commands_blocked": {"type": "boolean"},
                    },
                    required=["project_id"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_tool_catalog",
                "description": "Fetch the Mission Control tool catalog with availability, risk, and permission policy summaries.",
                "inputSchema": _object_schema({}),
                "outputSchema": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            {
                "name": "mission_control_set_tool_permission",
                "description": "Update the permission policy for a specific Mission Control tool.",
                "inputSchema": _object_schema(
                    {
                        "tool_id": {"type": "string", "minLength": 1},
                        "permission_policy": {"type": "string", "minLength": 1},
                    },
                    required=["tool_id", "permission_policy"],
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_get_agents_md_status",
                "description": "Check whether the project already has AGENTS.md guidance and whether Mission Control recommends creating or updating it.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_propose_agents_md",
                "description": "Generate a Mission Control-backed AGENTS.md proposal for user review in Codex chat.",
                "inputSchema": _object_schema({"project_id": {"type": "integer", "minimum": 1}}, required=["project_id"]),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
            {
                "name": "mission_control_request_recovery_options",
                "description": "Ask Mission Control Manager for safe recovery options after a stuck or failed run.",
                "inputSchema": _object_schema(
                    {
                        "project_id": {"type": "integer", "minimum": 1},
                        "orchestration_id": {"type": "integer", "minimum": 1},
                        "user_context": {"type": "string"},
                    }
                ),
                "outputSchema": GENERIC_OUTPUT_SCHEMA,
            },
        ]

    def list_tools(self) -> list[dict[str, Any]]:
        return self._tools

    def list_resources(self) -> list[dict[str, Any]]:
        return []

    def list_resource_templates(self) -> list[dict[str, Any]]:
        return [
            {
                "uriTemplate": entry["uri_template"],
                "name": entry["title"],
                "mimeType": "application/json",
                "description": entry["summary"],
            }
            for entry in resource_entries()
        ]

    def list_prompts(self) -> list[dict[str, Any]]:
        return [{"name": entry["name"], "description": entry["description"]} for entry in prompt_entries()]

    def get_prompt(self, name: str) -> dict[str, Any]:
        entry = prompt_entry(name)
        return {
            "description": entry["title"],
            "messages": [{"role": "user", "content": {"type": "text", "text": entry["prompt_text"]}}],
        }

    def _tool_result(self, payload: Any) -> dict[str, Any]:
        text = json.dumps(payload, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "structuredContent": payload}

    def _require_int(self, args: dict[str, Any], key: str) -> int:
        value = args.get(key)
        if value is None:
            raise RuntimeError(f"Missing required argument: {key}")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Argument {key} must be an integer.") from exc
        if parsed < 1:
            raise RuntimeError(f"Argument {key} must be a positive integer.")
        return parsed

    def _optional_int(self, args: dict[str, Any], key: str) -> int | None:
        value = args.get(key)
        if value is None:
            return None
        return self._require_int(args, key)

    def _require_string(self, args: dict[str, Any], key: str) -> str:
        value = str(args.get(key, "")).strip()
        if not value:
            raise RuntimeError(f"Argument {key} must be a non-empty string.")
        return value

    def _require_target(self, args: dict[str, Any], *, allow_project_only: bool = True) -> tuple[int | None, int | None]:
        orchestration_id = self._optional_int(args, "orchestration_id")
        project_id = self._optional_int(args, "project_id")
        if orchestration_id is None and (project_id is None or not allow_project_only):
            raise RuntimeError("Provide an orchestration_id or project_id.")
        return orchestration_id, project_id

    def _payload_without(self, args: dict[str, Any], *excluded: str) -> dict[str, Any]:
        return {key: value for key, value in args.items() if key not in excluded and value is not None}

    def _call_attach_workspace(self, args: dict[str, Any]) -> Any:
        return self.client.attach_workspace(
            workspace_path=self._require_string(args, "workspace_path"),
            project_name=str(args["project_name"]).strip() if args.get("project_name") else None,
            mode=str(args.get("mode", "auto")),
            read_only_first=bool(args.get("read_only_first", True)),
            attach_policy=str(args.get("attach_policy", "reuse_existing")),
        )

    def _call_start_task(self, args: dict[str, Any]) -> Any:
        return self.client.start_task(
            project_id=self._require_int(args, "project_id"),
            user_request=self._require_string(args, "user_request"),
            source=str(args.get("source", "codex_plugin")),
            orchestration_id=self._optional_int(args, "orchestration_id"),
        )

    def _call_get_status(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_status_summary(orchestration_id=orchestration_id, project_id=project_id)

    def _call_get_pending_decisions(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_pending_decisions(orchestration_id=orchestration_id, project_id=project_id)

    def _call_answer_decision(self, args: dict[str, Any]) -> Any:
        return self.client.answer_decision(
            decision_id=self._require_int(args, "decision_id"),
            project_id=self._require_int(args, "project_id"),
            option_id=self._require_string(args, "option_id"),
            selected_text=self._require_string(args, "selected_text"),
            free_text=str(args["free_text"]) if args.get("free_text") is not None else None,
        )

    def _call_pause(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        if orchestration_id is None:
            raise RuntimeError("Pause requires an orchestration_id.")
        return self.client.pause(orchestration_id, project_id=project_id)

    def _call_resume(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        if orchestration_id is None:
            raise RuntimeError("Resume requires an orchestration_id.")
        return self.client.resume(orchestration_id, project_id=project_id)

    def _call_get_handoff(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_handoff(orchestration_id=orchestration_id, project_id=project_id)

    def _call_import_existing_codebase(self, args: dict[str, Any]) -> Any:
        return self.client.import_existing_codebase(
            workspace_path=self._require_string(args, "workspace_path"),
            project_name=str(args["project_name"]).strip() if args.get("project_name") else None,
            attach_policy=str(args.get("attach_policy", "reuse_existing")),
            read_only_first=bool(args.get("read_only_first", True)),
        )

    def _call_plugin_health(self, _: dict[str, Any]) -> Any:
        return self.client.plugin_health_summary()

    def _call_enable_safe_mode(self, args: dict[str, Any]) -> Any:
        return self.client.enable_safe_mode(self._require_int(args, "project_id"))

    def _call_get_event_digest(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_event_digest(
            orchestration_id=orchestration_id,
            project_id=project_id,
            window=str(args.get("window", "last_15_minutes")),
        )

    def _call_get_handoff_summary(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_handoff_summary(orchestration_id=orchestration_id, project_id=project_id)

    def _call_generate_agents_md(self, args: dict[str, Any]) -> Any:
        return self.client.propose_agents_md(self._require_int(args, "project_id"))

    def _call_request_snapshot(self, args: dict[str, Any]) -> Any:
        return self.client.create_snapshot(
            self._require_int(args, "project_id"),
            label=self._require_string(args, "label"),
            description=self._require_string(args, "description"),
            created_before_task_id=self._optional_int(args, "created_before_task_id"),
            created_before_agent_id=self._optional_int(args, "created_before_agent_id"),
        )

    def _call_request_recovery_plan(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.request_recovery_plan(
            project_id=project_id,
            orchestration_id=orchestration_id,
            trigger_type=str(args.get("trigger_type", "bridge_request")),
            trigger_summary=self._require_string(args, "trigger_summary"),
            related_agent_id=self._optional_int(args, "related_agent_id"),
            related_task_id=self._optional_int(args, "related_task_id"),
            suggested_actions_json=[str(item) for item in args.get("suggested_actions_json", [])],
        )

    def _call_get_orchestration_events(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        if orchestration_id is None:
            raise RuntimeError("Orchestration events require an orchestration_id.")
        return self.client.get_orchestration_events(orchestration_id, project_id=project_id)

    def _call_get_codebase_map(self, args: dict[str, Any]) -> Any:
        return self.client.get_codebase_map(self._require_int(args, "project_id"))

    def _call_get_codebase_understanding(self, args: dict[str, Any]) -> Any:
        return self.client.get_codebase_understanding(self._require_int(args, "project_id"))

    def _call_set_import_interview_choice(self, args: dict[str, Any]) -> Any:
        return self.client.set_import_interview_choice(self._require_int(args, "project_id"), self._require_string(args, "choice"))

    def _call_get_diagnostics(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.get_diagnostics(orchestration_id=orchestration_id, project_id=project_id)

    def _call_get_workspace_tooling(self, args: dict[str, Any]) -> Any:
        return self.client.get_workspace_tooling(self._require_int(args, "project_id"))

    def _call_search_codebase(self, args: dict[str, Any]) -> Any:
        return self.client.search_codebase(
            self._require_int(args, "project_id"),
            pattern=self._require_string(args, "pattern"),
            glob=str(args["glob"]).strip() if args.get("glob") else None,
            max_matches=int(args.get("max_matches", 40)),
        )

    def _call_get_webwright_status(self, args: dict[str, Any]) -> Any:
        return self.client.get_webwright_status(self._require_int(args, "project_id"))

    def _call_get_nvidia_dynamo_status(self, args: dict[str, Any]) -> Any:
        return self.client.get_nvidia_dynamo_status(self._require_int(args, "project_id"))

    def _call_get_nvidia_aiq_status(self, args: dict[str, Any]) -> Any:
        return self.client.get_nvidia_aiq_status(self._require_int(args, "project_id"))

    def _call_run_nvidia_aiq_research(self, args: dict[str, Any]) -> Any:
        return self.client.run_nvidia_aiq_research(
            self._require_int(args, "project_id"),
            query=self._require_string(args, "query"),
            agent_type=str(args.get("agent_type", "deep_researcher")),
            timeout_seconds=int(args.get("timeout_seconds", 90)),
            poll_interval_seconds=float(args.get("poll_interval_seconds", 2.0)),
            expiry_seconds=int(args.get("expiry_seconds", 3600)),
            endpoint_override=str(args["endpoint_override"]).strip() if args.get("endpoint_override") else None,
        )

    def _call_get_nvidia_gpu_diagnostics(self, args: dict[str, Any]) -> Any:
        return self.client.get_nvidia_gpu_diagnostics(self._require_int(args, "project_id"))

    def _call_get_swarm_plan(self, args: dict[str, Any]) -> Any:
        return self.client.get_swarm_plan(self._require_int(args, "project_id"))

    def _call_update_swarm_preferences(self, args: dict[str, Any]) -> Any:
        return self.client.update_swarm_preferences(
            self._require_int(args, "project_id"),
            self._payload_without(args, "project_id"),
        )

    def _call_generate_swarm_plan(self, args: dict[str, Any]) -> Any:
        return self.client.generate_swarm_plan(
            self._require_int(args, "project_id"),
            goal=str(args["goal"]) if args.get("goal") is not None else None,
            milestone_id=self._optional_int(args, "milestone_id"),
        )

    def _call_approve_swarm_plan(self, args: dict[str, Any]) -> Any:
        return self.client.approve_swarm_plan(
            self._require_int(args, "project_id"),
            self._require_int(args, "swarm_plan_id"),
        )

    def _call_get_project_settings(self, args: dict[str, Any]) -> Any:
        return self.client.get_project_settings(self._require_int(args, "project_id"))

    def _call_update_project_settings(self, args: dict[str, Any]) -> Any:
        return self.client.update_project_settings(
            self._require_int(args, "project_id"),
            self._payload_without(args, "project_id"),
        )

    def _call_get_import_safety(self, args: dict[str, Any]) -> Any:
        return self.client.get_import_safety(self._require_int(args, "project_id"))

    def _call_update_import_safety(self, args: dict[str, Any]) -> Any:
        return self.client.update_import_safety(
            self._require_int(args, "project_id"),
            self._payload_without(args, "project_id"),
        )

    def _call_get_tool_catalog(self, _: dict[str, Any]) -> Any:
        return self.client.get_tool_catalog()

    def _call_set_tool_permission(self, args: dict[str, Any]) -> Any:
        return self.client.set_tool_permission(
            self._require_string(args, "tool_id"),
            self._require_string(args, "permission_policy"),
        )

    def _call_get_agents_md_status(self, args: dict[str, Any]) -> Any:
        return self.client.get_agents_md_status(self._require_int(args, "project_id"))

    def _call_propose_agents_md(self, args: dict[str, Any]) -> Any:
        return self.client.propose_agents_md(self._require_int(args, "project_id"))

    def _call_request_recovery_options(self, args: dict[str, Any]) -> Any:
        orchestration_id, project_id = self._require_target(args)
        return self.client.request_recovery_options(
            project_id=project_id,
            orchestration_id=orchestration_id,
            user_context=str(args["user_context"]) if args.get("user_context") is not None else None,
        )

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            raise RuntimeError(f"Unknown Mission Control tool: {name}")
        return self._tool_result(handler(dict(arguments or {})))

    def read_resource(self, uri: str) -> dict[str, Any]:
        payload = self.client.read_resource(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload, indent=2, default=str),
                }
            ]
        }

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        params = dict(request.get("params") or {})
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "mission-control", "title": "Codex Mission Control", "version": "1.3.0-beta.1"},
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "instructions": "Mission Control is a daemon-backed orchestration bridge. Use the exposed tools and resources instead of inventing local orchestration state.",
                }
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                result = self.call_tool(str(params.get("name")), params.get("arguments"))
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": self.list_resource_templates()}
            elif method == "resources/read":
                result = self.read_resource(str(params.get("uri")))
            elif method == "prompts/list":
                result = {"prompts": self.list_prompts()}
            elif method == "prompts/get":
                result = self.get_prompt(str(params.get("name")))
            elif method == "ping":
                result = {"status": "ok"}
            elif method == "notifications/initialized":
                return None
            else:
                raise RuntimeError(f"Unsupported Mission Control MCP method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            if request_id is None and method and str(method).startswith("notifications/"):
                return None
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
