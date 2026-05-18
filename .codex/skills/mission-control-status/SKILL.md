---
name: mission-control-status
description: Use when the user wants a compact Mission Control status summary, blocker report, or agent activity check.
---

# Mission Control Status

## Purpose

Report what Mission Control is doing without pretending that status and completion are the same thing.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- `What is Mission Control doing?`
- `What's the status?`
- `Are agents working?`
- `What's blocked?`

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_status`, `mission_control_get_pending_decisions`
- Resources: `mission-control://orchestrations/{orchestration_id}/status`, `mission-control://projects/{project_id}/agents`, `mission-control://projects/{project_id}/pending-decisions`
- Prompts: `continue-orchestration`, `show-pending-approvals`

## Step-By-Step Workflow

1. Read the orchestration status resource first.
2. Read the agents resource.
3. Read the pending decisions resource.
4. Return a compact markdown status summary.
5. If the run is complete, point the user to handoff retrieval.

## What To Show The User In Codex Chat

- Orchestration status and current phase
- Manager status and next expected action
- Active agent count and notable agent states
- Pending decision count
- Current blockers and handoff readiness

## Safety And Approval Behavior

- Surface unresolved approvals and questions before implying work can continue.
- Keep the summary compact and safe; do not dump raw logs.

## Fallback Behavior If The Daemon Is Unavailable

- Report that live status could not be read from Mission Control.
- Suggest `mission-control-debug` instead of inventing a status update.

## What Not To Do

- Do not say `done` unless handoff is actually ready.
- Do not blur blocked and active states together.
- Do not fabricate agent activity.
