---
name: mission-control-import-codebase
description: Import or attach an existing codebase into Mission Control. Use when the workspace already contains a repo and Codex should let Mission Control scan, understand, and classify it before edits.
---

# Mission Control Import Codebase

## Purpose

Import an existing repo safely and let Mission Control build understanding before execution.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The folder is non-empty and looks like a real codebase.
- The user wants Mission Control to take over an existing repo.
- You need codebase understanding before planning or writing.

## Workflow

1. Attach the current workspace with `mission_control_attach_workspace`.
2. Use `mission_control_import_existing_codebase` or the import prompt path for non-empty folders.
3. Request a read-only scan first.
4. Retrieve the codebase map and understanding summary.
5. Ask whether to skip interview, quick clarify, full interview, or let the Manager decide.
6. Start the requested task only after the understanding path is chosen.

## Mission Control calls

Tools:
- `mission_control_attach_workspace`
- `mission_control_import_existing_codebase`
- `mission_control_get_status`
- `mission_control_start_task`

Resources:
- `mission-control://projects/{project_id}/codebase-map`
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/pending-decisions`

## User-facing output

- Summarize what Mission Control learned about the stack and entry points.
- Show the available intake choices: skip, quick clarify, full interview, or Manager decides.
- Report the project identifier and safest next step.

## Approval behavior

Ask before any write-capable step, import permission change, or interview-skipping choice that materially changes assumptions.

## Never do

- Do not run builds, installs, or tests during initial scan unless the user explicitly wants that.
- Do not expose `.env` contents or secrets.
- Do not skip understanding and jump into edits.

## Failure and fallback

If import tooling is missing, attach the workspace, explain that import-specific tooling is expected or future, and rely on read-only codebase resources where available. If Mission Control registered but only partial MCP capabilities exposed, say that exact bridge limitation before falling back.

## Example invocation

`Attach this existing repo to Mission Control, scan it read-only, and then let the Manager decide how to proceed.`
