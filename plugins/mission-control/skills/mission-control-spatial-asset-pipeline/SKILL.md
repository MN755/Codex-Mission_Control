---
name: mission-control-spatial-asset-pipeline
description: Route spatial and 3D asset-pipeline work through Mission Control with explicit ingest, conversion, validation, and evidence boundaries.
---

# Mission Control Spatial Asset Pipeline

## Purpose

Use Mission Control to plan or repair a spatial or 3D asset pipeline without pretending that splats, USD scenes, textures, captures, and validation artifacts are all the same thing.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo handles spatial assets, Gaussian splats, point clouds, meshes, or scene packages.
- The user wants a starter lane for ingest, conversion, authoring, or validation.
- The workspace needs a real pipeline shape instead of another folder full of random scripts.

## Workflow

1. Confirm the repo actually has spatial or 3D signals.
2. Load the spatial feature catalog and workspace-tooling posture first.
3. Select the feature bundle that matches the requested asset pipeline lane.
4. Keep conversion, render validation, and evidence capture explicit.

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

- Do not claim a Blender, USD, or capture pipeline is ready without checking runtime/tooling posture.
- Do not flatten asset ingest, conversion, and validation into one vague “graphics” step.

## Failure and fallback

- If the spatial catalog is unavailable, fall back to `mission-control://projects/{project_id}/workspace-tooling` and explain the missing bridge surface plainly.
- If required external tools are missing, surface blockers and evidence gaps instead of inventing green validation.

## Example invocation

`Use Mission Control to map the spatial asset pipeline in this repo and recommend the right starter lane.`
