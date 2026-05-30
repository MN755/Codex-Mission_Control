# Answer Manager Question

## User Message

`Tell Mission Control to use the quick clarification path.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `show-pending-approvals`
2. Tool: `mission_control_get_pending_decisions`
3. Prompt: `answer-pending-approval`
4. Tool: `mission_control_answer_decision`
5. Tool: `mission_control_get_pending_decisions`

## Expected Codex Chat Response

Render the manager question, explain the options, record the user's answer, and report whether more decisions remain.
