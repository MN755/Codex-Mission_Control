---
name: mission-control-snapshot
description: Request a Mission Control snapshot or restore point before risky work. Use when the user wants rollback safety before refactors, broad edits, or uncertain changes, preferably through git-aware snapshotting when available.
---

# Mission Control Snapshot

## Purpose

Request a rollback point before risky work without restoring anything automatically.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for a snapshot.
- A refactor or broad change is risky.
- Recovery confidence should increase before edits begin.

## Workflow

1. Explain the likely snapshot mechanism: git snapshot, branch, commit, or another restore point if supported.
2. Call `mission_control_request_snapshot` when available.
3. Confirm the snapshot result and how it may be used later.
4. Do not perform restore actions in this skill.

## Mission Control calls

Tools:
- `mission_control_request_snapshot`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/status`
- `mission-control://projects/{project_id}/decision-ledger`

## User-facing output

- Explain whether a snapshot exists, what it protects, and any limits if the repo is not under git or snapshot support is absent.
- Keep the result operationally clear.

## Approval behavior

Creating a snapshot is usually safe, but restoring from one later may be destructive and requires separate approval.

## Never do

- Do not restore automatically.
- Do not imply rollback is guaranteed when snapshot support is weak.
- Do not hide unsupported state when there is no git history or snapshot tool.

## Failure and fallback

If snapshot tooling does not exist, say so directly, note whether git is likely available, and mark snapshot creation as expected or future.

## Example invocation

`Request a Mission Control snapshot before the refactor starts.`
