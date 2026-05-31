# Explain current swarm

Alias for `explain_current_swarm`.
Canonical prompt: `explain_current_swarm`
Invocation name: `explain-current-swarm`

## Purpose

Explain the active or proposed Mission Control swarm plan in compact Codex chat language.

## Tool Sequence

- `mission_control_get_swarm_plan`

## Resource Sequence

- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/risk-register`

## Safety Notes

Do not invent a swarm plan if Mission Control has not produced one.

## Prompt Text

Explain the current Mission Control swarm plan. Keep it short, include mode, size, risks, dynamic spawning state, and whether any approval gates apply.
