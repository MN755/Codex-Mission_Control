# Build Data And Search System

## User Message

`Use Mission Control for this repo and build a small database or search engine from scratch, with a benchmarkable query path and evidence-backed tests.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_generate_swarm_plan`
5. Tool: `mission_control_get_status`
6. Tool: `mission_control_get_pending_decisions`
7. Resource: `mission-control://projects/{project_id}/swarm-plan`
8. Resource: `mission-control://projects/{project_id}/codebase-map`
9. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the proposed storage and indexing design, the split between parser, storage, and validation work, and the next user decision if Mission Control needs one before building.
