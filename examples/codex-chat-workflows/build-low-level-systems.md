# Build Low-Level Systems

## User Message

`Use Mission Control for this repo and build a low-level system from scratch, like an operating system, processor emulator, virtual machine, or memory allocator.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_request_snapshot`
5. Tool: `mission_control_generate_swarm_plan`
6. Tool: `mission_control_get_pending_decisions`
7. Resource: `mission-control://projects/{project_id}/swarm-plan`
8. Resource: `mission-control://projects/{project_id}/decision-ledger`
9. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the architecture split, the rollback posture, the safety and validation checkpoints, and any assumptions that Mission Control wants confirmed before it starts dangerous low-level work.
