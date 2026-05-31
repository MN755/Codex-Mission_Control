---
name: mission-control-cuda-tile-refactor
description: Use when CUDA Tile or tile-shaped GPU refactors need Mission Control planning, validation, and benchmark discipline.
---

# Mission Control CUDA Tile Refactor

## Purpose

Route CUDA Tile refactors through Mission Control so tile shape, launch configuration, and benchmark deltas stay explicit.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo uses CUDA Tile or similar tile-programming patterns.
- The user wants a kernel reshaped for throughput or memory behavior.
- A refactor needs performance proof, not just syntactic churn.

## Workflow

1. Read the current codebase and validation context for the kernel path.
2. Ask Mission Control for a bounded tile-refactor plan with correctness checks first.
3. Require benchmark and profiling loops after the refactor.
4. Surface any GPU infrastructure blockers before blaming the tile change.
5. Review the final evidence and known tradeoffs.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_request_snapshot`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Show the tile-refactor goal and affected kernel area.
- Show the benchmark and profile loop Mission Control expects.
- Show whether the result is blocked by code, infrastructure, or mixed evidence.

## Approval behavior

Risky refactors, benchmark commands, profilers, and rollback points still require whatever approval Mission Control policy demands.

## Never do

- Do not refactor tile code without a validation loop.
- Do not confuse a style cleanup with a performance refactor.
- Do not hide benchmark regressions behind pretty code.

## Failure and fallback

If Mission Control cannot confirm a tile-oriented code path, fall back to a narrower CUDA-kernel review before proposing a tile refactor.

## Example invocation

`Use Mission Control to refactor this CUDA Tile kernel and prove the result.`
