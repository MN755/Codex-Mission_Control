---
name: mission-control-model-policy
description: Inspect or update Mission Control model-assignment policy. Use when the user wants to understand or change cost-saving, balanced, best-quality, local-first, or custom model routing across Manager, coding, docs, review, and fallback roles.
---

# Mission Control Model Policy

## Purpose

Explain or request model-policy changes while keeping billing and auth boundaries explicit.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks which models are being used.
- Cost or quality posture needs adjustment.
- Local-first or custom model routing should be requested.

## Workflow

1. Read current project status and model-policy-related state if exposed.
2. Summarize Manager model, coding model, docs model, review or security model, and fallback model.
3. If the user wants a change, route it through Mission Control policy controls or a Manager-led task.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`

## User-facing output

- Show the current policy and the tradeoffs among cost, speed, quality, and locality.
- Warn clearly if a requested change may use API-billed providers.

## Approval behavior

Do not switch to API-billed or higher-cost modes without explicit user awareness and approval.

## Never do

- Do not ask for raw API keys in chat.
- Do not claim a policy changed if the backend did not accept it.
- Do not hide billing implications.

## Failure and fallback

If model-policy controls are not first-class yet, explain the expected policy states and route the requested change through a Manager-led planning or settings task.

## Example invocation

`Show the Mission Control model policy and switch to balanced if needed.`
