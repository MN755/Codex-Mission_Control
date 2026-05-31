---
name: mission-control-orchestrate
description: Primary Mission Control entrypoint for the current workspace. Use when the user says to use Mission Control, have Mission Control manage the repo, run the task through the Manager, or switch this chat into Mission Control bridge mode.
---

# Mission Control Orchestrate

## Purpose

Use Mission Control as the orchestrator for the current workspace and keep Codex in the bridge role.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user says to use Mission Control for this repo.
- The user wants Manager-led orchestration instead of direct local coding.
- A new Mission Control task should be attached, started, monitored, and handed back through chat.

## Workflow

1. Determine the current workspace path or project reference.
2. Call `mission_control_attach_workspace` to register or reuse the project.
3. Call `mission_control_start_task` with the user request.
4. Return a compact status summary from the status tool or resource.
5. Check `mission_control_get_pending_decisions` and relay any approvals or questions.
6. Poll only when useful instead of spamming status.
7. Retrieve handoff through `mission_control_get_handoff` or `mission_control_get_handoff_summary` when complete.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_get_handoff`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`

## User-facing output

- Report the attached project or orchestration identifier.
- Show current state, pending decisions, blockers, and next checkpoint.
- When done, summarize the handoff with evidence level and limitations.

## Approval behavior

Relay every pending approval or Manager question to the user. Do not continue past approval gates with guessed answers.

## Never do

- Do not act as the Manager directly.
- Do not independently spawn worker agents.
- Do not bypass Mission Control approvals or write-permission gates.

## Failure and fallback

If Mission Control tools or the bridge are unavailable, say so clearly, offer the direct local-coding fallback only with user awareness, and avoid pretending orchestration happened.

## Example invocation

`Use Mission Control for this repo and fix the failing tests.`
