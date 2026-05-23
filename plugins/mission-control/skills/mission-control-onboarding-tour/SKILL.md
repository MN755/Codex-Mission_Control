---
name: mission-control-onboarding-tour
description: Generate a guided onboarding tour for a codebase using Mission Control's project map, domains, commands, risks, and recommended reading order.
---

# Mission Control Onboarding Tour

## Purpose

Produce an ordered learning path through a repo instead of dumping a file tree and calling it help.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A user is new to a repo.
- The team needs onboarding docs.
- A handoff should include how to understand the system.

## Workflow

1. Ask Mission Control for codebase map, commands, architecture, and domain notes.
2. Build a reading order by dependency and concept difficulty.
3. Include setup, run/test commands, key files, common workflows, and risks.
4. Mark unknown or unverified sections clearly.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Return a guided tour with stages, files to read, concepts learned, and next tasks.

## Approval behavior

Ask before writing onboarding docs into the repo.

## Never do

- Do not create onboarding docs from stale scans.
- Do not hide setup gaps.
- Do not overexplain obvious files while skipping architecture seams.

## Failure and fallback

If no map exists, ask to import the codebase first.

## Example invocation

`Use Mission Control to create a new-engineer onboarding tour for this repo.`
