---
name: mission-control-codebase-intake-burst
description: Use when Mission Control should recommend a read-only codebase intake burst with Repo Mapper, Test Finder, Docs Reader, Risk Scanner, and Dependency Mapper.
---

# Mission Control Codebase Intake Burst

## Purpose

Use Mission Control to recommend a bounded read-only intake burst for existing repos or unfamiliar workspaces.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo is large or unfamiliar.
- The user wants a quick parallel map of the codebase.
- Mission Control should stay read-only while gathering context.

## Workflow

1. Check project status.
2. Ask Mission Control for a `codebase_exploration` burst recommendation.
3. Surface any approval decision in Codex chat.
4. If approved, present the planned intake subagents and expected outputs.
5. Ingest returned summaries so the Manager can use them later.

## Mission Control calls

Daemon/API:
- `POST /api/projects/{project_id}/subagent-bursts/recommend`
- `GET /api/subagents/batches/{batch_id}`
- `POST /api/subagents/batches/{batch_id}/results`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/risk-register`

## User-facing output

- Show the intake burst purpose, count, risk, and proposed subagents.
- Keep the explanation read-only and bounded.

## Approval behavior

If the burst exceeds the approval threshold, wait for the user's decision before proceeding.

## Never do

- Do not let intake subagents edit files.
- Do not run commands by default.
- Do not treat intake as implementation work.

## Failure and fallback

If burst planning is unavailable, fall back to the normal codebase map and understanding resources.

## Example invocation

`Use Mission Control to propose a read-only codebase intake burst for this repo.`
