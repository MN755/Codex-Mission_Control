---
name: mission-control-nsight-profiling
description: Coordinate Nsight-based GPU profiling through Mission Control with safe evidence capture and approval-aware command use.
---

# Mission Control Nsight Profiling

## Purpose

Use Mission Control to plan or run Nsight profiling for GPU code paths and turn profiler output into actionable next steps.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for GPU profiling.
- A CUDA change needs Nsight Systems or Nsight Compute evidence.
- Performance claims need more than benchmark anecdotes.

## Workflow

1. Read the current Mission Control status, validation recipe, and diagnostics.
2. Ask Mission Control to isolate the GPU command or test worth profiling.
3. Keep profiler commands behind approval policy when needed.
4. Capture the profiler result as evidence, not raw noise.
5. Feed the result back into the next optimization or review step.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/handoff`

## User-facing output

- Show the target GPU path Mission Control wants to profile.
- Show the profiler loop and next expected evidence.
- Summarize the profiling result in bridge-safe language.

## Approval behavior

Profiler commands and any environment changes still follow Mission Control approval policy.

## Never do

- Do not dump raw profiler spam into chat.
- Do not claim a bottleneck moved unless the profile actually shows it.
- Do not profile the wrong workload just because it is convenient.

## Failure and fallback

If Nsight is unavailable, report that honestly and fall back to benchmark comparison plus code-path review.

## Example invocation

`Use Mission Control to profile the current CUDA path with Nsight and summarize the bottleneck.`
