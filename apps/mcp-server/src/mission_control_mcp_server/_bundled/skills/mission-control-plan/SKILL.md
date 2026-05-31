---
name: mission-control-plan
description: Ask Mission Control Manager to create or revise a plan. Use when the user asks for a plan, scope changes, imported codebases need planning, or the next milestone and validation strategy need clarification before execution.
---

# Mission Control Plan

## Purpose

Request a Mission Control plan or plan revision without taking over planning directly.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for a plan.
- Scope changes require replanning.
- A codebase was imported and needs structured milestones before execution.

## Workflow

1. Check current status and swarm plan resources first.
2. Ask Mission Control Manager to create or revise the plan through `mission_control_start_task` or plan-specific workflow prompts.
3. Return the plan summary with milestones, validation strategy, swarm strategy, and needed user decisions.
4. If the plan implies approvals, surface them instead of auto-applying them.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Show goal, assumptions, milestones, validation strategy, swarm strategy, risks, and user decisions needed.
- Call out whether the plan is new, revised, approved, or waiting on feedback.

## Approval behavior

If the plan changes scope, cost, model policy, or swarm scale, get user approval before asking Mission Control to execute it.

## Never do

- Do not silently replace the Manager's plan with your own.
- Do not claim approval status that Mission Control did not report.
- Do not skip surfaced assumptions.

## Failure and fallback

If plan-specific tooling is thin, use status and swarm resources to summarize current planning state and route the actual plan request through the Manager-led task flow.

## Example invocation

`Ask Mission Control Manager for a plan for this imported repo.`
