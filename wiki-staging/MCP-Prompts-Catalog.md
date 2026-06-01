# MCP Prompts Catalog

This page summarizes the current prompt workflows packaged for Mission Control bridge mode.

> Status: Current

## Catalog

- Attach current workspace (`attach_current_workspace`; aliases: `attach-current-workspace`) - tools: `mission_control_attach_workspace`, `mission_control_get_status`
- Use Mission Control for this repo (`use_mission_control_for_repo`; aliases: `use-mission-control-for-this-repo`) - tools: `mission_control_attach_workspace`, `mission_control_start_task`, `mission_control_get_status`, `mission_control_get_pending_decisions`
- Import existing codebase (`import_existing_codebase`; aliases: `import-existing-codebase`) - tools: `mission_control_import_existing_codebase`, `mission_control_set_import_interview_choice`, `mission_control_start_task`
- Start Manager-led task (`start_manager_led_task`; aliases: `start-manager-led-task`) - tools: `mission_control_start_task`, `mission_control_get_status`, `mission_control_get_pending_decisions`
- Continue orchestration (`continue_orchestration`; aliases: `continue-orchestration`) - tools: `mission_control_get_status`, `mission_control_get_pending_decisions`, `mission_control_get_event_digest`
- Show pending approvals (`show_pending_approvals`; aliases: `show-pending-approvals`) - tools: `mission_control_get_pending_decisions`
- Answer pending approval (`answer_pending_approval`; aliases: `answer-pending-approval`) - tools: `mission_control_answer_decision`, `mission_control_get_pending_decisions`
- Review latest handoff (`review_latest_handoff`; aliases: `review-latest-handoff`) - tools: `mission_control_get_handoff_summary`
- Debug failed orchestration (`debug_failed_orchestration`; aliases: `debug-failed-orchestration`) - tools: `mission_control_get_status`, `mission_control_get_diagnostics`, `mission_control_get_pending_decisions`, `mission_control_get_event_digest`, `mission_control_request_recovery_plan`
- Use Webwright for browser task (`use_webwright_for_browser_task`; aliases: `use-webwright-for-browser-task`) - tools: `mission_control_get_webwright_status`, `mission_control_start_task`, `mission_control_get_status`
- Pause orchestration (`pause_orchestration`; aliases: `pause-orchestration`) - tools: `mission_control_pause`, `mission_control_get_status`
- Resume orchestration (`resume_orchestration`; aliases: `resume-orchestration`) - tools: `mission_control_resume`, `mission_control_get_status`, `mission_control_get_pending_decisions`
- Explain current swarm (`explain_current_swarm`; aliases: `explain-current-swarm`) - tools: `mission_control_get_swarm_plan`
- Switch swarm strategy (`switch_swarm_strategy`; aliases: `switch-swarm-strategy`) - tools: `mission_control_update_swarm_preferences`, `mission_control_generate_swarm_plan`, `mission_control_get_swarm_plan`
- Enable safe mode (`enable_safe_mode`; aliases: `enable-safe-mode`) - tools: `mission_control_enable_safe_mode`, `mission_control_get_diagnostics`
- Generate AGENTS.md proposal (`generate_agents_md_proposal`; aliases: `generate-agents-md-proposal`) - tools: `mission_control_get_codebase_map`, `mission_control_get_agents_md_status`, `mission_control_generate_agents_md`
- Install from GitHub (`install_from_github`) - tools: `mission_control_plugin_health`
- Autowire providers (`autowire_providers`) - tools: `mission_control_plugin_health`
- Ask Manager for plan (`ask_manager_for_plan`; aliases: `ask-manager-for-plan`) - tools: `mission_control_start_task`, `mission_control_get_status`, `mission_control_get_pending_decisions`
- Review project capabilities (`review_project_capabilities`; aliases: `review-project-capabilities`) - tools: `mission_control_get_capability_report`
- Review project capability section (`review_project_capability_section`; aliases: `review-project-capability-section`) - tools: `mission_control_get_capability_section`
- Review TensorFlow feature catalog (`review_tensorflow_feature_catalog`; aliases: `review-tensorflow-feature-catalog`) - tools: `mission_control_get_tensorflow_feature_catalog`, `mission_control_get_workspace_tooling`
- Review TensorFlow feature bundle (`review_tensorflow_feature_bundle`; aliases: `review-tensorflow-feature-bundle`) - tools: `mission_control_get_tensorflow_feature_bundle`
- Review PyTorch feature catalog (`review_pytorch_feature_catalog`; aliases: `review-pytorch-feature-catalog`) - tools: `mission_control_get_pytorch_feature_catalog`, `mission_control_get_workspace_tooling`
- Review PyTorch feature bundle (`review_pytorch_feature_bundle`; aliases: `review-pytorch-feature-bundle`) - tools: `mission_control_get_pytorch_feature_bundle`
- Review spatial feature catalog (`review_spatial_feature_catalog`; aliases: `review-spatial-feature-catalog`) - tools: `mission_control_get_spatial_feature_catalog`, `mission_control_get_workspace_tooling`
- Review spatial feature bundle (`review_spatial_feature_bundle`; aliases: `review-spatial-feature-bundle`) - tools: `mission_control_get_spatial_feature_bundle`

## Related pages

Continue with [MCP Plugin Architecture](MCP-Plugin-Architecture), [Skills and Prompts](Skills-and-Prompts), and [Quick Start](Quick-Start).

## Integration additions

- Review integration catalog
- Import host integrations
- Review project integrations
- Review project integration family
