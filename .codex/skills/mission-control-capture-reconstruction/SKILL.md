---
name: mission-control-capture-reconstruction
description: Route capture, reconstruction, and spatial-ingest workflows through Mission Control with explicit data quality, reconstruction, and evidence boundaries.
---

# Mission Control Capture And Reconstruction

## Purpose

Use Mission Control to plan capture and reconstruction workflows with explicit ingest, QA, reconstruction, and validation boundaries instead of treating drone footage and splat outputs like they teleport into production.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo handles image/video capture, photogrammetry, neural reconstruction, or cloud processing.
- The user wants drone, mobile, or cloud reconstruction help.
- The pipeline needs quality gates before reconstruction results are trusted.

## Workflow

1. Confirm the repo has capture or reconstruction signals.
2. Use the spatial feature catalog to pick the relevant capture, cloud-reconstruction, or dataset-quality bundle.
3. Keep ingestion, QA, reconstruction, and downstream validation separate.
4. Make evidence targets explicit before claiming the lane is usable.

## Mission Control calls

Tools:
- `mission_control_get_spatial_feature_catalog`
- `mission_control_get_spatial_feature_bundle`
- `mission_control_get_workspace_tooling`

Resources:
- `mission-control://projects/{project_id}/spatial/features`
- `mission-control://projects/{project_id}/spatial/features/{feature_id}`
- `mission-control://projects/{project_id}/workspace-tooling`

## Never do

- Do not collapse capture QA and reconstruction into one step.
- Do not imply cloud or mobile capture tooling exists if the workspace only contains downstream assets.

## Failure and fallback

- If capture or reconstruction tooling is missing, state the blockers and the exact bundle that would apply once the runtime exists.
- If the repo is only consuming prebuilt assets, switch to the asset-pipeline or validation bundle instead.

## Example invocation

`Use Mission Control to review the capture and reconstruction workflow for this spatial project.`
