# Mission Control Daemon

This page explains the daemon as the long-running local orchestration surface behind the Codex chat bridge.

> Status: Current

## Responsibilities

The daemon owns:

- orchestration sessions
- Manager AI execution
- worker runner registry
- pending decisions
- bridge messages
- handoffs
- diagnostics
- runtime folders
- event logs

## Lifecycle

Typical lifecycle:

1. Start on localhost.
2. Accept bridge requests for attach, start, status, and handoff.
3. Persist orchestration state.
4. Coordinate Manager and worker execution.
5. Shut down safely without dropping state.

Copyable commands:

```powershell
.\scripts\start-mission-control-daemon.ps1
```

```bash
./scripts/start-mission-control-daemon.sh
```

## Health and status

Health checks should confirm:

- daemon reachable
- runtime folders writable
- SQLite usable
- localhost binding preserved
- runner registry readable
- plugin health summary available

## Safe shutdown

Safe shutdown should preserve orchestration state, partial handoffs, pending decisions, and diagnostics context.

It should not require the dashboard to be open.

## Related pages

Continue with [Logs and Runtime Folders](Logs-and-Runtime-Folders), [Diagnostics and Health Checks](Diagnostics-and-Health-Checks), [MCP Bridge Endpoints](MCP-Bridge-Endpoints), and [Runner Configuration](Runner-Configuration).
