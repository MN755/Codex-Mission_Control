---
name: mission-control-tool-policy
description: Inspect or update Mission Control tool-routing and permission policy. Use when the user wants to see allowed tools, blocked tools, approval-required tools, or per-agent archetype tool constraints.
---

# Mission Control Tool Policy

## Purpose

Explain or request tool-policy changes without bypassing the policy itself.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks which tools are allowed.
- Approval-required tools need explanation.
- A policy change is needed for a task.

## Workflow

1. Review current status and any tool-policy or approval state that Mission Control exposes.
2. Summarize allowed, blocked, and approval-required tools plus any archetype-specific constraints.
3. Route requested policy changes back through Mission Control rather than mutating them directly in chat.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show the effective tool policy, notable restrictions, and what the user would need to approve to loosen it.
- Keep the summary bridge-safe rather than dumping backend config.

## Approval behavior

Tool-policy changes are explicit policy decisions and should be confirmed with the user before they are requested.

## Never do

- Do not override the tool policy from chat.
- Do not blur approval-required and fully allowed tools.
- Do not claim blocked tools are available.

## Failure and fallback

If dedicated tool-policy state is not exposed, infer current policy from pending approvals and known Mission Control controls, and label that inference clearly.

## Example invocation

`Show the Mission Control tool policy for this project.`
