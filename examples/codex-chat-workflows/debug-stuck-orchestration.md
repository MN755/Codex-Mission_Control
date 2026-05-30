# Debug Stuck Orchestration

## User Message

`Mission Control looks stuck. Debug it.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `debug-failed-orchestration`
2. Tool: `mission_control_get_status`
3. Tool: `mission_control_get_diagnostics`
4. Tool: `mission_control_get_pending_decisions`
5. Tool: `mission_control_get_event_digest`
6. Tool: `mission_control_request_recovery_plan`
7. Resource: `mission-control://projects/{project_id}/diagnostics`
8. Resource: `mission-control://projects/{project_id}/decision-ledger`

## Expected Codex Chat Response

Return a concise blocker explanation, recent events, whether the issue is user-blocked or infrastructure-blocked, and safe recovery options.
