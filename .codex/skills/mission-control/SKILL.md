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

- `mission_control_list_projects`
- `mission_control_open_project`
- `mission_control_send_manager_message`
- `mission_control_get_project_status`
- `mission_control_get_project_action`
- `mission_control_get_pending_questions`
- `mission_control_get_pending_approvals`
- `mission_control_get_handoff`

## Mission Control resources it may read

- `mission-control://projects/current/summary`
- `mission-control://projects/current/workspace`
- `mission-control://projects/current/actions`
- `mission-control://projects/current/manager/queue`

## Decisions that must be passed to the user

- Which project or workspace Mission Control should operate on
- Any manager clarification question that affects scope, risk, or priority
- Any approval request before the decision tool is called
- Whether to fall back to non-Mission-Control work if the bridge is unavailable

## Workflow

1. Identify or open the Mission Control project that matches the user request.
2. Relay the user request to the manager through `mission_control_send_manager_message`.
3. Poll status, actions, pending questions, and pending approvals instead of guessing.
4. Return every manager question or approval to the user exactly when it matters.
5. Retrieve the handoff only after Mission Control reports that work is complete.

## Codex chat must not do

- Do not invent a manager plan or worker roster locally.
- Do not spawn side workers outside Mission Control mode.
- Do not answer approvals or questions on the user's behalf.
- Do not claim Mission Control executed anything if the bridge did not confirm it.
- Do not edit the repo directly once the user chose the Mission Control path unless the user explicitly abandons that path.
