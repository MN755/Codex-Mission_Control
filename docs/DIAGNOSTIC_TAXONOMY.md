# Mission Control Diagnostic Taxonomy

> Status: Current

Mission Control uses the same structured error model across health checks, API responses, Codex chat summaries, daemon logs, install reports, diagnostics, and handoffs so the same failure can be traced without guessing which layer renamed it.

## Flow of an error

The expected path is:

1. A runtime component raises a `MissionControlError` or an unknown exception.
2. Unknown exceptions are wrapped as `MC-UNKNOWN-UNEXPECTED-001`.
3. The error is reduced to a safe payload:
   - code
   - family
   - severity
   - breakpoint
   - retryable
   - user action required
   - recommended fix
   - correlation ID
   - safe details
4. Different formatters render the same error for different surfaces:
   - API problem details
   - Codex chat markdown
   - structured log event
   - health check item
   - install report item
   - diagnostic report item

## Diagnostic surfaces

### API and MCP responses

- Problem Details payloads carry stable fields for machine use.
- The `code` is the primary lookup key.
- `type` links to the wiki anchor for the code family entry.

### Codex chat summaries

- Codex chat receives a short, bridge-safe summary.
- The summary includes where the error happened, whether the user must act, whether it is retryable, and the recommended fix.
- Raw stack traces and secret-like values are excluded by default.

### Health checks

Health checks use coded status items so degraded and blocked states are explicit.

Each item can carry:

- `code`
- `status`
- `severity`
- `summary`
- `recommended_fix`
- `user_action_required`
- `retryable`
- `breakpoint`
- `correlation_id`

### Install reports

Install reports collect structured problems from bootstrap checks and runner probes. This keeps “install succeeded with warnings” separate from “install cannot proceed.”

### Diagnostics

Diagnostic reports should include:

- the current startup status
- the main problem payload, if one exists
- safe file locations
- safe recommended actions

### Handoffs

Handoffs use the same taxonomy for evidence gaps and validation failures. A handoff that claims success but carries `MC-HANDOFF-EVIDENCE-MISSING-001` or `MC-VALIDATION-NOT-RUN-001` is not evidence-backed yet.

## Correlation IDs

- Every `MissionControlError` gets a `correlation_id`.
- The correlation ID ties together API output, logs, diagnostics, and bridge summaries.
- Correlation IDs are safe to show in Codex chat.
- Correlation IDs are the preferred user-facing pointer into deeper internal logs.

## Redaction rules

Mission Control treats `safe_details` as a user-facing diagnostic payload, not a raw dump.

Rules:

- secret-like values are redacted before formatting
- `.env` values are not exposed
- API keys and tokens are not echoed back
- raw stack traces stay in internal logs by default
- `redaction_status` records whether the payload changed during redaction

## User action model

Diagnostics should make it obvious whether the next step belongs to the user or to Mission Control.

- `user_action_required: true` means Codex chat should ask for something explicit:
  - approval
  - workspace path
  - login
  - local service start
  - secure external configuration
- `user_action_required: false` means Mission Control can usually retry, degrade gracefully, or continue gathering diagnostics without blocking on the user

## Recommended fix style

Recommended fixes should be:

- local and specific
- safe to show in Codex chat
- phrased as the next practical step

Avoid:

- raw logs
- vague “contact support” wording
- instructions that require exposing secrets in chat

## Typical examples

### Missing Codex CLI

- code: `MC-CODEX-CLI-MISSING-001`
- breakpoint: `codex_cli.detect`
- likely surface: plugin health, startup checks, install report
- user action required: yes

### Invalid pending decision option

- code: `MC-DECISION-INVALID-OPTION-001`
- breakpoint: `decision.validate_option`
- likely surface: API response and Codex chat approval flow
- user action required: yes

### Unknown runtime exception

- code: `MC-UNKNOWN-UNEXPECTED-001`
- breakpoint: varies, preserved if known
- likely surface: problem details, diagnostics, logs
- user action required: usually no unless the safe details indicate a local repair step

## Related docs

- [Mission Control Errors](ERRORS.md)
- [Debug Breakpoints](DEBUG_BREAKPOINTS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
