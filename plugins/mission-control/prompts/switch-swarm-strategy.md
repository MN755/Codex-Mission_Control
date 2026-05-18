# Switch Swarm Strategy

## Purpose

Change the Mission Control swarm posture and summarize the updated plan or approval requirement.

## Required Arguments

- `PROJECT_ID`
- `STRATEGY_REQUEST`

## Intended Tool And Resource Sequence

1. Call `mission_control_update_swarm_preferences`.
2. Call `mission_control_generate_swarm_plan`.
3. Call `mission_control_get_swarm_plan`.

## Expected User-Facing Codex Chat Output

- Updated preferences
- Revised plan summary
- Approval warning if the new posture crosses a threshold

## Safety Notes

- Respect Mission Control approval policy for large or risky swarms.
- Do not scale blindly.
