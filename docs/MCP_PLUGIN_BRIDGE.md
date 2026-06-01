# MCP Plugin Bridge

> Status: Current

This page describes how Codex reaches Mission Control through plugin packaging, MCP tools, MCP resources, and MCP prompts.

## Purpose

The bridge keeps Codex chat thin. Mission Control remains the orchestrator. MCP surfaces give Codex a controlled way to attach workspaces, start tasks, read safe summaries, answer pending decisions, and retrieve handoffs.

## Surface types

- MCP tools: executable actions such as attach, start, answer, pause, and resume
- MCP resources: read-only summaries such as project status, agents, pending decisions, diagnostics, and handoff state
- MCP prompts: reusable workflow templates for common tasks
- skills: Codex-facing instructions that tell the bridge how to use Mission Control safely
- backend-only project routes: typed daemon APIs that are not yet surfaced as MCP tools or resources

## Expected tools

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
- `mission_control_get_orchestration_events`
- `mission_control_get_codebase_map`
- `mission_control_get_codebase_understanding`
- `mission_control_set_import_interview_choice`
- `mission_control_get_diagnostics`
- `mission_control_get_capability_report`
- `mission_control_get_capability_section`
- `mission_control_get_workspace_tooling`
- `mission_control_search_codebase`
- `mission_control_get_webwright_status`
- `mission_control_get_nvidia_dynamo_status`
- `mission_control_get_nvidia_nim_status`
- `mission_control_get_nvidia_aiq_status`
- `mission_control_run_nvidia_aiq_research`
- `mission_control_get_nvidia_gpu_diagnostics`
- `mission_control_get_nvidia_local_runtime_status`
- `mission_control_get_nvidia_validation_plan`
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

## Expected resources

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
- `mission-control://projects/{project_id}/nvidia-local-runtime`
- `mission-control://projects/{project_id}/nvidia-validation-plan`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/operator-snapshot`
- `mission-control://projects/{project_id}/instincts`
- `mission-control://projects/{project_id}/verification-brief`
- `mission-control://projects/{project_id}/capability-report`
- `mission-control://projects/{project_id}/capability-report/{section_key}`

## Current prompts

- `attach_current_workspace`
- `use_mission_control_for_repo`
- `import_existing_codebase`
- `start_manager_led_task`
- `continue_orchestration`
- `show_pending_approvals`
- `answer_pending_approval`
- `review_latest_handoff`
- `debug_failed_orchestration`
- `use_webwright_for_browser_task`
- `pause_orchestration`
- `resume_orchestration`
- `explain_current_swarm`
- `switch_swarm_strategy`
- `enable_safe_mode`
- `generate_agents_md_proposal`
- `install_from_github`
- `autowire_providers`
- `review_project_capabilities`
- `ask_manager_for_plan`
- `review_project_capability_section`

## Backend-only project routes

These routes are real backend surfaces in `apps/server/src/main.py`, but they are not currently exposed as MCP resources or MCP tools:

- `GET /api/projects/{project_id}/tensorflow/features`
- `GET /api/projects/{project_id}/tensorflow/features/{feature_id}?variant=...`

Those endpoints expose the typed TensorFlow starter catalog and bundle generator from `apps/server/src/tensorflow_starters.py`. They are useful for daemon and API clients today, but the plugin catalog does not advertise them yet, so docs should not pretend they are part of the MCP layer.

## Bridge rules

- attach the workspace before starting work
- prefer safe resource summaries before polling tools repeatedly
- relay user decisions instead of answering them locally
- keep raw logs and secrets out of normal chat output

## Related docs

- [Codex Chat Mode](CODEX_CHAT_MODE.md)
- [Pending Decisions](PENDING_DECISIONS.md)
- [Background Architecture](HEADLESS_ARCHITECTURE.md)
- [Security](SECURITY.md)

## Integration bridge additions

- `mission_control_get_integrations_catalog`
- `mission_control_get_integration_connections`
- `mission_control_import_host_integrations`
- `mission_control_get_project_integrations`
- `mission_control_get_project_integration_family`
- `mission_control_preview_integration_action`
- `mission_control_execute_integration_action`
- `mission-control://integrations/catalog`
- `mission-control://integrations/connections`
- `mission-control://integrations/health`
- `mission-control://projects/{project_id}/integrations`
- `mission-control://projects/{project_id}/integrations/{family}`
