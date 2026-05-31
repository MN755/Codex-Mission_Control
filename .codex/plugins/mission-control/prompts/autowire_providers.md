# Autowire providers


Canonical prompt: `autowire_providers`
Invocation name: `autowire_providers`

## Purpose

Probe safe local runners and provider config, then summarize ready and degraded runner paths.

## Tool Sequence

- `mission_control_plugin_health`

## Resource Sequence

- No explicit Mission Control resources are declared.

## Safety Notes

Local-first. Do not silently use billed API providers or persist secrets in chat-visible output.

## Prompt Text

Autowire all safely available Mission Control runners and providers, prefer local runners first, and report exactly which providers are ready, degraded, unavailable, or require explicit user setup.
