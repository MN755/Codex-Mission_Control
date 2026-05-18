---
name: mission-control-handoff
description: Retrieve and present the final Mission Control handoff. Use when the user asks for the finished result, final summary, what changed, how to run it, evidence, limitations, or next tasks.
---

# Mission Control Handoff

## Purpose

Present the Mission Control handoff as a clean, evidence-aware final summary.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The orchestration is complete or near complete.
- The user asks for the handoff or final report.
- You need to verify what changed and what evidence backs it.

## Workflow

1. Call `mission_control_get_handoff` or `mission_control_get_handoff_summary`.
2. Read the handoff resource for status, evidence level, and limitations.
3. Summarize what changed, how to run, validation or evidence, important files, and next tasks.
4. Warn explicitly if the run was dry-run, incomplete, or weakly evidenced.

## Mission Control calls

Tools:
- `mission_control_get_handoff`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Show status, confidence or evidence level, what changed, how to run, validation or evidence, known limitations, recommended next tasks, and important files or artifacts.
- Warn if tests were not run, evidence is missing, the handoff is incomplete, or the run was dry-run.

## Approval behavior

If the handoff requires explicit review or sign-off, relay that approval instead of declaring the work accepted.

## Never do

- Do not present a partial report as finished.
- Do not suppress missing evidence.
- Do not claim Codex performed the work directly.

## Failure and fallback

If no handoff exists yet, say so directly, provide the current status, and point the user to the blocking approvals or remaining tasks.

## Example invocation

`Get the Mission Control handoff and summarize what changed.`
