# Install From GitHub

Purpose: bootstrap Mission Control headlessly from the GitHub repo and report readiness in Codex chat.
Arguments: `REPO_URL`, `WORKSPACE_PATH`
Tool sequence: `mission_control_plugin_health`
Expected output: install status, daemon/MCP readiness, ready runners, and user actions still required.
Safety: do not ask the user to open the standalone UI, expose secrets, or force billed API providers.
