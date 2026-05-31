---
name: mission-control-quick-clarify
description: Ask only a few high-impact Mission Control clarifying questions. Use when the user wants speed, the repo already explains most things, or the task is urgent and only 3–6 targeted questions are justified.
---

# Mission Control Quick Clarify

## Purpose

Run a short, high-impact clarification flow instead of a full interview.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants speed.
- The task is a small fix or focused enhancement.
- Existing repo context answers most questions already.

## Workflow

1. Attach or confirm project context.
2. Ask Mission Control for a quick-clarify intake rather than a full interview.
3. Relay only 3 to 6 high-impact questions.
4. Capture the answers and resume planning or execution.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Show a compact question set, why those questions matter, and what the answers unlock.
- After answers, summarize the clarified assumptions and next step.

## Approval behavior

User answers are required; do not invent them. If the user wants you to propose answers, label them as proposals, not facts.

## Never do

- Do not drift into a full interview.
- Do not ask low-value generic questions.
- Do not ignore obvious answers already present in the repo or prior handoff.

## Failure and fallback

If quick-clarify is not a dedicated tool yet, phrase the request through the Manager-led task flow and constrain it to the same short question budget.

## Example invocation

`Ask Mission Control only the 3 to 6 highest-impact questions for this repo.`
