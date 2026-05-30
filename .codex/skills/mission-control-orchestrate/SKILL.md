---
name: mission-control-orchestrate
description: Use when Codex should route a workspace task through Mission Control instead of acting like the Manager AI.
---

# Mission Control Orchestrate

## Purpose

Start or continue a Mission Control-managed task from Codex chat without turning Codex into the manager.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- `Use Mission Control for this repo.`
- `Have Mission Control manage this.`
- `Run this through Mission Control.`
- `Use the Manager on this project.`

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_attach_workspace`, `mission_control_start_task`, `mission_control_get_status`, `mission_control_get_pending_decisions`, `mission_control_answer_decision`, `mission_control_get_handoff`
- Resources: `mission-control://projects/{project_id}/status`, `mission-control://projects/{project_id}/pending-decisions`, `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- Prompts: `attach-current-workspace`, `use-mission-control-for-this-repo`, `start-manager-led-task`, `continue-orchestration`

## Step-By-Step Workflow

1. Determine the current workspace path.
2. Call `mission_control_attach_workspace`.
3. Call `mission_control_start_task` with the user request.
4. Return a compact status summary.
5. Check `mission_control_get_pending_decisions`.
6. Surface pending approvals or questions in Codex chat.
7. Poll status only when useful, not on autopilot.
8. Retrieve `mission_control_get_handoff` when Mission Control reports completion.

## What To Show The User In Codex Chat

- Attached workspace or reused project/orchestration
- Current phase, manager status, and next expected action
- Pending decisions with risk and options
- Final handoff summary when ready

## Safety And Approval Behavior

- Respect Mission Control approval gates exactly as returned.
- Pass user answers back through `mission_control_answer_decision`.
- Treat imported codebases as read-first until Mission Control and the user allow writes.

## Fallback Behavior If The Daemon Is Unavailable

- Say that the Mission Control daemon or MCP bridge is unavailable.
- Do not fake orchestration progress.
- Ask whether the user wants to wait, debug the bridge, or fall back to direct Codex work.

## What Not To Do

- Do not independently spawn agents.
- Do not edit files outside Mission Control mode after the user chose this path.
- Do not bypass approvals.
- Do not claim the manager made a decision unless Mission Control returned it.
