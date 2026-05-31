---
name: mission-control-model-optimization
description: Use Mission Control to plan bounded TensorFlow model optimization work such as quantization or pruning with explicit tradeoffs.
---

# Mission Control Model Optimization

## Purpose

Use Mission Control to plan or review TensorFlow model-optimization work so quantization, pruning, and compression changes stay evidence-backed.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo uses TensorFlow Model Optimization Toolkit or equivalent flows.
- The user wants smaller, faster, or more device-friendly models.
- Accuracy tradeoffs must stay visible.

## Workflow

1. Establish the baseline model size, latency, and quality.
2. Ask Mission Control to keep optimization work bounded and comparable.
3. Capture before/after artifact evidence plus any degraded metrics.
4. Keep deployment target constraints visible throughout the loop.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not optimize blindly without a baseline.
- Do not celebrate a smaller model that quietly became worse where the product actually cares.

## Example invocation

`Use Mission Control to evaluate TensorFlow quantization or pruning changes against the current baseline.`
