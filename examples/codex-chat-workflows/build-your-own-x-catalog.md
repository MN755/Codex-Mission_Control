# Build-Your-Own-X Catalog

## User Message

`Use Mission Control for this repo and help me build something ambitious from scratch. Show me a few strong directions and start with the one I choose.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `ask-manager-for-plan`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_get_workspace_tooling`
5. Tool: `mission_control_get_tool_catalog`
6. Tool: `mission_control_generate_swarm_plan`
7. Tool: `mission_control_get_pending_decisions`
8. Resource: `mission-control://projects/{project_id}/workspace-tooling`
9. Resource: `mission-control://projects/{project_id}/swarm-plan`
10. Resource: `mission-control://projects/{project_id}/verification-brief`

## Example Project Directions

- `3D Renderer`, `Voxel Engine`, `Physics Engine`, `Game`, `Augmented Reality`
- `AI Model`, `Neural Network`, `Visual Recognition System`
- `BitTorrent Client`, `Bot`, `Network Stack`, `Search Engine`, `Web Server`, `Web Browser`
- `Database`, `Blockchain / Cryptocurrency`
- `Programming Language`, `Shell`, `Regex Engine`, `Template Engine`, `Text Editor`, `Command-Line Tool`, `Git`
- `Operating System`, `Processor`, `Memory Allocator`, `Emulator / Virtual Machine`, `Docker`
- `Front-end Framework / Library`
- `Uncategorized`

## Expected Codex Chat Response

Return a short shortlist of buildable project archetypes, the recommended starting architecture for each, the detected local toolchain, and the first blocking decision that Mission Control needs from the user.
