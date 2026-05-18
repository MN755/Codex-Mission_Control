---
name: mission-control-handoff
description: Use when the user wants the final Mission Control handoff, evidence summary, and next steps.
---

# Mission Control Handoff

## Purpose

Retrieve the latest Mission Control handoff and present it as a clean Codex chat summary.

## Bridge Rule

The Codex chat agent is not the Mission Control Manager. It is the bridge.

## When To Use

- `Show me the handoff`
- `What's the final output?`
- `Summarize the result`

## Required Mission Control Tools, Resources, And Prompts

- Tools: `mission_control_get_handoff`, `mission_control_get_status`
- Resources: `mission-control://projects/{project_id}/handoff`, `mission-control://projects/{project_id}/validation-summary`
- Prompts: `review-latest-handoff`

## Step-By-Step Workflow

1. Retrieve the handoff.
2. Summarize what changed.
3. Summarize how to run it.
4. Summarize validation and evidence.
5. Summarize limitations and next steps.
6. Warn if the handoff is dry-run or missing evidence.

## What To Show The User In Codex Chat

- What changed
- Run instructions
- Validation or evidence posture
- Known limitations
- Recommended next steps

## Safety And Approval Behavior

- Say clearly when evidence is partial, missing, or simulated.
- Do not overstate readiness.

## Fallback Behavior If The Daemon Is Unavailable

- Report that the handoff could not be retrieved from Mission Control.
- Suggest a later retry or `mission-control-debug`.

## What Not To Do

- Do not pretend Codex produced the handoff itself.
- Do not hide missing evidence.
- Do not rewrite a non-ready handoff into a success story.
