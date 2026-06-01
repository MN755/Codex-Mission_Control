---
name: mission-control-keras-tuning
description: Route KerasTuner and other bounded hyperparameter searches through Mission Control with explicit budgets and evidence.
---

# Mission Control Keras Tuning

## Purpose

Use Mission Control to keep KerasTuner or bounded hyperparameter search honest with baselines, search budgets, and result summaries.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo uses KerasTuner or comparable TensorFlow search loops.
- The user wants model tuning guidance without infinite compute theater.

## Workflow

1. Establish the current baseline and the tuning goal.
2. Ask Mission Control to keep the search bounded by explicit iteration or trial budgets.
3. Compare winning trials against the baseline with real metrics.
4. Record known variance or uncertainty before shipping the recommendation.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not treat more trials as a strategy.
- Do not report a tuned winner without baseline context.

## Example invocation

`Use Mission Control to run a bounded KerasTuner comparison and summarize the winning configuration honestly.`
