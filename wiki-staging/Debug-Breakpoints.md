# Debug Breakpoints

> Status: Current

Mission Control names major workflow stages as breakpoints so errors can say where they happened, not just what failed.

## Core breakpoint groups

### Bootstrap and daemon

- `bootstrap.start`
- `bootstrap.environment_probe`
- `bootstrap.dependency_probe`
- `bootstrap.runner_probe`
- `bootstrap.runner_autowire`
- `bootstrap.headless_config_write`
- `bootstrap.install_report`
- `bootstrap.health_check`
- `daemon.start`
- `daemon.health_check`
- `daemon.stop`
- `daemon.pid_check`
- `daemon.port_bind`

### MCP and plugin

- `mcp.start`
- `mcp.handshake`
- `mcp.tool_call`
- `mcp.resource_read`
- `mcp.prompt_render`
- `plugin.skill_discovery`
- `plugin.package_validate`

### Workspace and orchestration

- `workspace.attach`
- `workspace.detect_existing`
- `workspace.import_existing_codebase`
- `workspace.read_only_scan`
- `workspace.write_permission_request`
- `orchestration.create`
- `orchestration.plan`
- `orchestration.waiting_for_user`
- `orchestration.resume_after_decision`
- `orchestration.complete`
- `orchestration.fail`

### Manager, runner, and subagent

- `manager.analyze_request`
- `manager.generate_plan`
- `manager.create_swarm_plan`
- `manager.create_pending_decision`
- `manager.consume_agent_report`
- `manager.generate_handoff`
- `runner.registry_load`
- `runner.select`
- `runner.start`
- `runner.stream_events`
- `runner.complete`
- `runner.fail`
- `subagent_burst.plan`
- `subagent_burst.approve`
- `subagent_burst.spawn_prompt`
- `subagent_burst.ingest_result`
- `subagent_burst.summarize`

### Runner-specific

- `codex_cli.detect`
- `codex_cli.login_status`
- `codex_cli.exec`
- `ollama.detect`
- `ollama.server_check`
- `ollama.model_list`
- `claude_cli.detect`
- `claude_cli.auth_status`
- `api_provider.detect`
- `api_provider.auth_check`

### Decisions, bridge, handoff, and diagnostics

- `decision.create`
- `decision.render`
- `decision.answer`
- `decision.validate_option`
- `decision.apply`
- `decision.expire`
- `bridge.format_status`
- `bridge.format_approval`
- `bridge.format_question`
- `bridge.format_handoff`
- `bridge.redact_output`
- `handoff.collect_evidence`
- `handoff.generate`
- `handoff.validate_claims`
- `handoff.render_chat_summary`
- `diagnostics.run`
- `diagnostics.collect_logs`
- `diagnostics.redact`
- `diagnostics.write_report`

## Common breakpoint and code pairs

| Breakpoint | Common codes |
| --- | --- |
| `codex_cli.detect` | `MC-CODEX-CLI-MISSING-001` |
| `mcp.handshake` | `MC-MCP-HANDSHAKE-FAILED-001`, `MC-AUTH-BRIDGE-TOKEN-MISSING-001` |
| `workspace.attach` | `MC-WORKSPACE-PATH-MISSING-001`, `MC-WORKSPACE-PERMISSION-DENIED-001` |
| `decision.validate_option` | `MC-DECISION-INVALID-OPTION-001` |
| `bridge.redact_output` | `MC-BRIDGE-REDACTION-FAILED-001`, `MC-SECURITY-SECRET-DETECTED-001` |
| `handoff.validate_claims` | `MC-HANDOFF-EVIDENCE-MISSING-001` |
| `diagnostics.write_report` | `MC-DIAGNOSTIC-REPORT-WRITE-FAILED-001`, `MC-STORAGE-RUNTIME-WRITE-FAILED-001` |

## Why breakpoints matter

- They make logs and API output line up.
- They tell Codex chat what stage failed.
- They make health checks and diagnostics searchable.
- They reduce vague “something broke” summaries, which is a low bar but still worth clearing.

## Related pages

- [Errors and Debug Codes](Errors-and-Debug-Codes)
- [Troubleshooting Error Codes](Troubleshooting-Error-Codes)
- [Mission Control Daemon](Mission-Control-Daemon)
