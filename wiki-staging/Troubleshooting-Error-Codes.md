# Troubleshooting Error Codes

> Status: Current

This page covers the most common Mission Control error codes a user is likely to see in Codex chat, health checks, diagnostics, or install reports.

## `MC-DAEMON-NOT-RUNNING-001`

What it means:

- the local daemon is not reachable

What to do:

- start the daemon locally
- rerun the health check
- verify the localhost port is correct

## `MC-MCP-BRIDGE-MISSING-001`

What it means:

- Codex cannot reach the Mission Control MCP bridge

What to do:

- reload MCP configuration
- verify that Mission Control tools, resources, and prompts are registered

## `MC-CODEX-CLI-MISSING-001`

What it means:

- Codex CLI is not installed or not on `PATH`

What to do:

- install Codex CLI
- expose it on `PATH`
- continue in dry-run mode if needed

## `MC-CODEX-LOGIN-UNKNOWN-001`

What it means:

- Mission Control cannot confirm Codex CLI authentication

What to do:

- run `codex login status`
- sign in again if required

## `MC-OLLAMA-SERVER-OFFLINE-001`

What it means:

- local Ollama was expected but is not reachable

What to do:

- start Ollama locally
- confirm at least one model is available

## `MC-WORKSPACE-PATH-MISSING-001`

What it means:

- Mission Control was asked to attach or start work without a valid workspace path

What to do:

- provide the project folder path explicitly

## `MC-DECISION-INVALID-OPTION-001`

What it means:

- the answer to a pending decision was not one of the allowed options

What to do:

- refresh the pending decision list
- choose one of the returned options exactly

## `MC-HANDOFF-EVIDENCE-MISSING-001`

What it means:

- the handoff exists, but one or more claims do not have recorded evidence

What to do:

- run or record the missing validation
- regenerate the handoff

## `MC-VALIDATION-NOT-RUN-001`

What it means:

- Mission Control cannot confirm that the requested validation actually ran

What to do:

- run the validation step
- attach the result to the handoff or diagnostics

## `MC-UNKNOWN-UNEXPECTED-001`

What it means:

- Mission Control hit an unexpected internal exception

What to do:

- capture the correlation ID
- inspect diagnostics and internal logs
- retry if the issue appears transient

## Related pages

- [Errors and Debug Codes](Errors-and-Debug-Codes)
- [Debug Breakpoints](Debug-Breakpoints)
- [Debugging Common Issues](Debugging-Common-Issues)
