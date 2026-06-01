---
name: mission-control-3d-visual-regression
description: Route 3D visual-regression and render-diff work through Mission Control with explicit evidence targets and scene-aware validation.
---

# Mission Control 3D Visual Regression

## Purpose

Use Mission Control to review 3D visual-regression work with explicit renders, tolerances, and evidence targets instead of the timeless engineering strategy known as “looks fine on my machine.”

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo needs render diffing, scene snapshots, or browser/engine visual checks.
- The user asks whether a 3D change broke output quality.
- Evidence matters more than developer confidence theater.

## Workflow

1. Confirm the repo has renderable spatial signals.
2. Load the spatial feature catalog and choose the visual-regression bundle.
3. Keep render generation, baseline selection, comparison, and evidence capture explicit.
4. Surface blockers for missing renderers or browser harnesses.

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

- Do not claim visual regression exists if there is no baseline or diff evidence.
- Do not reduce scene validation to a single screenshot if the bundle expects multiple camera or output checks.

## Failure and fallback

- If render infrastructure is missing, explain which evidence targets cannot be satisfied yet.
- If the repo is not actually renderable, route to a more relevant spatial bundle instead.

## Example invocation

`Use Mission Control to review the 3D visual-regression path and evidence requirements.`
