---
name: mission-control-local-first
description: Switch Mission Control toward local-first behavior. Use when the user wants local files, local models, no cloud deployment, and no external APIs unless explicitly approved.
---

# Mission Control Local First

## Purpose

Bias the project toward local-first execution and explain the resulting constraints.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants local-first behavior.
- Cloud deployment or external APIs should be avoided.
- Privacy or offline constraints dominate.

## Workflow

1. Explain what local-first means for the project: local files, local models when configured, no cloud deployment, and external APIs only with approval.
2. Route the policy change through Mission Control.
3. Confirm status after the policy change and show any unsupported controls.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Summarize the local-first posture and any tradeoffs in capability, speed, or evidence depth.
- Tell the user which external actions are now blocked or approval-gated.

## Approval behavior

Switching posture is a project-level decision. Confirm it explicitly before requesting the change.

## Never do

- Do not imply that local-only guarantees exist if some tools still depend on external services.
- Do not enable deployments or external APIs while claiming local-first.
- Do not ask for API keys in this flow.

## Failure and fallback

If no local-first toggle exists yet, document the intended constraints in chat, route them through Manager planning, and continue with the most conservative behavior available.

## Example invocation

`Switch this project to Mission Control local-first mode.`
