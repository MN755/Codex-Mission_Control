# MCP Prompts

Mission Control MCP prompts are reusable Codex-chat workflows. They describe how the bridge should sequence tools and resources.

## Prompt Catalog

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

## Prompt Rules

- Prompts are workflow instructions, not secret storage.
- Prompts should produce compact Codex-chat output.
- Prompts should surface pending decisions instead of answering them locally.
- Prompts should reinforce that Codex chat is the bridge and Mission Control owns orchestration.

## Compatibility

- Canonical names use underscores.
- Legacy hyphenated names remain prompt aliases in the MCP catalog for compatibility.
- Key aliases include `use-mission-control-for-this-repo`, `continue-orchestration`, `use-webwright-for-browser-task`, `review-project-capabilities`, `ask-manager-for-plan`, and `review-project-capability-section`.
