---
name: mission-control
description: Use when Codex should act as the bridge into Mission Control instead of acting like the Manager AI itself.
---

# Mission Control

Use this skill when the user wants Codex to work through Mission Control for planning, execution, approvals, status, or final handoff.

## Bridge boundary

- Codex chat is the bridge between the user and Mission Control.
- Codex chat is not the Manager AI.
- Mission Control Manager owns planning, orchestration, worker routing, recovery actions, and completion state.

## Mission Control MCP tools to call

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_pause`
- `mission_control_resume`
- `mission_control_get_handoff`
- `mission_control_open_dashboard`

## Mission Control resources it may read

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## Decisions that must be passed to the user

- Which project or workspace Mission Control should operate on
- Any manager clarification question that affects scope, risk, or priority
- Any approval request before the decision tool is called
- Whether to fall back to non-Mission-Control work if the bridge is unavailable

## Workflow

1. Prove the Mission Control bridge surface before guessing:
   - prefer the named `mission_control_*` tools when the session exposes them
   - if tool exposure is unclear, verify MCP registration or resource visibility before claiming Mission Control is unavailable
2. Identify or open the Mission Control project that matches the user request.
3. Attach the workspace if needed, then start or continue the orchestration through `mission_control_start_task`.
4. Poll status and pending decisions instead of guessing.
5. Return every manager question or approval to the user exactly when it matters.
6. Retrieve the handoff only after Mission Control reports that work is complete.

## Verification rule

- Do not say the Mission Control MCP surface is unavailable unless you actually verified it.
- A stale path, a missing cache file, or a partial resource listing is not proof.
- In Codex CLI sessions, use `codex mcp list` when needed to distinguish "server registered" from "server callable here."
- If the MCP server is registered but the named tool surface is not exposed in the current session, say that precisely.
- If the bridge is degraded, surface that as a bridge problem, not as if the codebase itself caused it.

## Codex chat must not do

- Do not invent a manager plan or worker roster locally.
- Do not spawn side workers outside Mission Control mode.
- Do not answer approvals or questions on the user's behalf.
- Do not claim Mission Control executed anything if the bridge did not confirm it.
- Do not edit the repo directly once the user chose the Mission Control path unless the user explicitly abandons that path.
