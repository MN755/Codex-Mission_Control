# Review Handoff

## User Message

`Show me the Mission Control handoff.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `review-latest-handoff`
2. Tool: `mission_control_get_handoff_summary`
3. Resource: `mission-control://projects/{project_id}/handoff`
4. Resource: `mission-control://projects/{project_id}/validation-summary`

## Expected Codex Chat Response

Summarize what changed, how to run it, validation or evidence posture, limitations, and next steps. Warn if the handoff is dry-run or missing evidence.
