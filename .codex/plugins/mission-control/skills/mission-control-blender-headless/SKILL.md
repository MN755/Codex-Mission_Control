---
name: mission-control-blender-headless
description: Route Blender headless render and validation work through Mission Control with explicit external-runtime blockers and evidence loops.
---

# Mission Control Blender Headless

## Purpose

Use Mission Control to plan Blender-backed spatial work with explicit headless render validation instead of pretending `.blend` files validate themselves by existing.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo includes Blender files or Python automation for Blender.
- The user wants render validation, scene checks, or asset conversion through Blender.
- The workflow depends on headless rendering, not UI clicking.

## Workflow

1. Confirm Blender is actually relevant to the repo.
2. Use workspace tooling and the spatial feature catalog to identify the matching feature lane.
3. Load the target feature bundle before proposing commands or validation.
4. Keep render commands, expected outputs, and missing-runtime blockers explicit.

## Mission Control calls

Tools:
- `mission_control_get_workspace_tooling`
- `mission_control_get_spatial_feature_catalog`
- `mission_control_get_spatial_feature_bundle`

Resources:
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/spatial/features`
- `mission-control://projects/{project_id}/spatial/features/{feature_id}`

## Never do

- Do not imply Blender is installed just because the repo contains `.blend` files.
- Do not call UI-driven steps “validation” when the actual workflow is supposed to be headless.

## Failure and fallback

- If Blender is missing, say so plainly and surface the bundle’s blocked validation steps.
- If the repo has no Blender signals, say the skill is not the right lane and switch to the narrower spatial feature.

## Example invocation

`Use Mission Control to validate the Blender headless path for this spatial repo.`
