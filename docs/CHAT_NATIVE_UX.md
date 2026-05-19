# Chat-Native UX

Mission Control should read cleanly inside Codex chat without relying on the standalone app.

Codex chat is the bridge. It is not the Manager AI.

## Core outputs

- status summaries
- approval requests
- manager questions
- event digests
- handoff summaries
- diagnostic summaries
- safe-mode updates

## Status summary shape

Mission Control status responses are compact markdown, not log dumps.

```md
## Mission Control Status

**Project:** Repo Fix
**Manager:** Waiting for approval
**Mode:** dry_run / auto
**Swarm:** balanced / active
**User action needed:** yes
**Orchestration:** waiting_for_user
**Handoff:** not_ready
**Active agents:** 2

### Current work
- Manager is preparing the next safe step.
- Verifier: Simulating a local test command
- Blocker: A command approval is still open.

### Waiting on you
- Approve local validation command: Run a simulated local test command before continuing.

### Next expected step
Resume the runner once the approval is answered.
```

## Approval request shape

Command and tool approvals must be readable in plain text even if Codex cannot render custom cards.

```md
## Approve local validation command

**Risk / impact:** medium
**Requesting agent:** Verifier
**Command:** `python -m pytest`
**Working directory:** `C:/repo`
**Scope:** tests/
**Reason:** Run the local test command so Mission Control can validate the change safely.
**Recommended option:** `approve_once`

### Options
- `approve_once`: Approve once - Allow this exact action one time.
- `deny`: Deny - Reject this action and keep the current safeguards in place.
- `always_allow_if_safe`: Always allow if safe - Allow this class of action for the current project when Mission Control policy permits it.
```

## Manager question shape

```md
## Mission Control Manager needs a decision

**Risk / impact:** medium
**Question:** Should the repo preserve the current architecture?
**Impact:** high
**Auto-decide:** 2026-05-18T12:34:56+00:00

### Options
- `preserve`: Preserve it - Keep the current structure intact.
- `change`: Change it - Allow broader restructuring.
```

## Event digest shape

Digests are grouped summaries for recent work windows, not raw logs.

```md
## Mission Control event digest

### Manager
- Background turn completed -> waiting_for_user

### Approvals
- approval created: command_approval
- pending decision answered: command_approval

### Validation
- validation log: pytest reported one failing test
```

## Failure and safe-mode messages

Failures should explain the next safe step instead of trying to sound dramatic.

- failed status: explain what broke and what Mission Control needs next
- blocked status: explain what is waiting on the user
- safe mode: explain what is restricted and why

Failed orchestration example:

```md
## Mission Control Status

**Project:** Repo Fix
**Manager:** Background turn failed while validating the dry-run handoff.
**Mode:** dry_run / auto
**Swarm:** balanced / active
**User action needed:** no
**Orchestration:** failed
**Handoff:** not_ready
**Active agents:** 0

### Current work
- Background orchestration failed while preparing the next step.
- Blocker: Validation evidence is incomplete.

### Waiting on you
- Nothing pending from the user right now.

### Next expected step
Inspect the diagnostic summary and restart the orchestration after the blocker is resolved.
```

Safe-mode example:

```md
## Safe mode enabled

Mission Control is using stricter bridge-safe controls for this project.

- Require all command approvals: yes
- Destructive actions blocked: yes
- Deployment tools blocked: yes
- External account tools require approval: yes
- Dynamic spawning paused: yes
- Imported codebases require read-only scan: yes
```

## Redaction rules

Every chat-native output is passed through secret redaction before it leaves the backend.

Redacted patterns include:

- API keys
- bearer tokens
- private keys
- `.env`-style secret assignments
- common provider key prefixes such as `sk-proj-`, `ghp_`, and `xoxb-`
