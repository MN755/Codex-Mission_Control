# Build Programming Language Or Shell

## User Message

`Use Mission Control for this repo and build a programming language, shell, regex engine, template engine, or text editor from scratch.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_generate_swarm_plan`
5. Tool: `mission_control_get_tool_catalog`
6. Tool: `mission_control_get_pending_decisions`
7. Resource: `mission-control://projects/{project_id}/swarm-plan`
8. Resource: `mission-control://projects/{project_id}/agent-contracts`
9. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the parser, runtime, editing, and validation strategy, the proposed swarm split for compiler or shell work, and the first decision Mission Control needs before coding starts.
