# MCP Resources

Mission Control resources are read-only context surfaces for Codex chat.

## Resource Rules

- resources do not execute commands
- resources are summary-only by default
- resources redact secrets
- raw logs are hidden unless a future explicit safe view is added

## Resource Catalog

- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/questions/pending`
- `mission-control://projects/{project_id}/approvals/pending`
- `mission-control://projects/{project_id}/event-digest`
- `mission-control://projects/{project_id}/handoff-summary`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/handoff/evidence`
- `mission-control://projects/{project_id}/handoff/evidence/preview`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://integrations/catalog`
- `mission-control://integrations/connections`
- `mission-control://integrations/health`
- `mission-control://playbooks`
- `mission-control://playbooks/{playbook_key}`
- `mission-control://system/status`
- `mission-control://startup/status`
- `mission-control://profile/summary`
- `mission-control://preferences/summary`
- `mission-control://subagent-policy/summary`
- `mission-control://projects/{project_id}/integrations`
- `mission-control://projects/{project_id}/integrations/{family}`
- `mission-control://projects/{project_id}/runbook`
- `mission-control://projects/{project_id}/runbook/summary`
- `mission-control://projects/{project_id}/safe-mode`
- `mission-control://projects/{project_id}/recovery-plans`
- `mission-control://projects/{project_id}/recovery-plans/preview`
- `mission-control://projects/{project_id}/snapshots`
- `mission-control://projects/{project_id}/snapshots/{snapshot_id}/restore-plan`
- `mission-control://projects/{project_id}/playbook`
- `mission-control://projects/{project_id}/playbook/recommendations`
- `mission-control://projects/{project_id}/preferences/summary`
- `mission-control://projects/{project_id}/preferences/effective`
- `mission-control://projects/{project_id}/widgets/summary`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/execution-policy/summary`
- `mission-control://projects/{project_id}/coordination/summary`
- `mission-control://projects/{project_id}/tensorflow/features`
- `mission-control://projects/{project_id}/tensorflow/features/{feature_id}`
- `mission-control://projects/{project_id}/pytorch/features`
- `mission-control://projects/{project_id}/pytorch/features/{feature_id}`
- `mission-control://projects/{project_id}/spatial/features`
- `mission-control://projects/{project_id}/spatial/features/{feature_id}`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-nim`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
- `mission-control://projects/{project_id}/nvidia-local-runtime`
- `mission-control://projects/{project_id}/nvidia-validation-plan`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/swarm/simulations/latest`
- `mission-control://risks/summary`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/risks/summary`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/validation-coverage/summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/agents-md/status`
- `mission-control://projects/{project_id}/operator-snapshot`
- `mission-control://projects/{project_id}/instincts`
- `mission-control://projects/{project_id}/verification-brief`
- `mission-control://projects/{project_id}/capability-report`
- `mission-control://projects/{project_id}/capability-report/{section_key}`

## Why These Exist

- status and events support compact progress reporting
- pending decisions support approval relay
- pending questions and pending approvals expose unresolved manager prompts and gated actions without forcing chat to rummage through UI-only queues
- event digest and handoff summary expose short operational summaries directly, which is a lot less stupid than reconstructing them from raw status and events every time
- handoff supports final bridge summaries
- handoff evidence and handoff evidence preview expose stored proof plus safe derived candidates without making chat scrape raw agent reports or create rows on read
- codebase map supports imported repo understanding
- workspace tooling tells the bridge which repo-native helper lanes actually exist for intake, validation, and security before it recommends commands like a clown
- profile summary and subagent policy summary expose the operator defaults that shape provider choice, approvals, and whether subagent bursts are even allowed before the bridge starts making heroic assumptions
- preference summary and effective preference resources expose global defaults, project overrides, and inherited values before the bridge starts making configuration assumptions from thin air
- runbook and runbook summary expose the current operational guide without forcing chat to scrape widget markdown like an animal
- safe mode exposes whether Mission Control is currently enforcing the stricter approval and workspace-only guardrails before chat suggests something reckless
- recovery plans and recovery plan preview expose persisted rescue options plus current derived candidates before the bridge starts improvising “helpful” chaos
- snapshots and restore-plan resources expose recovery checkpoints and safe rollback planning without making chat invent git advice from thin air
- playbook and playbook recommendations expose the current execution template and nearby alternatives so chat can discuss project posture without re-deriving the same pattern match from scratch every time
- playbook catalog resources expose the shipped playbook library itself so chat can compare templates without already having a project in hand
- system status and startup status expose runtime readiness, auth posture, and startup health directly instead of making chat reverse-engineer the app's boot state from scattered symptoms
- execution policy summary tells the bridge which runner, sandbox, approval, tool-routing, and validation posture is actually in effect before it suggests work that contradicts local policy
- coordination summary exposes contract, lock, gate, conflict, and decision posture in one compact lane so chat can spot coordination drift before the swarm faceplants
- latest swarm simulation exposes launch readiness, conflicts, bottlenecks, and approval pressure without requiring a write path or a persisted simulation row first
- diagnostics, risk register, decision ledger, and path locks support stuck-run debugging without exposing raw internals
- risk summary resources expose compact global and project-specific risk posture without making chat hand-count statuses from raw records like a raccoon with a spreadsheet
- validation coverage summary exposes the backend's native read-only gap report directly, which is better than making chat trust a wrapper that guessed from the raw area list
- project widget summary exposes the current operator widget surface for a project, which is useful when headless chat needs to understand what status panes already exist without touching UI code
- agents-md status exposes whether repo-scoped agent instructions exist and where they live before chat pretends they are present or absent from vibes alone
- the Webwright resource tells the bridge whether the local browser-agent runtime is actually ready or whether the user still has setup work to do
- the NVIDIA resources tell the bridge whether GPU-backed inference, deep research, local CUDA tooling, and Prometheus/DCGM telemetry are actually available before Mission Control leans on them
- `nvidia-gpu-diagnostics` is a merged verdict, not a raw metrics dump
  it combines live Prometheus/DCGM telemetry with repo-local GPU summary files and reports whether the current failure smells like infrastructure, code, mixed, or still unknown
- `nvidia-local-runtime` tells the bridge whether the local CUDA, Compute Sanitizer, Nsight, CUDA-GDB, NGC CLI, and NVIDIA runtime tools are actually present before somebody blames a missing `nvcc` on the swarm
- `nvidia-validation-plan` turns repo mode, local runtime, cluster health, Compute Sanitizer, and optional NGC container smoke lanes into an explicit evidence loop for CUDA work
- operator snapshot, instincts, and verification brief give Codex or Claude chat a higher-signal operator surface for current state, execution rules, and release readiness
- capability report pulls together execution profiles, security posture, validation evidence, swarm templates, runner budget, browser evidence, and repo contract drift in one project-scoped surface
- capability section resources let the bridge pull one named lane such as `semantic_code_impact_mapping` or `release_readiness_mode` without hauling around the whole report
- TensorFlow and PyTorch feature resources expose typed starter catalogs and one named bundle so the bridge can discuss ML product lanes without hallucinating framework scaffolds
- spatial feature resources expose the shipped 3D and spatial starter catalog plus one named bundle without making Codex guess which capture, render, or reconstruction lane is even relevant

## Deliberate Non-Resources

Some backend routes are still real code without MCP exposure, but profile summary, subagent policy summary, handoff evidence preview, recovery plan preview, playbook, latest swarm simulation, and the TensorFlow, PyTorch, and spatial starter catalogs are no longer among them.
