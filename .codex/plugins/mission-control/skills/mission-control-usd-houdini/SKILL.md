---
name: mission-control-usd-houdini
description: Route OpenUSD and Houdini/Solaris workflow planning through Mission Control with explicit scene-graph, interchange, and validation boundaries.
---

# Mission Control USD And Houdini

## Purpose

Use Mission Control to reason about OpenUSD, Hydra, and Houdini/Solaris workflows like a real scene pipeline, not a pile of filenames with delusions of grandeur.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The repo carries `.usd`, `.usda`, `.usdc`, Solaris, or Houdini graph signals.
- The user wants interchange, scene composition, or DCC pipeline work.
- Validation needs to preserve scene-graph semantics and not just file existence.

## Workflow

1. Confirm USD or Houdini signals in the repo/tooling summary.
2. Review the spatial catalog and select the `houdini_usd` or related feature bundle.
3. Keep stage composition, conversion, and validation evidence separate.
4. Surface missing external runtime blockers honestly.

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

- Do not treat USD composition like generic asset export.
- Do not imply Houdini automation is runnable if the environment or scripts are not present.

## Failure and fallback

- If USD/Houdini tooling is absent, report the bundle and blockers rather than improvising a fake stage-validation story.
- If the repo is spatial but not USD-based, switch to the more relevant feature bundle.

## Example invocation

`Use Mission Control to review the USD and Houdini pipeline lane for this project.`
