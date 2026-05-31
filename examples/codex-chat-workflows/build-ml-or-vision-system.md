# Build ML Or Vision System

## User Message

`Use Mission Control for this repo and build an AI model, neural network, or visual recognition system from scratch, with a real training and evaluation plan.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_get_nvidia_local_runtime_status`
5. Tool: `mission_control_get_nvidia_validation_plan`
6. Tool: `mission_control_generate_swarm_plan`
7. Tool: `mission_control_get_pending_decisions`
8. Resource: `mission-control://projects/{project_id}/nvidia-local-runtime`
9. Resource: `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
10. Resource: `mission-control://projects/{project_id}/nvidia-validation-plan`
11. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the model or dataset plan, the GPU readiness summary, the training and evaluation loop Mission Control intends to use, and any blocker around data, runtime, or approvals.
