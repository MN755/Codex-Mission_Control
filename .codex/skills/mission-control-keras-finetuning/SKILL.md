---
name: mission-control-keras-finetuning
description: Route Keras fine-tuning and transfer-learning work through Mission Control with explicit baseline, unfreeze, and evaluation steps.
---

# Mission Control Keras Fine-Tuning

## Purpose

Use Mission Control to plan or execute Keras fine-tuning so transfer-learning changes preserve baseline comparisons and evaluation evidence.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants TensorFlow Hub or pretrained-model fine-tuning.
- The repo already has a Keras model but the training strategy needs work.
- Baseline versus tuned behavior needs to stay explicit.

## Workflow

1. Establish the current baseline model and metrics.
2. Ask Mission Control to plan the freeze, unfreeze, and evaluation loop.
3. Capture before/after evidence instead of declaring the tuned model better by instinct.
4. Keep export compatibility visible if the tuned model must ship.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not fine-tune blindly without a baseline.
- Do not confuse a transfer-learning experiment with a product-ready model.

## Example invocation

`Use Mission Control to fine-tune the Keras model and compare it against the current baseline.`
