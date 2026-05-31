---
name: mission-control-risk-register
description: Show or update the Mission Control risk register. Use when the user wants top risks, severity, likelihood, mitigation, owners, or current risk status summarized through Mission Control resources.
---

# Mission Control Risk Register

## Purpose

Surface the project risk register and related mitigation posture.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for project risks.
- Release or recovery planning needs risk visibility.
- A plan or handoff should include mitigation state.

## Workflow

1. Read the risk-register resource.
2. Summarize top risks, severity, likelihood, mitigation, owner, and status.
3. If the user wants changes, route them through Mission Control change or planning workflows rather than editing the register ad hoc.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Provide a compact ranked view of top risks and mitigations.
- Identify which risks are active blockers versus watch items.

## Approval behavior

If the user wants risk posture changes that affect execution policy, treat them as planning or tool-policy approvals.

## Never do

- Do not invent risk owners or mitigation status.
- Do not pretend the risk register exists if it does not.
- Do not hide severe risks for convenience.

## Failure and fallback

If no risk-register resource exists yet, summarize known risks from handoff, diagnostics, and decision resources and mark the register as expected or future.

## Example invocation

`Show the Mission Control risk register for this project.`
