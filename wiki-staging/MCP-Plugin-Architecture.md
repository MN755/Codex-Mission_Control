# MCP Plugin Architecture

This page explains how the plugin package, MCP tools, MCP resources, and MCP prompts work together around the Mission Control daemon.

> Status: Current

## Why the split exists

The MCP layer should stay thin and predictable:

- resources are read-only state summaries
- tools perform bridge actions
- prompts provide reusable Codex-chat workflows
- the daemon remains the orchestration authority

## Current MCP tools

- `mission_control_answer_decision`
- `mission_control_approve_swarm_plan`
- `mission_control_attach_workspace`
- `mission_control_enable_safe_mode`
- `mission_control_generate_agents_md`
- `mission_control_generate_swarm_plan`
- `mission_control_get_agents_md_status`
- `mission_control_get_capability_report`
- `mission_control_get_capability_section`
- `mission_control_get_codebase_map`
- `mission_control_get_codebase_understanding`
- `mission_control_get_diagnostics`
- `mission_control_get_event_digest`
- `mission_control_get_handoff`
- `mission_control_get_handoff_summary`
- `mission_control_get_import_safety`
- `mission_control_get_nvidia_aiq_status`
- `mission_control_get_nvidia_dynamo_status`
- `mission_control_get_nvidia_gpu_diagnostics`
- `mission_control_get_nvidia_local_runtime_status`
- `mission_control_get_nvidia_nim_status`
- `mission_control_get_nvidia_validation_plan`
- `mission_control_get_orchestration_events`
- `mission_control_get_pending_decisions`
- `mission_control_get_project_settings`
- `mission_control_get_status`
- `mission_control_get_swarm_plan`
- `mission_control_get_tool_catalog`
- `mission_control_get_webwright_status`
- `mission_control_get_workspace_tooling`
- `mission_control_import_existing_codebase`
- `mission_control_pause`
- `mission_control_plugin_health`
- `mission_control_propose_agents_md`
- `mission_control_request_recovery_options`
- `mission_control_request_recovery_plan`
- `mission_control_request_snapshot`
- `mission_control_resume`
- `mission_control_run_nvidia_aiq_research`
- `mission_control_search_codebase`
- `mission_control_set_import_interview_choice`
- `mission_control_set_tool_permission`
- `mission_control_start_task`
- `mission_control_update_import_safety`
- `mission_control_update_project_settings`
- `mission_control_update_swarm_preferences`

## Current MCP resources

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-nim`
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

## Current MCP prompts

- `attach_current_workspace` (aliases: `attach-current-workspace`)
- `use_mission_control_for_repo` (aliases: `use-mission-control-for-this-repo`)
- `import_existing_codebase` (aliases: `import-existing-codebase`)
- `start_manager_led_task` (aliases: `start-manager-led-task`)
- `continue_orchestration` (aliases: `continue-orchestration`)
- `show_pending_approvals` (aliases: `show-pending-approvals`)
- `answer_pending_approval` (aliases: `answer-pending-approval`)
- `review_latest_handoff` (aliases: `review-latest-handoff`)
- `debug_failed_orchestration` (aliases: `debug-failed-orchestration`)
- `use_webwright_for_browser_task` (aliases: `use-webwright-for-browser-task`)
- `pause_orchestration` (aliases: `pause-orchestration`)
- `resume_orchestration` (aliases: `resume-orchestration`)
- `explain_current_swarm` (aliases: `explain-current-swarm`)
- `switch_swarm_strategy` (aliases: `switch-swarm-strategy`)
- `enable_safe_mode` (aliases: `enable-safe-mode`)
- `generate_agents_md_proposal` (aliases: `generate-agents-md-proposal`)
- `install_from_github`
- `autowire_providers`
- `ask_manager_for_plan` (aliases: `ask-manager-for-plan`)
- `review_project_capabilities` (aliases: `review-project-capabilities`)
- `review_project_capability_section` (aliases: `review-project-capability-section`)

## Related pages

Continue with [Skills and Prompts](Skills-and-Prompts), [MCP Resources Catalog](MCP-Resources-Catalog), [MCP Prompts Catalog](MCP-Prompts-Catalog), and [MCP Bridge Endpoints](MCP-Bridge-Endpoints).

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
