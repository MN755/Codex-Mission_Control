---
name: mission-control-tensorflow-serving
description: Route TensorFlow SavedModel and serving-export work through Mission Control with explicit artifact and API validation.
---

# Mission Control TensorFlow Serving

## Purpose

Use Mission Control to validate TensorFlow export and serving flows so trained models become product artifacts instead of staying trapped in the trainer.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo exports SavedModel artifacts.
- The user wants inference API or serving-readiness work.
- Training and deployment are getting confused.

## Workflow

1. Identify the current export path and serving contract.
2. Ask Mission Control to validate both training outputs and serving inputs.
3. Capture artifact paths, signatures, and API evidence before handoff.
4. Keep serving skew or missing export steps visible.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not claim deployment readiness when only training was validated.
- Do not treat SavedModel existence as proof that serving actually works.

## Example invocation

`Use Mission Control to validate the TensorFlow serving/export path for this repo.`
