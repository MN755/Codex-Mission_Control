---
name: mission-control-review-tests
description: Review Mission Control testing coverage and status. Use when the user wants to know what tests exist, what ran, what failed, what was skipped, or where validation coverage is still weak.
---

# Mission Control Review Tests

## Purpose

Summarize test coverage and validation status from Mission Control evidence.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks about tests.
- A handoff needs test-focused review.
- Coverage and evidence quality need a status check.

## Workflow

1. Read validation-summary, handoff, and status resources.
2. Identify available test commands, executed tests, skipped tests, failures, and gaps.
3. Summarize recommended next tests if coverage is thin.

## Mission Control calls

Tools:
- `mission_control_get_handoff_summary`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Summarize available test commands, tests run, tests not run, failing tests, validation gaps, and recommended next tests.
- Highlight whether evidence is direct, dry-run, or missing.

## Approval behavior

If the user wants new tests run and policy requires command approval, shift to the run-validation flow and preserve the approval gate.

## Never do

- Do not grade coverage based on intuition alone.
- Do not hide missing evidence.
- Do not treat dry-run validation as equivalent to executed validation.

## Failure and fallback

If dedicated validation resources are missing, build the summary from handoff evidence and current status, then clearly label any inference.

## Example invocation

`Review the test coverage and tell me what still needs validation.`
