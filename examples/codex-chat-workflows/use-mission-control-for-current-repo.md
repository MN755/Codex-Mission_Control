# Use Mission Control For Current Repo

## User Message

`Use Mission Control for this repo and fix the failing tests.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `use-mission-control-for-this-repo`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Resource: `mission-control://orchestrations/{orchestration_id}/status`
5. Tool: `mission_control_get_pending_decisions`

## Expected Codex Chat Response

Return the attached project or orchestration ID, a compact status summary, and any pending user decision that blocks the run.
