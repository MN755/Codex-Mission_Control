---
name: mission-control-tf-data-pipelines
description: Use Mission Control to design or repair tf.data pipelines with explicit throughput, caching, and validation evidence.
---

# Mission Control tf.data Pipelines

## Purpose

Route TensorFlow input-pipeline work through Mission Control so tf.data changes stay measurable instead of becoming slow-motion folklore.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo uses `tf.data`.
- Data loading, batching, caching, shuffling, or TFRecord handling is the problem.
- Training looks slow or unstable because the input path is suspect.

## Workflow

1. Identify the current data sources and pipeline entry points.
2. Ask Mission Control to isolate whether correctness, throughput, or product skew is the main issue.
3. Keep dataset construction, preprocessing, and training consumption visible as separate stages.
4. Capture throughput or correctness evidence after the pipeline change.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/validation-summary`

## Never do

- Do not change the input pipeline without naming the data source and expected improvement.
- Do not claim the model is fixed when the real problem was the pipeline.

## Example invocation

`Use Mission Control to fix the tf.data pipeline and show what evidence improved.`
