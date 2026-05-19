# Pending Decisions and Approvals

This page explains the PendingDecision model, user approval flow, risk levels, and decision categories used by Mission Control.

> Status: Current

## Decision model

Pending decisions cover:

- command approvals
- tool approvals
- write permissions
- manager questions
- swarm approvals
- snapshot approvals
- handoff review
- recovery decisions
- scope change decisions
- safe mode confirmations

## Risk levels and auto-decision rules

Expected risk labels:

- low
- medium
- high
- critical

High-risk and critical actions should not auto-approve. Auto-decision rules, if present, should stay limited to low-risk, well-scoped actions and still record an audit trail.

## Examples

Command approval example:

```text
Pending decision: command approval
Risk: low
Command summary: run the repo test suite
```

Manager question example:

```text
Pending decision: manager question
Risk: medium
Question: should the final handoff optimize for builder detail or operator usage?
```

## User flow

1. Mission Control creates the decision.
2. Codex chat renders a safe summary.
3. User answers through chat.
4. Codex sends the answer back through the decision tool.
5. Mission Control resumes or remains blocked.

## Related pages

Read [Approval Card Fallback Text](Approval-Card-Fallback-Text), [Manager Questions](Manager-Questions), [Safe Mode](Safe-Mode), and [Safety and Security Model](Safety-and-Security-Model).
