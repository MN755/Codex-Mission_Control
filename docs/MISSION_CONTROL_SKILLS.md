# Mission Control Skills

This document describes the first-party Codex-facing Mission Control skill pack.

The skill pack exists in both repo layouts:

- [plugins/mission-control/skills](../plugins/mission-control/skills)
- [.codex/skills](../.codex/skills)

Every skill in this pack follows the same rule:

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## Skill Inventory

### `mission-control-orchestrate`

Use when the user wants Mission Control to manage the current repo or task. This skill attaches the workspace, starts the task, surfaces pending decisions, and retrieves the handoff when complete.

### `mission-control-import-codebase`

Use for existing repos and folders. This skill keeps the first pass read-only, retrieves the codebase map and understanding summary, asks for the interview mode, and then starts the requested work.

### `mission-control-status`

Use for status questions. This skill reads orchestration status, agent activity, and pending decisions, then returns a compact bridge-safe markdown summary.

### `mission-control-approve`

Use when Mission Control is blocked on user input. This skill renders the top approval or question, explains the options, and sends the user's answer back to Mission Control.

### `mission-control-handoff`

Use when the user wants the final output. This skill retrieves the latest handoff and summarizes changes, run instructions, evidence posture, limitations, and next steps.

### `mission-control-debug`

Use when orchestration is stuck, degraded, or unclear. This skill pulls status, diagnostics, pending decisions, and recent events, then asks Mission Control for recovery guidance when available.

### `mission-control-swarm`

Use when the user wants to inspect or adjust swarm strategy. This skill explains the current swarm plan and routes safe preference changes through Mission Control approval rules.

### `mission-control-safe-mode`

Use when the user wants stricter safety. This skill tightens approvals, pauses dynamic spawning when supported, preserves read-only import posture, and restricts risky tools.

### `mission-control-resume`

Use in a new Codex chat when the user wants to continue later. This skill reattaches the workspace, finds the active orchestration, surfaces pending decisions, and resumes only if the user asks.

### `mission-control-agents-md`

Use to review or generate `AGENTS.md`. This skill reads the codebase map, checks existing `AGENTS.md` status, requests a proposal, and asks the user before any write step.

## Skill Design Requirements

Each `SKILL.md` in this pack includes:

- purpose
- when to use
- required Mission Control tools, resources, and prompts
- step-by-step workflow
- what to show the user in Codex chat
- safety and approval behavior
- fallback behavior if the daemon is unavailable
- what not to do

## Compatibility Note

Some earlier placeholder skills still exist in the repo for compatibility or historical context. The headless Codex-chat pack for this pass is the ten-skill set listed above.
