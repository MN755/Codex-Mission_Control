# Debugging Common Issues

This page collects the most common failure patterns for headless Mission Control usage and the fastest checks to run from Codex chat or a local shell.

> Status: Current

## Daemon will not start

Symptoms:

- health endpoint unavailable
- startup script exits immediately

Likely cause:

- port conflict
- Python environment not ready
- another Mission Control daemon already owns the expected identity on the same port

Checks:

```powershell
.\scripts\start-mission-control-daemon.ps1
Invoke-WebRequest http://127.0.0.1:8010/api/health
```

Fix:

- verify Python environment
- inspect port usage
- confirm which repo root owns the live daemon
- check runtime folder permissions

## MCP bridge unreachable

Symptoms:

- Codex can see skills but not tools
- status requests fail

Likely cause:

- MCP config not loaded
- daemon token mismatch
- bridge cannot reach localhost daemon
- host app reload still has not happened after plugin or MCP config changes

Checks:

- inspect MCP config
- verify daemon health
- run plugin health doctor if available

Fix:

- reload Codex MCP config
- restart daemon
- re-run health checks

## Codex CLI missing or not logged in

Symptoms:

- preferred runner falls back unexpectedly
- health doctor reports missing login

Likely cause:

- local CLI not installed or not authenticated

Checks:

```powershell
codex --version
codex login status
```

Fix:

- install Codex CLI if missing
- complete local login
- re-run health checks

## Ollama installed but not running

Symptoms:

- Ollama mode requested but unavailable
- local-model runner not detected

Likely cause:

- service stopped
- no model installed
- provider adapter was overridden badly

Checks:

- verify Ollama service is active
- verify the intended model exists locally

Fix:

- start Ollama
- install the required local model with explicit user awareness
- restore the built-in adapter recipe unless a custom override is intentional
- fall back to Codex CLI or dry-run if needed

## API provider selected but still degraded

Symptoms:

- OpenAI, Anthropic, or xAI was selected
- startup or runner status still says runtime is not ready

Likely cause:

- the built-in adapter recipe exists, but the external API key is still missing

Checks:

- verify the provider key in the host environment
- rerun the support bundle and health checks

Fix:

- set the API key outside chat
- rerun startup or plugin health

## Claude CLI not detected

Symptoms:

- Claude CLI mode requested but unavailable

Likely cause:

- CLI not installed or not configured

Checks:

- verify CLI presence on PATH
- inspect local configuration

Fix:

- install or configure Claude CLI
- keep current runner policy until it is verified

## Webwright not ready

Symptoms:

- browser-task workflow reports setup blockers
- Mission Control refuses to fake browser-agent execution

Likely cause:

- `webwright` is not installed in the same Python environment as Mission Control
- Playwright or Chromium runtime is missing

Checks:

- inspect the project-scoped Webwright readiness surface
- verify the local Python environment

Fix:

- install the upstream Webwright runtime
- install the Chromium browser runtime through Playwright
- rerun the readiness check before claiming browser coverage

## API provider not configured

Symptoms:

- API runner requested but unavailable

Likely cause:

- secure provider config missing

Checks:

- inspect configured provider state in Mission Control

Fix:

- configure the provider through the secure path
- do not paste raw keys into chat

## Pending approval stuck

Symptoms:

- orchestration remains waiting on user
- the same approval keeps reappearing

Likely cause:

- user answer never reached Mission Control
- answer payload invalid
- upstream command remains blocked

Checks:

- re-fetch pending decisions
- confirm the decision id and selected option

Fix:

- answer the decision again through the bridge tool
- inspect bridge health if answers are not recorded

## Handoff missing evidence

Symptoms:

- final summary exists but confidence is weak
- claims are not backed by validation

Likely cause:

- validation skipped
- dry-run only
- artifacts not recorded

Checks:

- review validation summary
- review evidence checklist

Fix:

- run the missing validation through Mission Control
- mark remaining gaps honestly if validation cannot run

## Import scan slow or huge repo scan

Symptoms:

- existing-codebase attach takes too long
- codebase understanding appears too broad

Likely cause:

- repository is large
- scan is trying to go too deep too early

Checks:

- review the initial codebase map scope
- check whether a focused task was provided

Fix:

- use progressive understanding
- start with top-level map and focused entry points

## Permissions denied or port already in use

Symptoms:

- write-permission failures
- daemon startup collision

Likely cause:

- workspace boundary restriction
- another process already bound to the port

Checks:

- confirm the target path is inside the intended workspace
- inspect port usage before restarting the daemon

Fix:

- request the correct write permission through Mission Control
- free or change the daemon port deliberately

## Cross references

Dedicated follow-up pages:

See dedicated pages:

- [Troubleshooting CLI Runners](Troubleshooting-CLI-Runners)
- [Runner Configuration](Runner-Configuration)
- [Existing Codebase Mode](Existing-Codebase-Mode)
- [Handoffs and Evidence](Handoffs-and-Evidence)

## Related pages

Continue with [Diagnostics and Health Checks](Diagnostics-and-Health-Checks), [Localhost Binding and Ports](Localhost-Binding-and-Ports), [Recovery Planning](Recovery-Planning), and [Health Doctor Example Output](Health-Doctor-Example-Output).
