---
name: mission-control-tensorboard-observability
description: Use Mission Control to turn TensorBoard logs and training curves into explicit validation evidence.
---

# Mission Control TensorBoard Observability

## Purpose

Use Mission Control to plan or review TensorBoard-backed observability so training claims have actual telemetry behind them.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo logs to TensorBoard.
- The user wants to understand training behavior, regressions, or tuning outcomes.
- Model quality claims need evidence.

## Workflow

1. Confirm where TensorBoard logs live.
2. Ask Mission Control to read the training lane together with tests or export results.
3. Summarize the useful signals, not every pixel in the curve set.
4. Keep missing logs visible as a blocker instead of faking insight.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/handoff`

## Never do

- Do not describe training as healthy if there are no logs or metrics.
- Do not confuse pretty curves with product readiness.

## Example invocation

`Use Mission Control to review the TensorBoard evidence for this TensorFlow training run.`
