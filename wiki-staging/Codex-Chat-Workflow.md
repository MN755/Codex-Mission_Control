# Codex Chat Workflow

This page documents the actual user experience inside Codex chat when Mission Control is running in headless bridge mode.

> Status: Current

## Role split

Codex chat relays information.

Manager AI makes orchestration decisions.

The user approves, answers, and reviews through Codex chat.

## Status summary example

Example:

```text
Mission Control status

- Project: repo-startup-fix
- Phase: validation
- Manager state: waiting on approval
- Active agents: 2
- Blocker: test command requires approval
- Next step: approve or deny the requested validation run
- Handoff readiness: not ready
```

## Approval and question examples

Approval example:

```text
Pending decision: command approval
Risk: low
Reason: Mission Control wants to run the test suite before handoff.
Options: approve once, deny
```

Manager question example:

```text
Mission Control needs one product decision before planning:
Should the final handoff prioritize builder-ready implementation detail or operator-ready usage instructions?
```

## Event digest, handoff, and failure examples

Event digest example:

```text
Last 15 minutes
- Workspace attached
- Existing repo scanned read-only
- Manager created targeted fix plan
- Validation command requested approval
```

Handoff example:

```text
Handoff summary
- Confidence: medium
- Validation: tests ran, typecheck skipped
- Known limitation: deployment not verified
```

Failure example:

```text
Debug summary
- Blocker: Codex CLI not detected
- Recommended fix: verify local Codex installation and login status
```

## Related pages

Read [Manager AI vs Codex Chat](Manager-AI-vs-Codex-Chat), [Pending Decisions and Approvals](Pending-Decisions-and-Approvals), [Handoffs and Evidence](Handoffs-and-Evidence), and [Debugging Common Issues](Debugging-Common-Issues).
