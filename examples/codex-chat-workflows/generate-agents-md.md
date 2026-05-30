# Generate AGENTS.md

## User Message

`Generate an AGENTS.md proposal for this project.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `generate-agents-md-proposal`
2. Tool: `mission_control_get_codebase_map`
3. Tool: `mission_control_get_agents_md_status`
4. Tool: `mission_control_generate_agents_md`
5. Resource: `mission-control://projects/{project_id}/codebase-map`
6. Resource: `mission-control://projects/{project_id}/agent-contracts`

## Expected Codex Chat Response

Show whether AGENTS.md exists, the recommended target path, the proposal summary, and the proposed sections. Ask for approval before any write step.
