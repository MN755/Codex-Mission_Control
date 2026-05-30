# Check Status

## User Message

`What is Mission Control doing right now?`

## Tool, Resource, And Prompt Sequence

1. Prompt: `continue-orchestration`
2. Tool: `mission_control_get_status`
3. Tool: `mission_control_get_pending_decisions`
4. Tool: `mission_control_get_event_digest`
5. Resource: `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
6. Resource: `mission-control://projects/{project_id}/agents`
7. Resource: `mission-control://projects/{project_id}/pending-decisions`

## Expected Codex Chat Response

Return a compact markdown status summary with phase, manager note, active agents, blockers, and pending decisions.
