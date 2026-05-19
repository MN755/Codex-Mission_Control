---
name: mission-control-failure-diagnosis-burst
description: Use when Mission Control should recommend a read-only failure diagnosis burst across logs, recent changes, tests, dependencies, and recovery planning.
---

# Mission Control Failure Diagnosis Burst

## Purpose

Route stuck-run diagnosis through Mission Control with bounded parallel read-only subagents.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- Orchestration is stuck or failed.
- The likely causes can be explored independently.
- The user wants a faster diagnosis without jumping straight into edits.

## Workflow

1. Check status, diagnostics, and event summaries.
2. Ask Mission Control for a `failure_diagnosis` burst recommendation.
3. Surface any approval decision.
4. If approved, show the diagnosis subagents and their expected reports.
5. Ingest results and summarize recovery implications.

## Mission Control calls

Daemon/API:
- `POST /api/projects/{project_id}/subagent-bursts/recommend`
- `GET /api/subagents/batches/{batch_id}`
- `POST /api/subagents/batches/{batch_id}/results`

Resources:
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Explain why a diagnosis burst is being proposed.
- Show proposed subagents, risk, and estimated intensity.
- Keep diagnostics bridge-safe.

## Approval behavior

If Mission Control asks for burst approval, stop and relay the decision instead of improvising.

## Never do

- Do not run recovery commands from the burst by default.
- Do not dump raw logs.
- Do not convert diagnosis subagents into editing agents.

## Failure and fallback

If burst planning is unavailable, summarize the failure from normal diagnostics and event digest paths.

## Example invocation

`Use Mission Control to propose a failure diagnosis burst for this stuck run.`
