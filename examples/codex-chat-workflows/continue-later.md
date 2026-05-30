# Continue Later

## User Message

`Resume Mission Control for this repo.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `attach-current-workspace`
2. Tool: `mission_control_attach_workspace`
3. Prompt: `continue-orchestration`
4. Tool: `mission_control_get_status`
5. Tool: `mission_control_get_pending_decisions`
6. Tool: `mission_control_get_event_digest`
7. Prompt: `resume-orchestration` only if the run is paused and the user wants to continue it
8. Tool: `mission_control_resume` if the user wants to continue a paused run

## Expected Codex Chat Response

Return the last known state, surface pending decisions, and resume only if the user asks and Mission Control says the run is paused.
