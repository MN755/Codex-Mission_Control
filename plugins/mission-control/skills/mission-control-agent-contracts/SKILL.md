---
name: mission-control-agent-contracts
description: Show or request Mission Control agent contracts. Use when the user wants to inspect a worker mission, allowed paths, forbidden paths, tools, validation obligations, stop conditions, or escalation rules.
---

# Mission Control Agent Contracts

## Purpose

Surface worker contract boundaries so chat can explain them without inventing them.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks what an agent is allowed to do.
- Conflicts or path ownership need explanation.
- A refactor or security review depends on clear worker boundaries.

## Workflow

1. Read the agent-contracts resource.
2. Map each contract to mission, allowed paths, forbidden paths, tools, validation, stop conditions, and escalation rules.
3. If the user wants changes, route them back through Mission Control planning or swarm controls.

## Mission Control calls

Tools:
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Summarize contract boundaries and call out risky overlaps or missing guardrails.
- Keep the explanation compact and actionable.

## Approval behavior

Changes to contracts can affect safety and write scope, so treat them as explicit Manager-level decisions rather than casual chat edits.

## Never do

- Do not invent contract permissions.
- Do not widen agent scope silently.
- Do not claim contract isolation where none exists.

## Failure and fallback

If the resource returns no active contracts, say that explicitly and avoid inferring permissions from swarm plans, path locks, or agent roles alone.

## Example invocation

`Show me the Mission Control agent contracts for this project.`
