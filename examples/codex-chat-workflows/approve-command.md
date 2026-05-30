# Approve Command

## User Message

`Approve the pending build command once.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `show-pending-approvals`
2. Tool: `mission_control_get_pending_decisions`
3. Prompt: `answer-pending-approval`
4. Tool: `mission_control_answer_decision`
5. Tool: `mission_control_get_pending_decisions`

## Expected Codex Chat Response

Render the approval with risk and options, send the user's selected answer back to Mission Control, and confirm the decision was recorded.
