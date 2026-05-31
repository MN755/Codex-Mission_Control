# Build Web Stack

## User Message

`Use Mission Control for this repo and build a substantial web project from scratch, like a web server, web browser, or front-end framework, and validate it headlessly.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `use-webwright-for-browser-task`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_get_workspace_tooling`
5. Tool: `mission_control_get_webwright_status`
6. Tool: `mission_control_generate_swarm_plan`
7. Tool: `mission_control_get_pending_decisions`
8. Resource: `mission-control://projects/{project_id}/workspace-tooling`
9. Resource: `mission-control://projects/{project_id}/webwright`
10. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the proposed server, client, and validation lanes, whether browser automation is ready, and the first approval or architecture question that blocks implementation.
