---
name: mission-control-tfx-pipelines
description: Use Mission Control to plan or repair TFX-style production ML pipelines with explicit component and validation boundaries.
---

# Mission Control TFX Pipelines

## Purpose

Route TFX pipeline work through Mission Control so ingestion, validation, transform, trainer, evaluator, and pusher stages stay explicit.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo uses TFX or similar production ML pipelines.
- The user wants schema, transform, evaluation, or pipeline-debug help.
- Productization matters more than model training alone.

## Workflow

1. Map the current pipeline components and entry points.
2. Ask Mission Control to isolate the failing or missing component instead of diffusing blame across the whole stack.
3. Keep data validation, transform, trainer, evaluator, and push steps separate in the plan.
4. Require evidence from the changed component before handoff.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_request_snapshot`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`

## Never do

- Do not treat TFX as a single script.
- Do not claim the pipeline is fixed if only the trainer runs.

## Example invocation

`Use Mission Control to debug the TFX pipeline and isolate the failing component.`
