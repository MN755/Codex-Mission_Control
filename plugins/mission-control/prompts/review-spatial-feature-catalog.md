# Review spatial feature catalog

Alias for `review_spatial_feature_catalog`.
Canonical prompt: `review_spatial_feature_catalog`
Invocation name: `review-spatial-feature-catalog`

## Purpose

Load the shipped Mission Control spatial and 3D feature catalog when the operator needs a sane menu of starter lanes instead of hand-wavy graphics advice.

## Tool Sequence

- `mission_control_get_spatial_feature_catalog`
- `mission_control_get_workspace_tooling`

## Resource Sequence

- `mission-control://projects/{project_id}/spatial/features`
- `mission-control://projects/{project_id}/workspace-tooling`

## Safety Notes

Do not pretend every spatial feature applies to every repo. Use workspace-tooling posture to keep the recommendation grounded.

## Prompt Text

Review the Mission Control spatial and 3D feature catalog for this project. Load the spatial feature catalog and workspace-tooling summary, identify the most relevant starter lanes for the current repo, and summarize the safest next options without pretending unsupported toolchains are already installed.
