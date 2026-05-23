---
description: Diagnose Mission Control plugin, MCP, CLI, and runner health
disable-model-invocation: false
---

Run the Mission Control plugin health path.

Report:

- Daemon readiness.
- MCP bridge readiness.
- Codex plugin registration.
- Claude Code command and MCP readiness.
- Runner availability.
- Ollama status if available.
- Required host reloads or approvals.

If the bridge is missing, tell the user exactly which app action is still required.
