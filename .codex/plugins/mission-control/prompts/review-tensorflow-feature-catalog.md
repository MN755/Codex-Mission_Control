# Review TensorFlow feature catalog

Alias for `review_tensorflow_feature_catalog`.
Canonical prompt: `review_tensorflow_feature_catalog`
Invocation name: `review-tensorflow-feature-catalog`

## Purpose

Load the shipped TensorFlow starter catalog when the operator needs a real menu of Keras, serving, TFX, and edge-deployment lanes instead of notebook folklore.

## Tool Sequence

- `mission_control_get_tensorflow_feature_catalog`
- `mission_control_get_workspace_tooling`

## Resource Sequence

- `mission-control://projects/{project_id}/tensorflow/features`
- `mission-control://projects/{project_id}/workspace-tooling`

## Safety Notes

Do not pretend every TensorFlow feature fits every repo. Use workspace-tooling posture to keep the recommendation grounded.

## Prompt Text

Review the Mission Control TensorFlow starter catalog for this project. Load the TensorFlow feature catalog and workspace-tooling summary, identify the most relevant starter lanes for the current repo, and summarize the safest next options without pretending unsupported runtimes or exports already work.
