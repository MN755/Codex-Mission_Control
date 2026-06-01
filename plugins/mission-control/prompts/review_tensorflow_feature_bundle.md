# Review TensorFlow feature bundle


Canonical prompt: `review_tensorflow_feature_bundle`
Invocation name: `review_tensorflow_feature_bundle`

## Purpose

Load one named TensorFlow starter bundle so Codex can explain its files, dependencies, validation loop, and evidence targets without improvising ML architecture details.

## Tool Sequence

- `mission_control_get_tensorflow_feature_bundle`

## Resource Sequence

- `mission-control://projects/{project_id}/tensorflow/features/{feature_id}`

## Safety Notes

Keep the output scoped to the requested bundle and be explicit about runtime or export blockers instead of implying the path is magically shippable.

## Prompt Text

Review one named Mission Control TensorFlow starter bundle for this project. Load only the requested feature bundle, summarize its files, dependencies, validation steps, and evidence targets, and call out any runtime, export, or deployment blockers plainly.
