# Troubleshooting

> Status: Current

This page covers the most common structured Mission Control failures so a user or Codex chat agent can tell what failed, where it failed, and what to do next without reading raw logs.

## Device-aware first move

Before guessing, generate a local support bundle and use the platform-appropriate health command:

Windows 10 / Windows 11:

```powershell
.\scripts\mission-control-headless-health.ps1 -Json
.\scripts\mission-control-support-bundle.ps1
```

macOS / Linux:

```bash
./scripts/mission-control-headless-health.sh --json
./scripts/mission-control-support-bundle.sh
```

The support bundle is redacted and gives Codex or Claude chat a safer starting point than random raw logs.

Startup status is now recomputed fresh on each status check. If the app still shows a bad state after a real fix, suspect a live runtime problem instead of stale bootstrap cache.

## How to read an error

When Mission Control reports an error, focus on:

1. the stable error code
2. the breakpoint
3. whether user action is required
4. the recommended fix

Example:

```text
MC-CODEX-CLI-MISSING-001
Where: codex_cli.detect
User action required: Yes
Recommended fix: Install Codex CLI or expose it on PATH, or continue with dry-run mode.
```

## Common user-facing errors

### `MC-DAEMON-NOT-RUNNING-001`

Symptoms:

- plugin health shows the daemon as unavailable
- attach or start-task flows fail immediately

Likely cause:

- the local daemon is not running
- the daemon crashed before the health endpoint became available

Checks:

```powershell
Invoke-WebRequest http://127.0.0.1:8010/api/health
.\scripts\mission-control-headless-health.ps1
```

macOS / Linux equivalent:

```bash
curl -fsS http://127.0.0.1:8010/api/health
./scripts/mission-control-headless-health.sh --json
```

Fix:

- start the daemon locally
- verify the local port and runtime folder are usable

### `MC-MCP-BRIDGE-MISSING-001`

Symptoms:

- Codex cannot find Mission Control tools, resources, or prompts
- health check reports bridge setup failure

Likely cause:

- MCP bridge not configured
- plugin package not loaded correctly

Checks:

- confirm the Mission Control MCP entry exists in Codex configuration
- confirm plugin files are present

Fix:

- reload the Mission Control MCP bridge configuration
- reinstall or repair the plugin package if required

### `MC-CODEX-CLI-MISSING-001`

Symptoms:

- runner probe says Codex CLI is unavailable
- health is degraded even though the daemon is running

Likely cause:

- `codex` is not installed or not on `PATH`

Checks:

```powershell
codex --version
```

Fix:

- install Codex CLI
- expose it on `PATH`
- continue with dry-run mode if you only need a safe fallback

### `MC-CODEX-LOGIN-UNKNOWN-001`

Symptoms:

- Codex CLI exists, but Mission Control cannot confirm login state

Likely cause:

- Codex CLI auth session missing or unreadable

Checks:

```powershell
codex login status
```

Fix:

- sign in again outside Mission Control
- rerun the health check

### `MC-OLLAMA-SERVER-OFFLINE-001`

Symptoms:

- Ollama runner is detected, but local models are unavailable

Likely cause:

- Ollama service is not running

Checks:

```powershell
ollama list
```

Fix:

- start Ollama locally
- verify that at least one local model exists
- keep the built-in adapter recipe intact unless you intentionally override it

### `MC-API-KEY-MISSING-001`

Symptoms:

- selected API-backed provider stays degraded
- startup or runner status says the runtime is not ready

Likely cause:

- the external API key is missing even though the built-in adapter recipe exists

Checks:

- verify `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `XAI_API_KEY` in the host environment
- rerun the support bundle to confirm the provider state

Fix:

- set the provider key outside chat in the host environment
- rerun the startup or plugin health check

### `MC-WORKSPACE-PATH-MISSING-001`

Symptoms:

- attach workspace fails
- start-task fails before orchestration creation

Likely cause:

- no workspace path or project reference was supplied

Fix:

- provide the workspace path explicitly
- retry the attach or start request

### `MC-DECISION-INVALID-OPTION-001`

Symptoms:

- answering a pending decision returns a structured error

Likely cause:

- the chosen option is not allowed for that decision

Fix:

- refresh the pending decision list
- choose one of the returned options exactly

### `MC-HANDOFF-EVIDENCE-MISSING-001`

Symptoms:

- handoff exists but warns that evidence is incomplete

Likely cause:

- validation steps were not run
- validation output was not recorded

Fix:

- run the missing build, test, or manual verification step
- regenerate the handoff after evidence exists

### `MC-STORAGE-DB-UNAVAILABLE-001`

Symptoms:

- startup checks fail
- health is blocked or broken
- diagnostics mention local SQLite access failure

Likely cause:

- runtime database file missing, locked, or inaccessible

Checks:

- confirm the runtime directory exists
- confirm the process can write to it

Fix:

- repair local filesystem permissions
- restart the daemon

### `MC-UNKNOWN-UNEXPECTED-001`

Symptoms:

- a route or workflow fails without a more specific code

Likely cause:

- unexpected internal exception

Fix:

- capture the correlation ID
- inspect internal logs and diagnostics
- retry if the failure appears transient

## Daemon not starting

Check:

- the local health endpoint
- whether the runtime directory is writable
- whether the expected local port is already in use

Try:

```powershell
.\scripts\mission-control-headless-health.ps1
Invoke-WebRequest http://127.0.0.1:8010/api/health
```

macOS / Linux equivalent:

```bash
./scripts/mission-control-headless-health.sh --json
curl -fsS http://127.0.0.1:8010/api/health
```

Related codes:

- `MC-DAEMON-NOT-RUNNING-001`
- `MC-DAEMON-PORT-IN-USE-001`
- `MC-NETWORK-LOCALHOST-UNREACHABLE-001`

## MCP bridge not usable

Check:

- plugin assets are present
- expected tools, prompts, and resources are registered
- daemon token or local bridge configuration exists where required

Try:

```powershell
.\scripts\start-mission-control-mcp.ps1
```

Related codes:

- `MC-MCP-BRIDGE-MISSING-001`
- `MC-MCP-HANDSHAKE-FAILED-001`
- `MC-PLUGIN-PACKAGE-INVALID-001`

## Runner unavailable

Check:

- `codex_cli` is installed and logged in
- Ollama is running locally
- Claude CLI is available and authenticated
- API-backed providers are configured outside chat

Related codes:

- `MC-RUNNER-NONE-AVAILABLE-001`
- `MC-CODEX-CLI-MISSING-001`
- `MC-OLLAMA-SERVER-OFFLINE-001`
- `MC-CLAUDE-CLI-MISSING-001`
- `MC-API-KEY-MISSING-001`

## Pending decision appears stuck

Check whether the task is waiting on a user response, a blocked validation step, or a missing runner. Use the status summary and event digest before retrying commands.

Related codes:

- `MC-DECISION-HIGH-RISK-BLOCKED-001`
- `MC-DECISION-EXPIRED-001`
- `MC-VALIDATION-COMMAND-DENIED-001`

## Handoff missing evidence

If the handoff says validation was not run or evidence is missing, treat that as a real gap. Review the requested validation steps before calling the task complete.

Related codes:

- `MC-HANDOFF-EVIDENCE-MISSING-001`
- `MC-VALIDATION-NOT-RUN-001`
- `MC-VALIDATION-FAILED-001`

## Related docs

- [Mission Control Errors](ERRORS.md)
- [Debug Breakpoints](DEBUG_BREAKPOINTS.md)
- [Diagnostic Taxonomy](DIAGNOSTIC_TAXONOMY.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Plugin Health Doctor](PLUGIN_HEALTH_DOCTOR.md)
- [Runners](RUNNERS.md)
- [Handoffs](HANDOFFS.md)
