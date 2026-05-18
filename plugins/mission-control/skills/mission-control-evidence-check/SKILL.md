---
name: mission-control-evidence-check
description: Check whether Mission Control claims have backing evidence. Use when the user wants to know whether tests, builds, screenshots, artifacts, or handoff confidence are real, missing, weak, or dry-run only.
---

# Mission Control Evidence Check

## Purpose

Audit evidence quality behind Mission Control claims and handoffs.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user doubts a claim.
- A handoff needs an evidence review.
- Validation or artifact confidence matters before sign-off.

## Workflow

1. Review handoff, validation, and status resources.
2. Identify tests claimed but not run, builds claimed without output, missing screenshots or artifacts, dry-run-only evidence, and weak confidence signals.
3. Summarize what is backed and what still needs proof.

## Mission Control calls

Tools:
- `mission_control_get_handoff_summary`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Call out weak evidence clearly and identify the concrete missing artifact or validation step.
- Differentiate between executed evidence and dry-run or inferred evidence.

## Approval behavior

If the fix is to run additional validation that requires commands, preserve the normal approval flow.

## Never do

- Do not let evidence-free claims pass as verified.
- Do not overstate confidence.
- Do not treat dry-run as proof of execution.

## Failure and fallback

If evidence-specific resources are limited, inspect handoff and validation summaries, mark any inference explicitly, and note which dedicated evidence surfaces are expected or future.

## Example invocation

`Check whether the Mission Control handoff claims are actually backed by evidence.`
