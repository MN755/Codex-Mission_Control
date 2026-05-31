# Build Game Or Renderer

## User Message

`Use Mission Control for this repo and build something graphics-heavy from scratch, like a game, 3D renderer, voxel engine, physics engine, or AR prototype.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_get_workspace_tooling`
5. Tool: `mission_control_get_nvidia_local_runtime_status`
6. Tool: `mission_control_get_nvidia_validation_plan`
7. Tool: `mission_control_generate_swarm_plan`
8. Resource: `mission-control://projects/{project_id}/workspace-tooling`
9. Resource: `mission-control://projects/{project_id}/nvidia-local-runtime`
10. Resource: `mission-control://projects/{project_id}/nvidia-validation-plan`
11. Resource: `mission-control://projects/{project_id}/swarm-plan`

## Expected Codex Chat Response

Return the rendering or simulation architecture, the local GPU/runtime readiness, the benchmark or profiling path, and any missing runtime prerequisites before Mission Control starts building.
