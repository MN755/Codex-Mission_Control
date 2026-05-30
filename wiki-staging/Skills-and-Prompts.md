# Skills and Prompts

This page documents the Mission Control skill library and the workflow prompts used by Codex chat in bridge mode.

> Status: Current

## What a skill is

A skill is a reusable Codex instruction bundle. For Mission Control, skills should:

- keep Codex in the bridge role
- call Mission Control tools/resources/prompts when available
- preserve approvals
- avoid direct shell execution inside Mission Control mode
- summarize clearly for chat

## Bridge rules

The Codex chat agent is not the Manager AI.

It should not:

- independently spawn worker agents
- invent separate manager plans
- bypass pending decisions
- claim work happened without backend evidence

## Important skills

Core skills:

- `mission-control-orchestrate`
- `mission-control-import-codebase`
- `mission-control-status`
- `mission-control-approve`
- `mission-control-handoff`
- `mission-control-debug`
- `mission-control-swarm`
- `mission-control-safe-mode`
- `mission-control-resume`
- `mission-control-agents-md`

Additional bridge-oriented skills should include:

- `mission-control-install-from-github`
- `mission-control-autowire-providers`
- `mission-control-plan`
- `mission-control-pause`
- `mission-control-resume-agents`

Those bridge-oriented install, autowire, planning, and pause/resume helpers already ship in the repo skill pack.

## Prompts

Common workflow prompts should cover:

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
- `ask_manager_for_plan`

## Related pages

Read [MCP Plugin Architecture](MCP-Plugin-Architecture), [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [Contributor Rules for AI Agents](Contributor-Rules-for-AI-Agents), and [AGENTS md and Agent Instructions](AGENTS-md-and-Agent-Instructions).
