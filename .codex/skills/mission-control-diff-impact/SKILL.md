---
name: mission-control-diff-impact
description: Analyze the impact of current changes or a pull request through Mission Control. Use for ripple effects, affected tests, ownership, risk, and review focus.
---

# Mission Control Diff Impact

## Purpose

Estimate how a change affects the system before review, commit, or release.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks what their changes affect.
- A PR or diff needs risk analysis.
- Test selection should be guided by touched paths and dependencies.

## Workflow

1. Ask Mission Control to inspect changed files and map them to codebase graph nodes.
2. Identify affected modules, commands, tests, docs, and user-facing behavior.
3. Rank risks and recommend validation.
4. Summarize what is safe, risky, and unknown.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Include touched areas, likely ripple effects, recommended tests, and release risk.

## Approval behavior

Ask before running test suites, build commands, or PR comments.

## Never do

- Do not assume unchanged tests mean unchanged behavior.
- Do not claim no impact without graph or dependency evidence.
- Do not post review comments without user approval.

## Failure and fallback

If diff access is unavailable, ask the user for the diff or branch/PR reference.

## Example invocation

`Use Mission Control to analyze the impact of my current diff.`
