# Errors and Debug Codes

> Status: Current

Mission Control uses stable structured error codes so Codex chat, MCP responses, daemon logs, health checks, install reports, diagnostics, and handoffs can describe the same failure consistently.

## Error format

Mission Control error codes use this format:

`MC-{FAMILY}-{SPECIFIC}-{NNN}`

Examples:

- `MC-BOOT-RUNTIME-PATH-001`
- `MC-CODEX-CLI-MISSING-001`
- `MC-DECISION-INVALID-OPTION-001`

## What each error includes

- code
- family
- severity
- breakpoint
- retryable
- user action required
- recommended fix
- correlation ID
- safe details

Mission Control API responses use an RFC 9457-style Problem Details payload and add the fields above for machine-readable diagnostics.

## Severity levels

| Severity | Meaning |
| --- | --- |
| `debug` | developer detail, not shown by default |
| `info` | normal informational state |
| `warning` | degraded but still usable |
| `error` | operation failed |
| `fatal` | startup or core operation cannot continue |

## Major families

- `MC-BOOT`
- `MC-CONFIG`
- `MC-DAEMON`
- `MC-MCP`
- `MC-PLUGIN`
- `MC-RUNNER`
- `MC-CODEX`
- `MC-OLLAMA`
- `MC-CLAUDE`
- `MC-API`
- `MC-AUTH`
- `MC-SECRET`
- `MC-WORKSPACE`
- `MC-SCAN`
- `MC-ORCH`
- `MC-MANAGER`
- `MC-AGENT`
- `MC-SUBAGENT`
- `MC-DECISION`
- `MC-BRIDGE`
- `MC-HANDOFF`
- `MC-VALIDATION`
- `MC-SECURITY`
- `MC-DIAGNOSTIC`
- `MC-STORAGE`
- `MC-NETWORK`
- `MC-DOCS`
- `MC-UNKNOWN`

## Frequently encountered codes

| Code | Meaning | Typical next step |
| --- | --- | --- |
| `MC-DAEMON-NOT-RUNNING-001` | daemon not running | start the local daemon and retry health |
| `MC-MCP-BRIDGE-MISSING-001` | MCP bridge missing | reload bridge configuration |
| `MC-CODEX-CLI-MISSING-001` | Codex CLI not on PATH | install or expose Codex CLI |
| `MC-CODEX-LOGIN-UNKNOWN-001` | login state unclear | run `codex login status` |
| `MC-OLLAMA-SERVER-OFFLINE-001` | local Ollama server offline | start Ollama locally |
| `MC-WORKSPACE-PATH-MISSING-001` | workspace path missing | supply a valid path |
| `MC-DECISION-INVALID-OPTION-001` | invalid approval answer | choose one of the allowed options |
| `MC-HANDOFF-EVIDENCE-MISSING-001` | handoff evidence incomplete | run or record missing validation |
| `MC-VALIDATION-NOT-RUN-001` | validation not confirmed | run the required validation step |
| `MC-UNKNOWN-UNEXPECTED-001` | fallback unexpected error | inspect the correlation ID and diagnostics |

## Redaction

- safe details are redacted before user-facing output
- raw secrets, tokens, and `.env` values are not shown in Codex chat by default
- stack traces belong in internal logs, not in bridge summaries

## Related pages

- [Debug Breakpoints](Debug-Breakpoints)
- [Troubleshooting Error Codes](Troubleshooting-Error-Codes)
- [Diagnostics and Health Checks](Diagnostics-and-Health-Checks)
