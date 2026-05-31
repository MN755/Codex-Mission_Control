---
name: mission-control-compiler-autotuning-guidance
description: Request compiler and autotuning guidance for GPU code through Mission Control with bounded iteration and evidence requirements.
---

# Mission Control Compiler Autotuning Guidance

## Purpose

Use Mission Control to plan bounded compiler-flag, tile-shape, or autotuning guidance for CUDA work without pretending endless tuning loops are strategy.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks how to tune compiler or tile parameters for CUDA code.
- Benchmark or profiling output points to launch-shape or compiler sensitivity.
- The repo needs explicit iteration budgets for optimization loops.

## Workflow

1. Read the current benchmark, profiling, and validation evidence.
2. Ask Mission Control for a bounded autotuning or compiler-guidance loop.
3. Keep iteration budgets explicit so the optimization pass does not spiral forever.
4. Re-run benchmark and validation evidence after any tuning change.
5. Record what improved, regressed, or stayed inconclusive.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/handoff`

## User-facing output

- Show the tuning target and iteration budget.
- Show the evidence Mission Control expects after each optimization pass.
- Show whether the tuning loop is still code-bound or blocked by infrastructure.

## Approval behavior

Compiler, benchmark, profile, and environment-tuning commands still require approval when Mission Control policy says they do.

## Never do

- Do not tune without a measurement loop.
- Do not keep iterating just because a model enjoys the sound of optimization.
- Do not claim compiler magic fixed an infrastructure problem.

## Failure and fallback

If the current repo lacks a clear benchmark or profiler signal, fall back to benchmark-comparison or Nsight-profiling work first.

## Example invocation

`Use Mission Control to propose bounded compiler autotuning guidance for this CUDA path.`
