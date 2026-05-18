# Explain Current Swarm

## Purpose

Explain the active or proposed Mission Control swarm plan in compact Codex chat language.

## Required Arguments

- `PROJECT_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_swarm_plan`.
2. Read `mission-control://projects/{project_id}/agents`.
3. Read `mission-control://projects/{project_id}/risk-register`.

## Expected User-Facing Codex Chat Output

- Current swarm mode
- Agent count
- Dynamic spawning state
- Risks and bottlenecks

## Safety Notes

- Do not invent a plan if Mission Control does not have one.
- Keep this explanatory unless the user asks for a change.
