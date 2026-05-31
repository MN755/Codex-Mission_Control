---
name: mission-control-interview
description: Run a full Mission Control Manager interview. Use when the project is ambiguous, project-specific intake matters, or the user wants the Manager to ask clarifying questions with budgeted depth before planning or build work.
---

# Mission Control Interview

## Purpose

Run a full Manager-generated interview through Codex chat.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The project is new or ambiguous.
- Important requirements are still unknown.
- The user wants the Manager to gather structured clarifications first.

## Workflow

1. Attach or confirm the project context.
2. Start the interview flow through Mission Control.
3. Relay project-specific questions with category, why, impact, and options.
4. Respect the question budget and let the Manager stop early when enough is known.
5. Return the resulting interview state and next planning step.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Present each question cleanly with why it matters.
- Summarize answered themes, remaining unknowns, and whether the Manager believes the interview is complete.

## Approval behavior

The user answers the interview questions directly. Do not auto-fill answers unless the user explicitly asks you to propose one.

## Never do

- Do not fall back to a generic questionnaire if the repo already answers the question.
- Do not keep asking after the Manager has enough context.
- Do not answer for the user.

## Failure and fallback

If a dedicated interview tool is not available, request clarifications through a Manager-led task and preserve the same structured question format in chat.

## Example invocation

`Have Mission Control run the full project interview before planning.`
