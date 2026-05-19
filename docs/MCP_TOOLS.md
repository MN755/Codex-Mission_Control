# MCP Tools

Mission Control MCP tools are action endpoints for the Codex bridge. They do not run shell commands directly. They call daemon APIs.

## Core Tools

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_pause`
- `mission_control_resume`
- `mission_control_get_handoff`
- `mission_control_import_existing_codebase`
- `mission_control_plugin_health`
- `mission_control_enable_safe_mode`
- `mission_control_get_event_digest`
- `mission_control_get_handoff_summary`
- `mission_control_generate_agents_md`
- `mission_control_request_snapshot`
- `mission_control_request_recovery_plan`

## Extended Bridge Tools

- `mission_control_get_orchestration_events`
- `mission_control_get_codebase_map`
- `mission_control_get_codebase_understanding`
- `mission_control_set_import_interview_choice`
- `mission_control_get_diagnostics`
- `mission_control_get_swarm_plan`
- `mission_control_update_swarm_preferences`
- `mission_control_generate_swarm_plan`
- `mission_control_approve_swarm_plan`
- `mission_control_get_project_settings`
- `mission_control_update_project_settings`
- `mission_control_get_import_safety`
- `mission_control_update_import_safety`
- `mission_control_get_tool_catalog`
- `mission_control_set_tool_permission`
- `mission_control_get_agents_md_status`
- `mission_control_propose_agents_md`
- `mission_control_request_recovery_options`

## Tool Rules

- Input is validated before the daemon call.
- Output is bridge-safe JSON.
- Secrets are not returned.
- High-risk changes must stay approval-gated.
- Tools never bypass Mission Control safety policy.
