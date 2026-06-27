# Headless Happy Path

Mission Control should be usable from Codex chat without opening the dashboard at all.

## Small Validated Flow

1. Attach the workspace.
2. Start a task in `dry_run` or a configured runner.
3. Show a compact status summary in Codex chat.
4. Surface a pending approval.
5. Answer it through the bridge.
6. Show the event digest.
7. Show the handoff summary.
8. Show the approval audit log.

Transcript proof:

- [Terminal Transcript](TERMINAL_TRANSCRIPT.md)

## Primary endpoints

- `POST /api/headless/attach-workspace`
- `POST /api/orchestrations/attach-workspace`
- `POST /api/orchestrations`
- `POST /api/headless/start-task`
- `GET /api/orchestrations/{orchestration_id}/status-summary`
- `GET /api/orchestrations/{orchestration_id}/pending-decisions`
- `POST /api/decisions/{decision_id}/answer`
- `GET /api/orchestrations/{orchestration_id}/event-digest`
- `GET /api/orchestrations/{orchestration_id}/handoff-summary`
- `GET /api/projects/{project_id}/security/audit-log`
- `POST /api/headless/happy-path-demo`

`/api/orchestrations/attach-workspace` still exists for compatibility, but the headless-first path should use `/api/headless/attach-workspace`.

## Deterministic acceptance test

The backend happy-path test lives in:

- `apps/server/tests/test_headless_happy_path.py`

It covers:

- attach workspace
- start orchestration
- start task through the headless bridge
- status summary markdown
- pending command approval formatting
- answering the decision
- compact event digest
- dry-run handoff generation
- approval audit log
- redaction of secrets from chat output

## Deterministic demo route

`POST /api/headless/happy-path-demo` runs a dry-run-only bridge walkthrough:

1. attach workspace
2. force `dry_run`
3. create or reuse an orchestration
4. wait for or seed a pending decision
5. render the bridge message
6. answer the decision
7. return an event digest
8. return a dry-run handoff summary

It does not claim real edits or real test execution happened, because lying in the demo path would be an impressively stupid design choice.

## Smoke script

The manual smoke script lives in:

- [scripts/smoke-headless-happy-path.ps1](../scripts/smoke-headless-happy-path.ps1)

It will:

1. verify the local daemon, or start it if allowed
2. create a temporary repo-shaped workspace
3. attach that workspace
4. start a headless `dry_run` task
5. print the status summary
6. print and answer one approval
7. print the event digest
8. print the handoff summary
9. print the approval audit log

## Why this exists

If the happy path only works from the dashboard, Mission Control is not actually headless. It is just pretending while the dashboard does the real work behind the curtain.
