# Build Networked System

## User Message

`Use Mission Control for this repo and build something network-heavy from scratch, like a BitTorrent client, bot, blockchain prototype, or custom network stack.`

## Tool, Resource, And Prompt Sequence

1. Prompt: `use-mission-control-for-this-repo`
2. Tool: `mission_control_attach_workspace`
3. Tool: `mission_control_start_task`
4. Tool: `mission_control_generate_swarm_plan`
5. Tool: `mission_control_enable_safe_mode`
6. Tool: `mission_control_get_pending_decisions`
7. Tool: `mission_control_get_diagnostics`
8. Resource: `mission-control://projects/{project_id}/swarm-plan`
9. Resource: `mission-control://projects/{project_id}/diagnostics`
10. Resource: `mission-control://projects/{project_id}/verification-brief`

## Expected Codex Chat Response

Return the proposed protocol, safety posture, validation plan, and any approval gates that Mission Control wants enabled before touching risky networking behavior.
