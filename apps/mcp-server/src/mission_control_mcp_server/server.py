from __future__ import annotations

import json
from typing import Any

from mission_control_mcp_server.catalog import prompt_entries, prompt_entry, resource_entries
from mission_control_mcp_server.client import MissionControlDaemonClient


class MissionControlMcpServer:
    def __init__(self, client: MissionControlDaemonClient | None = None) -> None:
        self.client = client or MissionControlDaemonClient()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "mission_control_attach_workspace",
                "description": "Attach the current workspace to Mission Control and safely reuse or import it before orchestration.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace_path": {"type": "string"},
                        "project_name": {"type": "string"},
                        "mode": {"type": "string", "enum": ["auto", "new_project", "existing_codebase"]},
                        "read_only_first": {"type": "boolean"},
                        "attach_policy": {"type": "string", "enum": ["reuse_existing", "create_new", "ask"]}
                    },
                    "required": ["workspace_path"]
                }
            },
            {
                "name": "mission_control_start_task",
                "description": "Start or continue a background Mission Control task for an attached project.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "user_request": {"type": "string"},
                        "source": {"type": "string"},
                        "orchestration_id": {"type": "integer"}
                    },
                    "required": ["project_id", "user_request"]
                }
            },
            {
                "name": "mission_control_get_status",
                "description": "Get a compact orchestration status summary suitable for Codex chat polling.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"},
                        "project_id": {"type": "integer"}
                    }
                }
            },
            {
                "name": "mission_control_get_pending_decisions",
                "description": "List approvals and manager questions that still need a user answer.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"},
                        "project_id": {"type": "integer"}
                    }
                }
            },
            {
                "name": "mission_control_answer_decision",
                "description": "Send the user's selected answer back to Mission Control so orchestration can continue safely.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "decision_id": {"type": "integer"},
                        "option_id": {"type": "string"},
                        "selected_text": {"type": "string"},
                        "free_text": {"type": "string"}
                    },
                    "required": ["decision_id", "option_id", "selected_text"]
                }
            },
            {
                "name": "mission_control_get_handoff",
                "description": "Fetch the latest Mission Control handoff summary when available.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"},
                        "project_id": {"type": "integer"}
                    }
                }
            },
            {
                "name": "mission_control_get_orchestration_events",
                "description": "Fetch recent safe orchestration events for debugging or progress summaries.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"}
                    },
                    "required": ["orchestration_id"]
                }
            },
            {
                "name": "mission_control_get_codebase_map",
                "description": "Fetch the current codebase map for an attached Mission Control project.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_get_codebase_understanding",
                "description": "Fetch Mission Control's compact understanding summary for an imported codebase.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_set_import_interview_choice",
                "description": "Tell Mission Control which import interview mode the user selected.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "choice": {"type": "string", "enum": ["skip", "quick_clarify", "full_interview", "manager_decides"]}
                    },
                    "required": ["project_id", "choice"]
                }
            },
            {
                "name": "mission_control_get_diagnostics",
                "description": "Fetch bridge-safe diagnostics and plugin-health context for a Mission Control project or orchestration.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "orchestration_id": {"type": "integer"}
                    }
                }
            },
            {
                "name": "mission_control_get_swarm_plan",
                "description": "Fetch the current or proposed Mission Control swarm plan.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_update_swarm_preferences",
                "description": "Update swarm preferences such as optimization mode, agent budget, or dynamic spawning posture.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "optimization_mode": {"type": "string"},
                        "swarm_aggressiveness": {"type": "string"},
                        "max_agents": {"type": "integer"},
                        "require_approval_above_agent_count": {"type": "integer"},
                        "allow_dynamic_spawning": {"type": "boolean"},
                        "allow_dynamic_retirement": {"type": "boolean"},
                        "docs_depth": {"type": "string"},
                        "testing_depth": {"type": "string"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_generate_swarm_plan",
                "description": "Ask Mission Control to generate or refresh a swarm plan for the project.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "goal": {"type": "string"},
                        "milestone_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_approve_swarm_plan",
                "description": "Approve a pending Mission Control swarm plan after the user explicitly asks to proceed.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "swarm_plan_id": {"type": "integer"}
                    },
                    "required": ["project_id", "swarm_plan_id"]
                }
            },
            {
                "name": "mission_control_get_project_settings",
                "description": "Fetch the current project settings that affect runner mode, sandbox, and approval posture.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_update_project_settings",
                "description": "Update project settings such as approval policy or sandbox posture for safer Mission Control execution.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "provider": {"type": "string"},
                        "runner_mode": {"type": "string"},
                        "sandbox_mode": {"type": "string"},
                        "approval_policy": {"type": "string"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_get_import_safety",
                "description": "Fetch the current imported-codebase safety posture for the project.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_update_import_safety",
                "description": "Update imported-codebase safety switches such as write permission or approval requirements.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "write_permission_status": {"type": "string"},
                        "require_snapshot_before_edits": {"type": "boolean"},
                        "require_approval_for_dependency_changes": {"type": "boolean"},
                        "require_approval_for_test_commands": {"type": "boolean"},
                        "require_approval_for_build_commands": {"type": "boolean"},
                        "require_approval_for_formatting": {"type": "boolean"},
                        "require_approval_for_package_file_changes": {"type": "boolean"},
                        "destructive_commands_blocked": {"type": "boolean"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_get_tool_catalog",
                "description": "Fetch the Mission Control tool catalog with availability, risk, and permission policy summaries.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "mission_control_set_tool_permission",
                "description": "Update the permission policy for a specific Mission Control tool.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_id": {"type": "string"},
                        "permission_policy": {"type": "string"}
                    },
                    "required": ["tool_id", "permission_policy"]
                }
            },
            {
                "name": "mission_control_get_agents_md_status",
                "description": "Check whether the project already has AGENTS.md guidance and whether Mission Control recommends creating or updating it.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_propose_agents_md",
                "description": "Generate a Mission Control-backed AGENTS.md proposal for user review in Codex chat.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"}
                    },
                    "required": ["project_id"]
                }
            },
            {
                "name": "mission_control_request_recovery_options",
                "description": "Ask Mission Control for recovery options after a stuck or failed run.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "integer"},
                        "orchestration_id": {"type": "integer"},
                        "user_context": {"type": "string"}
                    }
                }
            },
            {
                "name": "mission_control_pause",
                "description": "Pause a running Mission Control orchestration.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"}
                    },
                    "required": ["orchestration_id"]
                }
            },
            {
                "name": "mission_control_resume",
                "description": "Resume a paused Mission Control orchestration.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "orchestration_id": {"type": "integer"}
                    },
                    "required": ["orchestration_id"]
                }
            }
        ]

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {
                "uriTemplate": entry["uri_template"],
                "name": entry["title"],
                "mimeType": "application/json",
                "description": entry["summary"]
            }
            for entry in resource_entries()
        ]

    def list_prompts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": entry["name"],
                "description": entry["description"]
            }
            for entry in prompt_entries()
        ]

    def get_prompt(self, name: str) -> dict[str, Any]:
        entry = prompt_entry(name)
        return {
            "description": entry["title"],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": entry["prompt_text"]
                    }
                }
            ]
        }

    def _tool_result(self, payload: Any) -> dict[str, Any]:
        text = json.dumps(payload, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "structuredContent": payload}

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(arguments or {})
        if name == "mission_control_attach_workspace":
            return self._tool_result(
                self.client.attach_workspace(
                    workspace_path=str(args["workspace_path"]),
                    project_name=args.get("project_name"),
                    mode=str(args.get("mode", "auto")),
                    read_only_first=bool(args.get("read_only_first", True)),
                    attach_policy=str(args.get("attach_policy", "reuse_existing"))
                )
            )
        if name == "mission_control_start_task":
            return self._tool_result(
                self.client.start_task(
                    project_id=int(args["project_id"]),
                    user_request=str(args["user_request"]),
                    source=str(args.get("source", "codex_plugin")),
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None
                )
            )
        if name == "mission_control_get_status":
            return self._tool_result(
                self.client.get_status(
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None,
                    project_id=int(args["project_id"]) if args.get("project_id") is not None else None
                )
            )
        if name == "mission_control_get_pending_decisions":
            return self._tool_result(
                self.client.get_pending_decisions(
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None,
                    project_id=int(args["project_id"]) if args.get("project_id") is not None else None
                )
            )
        if name == "mission_control_answer_decision":
            return self._tool_result(
                self.client.answer_decision(
                    decision_id=int(args["decision_id"]),
                    option_id=str(args["option_id"]),
                    selected_text=str(args["selected_text"]),
                    free_text=str(args["free_text"]) if args.get("free_text") is not None else None
                )
            )
        if name == "mission_control_get_handoff":
            return self._tool_result(
                self.client.get_handoff(
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None,
                    project_id=int(args["project_id"]) if args.get("project_id") is not None else None
                )
            )
        if name == "mission_control_get_orchestration_events":
            return self._tool_result(self.client.get_orchestration_events(int(args["orchestration_id"])))
        if name == "mission_control_get_codebase_map":
            return self._tool_result(self.client.get_codebase_map(int(args["project_id"])))
        if name == "mission_control_get_codebase_understanding":
            return self._tool_result(self.client.get_codebase_understanding(int(args["project_id"])))
        if name == "mission_control_set_import_interview_choice":
            return self._tool_result(self.client.set_import_interview_choice(int(args["project_id"]), str(args["choice"])))
        if name == "mission_control_get_diagnostics":
            return self._tool_result(
                self.client.get_diagnostics(
                    project_id=int(args["project_id"]) if args.get("project_id") is not None else None,
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None
                )
            )
        if name == "mission_control_get_swarm_plan":
            return self._tool_result(self.client.get_swarm_plan(int(args["project_id"])))
        if name == "mission_control_update_swarm_preferences":
            payload = {key: args[key] for key in args if key != "project_id"}
            return self._tool_result(self.client.update_swarm_preferences(int(args["project_id"]), payload))
        if name == "mission_control_generate_swarm_plan":
            return self._tool_result(
                self.client.generate_swarm_plan(
                    int(args["project_id"]),
                    goal=str(args["goal"]) if args.get("goal") is not None else None,
                    milestone_id=int(args["milestone_id"]) if args.get("milestone_id") is not None else None
                )
            )
        if name == "mission_control_approve_swarm_plan":
            return self._tool_result(self.client.approve_swarm_plan(int(args["project_id"]), int(args["swarm_plan_id"])))
        if name == "mission_control_get_project_settings":
            return self._tool_result(self.client.get_project_settings(int(args["project_id"])))
        if name == "mission_control_update_project_settings":
            payload = {key: args[key] for key in args if key != "project_id"}
            return self._tool_result(self.client.update_project_settings(int(args["project_id"]), payload))
        if name == "mission_control_get_import_safety":
            return self._tool_result(self.client.get_import_safety(int(args["project_id"])))
        if name == "mission_control_update_import_safety":
            payload = {key: args[key] for key in args if key != "project_id"}
            return self._tool_result(self.client.update_import_safety(int(args["project_id"]), payload))
        if name == "mission_control_get_tool_catalog":
            return self._tool_result(self.client.get_tool_catalog())
        if name == "mission_control_set_tool_permission":
            return self._tool_result(self.client.set_tool_permission(str(args["tool_id"]), str(args["permission_policy"])))
        if name == "mission_control_get_agents_md_status":
            return self._tool_result(self.client.get_agents_md_status(int(args["project_id"])))
        if name == "mission_control_propose_agents_md":
            return self._tool_result(self.client.propose_agents_md(int(args["project_id"])))
        if name == "mission_control_request_recovery_options":
            return self._tool_result(
                self.client.request_recovery_options(
                    project_id=int(args["project_id"]) if args.get("project_id") is not None else None,
                    orchestration_id=int(args["orchestration_id"]) if args.get("orchestration_id") is not None else None,
                    user_context=str(args["user_context"]) if args.get("user_context") is not None else None
                )
            )
        if name == "mission_control_pause":
            return self._tool_result(self.client.pause(int(args["orchestration_id"])))
        if name == "mission_control_resume":
            return self._tool_result(self.client.resume(int(args["orchestration_id"])))
        raise RuntimeError(f"Unknown Mission Control tool: {name}")

    def read_resource(self, uri: str) -> dict[str, Any]:
        payload = self.client.read_resource(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(payload, indent=2, default=str)
                }
            ]
        }

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        request_id = request.get("id")
        params = dict(request.get("params") or {})
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "mission-control", "title": "Codex Mission Control", "version": "0.2.0"},
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}}
                }
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                result = self.call_tool(str(params.get("name")), params.get("arguments"))
            elif method == "resources/list":
                result = {"resources": self.list_resources()}
            elif method == "resources/read":
                result = self.read_resource(str(params.get("uri")))
            elif method == "prompts/list":
                result = {"prompts": self.list_prompts()}
            elif method == "prompts/get":
                result = self.get_prompt(str(params.get("name")))
            elif method == "ping":
                result = {"status": "ok"}
            else:
                raise RuntimeError(f"Unsupported Mission Control MCP method: {method}")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
