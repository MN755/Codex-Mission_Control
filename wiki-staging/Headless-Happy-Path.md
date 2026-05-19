# Background-Running Happy Path

This page documents the simplest successful Mission Control flow from install through final handoff using Codex chat as the bridge.

> Status: Current

## Overview

The background-running happy path is:

1. install or autowire Mission Control
2. run a health check
3. attach the workspace
4. start a task
5. handle any pending decision
6. check status
7. review an event digest if needed
8. get the final handoff

## Step 1: install or autowire

User prompt:

```text
Install Mission Control from https://github.com/MN755/Codex-Mission_Control and wire it up for this workspace.
```

Expected Codex chat text:

```text
Mission Control install summary

- Repo: attached
- Daemon: ready on localhost
- MCP bridge: configured
- Skills: available
- Preferred runner: codex_cli
- Missing action: none
```

## Step 2: health check

User prompt:

```text
Run a Mission Control health check.
```

Expected Codex chat text:

```text
Mission Control health

- Overall: ready
- Daemon: ready
- MCP bridge: ready
- Codex CLI: ready
- Runtime folder: writable
```

## Step 3: attach workspace

User prompt:

```text
Attach the current workspace to Mission Control.
```

Expected Codex chat text:

```text
Workspace attached to Mission Control.

- Project: repo-startup-fix
- Project id: 42
- Mode: existing codebase
- Next step: read-only scan and codebase understanding
```

## Step 4: start task

User prompt:

```text
Use Mission Control for this repo and fix the failing tests.
```

Expected Codex chat text:

```text
Mission Control task started.

- Project: repo-startup-fix
- Phase: planning
- Manager state: active
- Next checkpoint: targeted fix plan
```

## Step 5: handle a pending decision

User prompt:

```text
Show pending Mission Control approvals.
```

Expected Codex chat text:

```text
Pending decision: command approval
Risk: low
Reason: Mission Control wants to run the test suite before handoff.
Options: approve once, deny
```

User response:

```text
Approve once.
```

Expected Codex chat text:

```text
Decision recorded.

- Result: approved once
- Next step: validation is running
```

## Step 6: get status

User prompt:

```text
Show Mission Control status.
```

Expected Codex chat text:

```text
Mission Control status

- Project: repo-startup-fix
- Phase: validation
- Manager state: active
- Active agents: 2
- Pending decisions: 0
- Next step: prepare handoff
```

## Step 7: get an event digest

User prompt:

```text
Give me a Mission Control event digest for the last 15 minutes.
```

Expected Codex chat text:

```text
Last 15 minutes

- Workspace attached
- Existing repo scanned read-only
- Manager created targeted fix plan
- Validation ran after approval
- Handoff preparation started
```

## Step 8: get the handoff

User prompt:

```text
Get the latest Mission Control handoff.
```

Expected Codex chat text:

```text
Handoff summary

- Status: ready for review
- Confidence: medium
- Validation: tests ran
- Known limitation: deployment not verified
- Next task: review release readiness if shipping is required
```

## Related pages

- [Quick Start](Quick-Start)
- [Copy Paste Codex Prompts](Copy-Paste-Codex-Prompts)
- [Codex Chat Workflow](Codex-Chat-Workflow)
- [Pending Decisions and Approvals](Pending-Decisions-and-Approvals)
- [Handoffs and Evidence](Handoffs-and-Evidence)
