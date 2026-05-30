# Generate AGENTS.md Proposal

## Purpose

Create a Codex-chat-friendly `AGENTS.md` proposal using Mission Control context.

## Required Arguments

- `PROJECT_ID`

## Intended Tool And Resource Sequence

1. Call `mission_control_get_codebase_map`.
2. Call `mission_control_get_agents_md_status`.
3. Call `mission_control_generate_agents_md`.
4. Read `mission-control://projects/{project_id}/codebase-map`.
5. Read `mission-control://projects/{project_id}/agent-contracts`.

## Expected User-Facing Codex Chat Output

- Whether `AGENTS.md` already exists
- Recommended target path
- Proposal summary
- Proposed sections and commands

## Safety Notes

- Ask before any write step.
- Keep the proposal grounded in actual repo context.
