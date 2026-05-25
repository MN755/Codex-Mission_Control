# Provider Autowiring

This page describes what Mission Control can detect automatically, what requires explicit user action, and what must never be automatic.

> Status: Current

## What can be automatic

Automatic probing can safely check:

- local CLI presence
- login state availability when the CLI exposes it
- daemon and runtime readiness
- localhost health endpoints
- plugin/skill file presence
- Ollama service presence
- built-in adapter recipe availability for Ollama and API-backed providers

## What requires user action

User action may still be needed for:

- Codex login
- Claude CLI login or install
- API provider secrets in a secure store
- network-heavy model downloads
- elevated permissions outside the workspace
- app reload after plugin or MCP configuration changes

## What should never be automatic

Never do these automatically:

- print raw API keys into logs, diagnostics, or docs
- pull huge Ollama models without approval
- silently switch to billed API providers
- silently widen filesystem permissions

## Redaction and reporting

Install and health reports should return:

- detected providers
- configured providers
- blocked or missing prerequisites
- next manual action

Reports should not contain secrets.

## Related pages

See [Runner Configuration](Runner-Configuration), [Install From Codex](Install-From-Codex), [Headless Install and Autowire](Headless-Install-and-Autowire), and [Safety and Security Model](Safety-and-Security-Model).
