# Codex Plugin Mode

Mission Control can run headless in the background and be driven from a normal Codex desktop chat through a local MCP bridge.

## Role split

This mode only works if the responsibilities stay separated:

- Codex chat is the bridge between the user and Mission Control
- Mission Control Manager is the orchestrator
- worker runners remain behind Mission Control

Codex chat should:

- attach the workspace
- start or continue the Mission Control task
- poll compact status
- surface pending decisions
- send the user’s answer back
- retrieve the final handoff

Codex chat should not:

- invent its own manager plan
- spawn extra workers outside Mission Control mode
- bypass Mission Control approvals
- quietly edit the repo on Mission Control’s behalf

## Bridge flow

1. Codex calls `mission_control_attach_workspace`.
2. Mission Control reuses an existing project or imports the folder safely.
3. Codex calls `mission_control_start_task`.
4. Mission Control creates or resumes one active orchestration for that workspace.
5. Mission Control Manager runs in the background.
6. If the run needs clarification or approval, Mission Control creates a `PendingDecision`.
7. Codex reads pending decisions and asks the user.
8. Codex submits the answer through `mission_control_answer_decision`.
9. Mission Control resumes background orchestration.
10. Codex fetches the handoff when the run is complete.

## Background daemon

Mission Control daemon mode reuses the same FastAPI backend used by the dashboard. It runs on localhost only and stores orchestration state in the normal Mission Control database.

Useful commands:

### Windows

```powershell
.\scripts\start-mission-control-daemon.ps1
```

### macOS or Linux

```bash
./scripts/start-mission-control-daemon.sh
```

The MCP bridge can auto-start the daemon when `GET /api/health` fails and the configured localhost port is free. If the port is occupied but does not answer the health check, the bridge returns a structured error instead of blindly trampling some unrelated process.

## Current MCP tools

- `mission_control_attach_workspace`
- `mission_control_start_task`
- `mission_control_get_status`
- `mission_control_get_pending_decisions`
- `mission_control_answer_decision`
- `mission_control_pause`
- `mission_control_resume`
- `mission_control_get_handoff`
- `mission_control_import_existing_codebase`
- `mission_control_plugin_health`
- `mission_control_enable_safe_mode`
- `mission_control_get_event_digest`
- `mission_control_get_handoff_summary`
- `mission_control_generate_agents_md`
- `mission_control_request_snapshot`
- `mission_control_request_recovery_plan`
- `mission_control_get_orchestration_events`
- `mission_control_get_codebase_map`
- `mission_control_get_codebase_understanding`
- `mission_control_set_import_interview_choice`
- `mission_control_get_workspace_tooling`
- `mission_control_search_codebase`
- `mission_control_get_webwright_status`
- `mission_control_get_nvidia_dynamo_status`
- `mission_control_get_nvidia_aiq_status`
- `mission_control_run_nvidia_aiq_research`
- `mission_control_get_nvidia_gpu_diagnostics`
- `mission_control_get_nvidia_local_runtime_status`
- `mission_control_get_nvidia_validation_plan`
- `mission_control_get_swarm_plan`
- `mission_control_update_swarm_preferences`
- `mission_control_generate_swarm_plan`
- `mission_control_approve_swarm_plan`
- `mission_control_get_diagnostics`
- `mission_control_get_project_settings`
- `mission_control_update_project_settings`
- `mission_control_get_import_safety`
- `mission_control_update_import_safety`
- `mission_control_get_tool_catalog`
- `mission_control_set_tool_permission`
- `mission_control_get_agents_md_status`
- `mission_control_propose_agents_md`
- `mission_control_request_recovery_options`

## Current MCP resources

- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/swarm-plan`
- `mission-control://projects/{project_id}/agents`
- `mission-control://projects/{project_id}/pending-decisions`
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/workspace-tooling`
- `mission-control://projects/{project_id}/diagnostics`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/status`
- `mission-control://projects/{project_id}/orchestrations/{orchestration_id}/events`
- `mission-control://projects/{project_id}/webwright`
- `mission-control://projects/{project_id}/nvidia-dynamo`
- `mission-control://projects/{project_id}/nvidia-aiq`
- `mission-control://projects/{project_id}/nvidia-gpu-diagnostics`
- `mission-control://projects/{project_id}/nvidia-local-runtime`
- `mission-control://projects/{project_id}/nvidia-validation-plan`
- `mission-control://projects/{project_id}/risk-register`
- `mission-control://projects/{project_id}/agent-contracts`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/path-locks`
- `mission-control://projects/{project_id}/operator-snapshot`
- `mission-control://projects/{project_id}/instincts`
- `mission-control://projects/{project_id}/verification-brief`

These resources expose safe summaries only. They do not expose raw logs, secret headers, or giant transcripts by default because this is an orchestration bridge, not an exfiltration bridge.

## Pending decisions

Mission Control uses `PendingDecision` as the bridge-safe queue for:

- manager questions
- command approvals
- tool approvals
- write permission prompts
- swarm approvals
- snapshot approvals
- recovery decisions
- handoff review requests

Each decision includes:

- a text-safe title and message
- a risk level
- structured options
- an optional recommended option
- presentation metadata for Codex-style approval cards when supported

Custom UI is optional. Plain structured text must always be enough to complete the workflow.

## Dashboard is optional

The dashboard remains useful for operators who want live visual state, but it is not required for Codex plugin mode. The headless orchestration path is first-class now, not an apologetic afterthought.
