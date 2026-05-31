---
name: mission-control-understand-chat
description: Ask questions against Mission Control's codebase understanding. Use for architecture questions, where-is-this-handled, why-does-this-exist, and codebase Q&A grounded in the project map.
---

# Mission Control Understand Chat

## Purpose

Answer codebase questions from Mission Control's project understanding instead of making the chat agent free-associate from filenames.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks how part of the repo works.
- The user asks where behavior is implemented.
- A previous codebase import or graph exists.

## Workflow

1. Read the codebase map and current status.
2. Ask Mission Control to answer the user question with cited files and confidence levels.
3. Separate confirmed facts from likely inferences.
4. Offer follow-up drilldowns or a task if the answer implies code changes.

## Mission Control calls

Tools:
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Answer the question directly, cite files or resources, and list uncertainty.

## Approval behavior

No approval is needed for read-only Q&A, but changes discovered from Q&A still go through Mission Control approvals.

## Never do

- Do not answer as if guesses are facts.
- Do not ignore stale codebase maps.
- Do not perform unrelated repo archaeology after Mission Control has a map.

## Failure and fallback

If no map exists, ask to import or scan the codebase first.

## Example invocation

`Ask Mission Control where authentication is handled and what files matter.`
