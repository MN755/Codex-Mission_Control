# Mission Control Errors

> Status: Current

Mission Control uses stable structured error codes so Codex chat, MCP responses, daemon logs, health checks, install reports, diagnostics, and handoffs can describe failures consistently without exposing secrets.

The generated registry is published in [Error Registry](ERROR_REGISTRY.md). It is exported directly from `apps/server/src/errors/registry.py` so the public reference does not drift from the code.

## Error shape

Mission Control error responses follow an RFC 9457-style Problem Details shape and add Mission Control fields:

```json
{
  "type": "https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-runner-codex-cli-missing-001",
  "title": "Codex CLI missing",
  "status": 503,
  "detail": "Codex CLI was not found on PATH.",
  "instance": "/api/plugin-health",
  "code": "MC-CODEX-CLI-MISSING-001",
  "family": "MC-CODEX",
  "severity": "warning",
  "breakpoint": "codex_cli.detect",
  "retryable": true,
  "user_action_required": true,
  "recommended_fix": "Install Codex CLI or expose it on PATH, or continue with dry-run mode.",
  "correlation_id": "6f0f7d0d9ac846f0b3d4c1d2db6d11f2",
  "safe_details": {
    "runner": "codex_cli"
  }
}
```

Internal log events may also include `exception.type`, `exception.message`, and `exception.stacktrace`. Stack traces stay in internal logs by default and are not intended for Codex chat summaries.

## Code format

Codes use this format:

`MC-{FAMILY}-{SPECIFIC}-{NNN}`

Examples:

- `MC-BOOT-RUNTIME-PATH-001`
- `MC-MCP-TOOL-NOT-FOUND-001`
- `MC-DECISION-INVALID-OPTION-001`

Rules:

- Codes are stable identifiers.
- Codes do not contain dynamic values.
- User-facing wording may change, but the code should not.
- The code is the fastest way to search logs, diagnostics, tests, and docs.

## Error families

Mission Control currently defines these families:

- `MC-BOOT`: startup and bootstrap
- `MC-CONFIG`: background-running config
- `MC-DAEMON`: daemon lifecycle
- `MC-MCP`: MCP bridge, tools, resources, prompts
- `MC-PLUGIN`: plugin package and skills
- `MC-RUNNER`: runner registry and lifecycle
- `MC-CODEX`: Codex CLI
- `MC-OLLAMA`: Ollama
- `MC-CLAUDE`: Claude CLI
- `MC-API`: API-backed runners
- `MC-AUTH`: auth and bridge token checks
- `MC-SECRET`: secret redaction failures
- `MC-WORKSPACE`: workspace attach and path handling
- `MC-SCAN`: existing codebase scan and indexing
- `MC-ORCH`: orchestration session lifecycle
- `MC-MANAGER`: Manager AI planning and question flow
- `MC-AGENT`: worker agent lifecycle
- `MC-SUBAGENT`: Codex subagent burst flow
- `MC-DECISION`: pending decisions and approvals
- `MC-BRIDGE`: chat bridge formatting and redaction
- `MC-HANDOFF`: handoff and evidence
- `MC-VALIDATION`: build, test, and validation execution
- `MC-SECURITY`: policy and safety blocks
- `MC-DIAGNOSTIC`: health and diagnostic report generation
- `MC-STORAGE`: SQLite and runtime files
- `MC-NETWORK`: localhost and port checks
- `MC-DOCS`: documentation validation
- `MC-UNKNOWN`: fallback unexpected errors

## Severity and user-facing status

Severity describes technical seriousness. Health status describes how usable Mission Control remains.

| Severity | Meaning | Typical user-facing status |
| --- | --- | --- |
| `debug` | developer detail, not shown by default | `ready` |
| `info` | normal state or informative skip | `ready` |
| `warning` | degraded but usable | `degraded` |
| `error` | operation failed, system may continue | `failed` or `blocked` |
| `fatal` | startup or core service cannot continue | `fatal` |

## Retryability and user action

- `retryable: true` means the operation may succeed later after a fix or retry.
- `user_action_required: true` means Codex chat should explicitly ask for a user decision, approval, login, or local repair step.
- A retryable error can still require no user action if Mission Control can safely retry internally.

## Redaction rules

- `safe_details` is the user-facing diagnostic payload.
- Secret-like values are redacted before they are stored in `safe_details`.
- Raw `.env` values, API keys, access tokens, and full stack traces are not included in Codex chat output by default.
- `redaction_status` indicates whether the payload was changed during redaction.

## Initial code catalog

### Bootstrap and config

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-BOOT-RUNTIME-PATH-001` | runtime path unavailable | `bootstrap.start` |
| `MC-BOOT-DEPENDENCY-MISSING-001` | required local dependency missing | `bootstrap.dependency_probe` |
| `MC-BOOT-INSTALL-REPORT-FAILED-001` | install report build failed | `bootstrap.install_report` |
| `MC-CONFIG-HEADLESS-MISSING-001` | background-running config missing | `bootstrap.headless_config_write` |
| `MC-CONFIG-HEADLESS-INVALID-001` | background-running config invalid | `bootstrap.headless_config_write` |
| `MC-CONFIG-WRITE-FAILED-001` | config write failed | `bootstrap.headless_config_write` |

### Daemon and MCP

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-DAEMON-NOT-RUNNING-001` | daemon unavailable | `daemon.health_check` |
| `MC-DAEMON-PORT-IN-USE-001` | daemon port conflict | `daemon.port_bind` |
| `MC-DAEMON-HEALTH-FAILED-001` | daemon reachable but unhealthy | `daemon.health_check` |
| `MC-DAEMON-PID-STALE-001` | stale daemon metadata | `daemon.pid_check` |
| `MC-MCP-BRIDGE-MISSING-001` | MCP bridge missing | `mcp.start` |
| `MC-MCP-TOOL-NOT-FOUND-001` | tool missing | `mcp.tool_call` |
| `MC-MCP-RESOURCE-NOT-FOUND-001` | resource missing | `mcp.resource_read` |
| `MC-MCP-PROMPT-NOT-FOUND-001` | prompt missing | `mcp.prompt_render` |
| `MC-MCP-HANDSHAKE-FAILED-001` | handshake failed | `mcp.handshake` |
| `MC-PLUGIN-SKILL-MISSING-001` | skill file missing | `plugin.skill_discovery` |
| `MC-PLUGIN-PACKAGE-INVALID-001` | plugin package invalid | `plugin.package_validate` |

### Runners and auth

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-RUNNER-NONE-AVAILABLE-001` | no usable runner detected | `runner.select` |
| `MC-RUNNER-SELECTION-FAILED-001` | runner selection failed | `runner.select` |
| `MC-RUNNER-START-FAILED-001` | runner start failed | `runner.start` |
| `MC-RUNNER-TIMEOUT-001` | runner timed out | `runner.fail` |
| `MC-CODEX-CLI-MISSING-001` | Codex CLI missing | `codex_cli.detect` |
| `MC-CODEX-LOGIN-UNKNOWN-001` | Codex login unknown | `codex_cli.login_status` |
| `MC-CODEX-EXEC-FAILED-001` | Codex CLI execution failed | `codex_cli.exec` |
| `MC-OLLAMA-CLI-MISSING-001` | Ollama CLI missing | `ollama.detect` |
| `MC-OLLAMA-SERVER-OFFLINE-001` | Ollama server offline | `ollama.server_check` |
| `MC-OLLAMA-NO-MODELS-001` | Ollama has no usable models | `ollama.model_list` |
| `MC-CLAUDE-CLI-MISSING-001` | Claude CLI missing | `claude_cli.detect` |
| `MC-CLAUDE-AUTH-UNKNOWN-001` | Claude auth unknown | `claude_cli.auth_status` |
| `MC-API-KEY-MISSING-001` | API-backed runner not configured | `api_provider.auth_check` |
| `MC-API-BILLING-WARNING-001` | billed API provider selected | `api_provider.detect` |
| `MC-AUTH-BRIDGE-TOKEN-MISSING-001` | bridge token missing | `mcp.handshake` |
| `MC-AUTH-BRIDGE-TOKEN-INVALID-001` | bridge token invalid | `mcp.handshake` |

### Workspace and orchestration

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-WORKSPACE-PATH-MISSING-001` | workspace path missing | `workspace.attach` |
| `MC-WORKSPACE-PERMISSION-DENIED-001` | workspace inaccessible | `workspace.attach` |
| `MC-WORKSPACE-AMBIGUOUS-001` | workspace choice required | `workspace.detect_existing` |
| `MC-SCAN-READ-FAILED-001` | scan read failed | `workspace.read_only_scan` |
| `MC-SCAN-TOO-LARGE-001` | scan scope limited | `workspace.read_only_scan` |
| `MC-SCAN-SECRET-LIKE-FILE-001` | sensitive file detected during scan | `workspace.read_only_scan` |
| `MC-SCAN-IGNORED-DIR-SKIPPED-001` | ignored directory skipped | `workspace.read_only_scan` |
| `MC-ORCH-SESSION-NOT-FOUND-001` | orchestration missing | `orchestration.create` |
| `MC-ORCH-INVALID-STATE-001` | orchestration state invalid | `orchestration.fail` |
| `MC-ORCH-START-FAILED-001` | orchestration start failed | `orchestration.create` |
| `MC-ORCH-RESUME-FAILED-001` | orchestration resume failed | `orchestration.resume_after_decision` |
| `MC-MANAGER-PLAN-FAILED-001` | Manager could not produce a plan | `manager.generate_plan` |
| `MC-MANAGER-OUTPUT-INVALID-001` | Manager output invalid | `manager.consume_agent_report` |
| `MC-MANAGER-QUESTION-FAILED-001` | Manager question flow failed | `manager.create_pending_decision` |

### Agents, decisions, and bridge output

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-AGENT-START-FAILED-001` | worker agent start failed | `runner.start` |
| `MC-AGENT-REPORT-INVALID-001` | worker report invalid | `manager.consume_agent_report` |
| `MC-AGENT-STUCK-001` | worker appears stuck | `runner.stream_events` |
| `MC-SUBAGENT-BURST-DENIED-001` | subagent burst denied | `subagent_burst.approve` |
| `MC-SUBAGENT-RESULT-INVALID-001` | subagent result invalid | `subagent_burst.ingest_result` |
| `MC-SUBAGENT-TOO-MANY-001` | burst size exceeds limit | `subagent_burst.plan` |
| `MC-DECISION-NOT-FOUND-001` | decision missing | `decision.answer` |
| `MC-DECISION-INVALID-OPTION-001` | invalid approval answer | `decision.validate_option` |
| `MC-DECISION-EXPIRED-001` | decision expired | `decision.expire` |
| `MC-DECISION-HIGH-RISK-BLOCKED-001` | high-risk action blocked | `decision.apply` |
| `MC-BRIDGE-FORMAT-FAILED-001` | safe summary formatting failed | `bridge.format_status` |
| `MC-BRIDGE-REDACTION-FAILED-001` | bridge redaction failed | `bridge.redact_output` |
| `MC-BRIDGE-MISSING-FALLBACK-001` | fallback summary missing | `bridge.format_status` |

### Handoff, validation, security, and diagnostics

| Code | Meaning | Breakpoint |
| --- | --- | --- |
| `MC-HANDOFF-NOT-READY-001` | handoff not ready | `handoff.generate` |
| `MC-HANDOFF-EVIDENCE-MISSING-001` | handoff evidence incomplete | `handoff.validate_claims` |
| `MC-HANDOFF-RENDER-FAILED-001` | handoff rendering failed | `handoff.render_chat_summary` |
| `MC-VALIDATION-NOT-RUN-001` | validation not confirmed | `handoff.collect_evidence` |
| `MC-VALIDATION-FAILED-001` | validation failed | `handoff.collect_evidence` |
| `MC-VALIDATION-COMMAND-DENIED-001` | validation blocked by approval or policy | `decision.apply` |
| `MC-SECURITY-POLICY-BLOCKED-001` | action blocked by policy | `decision.apply` |
| `MC-SECURITY-SECRET-DETECTED-001` | secret-like output detected | `bridge.redact_output` |
| `MC-SECRET-REDACTION-FAILED-001` | secret redaction failed | `bridge.redact_output` |
| `MC-STORAGE-DB-UNAVAILABLE-001` | SQLite unavailable | `bootstrap.health_check` |
| `MC-STORAGE-RUNTIME-WRITE-FAILED-001` | runtime folder not writable | `diagnostics.write_report` |
| `MC-DIAGNOSTIC-RUN-FAILED-001` | diagnostic run failed | `diagnostics.run` |
| `MC-DIAGNOSTIC-REPORT-WRITE-FAILED-001` | diagnostic report write failed | `diagnostics.write_report` |
| `MC-NETWORK-LOCALHOST-UNREACHABLE-001` | localhost endpoint unreachable | `daemon.health_check` |
| `MC-NETWORK-PORT-CHECK-FAILED-001` | local port state unknown | `daemon.port_bind` |
| `MC-DOCS-LINK-CHECK-FAILED-001` | docs validation failed | `diagnostics.run` |
| `MC-UNKNOWN-UNEXPECTED-001` | fallback unexpected error | `diagnostics.run` |

## How to search an error code

1. Search the code in Codex chat output, health checks, or diagnostics.
2. Search the code in the repo:

```powershell
rg "MC-CODEX-CLI-MISSING-001" .
```

3. Review the registry entry in `apps/server/src/errors/registry.py`.
4. Review the related breakpoint in [DEBUG_BREAKPOINTS.md](DEBUG_BREAKPOINTS.md).
5. Check the relevant operational doc:
   - [Background Health](HEADLESS_HEALTH.md)
   - [Troubleshooting](TROUBLESHOOTING.md)
   - [Security](SECURITY.md)

## Related docs

- [Error Registry](ERROR_REGISTRY.md)
- [Debug Breakpoints](DEBUG_BREAKPOINTS.md)
- [Diagnostic Taxonomy](DIAGNOSTIC_TAXONOMY.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
