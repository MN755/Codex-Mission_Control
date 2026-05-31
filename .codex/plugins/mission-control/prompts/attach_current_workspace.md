# Attach current workspace


Canonical prompt: `attach_current_workspace`
Invocation name: `attach_current_workspace`

## Purpose

Attach the current folder to Mission Control and report the safest next step.

## Tool Sequence

- `mission_control_attach_workspace`
- `mission_control_get_status`

## Resource Sequence

- `mission-control://projects/{project_id}/status`

## Safety Notes

Prefer read-only import posture for existing codebases and do not expose secrets.

## Prompt Text

Attach the current workspace to Mission Control. Reuse an existing project or orchestration if safe. If the folder looks like an existing codebase, prefer read-only first behavior. Summarize the attach result and the safest next step in compact markdown.
