---
name: mission-control-resume
description: Use when a new Codex chat needs to reconnect to a recent Mission Control orchestration safely.
---

# Mission Control Resume

## Purpose

Reconnect Codex chat to the current workspace's active or recent Mission Control orchestration.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- The user opens a new Codex chat and wants to continue later
- The user says `resume Mission Control`
- The bridge needs to find the last known orchestration

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_attach_workspace`, `mission_control_get_status`, `mission_control_get_pending_decisions`, `mission_control_resume`
- Resources: `mission-control://orchestrations/{orchestration_id}/status`, `mission-control://projects/{project_id}/pending-decisions`
- Prompts: `attach-current-workspace`, `resume-orchestration`, `continue-orchestration`

## Step-By-Step Workflow

1. Attach the current workspace.
2. Find the active or reused orchestration from the attach result.
3. Return the last known state.
4. Surface pending decisions.
5. Resume only if Mission Control reports the run is paused and the user asks to continue.

## What To Show The User In Codex Chat

- Reused project or orchestration ID
- Current status and manager note
- Pending approvals or questions
- Whether the run was resumed

## Safety And Approval Behavior

- Do not auto-resume on attach.
- Respect any pending decision before continuing execution.

## Fallback Behavior If The Daemon Is Unavailable

- Say the previous orchestration could not be recovered from Mission Control.
- Offer to debug the bridge or wait until the daemon is back.

## What Not To Do

- Do not create a new plan if a paused orchestration already exists.
- Do not resume automatically just because an orchestration was found.
