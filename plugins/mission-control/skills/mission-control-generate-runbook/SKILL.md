---
name: mission-control-generate-runbook
description: Generate an operational runbook through Mission Control. Use when the user wants RUNBOOK.md or a chat-native runbook covering startup, tests, build, debugging, local reset, logs, and deployment notes.
---

# Mission Control Generate Runbook

## Purpose

Generate or summarize a runbook grounded in Mission Control evidence and repo understanding.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants a runbook.
- A handoff should include stronger operational guidance.
- Support or onboarding documentation is needed.

## Workflow

1. Read codebase map and handoff resources.
2. Ask Mission Control to generate a runbook or prepare a runbook summary.
3. Present the proposed sections and ask before writing any file.

## Mission Control calls

Tools:
- `mission_control_get_handoff_summary`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Cover start dev server, run tests, build, debug common failures, reset local state, logs, and deployment if configured.
- Tell the user whether the result is chat-only or ready to write to `RUNBOOK.md`.

## Approval behavior

Ask before writing or overwriting runbook files.

## Never do

- Do not invent commands that are not backed by the repo or handoff.
- Do not write files silently.
- Do not expose raw logs.

## Failure and fallback

If runbook generation is not exposed yet, use handoff and codebase understanding to produce a chat-native runbook and mark file generation as expected or future.

## Example invocation

`Use Mission Control to generate a runbook for this repo.`
