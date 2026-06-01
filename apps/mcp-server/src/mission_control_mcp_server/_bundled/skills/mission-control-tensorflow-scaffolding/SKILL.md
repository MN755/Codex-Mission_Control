---
name: mission-control-tensorflow-scaffolding
description: Route TensorFlow and Keras project scaffolding through Mission Control with explicit validation, export, and product-readiness expectations.
---

# Mission Control TensorFlow Scaffolding

## Purpose

Use Mission Control to scaffold TensorFlow or Keras code with real project structure, validation steps, and product-facing outputs instead of another disposable notebook.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants to start a TensorFlow or Keras project.
- The repo needs a clean training, evaluation, and export skeleton.
- Product code matters more than demo-notebook theater.

## Workflow

1. Confirm the repo or requested feature actually needs TensorFlow.
2. Ask Mission Control to choose a Keras-first starter shape for the product goal.
3. Keep data loading, training, testing, export, and deployment surfaces separate.
4. Require a validation loop that proves the scaffold runs before handoff.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`

## Never do

- Do not treat TensorFlow scaffolding like generic Python boilerplate.
- Do not stop at `model.fit()` if the user asked for a product path.

## Example invocation

`Use Mission Control to scaffold a Keras-first TensorFlow product workflow in this repo.`
