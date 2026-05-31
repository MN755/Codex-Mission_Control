---
name: mission-control-cuda-kernel-generation
description: Route CUDA kernel generation or repair through Mission Control with GPU-aware validation and infrastructure checks.
---

# Mission Control CUDA Kernel Generation

## Purpose

Use Mission Control to plan or execute CUDA kernel generation, repair, or extension with explicit build, test, benchmark, and profiling loops.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo contains CUDA kernels or GPU extensions.
- The user asks Mission Control to write CUDA or CUDA Tile code.
- GPU correctness and performance both matter.

## Workflow

1. Confirm the repo is a CUDA-capable workspace through Mission Control codebase understanding or repo signals.
2. Read current status, validation, and diagnostics before changing kernels.
3. Ask Mission Control to produce a GPU-aware task plan with build, focused test, benchmark, and profile checkpoints.
4. Keep cluster-health or pending-pod blockers visible so code and infrastructure do not get confused.
5. Review the resulting validation evidence and handoff notes.

## Mission Control calls

Tools:
- `mission_control_import_existing_codebase`
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/diagnostics`

## User-facing output

- Show whether Mission Control detected a CUDA repo.
- Show the planned kernel-edit loop and required validation.
- Call out whether the current failure looks like code or infrastructure.

## Approval behavior

Builds, tests, benchmark commands, profilers, and dependency changes still follow Mission Control approval policy.

## Never do

- Do not treat CUDA work like generic Python editing.
- Do not claim GPU performance wins without benchmark or profiling evidence.
- Do not ignore cluster blockers such as pending pods or saturated GPU memory.

## Failure and fallback

If CUDA-specific signals are weak, report that Mission Control could not confirm GPU mode yet and fall back to a narrower investigation before broad kernel edits.

## Example invocation

`Use Mission Control to generate and validate a CUDA kernel change in this repo.`
