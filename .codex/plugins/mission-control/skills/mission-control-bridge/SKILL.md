---
name: mission-control-bridge
description: Use when Codex should relay user intent to Mission Control instead of acting as the Manager itself.
---

# Mission Control Bridge

Use this skill when the user asks Codex to use Mission Control for the current workspace.

## Rule zero

Codex chat is the bridge. Mission Control Manager is the manager. If Codex starts freelancing as the manager here, the whole architecture turns into self-parody.

## Tool flow

1. Call `mission_control_attach_workspace`.
2. Call `mission_control_start_task`.
3. Poll `mission_control_get_status`.
4. If needed, read `mission_control_get_pending_decisions`.
5. Ask the user for the decision.
6. Send the answer back with `mission_control_answer_decision`.
7. Retrieve the final result with `mission_control_get_handoff`.

## Guardrails

- Do not bypass Mission Control approvals.
- Do not run worker commands directly from Codex chat.
- Do not claim completion until Mission Control reports readiness.
- Use `mission_control_open_dashboard` only as an optional convenience.
