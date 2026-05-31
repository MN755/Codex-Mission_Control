---
name: mission-control-tool-registry
description: Design or audit tool registries, tool schemas, permissions, and runner capabilities through Mission Control.
---

# Mission Control Tool Registry

## Purpose

Make tool availability, permissions, and execution boundaries explicit before agents start clicking every shiny button.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks what tools agents can use.
- A new tool or runner should be added.
- Tool policy, schemas, or approvals need review.

## Workflow

1. Ask Mission Control for current runner and tool inventory.
2. Classify tools by read/write/destructive/network/secrets risk.
3. Define schemas, owner, approvals, and audit logging expectations.
4. Return policy recommendations and required changes.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/diagnostics`

## User-facing output

- Show tool inventory, risk classes, approval policy, missing schemas, and recommended lock-downs.

## Approval behavior

Require approval before enabling new write, network, deployment, or destructive tools.

## Never do

- Do not silently widen tool permissions.
- Do not bury destructive capability behind friendly names.
- Do not expose secrets in tool diagnostics.

## Failure and fallback

If tool inventory is incomplete, mark unknown tools as blocked until reviewed.

## Example invocation

`Use Mission Control to audit the available tools and approval policy.`
