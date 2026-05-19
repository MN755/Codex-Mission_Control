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
- `pause_orchestration`
- `resume_orchestration`
- `explain_current_swarm`
- `switch_swarm_strategy`
- `enable_safe_mode`
- `generate_agents_md_proposal`
- `install_from_github`
- `autowire_providers`

## Prompt Rules

- Prompts are workflow instructions, not secret storage.
- Prompts should produce compact Codex-chat output.
- Prompts should surface pending decisions instead of answering them locally.
- Prompts should reinforce that Codex chat is the bridge and Mission Control owns orchestration.

## Compatibility

- Canonical names use underscores.
- Legacy hyphenated names remain prompt aliases in the MCP catalog for compatibility.
