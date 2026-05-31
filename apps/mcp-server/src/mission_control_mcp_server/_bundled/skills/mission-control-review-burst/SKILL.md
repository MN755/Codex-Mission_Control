---
name: mission-control-review-burst
description: Use when Mission Control should recommend a bounded read-only review burst across correctness, security, testing, maintainability, and docs.
---

# Mission Control Review Burst

## Purpose

Ask Mission Control to split review work into bounded read-only Codex subagents.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants a multi-angle review.
- The work is read-heavy and does not require coordinated edits.
- A single reviewer would be slower or less complete.

## Workflow

1. Check status and current scope.
2. Ask Mission Control for a `review` burst recommendation.
3. Surface any approval requirement.
4. If approved, show the proposed reviewers and expected outputs.
5. Ingest results for Manager follow-up.

## Mission Control calls

Daemon/API:
- `POST /api/projects/{project_id}/subagent-bursts/recommend`
- `GET /api/subagents/batches/{batch_id}`
- `POST /api/subagents/batches/{batch_id}/results`

Resources:
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/validation-summary`

## User-facing output

- Show review focus areas, burst size, risk, and approval posture.
- Return findings as summaries, not raw transcripts.

## Approval behavior

Do not push a larger review burst through without answering the pending decision first.

## Never do

- Do not let review bursts mutate code by default.
- Do not bypass approvals.
- Do not invent findings without cited evidence.

## Failure and fallback

If burst planning is unavailable, fall back to a normal Mission Control review flow and say the burst path is unavailable.

## Example invocation

`Ask Mission Control whether a review burst makes sense for this change.`
