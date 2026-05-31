---
name: mission-control-refactor-safely
description: Run a safe Mission Control refactor workflow. Use when the user wants non-trivial refactors that need codebase understanding, snapshots, path locks, contracts, validation planning, and controlled risk.
---

# Mission Control Refactor Safely

## Purpose

Route refactors through Mission Control safety controls before code movement begins.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for a refactor.
- Changes may span multiple files or subsystems.
- Risk mitigation and validation planning matter.

## Workflow

1. Require codebase understanding first.
2. Request a snapshot or restore point if supported.
3. Check path locks and agent contracts.
4. Ask Mission Control for a validation plan before execution.
5. Run the refactor only after approvals and safety boundaries are clear.
6. Use the handoff to summarize changed files and residual risks.

## Mission Control calls

Tools:
- `mission_control_request_snapshot`
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Show whether understanding exists, whether a snapshot was requested, how validation will run, and what boundaries the refactor will respect.
- After completion, summarize changed files, validation results, and remaining risks.

## Approval behavior

Require explicit approval for broad rewrites, risky snapshots, or destructive restore steps.

## Never do

- Do not attempt a broad rewrite without understanding and validation.
- Do not restore or revert destructively without approval.
- Do not ignore path-lock or contract conflicts.

## Failure and fallback

If snapshot, path-lock, or contract resources are not fully implemented, make those missing protections explicit and let the user decide whether to proceed with reduced guarantees.

## Example invocation

`Use Mission Control to refactor this module safely with validation and rollback planning.`
