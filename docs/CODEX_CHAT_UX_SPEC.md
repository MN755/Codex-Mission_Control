# Codex Chat UX Specification

This document defines the canonical chat-native outputs for Mission Control when used from Codex.

All outputs must be:

- compact
- evidence-based
- redacted
- bridge-safe

Default rules:

- no raw logs by default
- no secrets
- no fake claims
- no `tests passed` unless evidence exists

## Status Summary

Required fields:

- project
- orchestration state
- current phase
- manager intent
- active worker count
- waiting on user
- waiting on approval
- top risk
- latest evidence

Markdown example:

```md
## Mission Control Status

**Project:** security hardening
**Manager:** waiting for approval
**Mode:** dry_run / deterministic
**Swarm:** balanced / active
**User action needed:** yes

### Current work
- manager is reviewing validation blockers

### Waiting on you
- approve the safe local test command

### Next expected step
resume the dry-run validation turn
```

Structured payload fields:

- `project_id`
- `project_name`
- `manager_status`
- `mode`
- `swarm`
- `waiting_on_you`
- `next_expected_step`
- `current_blockers`
- `active_agent_count`
- `orchestration_status`

What not to include:

- raw log dumps
- full transcripts
- secrets

Redaction requirements:

- mask tokens, keys, cookies, and private paths when sensitive

## Pending Approval

Required fields:

- approval type
- title
- risk
- reason
- command or tool summary
- options
- recommended option when available

Markdown example:

```md
## Approval Needed

- Type: command
- Title: install test dependencies
- Risk: medium
- Reason: validation requires a missing package
- Command: `python -m pip install -r requirements.txt`

Reply with:
- `approve`
- `deny`
```

Structured payload fields:

- `decision_id`
- `decision_type`
- `risk_level`
- `title`
- `reason`
- `command`
- `tool_name`
- `options`
- `recommended_option`

What not to include:

- secret command arguments
- environment variable values
- raw headers

Redaction requirements:

- strip secret flags and secret-like values from command previews

## Manager Question

Required fields:

- question
- why it matters
- options
- recommended option when available
- impact

Markdown example:

```md
## Manager Question

- Question: Should the Manager defer integration cleanup?
- Why it matters: this changes scope and validation depth
- Impact: medium
- Recommended answer: defer integration cleanup
```

Structured payload fields:

- `decision_id`
- `question`
- `why`
- `impact`
- `options`
- `recommended_option`

What not to include:

- fake certainty
- hidden assumptions without stating them

Redaction requirements:

- redact any embedded secrets or private user data in context strings

## Handoff

Required fields:

- outcome
- what changed
- validation summary
- remaining risks
- follow-up actions

Markdown example:

```md
## Handoff Summary

- Outcome: success
- What changed: updated bridge-safe approval formatting and security docs
- Validation: targeted backend tests passed
- Remaining risks: full suite not run
- Follow-up: run broader integration checks before release
```

Structured payload fields:

- `project_id`
- `outcome`
- `changes`
- `validation`
- `remaining_risks`
- `follow_up`

What not to include:

- unverifiable success claims
- raw evidence blobs unless explicitly requested

Redaction requirements:

- redact secrets and sensitive paths from evidence summaries

## Error And Diagnostic Summary

Required fields:

- failure title
- impact
- likely cause
- next recovery action
- diagnostics availability

Markdown example:

```md
## Diagnostic Summary

- Issue: GitHub push blocked
- Impact: handoff ready, publish blocked
- Likely cause: remote auth or ref mismatch
- Next action: refresh auth and retry push
- Diagnostics: compact summary available
```

Structured payload fields:

- `error_type`
- `title`
- `impact`
- `likely_cause`
- `next_action`
- `diagnostics_available`

What not to include:

- raw stack traces by default
- full environment dumps

Redaction requirements:

- redact hostnames, keys, tokens, and credentials when sensitive

## Safe Mode Confirmation

Required fields:

- safe mode state
- why it changed
- what actions are blocked or narrowed

Markdown example:

```md
## Safe Mode Enabled

- State: enabled
- Reason: repeated command failures during validation
- Effect: high-risk actions stay blocked until review
```

Structured payload fields:

- `enabled`
- `reason`
- `restricted_actions`

What not to include:

- ambiguous descriptions of what safe mode does

Redaction requirements:

- keep reasons compact and non-secret

## Existing Codebase Understanding

Required fields:

- repo summary
- likely stack
- likely run/test commands
- top risks
- missing context

Markdown example:

```md
## Existing Codebase Understanding

- Summary: FastAPI backend with local-first orchestration and optional dashboard
- Likely stack: Python, FastAPI, SQLite, React, Vite
- Likely run command: `python -m uvicorn main:app --app-dir src --reload`
- Likely test command: `python -m pytest`
- Top risk: dashboard docs currently outweigh headless docs
```

Structured payload fields:

- `project_id`
- `summary`
- `detected_stack`
- `run_commands`
- `test_commands`
- `top_risks`
- `missing_context`

What not to include:

- fake architectural certainty
- giant directory listings

Redaction requirements:

- avoid disclosing sensitive local paths unless needed

## Event Digest

Required fields:

- time window or recent scope
- notable events
- blockers
- next expected action

Markdown example:

```md
## Event Digest

- Recent events: attach completed, scan completed, one approval created
- Blockers: waiting on command approval
- Next expected action: resume validation after user answer
```

Structured payload fields:

- `window`
- `events`
- `blockers`
- `next_action`

What not to include:

- verbose event transcripts

Redaction requirements:

- event descriptions must remain safe for chat display

## Swarm Explanation

Required fields:

- swarm goal
- worker count
- role split
- why this swarm size exists
- approval threshold or bottleneck note

Markdown example:

```md
## Swarm Explanation

- Goal: isolate backend fix and validate it safely
- Worker count: 3
- Roles: backend, test, review
- Why this size: enough parallelism without path overlap
- Bottleneck: waiting on validation evidence
```

Structured payload fields:

- `goal`
- `worker_count`
- `roles`
- `rationale`
- `bottlenecks`
- `approval_threshold`

What not to include:

- hidden worker behavior
- invented progress

Redaction requirements:

- do not expose secret tool config or tokens

## Recovery Options

Required fields:

- current issue
- impact
- options
- recommended option when available

Markdown example:

```md
## Recovery Options

- Current issue: daemon health check failed
- Impact: orchestration cannot resume
- Options:
  - restart daemon
  - inspect diagnostics summary
  - stop and preserve current handoff state
- Recommended option: inspect diagnostics summary
```

Structured payload fields:

- `issue`
- `impact`
- `options`
- `recommended_option`

What not to include:

- destructive suggestions without explicit labeling

Redaction requirements:

- keep recovery detail compact and secret-free
