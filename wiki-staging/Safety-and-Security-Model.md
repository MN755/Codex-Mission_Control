# Safety and Security Model

This page summarizes the practical safety model for headless Mission Control operation, approvals, redaction, and local-only daemon behavior.

> Status: Current

## Core principles

Mission Control is local-first.

The daemon should be localhost-only.

Secrets should never appear in logs, docs, diagnostics, approval summaries, or handoffs.

High-risk actions should remain behind explicit approval.

## What is not allowed

Mission Control should not:

- expose raw API keys in storage or docs
- run arbitrary shell commands through MCP as an uncontrolled escape hatch
- silently switch to billed providers
- skip safe imported-codebase mode
- weaken approvals to make demos look smoother

## Imported codebase safety

Imported codebases should default to:

- read-only scan first
- write permission prompts
- redacted summaries
- cautious runner use

## Billing and external effects

API billing warnings should be explicit.

Plugin/account side effects should remain gated.

Network-heavy actions such as model pulls or dependency installs should not be treated like harmless local reads.

## Related pages

Continue with [Provider Autowiring](Provider-Autowiring), [Pending Decisions and Approvals](Pending-Decisions-and-Approvals), [Safe Mode](Safe-Mode), and [Logs and Runtime Folders](Logs-and-Runtime-Folders).
