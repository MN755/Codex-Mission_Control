---
name: mission-control-tflite-deployment
description: Route TensorFlow Lite export and edge-readiness checks through Mission Control with explicit artifact and constraint validation.
---

# Mission Control TensorFlow Lite Deployment

## Purpose

Use Mission Control to validate TensorFlow Lite export and edge-deployment work so mobile or device targets get real artifact checks.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo exports `.tflite` artifacts.
- The user wants mobile, embedded, or edge deployment help.
- Size, latency, or accuracy constraints matter.

## Workflow

1. Confirm the SavedModel or training source artifact.
2. Ask Mission Control to validate conversion plus target constraints.
3. Capture the produced `.tflite` artifact path and any post-conversion checks.
4. Call out accuracy, latency, or memory risk instead of hiding it.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not claim edge readiness because a conversion command exists.
- Do not hide accuracy or latency regressions behind a successful export.

## Example invocation

`Use Mission Control to export and validate the TensorFlow Lite artifact for this product path.`
