# Security Model

Mission Control is a local-first orchestration layer. That does not make it magically safe. It just means the blast radius starts on the local machine instead of in somebody else's cloud.

This document defines the practical security model for approvals, permissions, redaction, and local daemon exposure.

## Core invariants

- The Mission Control daemon is local-only by default and should bind to loopback, not a public interface.
- Codex chat is the user-facing bridge. Mission Control remains the authority for approvals and policy enforcement.
- Plugin, MCP, and connected-account actions must not bypass Mission Control approval checks.
- High-risk and critical actions must never auto-approve.
- Secret material must be redacted before it reaches diagnostics, approval payload summaries, audit logs, or handoff evidence.
- Mission Control must not require API keys for the Codex login flow.

## Assets that matter

- Local source code and workspace files
- Local runtime state in SQLite and runtime folders
- Approval decisions and audit history
- Connected accounts and plugin permissions
- Provider credentials, CLI auth state, tokens, `.env` data, and private keys
- Deployment targets and external services

## Trust boundaries

### User boundary

The user is the final authority for high-risk actions. Manager or worker agents can recommend actions, but they do not get to silently bless dangerous ones.

### Mission Control boundary

Mission Control is the policy enforcement layer between:

- Codex desktop chat and the daemon
- Manager decisions and worker execution
- Plugin or connected-account requests and actual side effects

### Workspace boundary

Workspace writes are safer than arbitrary filesystem writes, but they are still writes. Anything outside the current workspace is treated as critical unless explicitly and deliberately approved by the user.

### External boundary

Anything that deploys, installs dependencies from the network, uses external accounts, or requests remote side effects crosses a higher-risk boundary.

## Deterministic risk assessment

Mission Control uses a deterministic classifier. It does not execute commands to guess risk.

Important examples:

- local validation commands like `python -m pytest` are low risk
- dependency installs like `npm install` are high risk
- deployments like `vercel deploy` are high risk
- deleting folders is critical
- reading `.env`, private keys, or bearer tokens is critical
- writing outside the workspace is critical

The classifier produces:

- risk level
- reasons
- affected paths
- external-access flags
- recommended approval posture

## Approval model

Mission Control stores:

- `SecurityPolicy`: default approval behavior for commands, tools, network, writes, deployments, and destructive actions
- `RiskAssessment`: normalized classification for a requested action
- `ApprovalAuditLog`: what was requested, how risky it was, who decided, and why

High-risk and critical actions stay gated even if low-risk auto-approval is enabled.

## Redaction model

Mission Control redacts common secret patterns before persistence or display:

- API keys
- bearer tokens
- `.env`-style secrets
- private keys
- passwords
- common provider-specific key prefixes

Redaction is applied to:

- diagnostics
- approval details
- audit logs
- MCP and resource summaries
- handoff evidence summaries

## Local daemon security

Mission Control is intended for loopback use:

- backend host should remain `127.0.0.1` unless you are deliberately widening the trust boundary
- bridge calls should require the local Mission Control token
- the daemon should not be treated as a public web service

If you expose it publicly, you own the consequences. Mission Control does not pretend that is a hardened default.

## What Mission Control will never auto-approve

- destructive file deletion
- writes outside the workspace
- credential or secret access
- deployments or releases when policy denies them
- connected-account or plugin side effects when policy denies them
- high-risk or critical actions when `high_risk_requires_user` is enabled

## Non-goals

- It is not a full OS sandbox.
- It does not prove a command is safe.
- It does not let plugin or MCP tools become arbitrary shell launchers.
- It does not replace code review or environment hardening.
