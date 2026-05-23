---
name: mission-control-domain-map
description: Extract business domains, flows, process steps, and domain vocabulary from a codebase or knowledge base through Mission Control.
---

# Mission Control Domain Map

## Purpose

Map technical code to business concepts so implementation work does not trample hidden product rules.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for business logic or domain understanding.
- A refactor or migration risks changing product behavior.
- Onboarding needs domain vocabulary and flows.

## Workflow

1. Ask Mission Control to identify domains, flows, actors, entities, and invariants.
2. Link domain concepts to files, tests, and commands where possible.
3. Separate explicit code facts from inferred business rules.
4. Return flows, risks, and validation suggestions.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Provide domain map, key flows, source files, assumptions, and risky change points.

## Approval behavior

Ask before changing domain-critical behavior or deleting compatibility paths.

## Never do

- Do not invent business rules from variable names alone.
- Do not flatten uncertain domain inferences into facts.
- Do not skip tests for domain-critical changes.

## Failure and fallback

If domain evidence is thin, return questions for the user and mark the map as provisional.

## Example invocation

`Use Mission Control to map the business flows in this codebase.`
