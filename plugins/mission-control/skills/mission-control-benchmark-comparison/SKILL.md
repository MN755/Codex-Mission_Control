---
name: mission-control-benchmark-comparison
description: Compare before-and-after performance evidence through Mission Control without turning benchmark claims into theater.
---

# Mission Control Benchmark Comparison

## Purpose

Use Mission Control to compare GPU benchmark results before and after code changes with explicit evidence and known variance.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks whether a CUDA change made things faster.
- A kernel optimization needs before-and-after comparison.
- Performance work risks trading away correctness or stability.

## Workflow

1. Read the current validation summary and diagnostics.
2. Ask Mission Control to identify the benchmark path that matches the changed code.
3. Keep the benchmark loop paired with focused correctness validation.
4. Record the delta and the confidence level honestly.
5. Feed the result back into optimization, review, or handoff output.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/diagnostics`

## User-facing output

- Show the benchmark target and the claimed delta.
- Show whether the evidence supports speedup, regression, or inconclusive results.
- Show whether infrastructure issues contaminated the run.

## Approval behavior

Benchmark commands and any supporting build or profile steps still use Mission Control approval rules.

## Never do

- Do not compare unmatched workloads.
- Do not call noisy or one-off results a win.
- Do not hide correctness regressions behind faster numbers.

## Failure and fallback

If the repo has no clear benchmark target, say that plainly and fall back to a focused profiling or validation task first.

## Example invocation

`Use Mission Control to compare the current GPU benchmark against the previous baseline.`
