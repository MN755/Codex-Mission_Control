---
name: mission-control-handoff-audit-burst
description: Use when Mission Control should recommend a read-only handoff audit burst for run instructions, validation evidence, limitations, docs quality, and security caveats.
---

# Mission Control Handoff Audit Burst

## Purpose

Use Mission Control to audit handoff quality with bounded read-only Codex subagents.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- A handoff exists but confidence is not high enough.
- The user wants structured handoff review before trusting it.
- Validation and docs need an independent audit pass.

## Workflow

1. Read the latest handoff summary and validation posture.
2. Ask Mission Control for a `handoff_audit` burst recommendation.
3. Surface any approval decision in Codex chat.
4. If approved, show the planned auditors and expected outputs.
5. Ingest results so the Manager can tighten the handoff.

## Mission Control calls

Daemon/API:
- `POST /api/projects/{project_id}/subagent-bursts/recommend`
- `GET /api/subagents/batches/{batch_id}`
- `POST /api/subagents/batches/{batch_id}/results`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Show what the audit burst is checking and why.
- Keep the output concise, with clear evidence and caveats.

## Approval behavior

Do not auto-approve a larger handoff audit burst.

## Never do

- Do not claim the handoff is trustworthy before the audit says so.
- Do not run commands or edit docs by default.
- Do not bypass Mission Control approval flow.

## Failure and fallback

If burst planning is unavailable, fall back to the normal handoff summary and highlight evidence gaps manually.

## Example invocation

`Ask Mission Control whether we should run a handoff audit burst before accepting this handoff.`
