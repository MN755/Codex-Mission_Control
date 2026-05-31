---
name: mission-control-swarm
description: Inspect or adjust Mission Control swarm behavior. Use when the user wants to show the swarm plan, explain agent roles, scale up or down, change strategy, pause dynamic spawning, resume dynamic spawning, or inspect active agents.
---

# Mission Control Swarm

## Purpose

Inspect the swarm plan and route any swarm changes through Mission Control.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks how the swarm is organized.
- The user wants to scale up, scale down, or switch swarm strategy.
- Agent activity needs a coordinated explanation.

## Workflow

1. Read the swarm plan and active agents resources.
2. Explain current swarm shape, role assignments, ownership boundaries, and approvals.
3. If the user requests a change, route it through Mission Control tools or prompts.
4. Require explicit approval before scaling above the configured threshold or changing risk posture.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task` (for swarm-change requests)
- `mission_control_pause` and `mission_control_resume` when pausing or resuming swarm activity is supported

Resources:
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show swarm plan, active agents, ownership boundaries, approval state, and any scaling warnings.
- If change is requested, explain what Mission Control will need from the user next.

## Approval behavior

Never scale above threshold, broaden write scope, or change dynamic spawning policy without user approval or an explicit Mission Control approval record.

## Never do

- Do not invent your own swarm topology.
- Do not spawn workers outside Mission Control.
- Do not bypass swarm approvals.

## Failure and fallback

If direct swarm controls are not exposed yet, explain the current swarm from resources and treat any adjustment as an expected or future Mission Control task request.

## Example invocation

`Show the swarm plan and explain whether we should scale up.`
