# Mission Control Debug Breakpoints

> Status: Current

Mission Control names major workflow stages as breakpoints so logs, diagnostics, tests, and Codex chat summaries can point to the same place in the system when something fails.

## How to read a breakpoint

A breakpoint identifies where the failure happened, not just what failed.

- `bootstrap.*`: install and startup
- `daemon.*`: daemon lifecycle
- `mcp.*`: MCP bridge operations
- `workspace.*`: workspace attach and scan
- `orchestration.*`: session lifecycle
- `manager.*`: Manager AI planning and control
- `runner.*`: runner registry and execution
- `decision.*`: approvals and pending questions
- `bridge.*`: Codex-chat-safe formatting
- `handoff.*`: evidence and handoff generation
- `diagnostics.*`: health and report generation
- `subagent_burst.*`: controlled subagent bursts

## Bootstrap and install

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `bootstrap.start` | bootstrap entrypoint | `MC-BOOT-RUNTIME-PATH-001` | startup checks |
| `bootstrap.environment_probe` | local environment probe | `MC-BOOT-DEPENDENCY-MISSING-001` | install report |
| `bootstrap.dependency_probe` | required executable checks | `MC-BOOT-DEPENDENCY-MISSING-001` | startup checks |
| `bootstrap.runner_probe` | runner capability detection | runner-specific warnings | install report |
| `bootstrap.runner_autowire` | default runner selection | `MC-RUNNER-SELECTION-FAILED-001` | install report |
| `bootstrap.headless_config_write` | background-running config write | `MC-CONFIG-HEADLESS-MISSING-001`, `MC-CONFIG-WRITE-FAILED-001` | install report |
| `bootstrap.install_report` | install summary assembly | `MC-BOOT-INSTALL-REPORT-FAILED-001` | install report |
| `bootstrap.health_check` | startup health summary | `MC-STORAGE-DB-UNAVAILABLE-001` | health checks |

## Daemon and MCP

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `daemon.start` | daemon startup | `MC-DAEMON-NOT-RUNNING-001` | daemon logs |
| `daemon.health_check` | daemon reachability and local health | `MC-DAEMON-HEALTH-FAILED-001`, `MC-NETWORK-LOCALHOST-UNREACHABLE-001` | plugin health |
| `daemon.stop` | daemon shutdown | lifecycle failures | daemon logs |
| `daemon.pid_check` | PID metadata validation | `MC-DAEMON-PID-STALE-001` | diagnostics |
| `daemon.port_bind` | localhost port bind | `MC-DAEMON-PORT-IN-USE-001`, `MC-NETWORK-PORT-CHECK-FAILED-001` | startup and logs |
| `mcp.start` | MCP bridge startup | `MC-MCP-BRIDGE-MISSING-001` | plugin health |
| `mcp.handshake` | bridge handshake and token check | `MC-MCP-HANDSHAKE-FAILED-001`, `MC-AUTH-BRIDGE-TOKEN-MISSING-001` | tool calls |
| `mcp.tool_call` | MCP tool execution | `MC-MCP-TOOL-NOT-FOUND-001` | tool responses |
| `mcp.resource_read` | MCP resource read | `MC-MCP-RESOURCE-NOT-FOUND-001` | resource reads |
| `mcp.prompt_render` | MCP prompt render | `MC-MCP-PROMPT-NOT-FOUND-001` | prompt workflows |

## Workspace and orchestration

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `workspace.attach` | workspace attach | `MC-WORKSPACE-PATH-MISSING-001`, `MC-WORKSPACE-PERMISSION-DENIED-001` | API and chat |
| `workspace.detect_existing` | existing repo detection | `MC-WORKSPACE-AMBIGUOUS-001` | attach workflow |
| `workspace.import_existing_codebase` | existing codebase import | scan and attach failures | import workflow |
| `workspace.read_only_scan` | read-only scan | `MC-SCAN-READ-FAILED-001`, `MC-SCAN-TOO-LARGE-001`, `MC-SCAN-SECRET-LIKE-FILE-001` | diagnostics and import |
| `workspace.write_permission_request` | write approval generation | decision flow failures | approvals |
| `orchestration.create` | orchestration creation | `MC-ORCH-START-FAILED-001`, `MC-ORCH-SESSION-NOT-FOUND-001` | start-task response |
| `orchestration.plan` | orchestration planning | `MC-MANAGER-PLAN-FAILED-001` | status and handoff |
| `orchestration.waiting_for_user` | waiting for approval or answer | `MC-DECISION-HIGH-RISK-BLOCKED-001` | status |
| `orchestration.resume_after_decision` | resume after answer | `MC-ORCH-RESUME-FAILED-001` | approval flow |
| `orchestration.complete` | normal completion | handoff warnings | handoff |
| `orchestration.fail` | terminal failure path | `MC-ORCH-INVALID-STATE-001` | status and diagnostics |

## Manager, runners, and subagents

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `manager.analyze_request` | request analysis | invalid context or unsupported task | planning |
| `manager.generate_plan` | plan generation | `MC-MANAGER-PLAN-FAILED-001` | plan output |
| `manager.create_swarm_plan` | swarm planning | runner or capacity limits | swarm plan |
| `manager.create_pending_decision` | pending decision creation | `MC-MANAGER-QUESTION-FAILED-001` | approval flow |
| `manager.consume_agent_report` | ingest worker output | `MC-MANAGER-OUTPUT-INVALID-001`, `MC-AGENT-REPORT-INVALID-001` | orchestration |
| `manager.generate_handoff` | final handoff generation | `MC-HANDOFF-NOT-READY-001` | handoff |
| `runner.registry_load` | load runner inventory | `MC-RUNNER-SELECTION-FAILED-001` | health and diagnostics |
| `runner.select` | choose a runner | `MC-RUNNER-NONE-AVAILABLE-001`, `MC-RUNNER-SELECTION-FAILED-001` | health and start-task |
| `runner.start` | start the chosen runner | `MC-RUNNER-START-FAILED-001`, `MC-AGENT-START-FAILED-001` | orchestration |
| `runner.stream_events` | stream progress | `MC-AGENT-STUCK-001` | status and event digest |
| `runner.complete` | runner completion | evidence gaps may follow | handoff |
| `runner.fail` | runner failure | `MC-RUNNER-TIMEOUT-001` | diagnostics |
| `subagent_burst.plan` | burst planning | `MC-SUBAGENT-TOO-MANY-001` | subagent policy |
| `subagent_burst.approve` | burst approval gate | `MC-SUBAGENT-BURST-DENIED-001` | approvals |
| `subagent_burst.spawn_prompt` | spawn prompt creation | bridge or prompt failures | subagent workflow |
| `subagent_burst.ingest_result` | result ingestion | `MC-SUBAGENT-RESULT-INVALID-001` | orchestration |
| `subagent_burst.summarize` | burst summary generation | summary or redaction failures | bridge output |

## Runner-specific breakpoints

| Breakpoint | Meaning | Common errors |
| --- | --- | --- |
| `codex_cli.detect` | detect Codex CLI | `MC-CODEX-CLI-MISSING-001` |
| `codex_cli.login_status` | verify Codex login | `MC-CODEX-LOGIN-UNKNOWN-001` |
| `codex_cli.exec` | execute Codex CLI | `MC-CODEX-EXEC-FAILED-001` |
| `ollama.detect` | detect Ollama CLI | `MC-OLLAMA-CLI-MISSING-001` |
| `ollama.server_check` | check local Ollama server | `MC-OLLAMA-SERVER-OFFLINE-001` |
| `ollama.model_list` | list local models | `MC-OLLAMA-NO-MODELS-001` |
| `claude_cli.detect` | detect Claude CLI | `MC-CLAUDE-CLI-MISSING-001` |
| `claude_cli.auth_status` | check Claude auth | `MC-CLAUDE-AUTH-UNKNOWN-001` |
| `api_provider.detect` | detect API-backed runner | `MC-API-BILLING-WARNING-001` |
| `api_provider.auth_check` | check API credential presence | `MC-API-KEY-MISSING-001` |

## Decisions, bridge, and handoffs

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `decision.create` | create pending decision | question creation failures | manager output |
| `decision.render` | render approval or question | bridge formatting issues | chat output |
| `decision.answer` | process user answer | `MC-DECISION-NOT-FOUND-001` | API and chat |
| `decision.validate_option` | validate selected option | `MC-DECISION-INVALID-OPTION-001` | approvals |
| `decision.apply` | apply chosen option | `MC-DECISION-HIGH-RISK-BLOCKED-001`, `MC-VALIDATION-COMMAND-DENIED-001`, `MC-SECURITY-POLICY-BLOCKED-001` | orchestration |
| `decision.expire` | expire stale decision | `MC-DECISION-EXPIRED-001` | approvals |
| `bridge.format_status` | status summary render | `MC-BRIDGE-FORMAT-FAILED-001`, `MC-BRIDGE-MISSING-FALLBACK-001` | Codex chat |
| `bridge.format_approval` | approval card render | formatting failures | Codex chat |
| `bridge.format_question` | manager question render | formatting failures | Codex chat |
| `bridge.format_handoff` | handoff summary render | `MC-HANDOFF-RENDER-FAILED-001` | Codex chat |
| `bridge.redact_output` | output redaction | `MC-BRIDGE-REDACTION-FAILED-001`, `MC-SECURITY-SECRET-DETECTED-001`, `MC-SECRET-REDACTION-FAILED-001` | bridge and diagnostics |
| `handoff.collect_evidence` | collect validation evidence | `MC-VALIDATION-NOT-RUN-001`, `MC-VALIDATION-FAILED-001` | handoff |
| `handoff.generate` | assemble handoff | `MC-HANDOFF-NOT-READY-001` | handoff |
| `handoff.validate_claims` | verify claims against evidence | `MC-HANDOFF-EVIDENCE-MISSING-001` | handoff |
| `handoff.render_chat_summary` | render safe handoff summary | `MC-HANDOFF-RENDER-FAILED-001` | Codex chat |

## Diagnostics

| Breakpoint | Meaning | Common errors | Related surface |
| --- | --- | --- | --- |
| `diagnostics.run` | diagnostic entrypoint | `MC-DIAGNOSTIC-RUN-FAILED-001`, `MC-DOCS-LINK-CHECK-FAILED-001`, `MC-UNKNOWN-UNEXPECTED-001` | diagnostics |
| `diagnostics.collect_logs` | collect log material | storage or access failures | diagnostics |
| `diagnostics.redact` | redact report details | redaction failures | diagnostics |
| `diagnostics.write_report` | write report to runtime | `MC-DIAGNOSTIC-REPORT-WRITE-FAILED-001`, `MC-STORAGE-RUNTIME-WRITE-FAILED-001` | diagnostics |

## Related docs

- [Mission Control Errors](ERRORS.md)
- [Diagnostic Taxonomy](DIAGNOSTIC_TAXONOMY.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Troubleshooting](TROUBLESHOOTING.md)
