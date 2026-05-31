---
name: mission-control-docs-heavy
description: Switch the project toward documentation-heavy Mission Control work. Use when the user wants the swarm or plan to prioritize README, guides, examples, docs review, or public-facing written material more than feature code.
---

# Mission Control Docs Heavy

## Purpose

Bias Mission Control toward documentation-heavy execution without directly spawning doc writers from chat.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants documentation first.
- The repo needs README, guides, examples, or API docs work.
- Release or public publication depends on better docs.

## Workflow

1. Review current handoff, plan, and swarm resources.
2. Ask Mission Control to prioritize docs-heavy work and the relevant agent roles or milestones.
3. Explain what documentation areas will be emphasized and what approvals may be needed.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Identify the desired doc roles: README writer, user guide writer, developer guide writer, API docs writer, examples writer, or docs reviewer.
- Summarize the docs-heavy objective and next checkpoint.

## Approval behavior

If docs-heavy mode changes swarm scale, write scope, or release posture, get user approval through Mission Control before execution.

## Never do

- Do not spawn documentation agents yourself.
- Do not confuse docs priority with UI work.
- Do not claim public readiness without review.

## Failure and fallback

If docs-mode controls are not first-class yet, express the priority as a Manager-led task request and track it through status and handoff outputs.

## Example invocation

`Switch this Mission Control project into docs-heavy mode.`
