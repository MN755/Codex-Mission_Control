# Generate AGENTS.md proposal


Canonical prompt: `generate_agents_md_proposal`
Invocation name: `generate_agents_md_proposal`

## Purpose

Produce a chat-friendly AGENTS.md proposal from Mission Control's codebase understanding.

## Tool Sequence

- `mission_control_get_codebase_map`
- `mission_control_get_agents_md_status`
- `mission_control_generate_agents_md`

## Resource Sequence

- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/agent-contracts`

## Safety Notes

Ask before writing or replacing AGENTS.md.

## Prompt Text

Generate an AGENTS.md proposal through Mission Control. Use the codebase map and AGENTS.md status, then present the proposal in Codex chat and ask the user whether to accept or revise it.
