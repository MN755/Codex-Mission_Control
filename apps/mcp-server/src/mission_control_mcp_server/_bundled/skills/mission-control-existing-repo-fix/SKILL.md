---
name: mission-control-existing-repo-fix
description: Run a direct Mission Control fix workflow for an existing repo. Use when the task is a bugfix or targeted change in a non-empty codebase and the Manager should classify the request, plan narrowly, request write permission, and execute safely.
---

# Mission Control Existing Repo Fix

## Purpose

Route targeted fixes in an existing repo through Mission Control with minimal detours.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants a bug fixed in an existing folder.
- A targeted change should not trigger a blank-project flow.
- Write permission and codebase understanding both matter.

## Workflow

1. Attach the workspace and import it as an existing codebase.
2. Run or read a codebase scan.
3. Ask the Manager to classify the request and create a targeted plan.
4. Request write permission if Mission Control requires it.
5. Run the orchestration and keep approvals flowing through chat.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_import_existing_codebase`
- `mission_control_start_task`
- `mission_control_get_pending_decisions`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show the classified task type, narrow plan, write-permission status, and next checkpoint.
- Avoid giant repo tours unless the user asks for them.

## Approval behavior

Write permission, risky commands, and scope expansions still need approval when Mission Control policy requires them.

## Never do

- Do not treat a mature repo like a new greenfield project.
- Do not start editing before import safety is understood.
- Do not bypass approvals to move faster.

## Failure and fallback

If repo-fix workflow tooling is partial, combine import-codebase, codebase-map, and Manager-led task flows and make the narrow-fix intent explicit. If the bridge registered but named tools hidden in this session, say that exact partial state instead of pretending Mission Control disappeared.

## Example invocation

`Use Mission Control to fix this existing repo without doing a full greenfield setup flow.`
