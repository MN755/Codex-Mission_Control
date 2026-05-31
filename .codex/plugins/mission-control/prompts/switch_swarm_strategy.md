# Switch swarm strategy


Canonical prompt: `switch_swarm_strategy`
Invocation name: `switch_swarm_strategy`

## Purpose

Request a change to swarm strategy and summarize the updated plan or approval requirement.

## Tool Sequence

- `mission_control_update_swarm_preferences`
- `mission_control_generate_swarm_plan`
- `mission_control_get_swarm_plan`

## Resource Sequence

- `mission-control://projects/{project_id}/swarm-plan`

## Safety Notes

Respect Mission Control approval thresholds for larger or riskier swarms.

## Prompt Text

Switch the Mission Control swarm strategy according to the user's request, regenerate or refresh the plan if needed, and summarize the updated plan with any approval implications.
