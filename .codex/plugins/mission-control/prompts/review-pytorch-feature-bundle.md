# Review PyTorch feature bundle

Alias for `review_pytorch_feature_bundle`.
Canonical prompt: `review_pytorch_feature_bundle`
Invocation name: `review-pytorch-feature-bundle`

## Purpose

Load one named PyTorch starter bundle so Codex can explain its files, dependencies, validation loop, and evidence targets without making up model-training process from vibes.

## Tool Sequence

- `mission_control_get_pytorch_feature_bundle`

## Resource Sequence

- `mission-control://projects/{project_id}/pytorch/features/{feature_id}`

## Safety Notes

Keep the output scoped to the requested bundle and be explicit about runtime, distributed, or export blockers instead of implying the path is already proven.

## Prompt Text

Review one named Mission Control PyTorch starter bundle for this project. Load only the requested feature bundle, summarize its files, dependencies, validation steps, and evidence targets, and call out any runtime, distributed, or export blockers plainly.
