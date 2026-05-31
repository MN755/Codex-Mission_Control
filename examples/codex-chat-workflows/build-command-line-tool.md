# Build Command-Line Tool

## User Message

`Use Mission Control for this repo and build a polished command-line tool from scratch, with tests, help text, and release-ready validation.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `use-mission-control-for-this-repo`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_get_workspace_tooling`
5. Tool: `mission_control_get_tool_catalog`
6. Tool: `mission_control_generate_swarm_plan`
7. Tool: `mission_control_get_pending_decisions`
8. Resource: `mission-control://projects/{project_id}/workspace-tooling`
9. Resource: `mission-control://projects/{project_id}/swarm-plan`
10. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the detected toolchain, the proposed language and packaging path, the validation plan, and any approval or scope decision that blocks the first implementation pass.
