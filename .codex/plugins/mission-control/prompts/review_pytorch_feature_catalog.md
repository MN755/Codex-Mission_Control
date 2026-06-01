# Review PyTorch feature catalog


Canonical prompt: `review_pytorch_feature_catalog`
Invocation name: `review_pytorch_feature_catalog`

## Purpose

Load the shipped PyTorch starter catalog when the operator needs a real menu of training, distributed, export, and fine-tuning lanes instead of generic Python wishcasting.

## Tool Sequence

- `mission_control_get_pytorch_feature_catalog`
- `mission_control_get_workspace_tooling`

## Resource Sequence

- `mission-control://projects/{project_id}/pytorch/features`
- `mission-control://projects/{project_id}/workspace-tooling`

## Safety Notes

Do not pretend every PyTorch feature fits every repo. Use workspace-tooling posture to keep the recommendation grounded.

## Prompt Text

Review the Mission Control PyTorch starter catalog for this project. Load the PyTorch feature catalog and workspace-tooling summary, identify the most relevant starter lanes for the current repo, and summarize the safest next options without pretending unsupported runtimes or export paths already work.
