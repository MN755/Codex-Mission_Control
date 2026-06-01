# Review spatial feature bundle


Canonical prompt: `review_spatial_feature_bundle`
Invocation name: `review_spatial_feature_bundle`

## Purpose

Load one named spatial or 3D starter bundle so Codex can explain its dependencies, validation loop, and evidence targets without inventing graphics pipeline details.

## Tool Sequence

- `mission_control_get_spatial_feature_bundle`

## Resource Sequence

- `mission-control://projects/{project_id}/spatial/features/{feature_id}`

## Safety Notes

Keep the output scoped to the requested bundle and be explicit about missing external tools such as Blender, Houdini, or GIS runtimes.

## Prompt Text

Review one named Mission Control spatial or 3D starter bundle for this project. Load only the requested feature bundle, summarize its dependencies, starter files, validation steps, and evidence targets, and call out any external runtime blockers plainly instead of implying the workflow is magically ready.
