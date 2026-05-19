# Headless UX

This document describes the primary Mission Control user experience from inside Codex.

The key role split is fixed:

- Codex chat is the bridge
- Mission Control daemon owns orchestration
- Mission Control Manager plans and coordinates work
- worker runners execute in the background

The user-facing UX should appear in:

- Codex chat messages
- skills and prompts
- MCP tools/resources/prompts
- approval payloads
- status summaries
- handoff summaries
- diagnostics summaries
- install and autowire summaries

## Workflow A: Install From GitHub

User:

`Install Mission Control from MN755/Codex-Mission_Control and wire it up.`

Expected flow:

1. Codex clones or reuses the repo locally.
2. Codex runs a headless bootstrap flow.
3. Mission Control detects available runners.
4. Mission Control configures daemon and MCP wiring.
5. Mission Control reports `ready`, `degraded`, or `blocked`.
6. Codex asks only for missing logins, secrets, or permissions when required.

Expected summary shape:

- install source
- bootstrap result
- daemon status
- MCP status
- runner detection summary
- missing requirements
- next command or next prompt

## Workflow B: Attach Empty Folder

User:

`Use Mission Control to build this project.`

Expected flow:

1. Codex attaches the current workspace.
2. Mission Control creates or reuses a project record.
3. Mission Control Manager may ask a short clarification set.
4. Mission Control produces a plan and swarm posture.
5. Background execution begins only after required approvals.
6. Approvals and questions relay through Codex chat.
7. Mission Control returns a chat-native handoff.

Expected bridge behavior:

- no standalone dashboard required
- no worker-side user chats
- no fake task progress

## Workflow C: Attach Existing Repo

User:

`Use Mission Control to understand this repo and fix the failing tests.`

Expected flow:

1. Codex attaches the workspace.
2. Mission Control performs a read-only scan first.
3. Mission Control builds a codebase map and understanding summary.
4. Mission Control may ask a brief clarification if repo intent or scope is ambiguous.
5. Mission Control starts the task.
6. Status, approvals, and handoff stay in Codex chat.

Expected scan outputs:

- codebase map
- likely stack
- likely run/test commands
- known risks
- missing context
- first task recommendation

## Workflow D: Pending Approval

Mission Control should relay approvals as compact, structured, bridge-safe summaries.

### Command approval example

User-facing example:

```md
## Approval Needed

Mission Control wants to run a command.

- Type: command
- Risk: medium
- Working directory: `C:\repo`
- Reason: install test dependencies needed for validation
- Command: `python -m pytest`

Reply with:
- `approve`
- `deny`
- `approve for this project` when policy allows it
```

### Tool approval example

```md
## Approval Needed

Mission Control wants to use a tool.

- Type: tool
- Risk: high
- Tool: deployment
- Reason: publish the built artifact to the configured environment

Reply with:
- `approve`
- `deny`
```

### Manager question example

```md
## Manager Question

The Manager needs a scope decision before continuing.

- Question: Should failing integration tests block the MVP fix?
- Recommended answer: defer integration cleanup
- Why it matters: this changes scope and validation depth

Reply with one of:
- `block on integration tests`
- `defer integration cleanup`
```

## Workflow E: Status Check

User:

`What is Mission Control doing right now?`

Expected status summary:

```md
## Mission Control Status

- Project: repo test repair
- State: running
- Current phase: validation
- Manager intent: finish test triage and confirm fix scope
- Active workers: 2
- Waiting on user: no
- Waiting on approval: yes
- Top risk: dependency install may widen scope
- Latest evidence: failing test narrowed to one backend module
```

## Workflow F: Handoff

User:

`Show me the handoff.`

Expected handoff format:

```md
## Handoff Summary

- Outcome: partial success
- What changed: fixed backend test harness and updated docs
- Validation run: `python -m pytest apps/server/tests/test_security.py`
- Validation result: passed
- Remaining issues: full suite not run
- Next recommended action: run broader backend tests before release
```

Expected sections:

- outcome
- what changed
- validation run
- validation result
- remaining issues
- next recommended action

## Workflow G: Failure And Recovery

User:

`Why is Mission Control stuck?`

Expected flow:

1. Codex asks Mission Control for a diagnostics summary or event digest.
2. Mission Control returns a compact, redacted explanation.
3. If recovery choices exist, Mission Control presents them as structured options.
4. Codex relays the user choice.
5. Mission Control resumes or pauses accordingly.

Expected recovery summary:

```md
## Recovery Options

- Current issue: missing GitHub authentication for push
- Impact: handoff ready, publish blocked
- Safe options:
  - re-authenticate GitHub CLI
  - switch remote to SSH
  - stop before publish and keep local handoff
```

## Headless UX Rules

- no dashboard dependency for normal use
- no raw logs by default
- no secrets in summaries
- no fake claims about tests, deploys, or approvals
- no confusion between Codex chat and the Manager AI
