# Mission Control Error Registry

> Status: Reference

This file is generated from `apps/server/src/errors/registry.py`. Do not edit it by hand.

Total codes: `77`

| Code | Title | Family | Severity | Breakpoint | Retryable | User action required | HTTP |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [MC-BOOT-RUNTIME-PATH-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-boot-runtime-path-001) | Runtime path unavailable | `MC-BOOT` | `fatal` | `bootstrap.start` | Yes | Yes | `500` |
| [MC-BOOT-DEPENDENCY-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-boot-dependency-missing-001) | Required dependency missing | `MC-BOOT` | `error` | `bootstrap.dependency_probe` | Yes | Yes | `503` |
| [MC-BOOT-INSTALL-REPORT-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-boot-install-report-failed-001) | Install report failed | `MC-BOOT` | `error` | `bootstrap.install_report` | Yes | No | `500` |
| [MC-CONFIG-HEADLESS-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-config-headless-missing-001) | Background-running config missing | `MC-CONFIG` | `warning` | `bootstrap.headless_config_write` | Yes | Yes | `404` |
| [MC-CONFIG-HEADLESS-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-config-headless-invalid-001) | Background-running config invalid | `MC-CONFIG` | `error` | `bootstrap.headless_config_write` | Yes | Yes | `400` |
| [MC-CONFIG-WRITE-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-config-write-failed-001) | Config write failed | `MC-CONFIG` | `error` | `bootstrap.headless_config_write` | Yes | Yes | `500` |
| [MC-DAEMON-NOT-RUNNING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-daemon-not-running-001) | Daemon not running | `MC-DAEMON` | `error` | `daemon.health_check` | Yes | Yes | `503` |
| [MC-DAEMON-PORT-IN-USE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-daemon-port-in-use-001) | Daemon port already in use | `MC-DAEMON` | `error` | `daemon.port_bind` | Yes | Yes | `409` |
| [MC-DAEMON-HEALTH-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-daemon-health-failed-001) | Daemon health check failed | `MC-DAEMON` | `error` | `daemon.health_check` | Yes | Yes | `503` |
| [MC-DAEMON-PID-STALE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-daemon-pid-stale-001) | Daemon PID metadata stale | `MC-DAEMON` | `warning` | `daemon.pid_check` | Yes | No | `409` |
| [MC-MCP-BRIDGE-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-mcp-bridge-missing-001) | MCP bridge missing | `MC-MCP` | `error` | `mcp.start` | Yes | Yes | `503` |
| [MC-MCP-TOOL-NOT-FOUND-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-mcp-tool-not-found-001) | MCP tool not found | `MC-MCP` | `error` | `mcp.tool_call` | No | No | `404` |
| [MC-MCP-RESOURCE-NOT-FOUND-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-mcp-resource-not-found-001) | MCP resource not found | `MC-MCP` | `error` | `mcp.resource_read` | No | No | `404` |
| [MC-MCP-PROMPT-NOT-FOUND-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-mcp-prompt-not-found-001) | MCP prompt not found | `MC-MCP` | `error` | `mcp.prompt_render` | No | No | `404` |
| [MC-MCP-HANDSHAKE-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-mcp-handshake-failed-001) | MCP handshake failed | `MC-MCP` | `error` | `mcp.handshake` | Yes | Yes | `503` |
| [MC-PLUGIN-SKILL-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-plugin-skill-missing-001) | Plugin skill missing | `MC-PLUGIN` | `error` | `plugin.skill_discovery` | No | Yes | `500` |
| [MC-PLUGIN-PACKAGE-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-plugin-package-invalid-001) | Plugin package invalid | `MC-PLUGIN` | `error` | `plugin.package_validate` | No | Yes | `500` |
| [MC-RUNNER-NONE-AVAILABLE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-runner-none-available-001) | No runners available | `MC-RUNNER` | `warning` | `runner.select` | Yes | Yes | `503` |
| [MC-RUNNER-SELECTION-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-runner-selection-failed-001) | Runner selection failed | `MC-RUNNER` | `error` | `runner.select` | Yes | No | `500` |
| [MC-RUNNER-START-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-runner-start-failed-001) | Runner start failed | `MC-RUNNER` | `error` | `runner.start` | Yes | No | `500` |
| [MC-RUNNER-TIMEOUT-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-runner-timeout-001) | Runner timed out | `MC-RUNNER` | `error` | `runner.fail` | Yes | No | `504` |
| [MC-CODEX-CLI-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-codex-cli-missing-001) | Codex CLI missing | `MC-CODEX` | `warning` | `codex_cli.detect` | Yes | Yes | `503` |
| [MC-CODEX-LOGIN-UNKNOWN-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-codex-login-unknown-001) | Codex login unknown | `MC-CODEX` | `warning` | `codex_cli.login_status` | Yes | Yes | `503` |
| [MC-CODEX-EXEC-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-codex-exec-failed-001) | Codex CLI execution failed | `MC-CODEX` | `error` | `codex_cli.exec` | Yes | No | `500` |
| [MC-OLLAMA-CLI-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-ollama-cli-missing-001) | Ollama CLI missing | `MC-OLLAMA` | `warning` | `ollama.detect` | Yes | Yes | `503` |
| [MC-OLLAMA-SERVER-OFFLINE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-ollama-server-offline-001) | Ollama server offline | `MC-OLLAMA` | `warning` | `ollama.server_check` | Yes | Yes | `503` |
| [MC-OLLAMA-NO-MODELS-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-ollama-no-models-001) | No Ollama models available | `MC-OLLAMA` | `warning` | `ollama.model_list` | Yes | Yes | `503` |
| [MC-CLAUDE-CLI-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-claude-cli-missing-001) | Claude CLI missing | `MC-CLAUDE` | `warning` | `claude_cli.detect` | Yes | Yes | `503` |
| [MC-CLAUDE-AUTH-UNKNOWN-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-claude-auth-unknown-001) | Claude auth unknown | `MC-CLAUDE` | `warning` | `claude_cli.auth_status` | Yes | Yes | `503` |
| [MC-API-KEY-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-api-key-missing-001) | API key missing | `MC-API` | `warning` | `api_provider.auth_check` | Yes | Yes | `503` |
| [MC-API-BILLING-WARNING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-api-billing-warning-001) | API billing warning | `MC-API` | `warning` | `api_provider.detect` | Yes | Yes | `409` |
| [MC-AUTH-BRIDGE-TOKEN-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-auth-bridge-token-missing-001) | Bridge token missing | `MC-AUTH` | `error` | `mcp.handshake` | Yes | Yes | `503` |
| [MC-AUTH-BRIDGE-TOKEN-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-auth-bridge-token-invalid-001) | Bridge token invalid | `MC-AUTH` | `error` | `mcp.handshake` | Yes | Yes | `401` |
| [MC-SECRET-REDACTION-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-secret-redaction-failed-001) | Secret redaction failed | `MC-SECRET` | `error` | `bridge.redact_output` | No | No | `500` |
| [MC-WORKSPACE-PATH-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-workspace-path-missing-001) | Workspace path missing | `MC-WORKSPACE` | `error` | `workspace.attach` | Yes | Yes | `400` |
| [MC-WORKSPACE-PERMISSION-DENIED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-workspace-permission-denied-001) | Workspace permission denied | `MC-WORKSPACE` | `error` | `workspace.attach` | Yes | Yes | `403` |
| [MC-WORKSPACE-AMBIGUOUS-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-workspace-ambiguous-001) | Workspace selection ambiguous | `MC-WORKSPACE` | `warning` | `workspace.detect_existing` | Yes | Yes | `409` |
| [MC-SCAN-READ-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-scan-read-failed-001) | Scan read failed | `MC-SCAN` | `error` | `workspace.read_only_scan` | Yes | No | `500` |
| [MC-SCAN-TOO-LARGE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-scan-too-large-001) | Scan scope too large | `MC-SCAN` | `warning` | `workspace.read_only_scan` | Yes | Yes | `413` |
| [MC-SCAN-SECRET-LIKE-FILE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-scan-secret-like-file-001) | Secret-like file detected | `MC-SCAN` | `warning` | `workspace.read_only_scan` | Yes | Yes | `409` |
| [MC-SCAN-IGNORED-DIR-SKIPPED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-scan-ignored-dir-skipped-001) | Ignored directory skipped | `MC-SCAN` | `info` | `workspace.read_only_scan` | Yes | No | `200` |
| [MC-ORCH-SESSION-NOT-FOUND-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-orch-session-not-found-001) | Orchestration session not found | `MC-ORCH` | `error` | `orchestration.create` | No | No | `404` |
| [MC-ORCH-INVALID-STATE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-orch-invalid-state-001) | Invalid orchestration state | `MC-ORCH` | `error` | `orchestration.fail` | No | No | `409` |
| [MC-ORCH-START-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-orch-start-failed-001) | Orchestration start failed | `MC-ORCH` | `error` | `orchestration.create` | Yes | No | `500` |
| [MC-ORCH-RESUME-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-orch-resume-failed-001) | Orchestration resume failed | `MC-ORCH` | `error` | `orchestration.resume_after_decision` | Yes | No | `409` |
| [MC-MANAGER-PLAN-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-manager-plan-failed-001) | Manager plan failed | `MC-MANAGER` | `error` | `manager.generate_plan` | Yes | No | `500` |
| [MC-MANAGER-OUTPUT-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-manager-output-invalid-001) | Manager output invalid | `MC-MANAGER` | `error` | `manager.consume_agent_report` | Yes | No | `500` |
| [MC-MANAGER-QUESTION-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-manager-question-failed-001) | Manager question failed | `MC-MANAGER` | `error` | `manager.create_pending_decision` | Yes | No | `500` |
| [MC-AGENT-START-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-agent-start-failed-001) | Agent start failed | `MC-AGENT` | `error` | `runner.start` | Yes | No | `500` |
| [MC-AGENT-REPORT-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-agent-report-invalid-001) | Agent report invalid | `MC-AGENT` | `error` | `manager.consume_agent_report` | Yes | No | `500` |
| [MC-AGENT-STUCK-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-agent-stuck-001) | Agent appears stuck | `MC-AGENT` | `warning` | `runner.stream_events` | Yes | No | `504` |
| [MC-SUBAGENT-BURST-DENIED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-subagent-burst-denied-001) | Subagent burst denied | `MC-SUBAGENT` | `warning` | `subagent_burst.approve` | No | Yes | `403` |
| [MC-SUBAGENT-RESULT-INVALID-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-subagent-result-invalid-001) | Subagent result invalid | `MC-SUBAGENT` | `error` | `subagent_burst.ingest_result` | Yes | No | `500` |
| [MC-SUBAGENT-TOO-MANY-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-subagent-too-many-001) | Too many subagents requested | `MC-SUBAGENT` | `warning` | `subagent_burst.plan` | Yes | Yes | `409` |
| [MC-DECISION-NOT-FOUND-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-decision-not-found-001) | Pending decision not found | `MC-DECISION` | `error` | `decision.answer` | No | No | `404` |
| [MC-DECISION-INVALID-OPTION-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-decision-invalid-option-001) | Invalid pending decision option | `MC-DECISION` | `error` | `decision.validate_option` | No | Yes | `400` |
| [MC-DECISION-EXPIRED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-decision-expired-001) | Pending decision expired | `MC-DECISION` | `error` | `decision.expire` | No | No | `409` |
| [MC-DECISION-HIGH-RISK-BLOCKED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-decision-high-risk-blocked-001) | High-risk decision blocked | `MC-DECISION` | `warning` | `decision.apply` | Yes | Yes | `403` |
| [MC-BRIDGE-FORMAT-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-bridge-format-failed-001) | Bridge format failed | `MC-BRIDGE` | `error` | `bridge.format_status` | Yes | No | `500` |
| [MC-BRIDGE-REDACTION-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-bridge-redaction-failed-001) | Bridge redaction failed | `MC-BRIDGE` | `error` | `bridge.redact_output` | No | No | `500` |
| [MC-BRIDGE-MISSING-FALLBACK-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-bridge-missing-fallback-001) | Bridge fallback missing | `MC-BRIDGE` | `error` | `bridge.format_status` | Yes | No | `500` |
| [MC-HANDOFF-NOT-READY-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-handoff-not-ready-001) | Handoff not ready | `MC-HANDOFF` | `warning` | `handoff.generate` | Yes | No | `409` |
| [MC-HANDOFF-EVIDENCE-MISSING-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-handoff-evidence-missing-001) | Handoff evidence missing | `MC-HANDOFF` | `warning` | `handoff.validate_claims` | Yes | Yes | `409` |
| [MC-HANDOFF-RENDER-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-handoff-render-failed-001) | Handoff render failed | `MC-HANDOFF` | `error` | `handoff.render_chat_summary` | Yes | No | `500` |
| [MC-VALIDATION-NOT-RUN-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-validation-not-run-001) | Validation not run | `MC-VALIDATION` | `warning` | `handoff.collect_evidence` | Yes | Yes | `409` |
| [MC-VALIDATION-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-validation-failed-001) | Validation failed | `MC-VALIDATION` | `error` | `handoff.collect_evidence` | Yes | No | `422` |
| [MC-VALIDATION-COMMAND-DENIED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-validation-command-denied-001) | Validation command denied | `MC-VALIDATION` | `warning` | `decision.apply` | Yes | Yes | `403` |
| [MC-SECURITY-POLICY-BLOCKED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-security-policy-blocked-001) | Security policy blocked action | `MC-SECURITY` | `warning` | `decision.apply` | Yes | Yes | `403` |
| [MC-SECURITY-SECRET-DETECTED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-security-secret-detected-001) | Secret-like data detected | `MC-SECURITY` | `warning` | `bridge.redact_output` | Yes | No | `409` |
| [MC-STORAGE-DB-UNAVAILABLE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-storage-db-unavailable-001) | Database unavailable | `MC-STORAGE` | `error` | `bootstrap.health_check` | Yes | Yes | `503` |
| [MC-STORAGE-RUNTIME-WRITE-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-storage-runtime-write-failed-001) | Runtime write failed | `MC-STORAGE` | `error` | `diagnostics.write_report` | Yes | Yes | `500` |
| [MC-DIAGNOSTIC-RUN-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-diagnostic-run-failed-001) | Diagnostic run failed | `MC-DIAGNOSTIC` | `error` | `diagnostics.run` | Yes | No | `500` |
| [MC-DIAGNOSTIC-REPORT-WRITE-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-diagnostic-report-write-failed-001) | Diagnostic report write failed | `MC-DIAGNOSTIC` | `error` | `diagnostics.write_report` | Yes | Yes | `500` |
| [MC-NETWORK-LOCALHOST-UNREACHABLE-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-network-localhost-unreachable-001) | Localhost unreachable | `MC-NETWORK` | `error` | `daemon.health_check` | Yes | Yes | `503` |
| [MC-NETWORK-PORT-CHECK-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-network-port-check-failed-001) | Port check failed | `MC-NETWORK` | `warning` | `daemon.port_bind` | Yes | No | `500` |
| [MC-DOCS-LINK-CHECK-FAILED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-docs-link-check-failed-001) | Documentation link check failed | `MC-DOCS` | `warning` | `diagnostics.run` | Yes | No | `500` |
| [MC-UNKNOWN-UNEXPECTED-001](https://github.com/MN755/Codex-Mission_Control/wiki/Errors-and-Debug-Codes#mc-unknown-unexpected-001) | Unexpected Mission Control error | `MC-UNKNOWN` | `error` | `diagnostics.run` | No | No | `500` |

## Notes

- The code is the stable identifier. User-facing wording may change.
- Search the code in logs, tests, diagnostics, or the wiki first.
- See [Mission Control Errors](ERRORS.md) for the error shape and family overview.
