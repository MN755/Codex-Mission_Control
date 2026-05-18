# Plugin Health Doctor

Plugin Health Doctor is the read-only bridge health check for Codex plugin and MCP mode.

It tells Codex chat whether Mission Control is actually usable instead of making everyone guess from vibes and broken prompts.

## Endpoints

- `GET /api/plugin/health`
- `POST /api/plugin/health/check`
- `GET /api/orchestrations/plugin-health`

## Overall status

Top-level status is one of:

- `ready`
- `degraded`
- `broken`

Individual checks use:

- `ready`
- `degraded`
- `broken`
- `unknown`

## Checks

Current checks cover:

- Mission Control daemon reachable
- MCP server reachable
- MCP tools registered when metadata is available
- MCP resources registered when metadata is available
- MCP prompts registered when metadata is available
- plugin package exists
- skill files exist
- Codex CLI detected
- Codex login status detectable
- runner registry available
- runtime directory writable
- SQLite DB reachable
- localhost-only binding
- dashboard optional status

Dashboard reachability is informative only. Headless bridge mode does not require it.

## Response shape

The health summary returns:

- `status`
- `checks`
- `recommended_next_steps`
- `safe_troubleshooting_commands`
- `codex_chat_markdown`
- `checked_at`
- `notes`

Each check returns:

- `key`
- `label`
- `status`
- `summary`
- `recommended_fix`
- `details_json`
- `checked_at`

## Security behavior

Health Doctor does not expose:

- daemon tokens
- API keys
- bearer tokens
- `.env` contents
- private key blocks
- secret file contents

It returns only redacted, high-level diagnostic state plus safe copyable commands.

## Example troubleshooting commands

```powershell
.\scripts\start-mission-control.ps1
codex --version
codex login status
codex mcp list --json
Invoke-WebRequest http://127.0.0.1:8000/api/health
Get-ChildItem plugins\mission-control -Recurse
Get-ChildItem .codex\skills
```

## Test coverage

Backend tests cover:

- ready state
- degraded state
- broken state
- chat markdown output
- dashboard optional behavior

See [apps/server/tests/test_plugin_health.py](../apps/server/tests/test_plugin_health.py).
