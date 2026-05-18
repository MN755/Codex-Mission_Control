# Codex Approval UI

This document describes the desired user-facing approval and decision presentation when Mission Control is surfaced through Codex.

Custom approval UI is optional and depends on Codex plugin presentation support. If structured cards are unavailable, the fallback text format below is the expected backup.

## Goals

- Make pending decisions obvious
- Preserve risk level and exact requested action
- Keep user response explicit
- Avoid hiding dangerous operations behind vague language

## Desired approval card style

Each approval or question card should show:

- title
- request type
- risk level
- short reason
- exact action or command when available
- working directory or target path when relevant
- safer alternative or mitigation when relevant

## Buttons

Recommended button set:

- `Approve once`
- `Deny`
- `Ask Manager for safer option`
- `Open details`

Question-type cards can use:

- `Accept recommendation`
- `Choose another option`
- `Ask follow-up`

Write-permission cards can use:

- `Keep read-only`
- `Allow limited write`
- `Allow write`

## High-risk actions

Treat these as high risk by default:

- destructive filesystem commands
- dependency installs from untrusted repos
- package manager lockfile rewrites
- build or test commands on unfamiliar imported codebases when policy still requires approval
- broad formatting or refactor passes across the repo
- permission changes from read-only to write-enabled

## Structured payload shape

Suggested payload fields:

```json
{
  "type": "command_approval",
  "title": "Approve build command",
  "risk_level": "low",
  "reason_short": "Mission Control wants to run the project build before handoff.",
  "details": {
    "command": "npm run build",
    "cwd": "/workspace/app"
  },
  "actions": [
    {"id": "approve_once", "label": "Approve once"},
    {"id": "deny", "label": "Deny"},
    {"id": "ask_safer_option", "label": "Ask Manager for safer option"}
  ]
}
```

## Fallback text format

If custom cards are unavailable, render pending decisions like this:

```text
Mission Control needs a decision.
Type: command approval
Risk: low
Reason: Mission Control wants to run the project build before handoff.
Command: npm run build
Working directory: /workspace/app
Reply with one of:
- approve
- deny
- ask for safer option
```

## Example payloads

### Command approval

```json
{
  "type": "command_approval",
  "title": "Approve test run",
  "risk_level": "medium",
  "reason_short": "Mission Control wants to run the test suite before applying the final handoff.",
  "details": {
    "command": "python -m pytest",
    "cwd": "/workspace/apps/server"
  }
}
```

### Tool approval

```json
{
  "type": "tool_approval",
  "title": "Approve browser verification",
  "risk_level": "medium",
  "reason_short": "Mission Control wants to verify the local UI with the browser tool.",
  "details": {
    "tool_name": "Browser",
    "target": "http://127.0.0.1:5173"
  }
}
```

### Manager question

```json
{
  "type": "manager_question",
  "title": "Choose the first priority",
  "risk_level": "low",
  "reason_short": "Mission Control needs a project decision before routing worker tasks.",
  "details": {
    "question": "What should the Manager prioritize first?",
    "options": [
      "Fix failing tests",
      "Implement the requested feature",
      "Write missing docs"
    ],
    "recommended_option": "Fix failing tests"
  }
}
```

### Swarm approval

```json
{
  "type": "swarm_approval",
  "title": "Approve swarm plan",
  "risk_level": "medium",
  "reason_short": "Mission Control recommends a five-agent swarm for faster delivery with moderate coordination risk.",
  "details": {
    "recommended_agent_count": 5,
    "coordination_risk": "medium",
    "current_bottleneck": "Frontend and validation work share adjacent paths."
  }
}
```

### Write permission request

```json
{
  "type": "write_permission_request",
  "title": "Allow edits on imported codebase",
  "risk_level": "high",
  "reason_short": "Mission Control completed the read-only scan and now needs permission to make changes.",
  "details": {
    "project_mode": "imported_codebase",
    "current_permission": "read_only",
    "requested_permission": "write_allowed"
  }
}
```
