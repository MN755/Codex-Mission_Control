# Check Status

## User Message

`What is Mission Control doing right now?`

## Tool, Resource, And Prompt Sequence

1. Prompt: `continue-orchestration`
2. Resource: `mission-control://orchestrations/{orchestration_id}/status`
3. Resource: `mission-control://projects/{project_id}/agents`
4. Resource: `mission-control://projects/{project_id}/pending-decisions`

## Expected Codex Chat Response

Return a compact markdown status summary with phase, manager note, active agents, blockers, and pending decisions.
