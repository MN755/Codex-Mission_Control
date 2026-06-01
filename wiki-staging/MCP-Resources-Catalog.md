# MCP Resources Catalog

This page summarizes the current read-only MCP resources exposed for Mission Control bridge mode.

> Status: Current

## Catalog

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`: Orchestration status - Compact bridge-safe orchestration status with phase, blockers, pending decisions, and handoff readiness.
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`: Orchestration events - Recent orchestration events summarized for Codex chat without raw log streaming.
- `mission-control://projects/{project_id}/status`: Project status - High-signal project summary combining project state, active orchestration state, and next checkpoint.
- `mission-control://projects/{project_id}/agents`: Project agents - Compact worker roster summary with agent role, state, and current assignment hints.
- `mission-control://projects/{project_id}/pending-decisions`: Pending decisions - Unified queue of approvals, manager questions, and orchestration decisions that need user input.
- `mission-control://projects/{project_id}/handoff`: Project handoff - Final handoff summary with run guidance, evidence posture, limitations, and dry-run warnings.
- `mission-control://projects/{project_id}/codebase-map`: Codebase map - Compact structure and repo-understanding summary for imported or attached codebases.
- `mission-control://projects/{project_id}/workspace-tooling`: Workspace tooling - Project-scoped repo-native tooling summary covering intake, validation, and security helper lanes.
- `mission-control://projects/{project_id}/tensorflow/features`: TensorFlow feature catalog - Project-scoped TensorFlow and Keras starter catalog for product-ready ML workflows.
- `mission-control://projects/{project_id}/tensorflow/features/{feature_id}`: TensorFlow feature bundle - One named TensorFlow starter bundle with files, dependencies, validation steps, and evidence targets.
- `mission-control://projects/{project_id}/pytorch/features`: PyTorch feature catalog - Project-scoped PyTorch starter catalog for training, distributed, export, and fine-tuning lanes.
- `mission-control://projects/{project_id}/pytorch/features/{feature_id}`: PyTorch feature bundle - One named PyTorch starter bundle with files, dependencies, validation steps, and evidence targets.
- `mission-control://projects/{project_id}/spatial/features`: Spatial feature catalog - Project-scoped spatial and 3D starter catalog for asset pipelines, rendering, capture, reconstruction, geospatial, and scene-validation workflows.
- `mission-control://projects/{project_id}/spatial/features/{feature_id}`: Spatial feature bundle - One named spatial or 3D starter bundle with dependencies, starter files, validation steps, and evidence targets.
- `mission-control://projects/{project_id}/diagnostics`: Project diagnostics - Bridge-safe diagnostic summary for degraded orchestration or environment issues.
- `mission-control://projects/{project_id}/webwright`: Webwright readiness - Project-scoped Webwright readiness summary for browser-agent work, install posture, and recommended next steps.
- `mission-control://projects/{project_id}/nvidia-dynamo`: NVIDIA Dynamo readiness - Project-scoped NVIDIA Dynamo readiness summary for GPU-backed worker inference through an OpenAI-compatible frontend.
- `mission-control://projects/{project_id}/nvidia-nim`: NVIDIA NIM readiness - Project-scoped NVIDIA NIM readiness summary for hosted or self-hosted GPU-backed worker inference through an OpenAI-compatible frontend.
- `mission-control://projects/{project_id}/nvidia-aiq`: NVIDIA AI-Q readiness - Project-scoped NVIDIA AI-Q readiness summary for deep research delegation and async job execution.
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`: NVIDIA GPU diagnostics - Project-scoped GPU telemetry summary derived from Prometheus and DCGM exporter metrics.
- `mission-control://projects/{project_id}/nvidia-local-runtime`: NVIDIA local runtime - Project-scoped local CUDA and NVIDIA runtime readiness for build, test, and profile loops.
- `mission-control://projects/{project_id}/nvidia-validation-plan`: NVIDIA validation plan - Project-scoped GPU validation loop that combines local runtime readiness, CUDA repo mode, and cluster health.
- `mission-control://projects/{project_id}/swarm-plan`: Swarm plan - Current or proposed swarm plan, risk posture, dynamic spawning state, and approval requirements.
- `mission-control://projects/{project_id}/risk-register`: Risk register - Open and recently mitigated project risks summarized for bridge-safe review.
- `mission-control://projects/{project_id}/agent-contracts`: Agent contracts - Read-only summary of per-agent mission contracts, allowed paths, tool boundaries, and validation expectations.
- `mission-control://projects/{project_id}/validation-summary`: Validation summary - Compact validation coverage summary with counts and notable gaps.
- `mission-control://projects/{project_id}/decision-ledger`: Decision ledger - Read-only ledger of important user and manager decisions that shaped the orchestration.
- `mission-control://projects/{project_id}/path-locks`: Path locks - Read-only summary of active and waiting path ownership constraints used to keep worker edits safe.
- `mission-control://projects/{project_id}/operator-snapshot`: Operator snapshot - Compact operator-facing snapshot of project health, focus, risks, and next action.
- `mission-control://projects/{project_id}/instincts`: Operational instincts - Derived operational instincts that turn current project state into reusable execution rules.
- `mission-control://projects/{project_id}/verification-brief`: Verification brief - Release- and review-oriented verification brief with checks, blockers, and evidence gaps.
- `mission-control://projects/{project_id}/capability-report`: Capability report - Project-scoped capability report covering execution profiles, security, validation, swarm templates, runner posture, and repo drift.
- `mission-control://projects/{project_id}/capability-report/{section_key}`: Capability section - One named capability-report section for focused review of a single Mission Control lane such as semantic impact mapping or release readiness.

## Related pages

Continue with [MCP Plugin Architecture](MCP-Plugin-Architecture), [MCP Prompts Catalog](MCP-Prompts-Catalog), and [Mission Control Daemon](Mission-Control-Daemon).

## Integration additions

- `mission-control://integrations/catalog`
- `mission-control://integrations/connections`
- `mission-control://integrations/health`
- `mission-control://projects/{project_id}/integrations`
- `mission-control://projects/{project_id}/integrations/{family}`
