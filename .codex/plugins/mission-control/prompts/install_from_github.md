# Install from GitHub


Canonical prompt: `install_from_github`
Invocation name: `install_from_github`

## Purpose

Bootstrap Mission Control headlessly from the GitHub repo, then report what is ready in Codex chat.

## Tool Sequence

- `mission_control_plugin_health`

## Resource Sequence

- No explicit Mission Control resources are declared.

## Safety Notes

Do not ask the user to open the standalone Mission Control UI. Never expose secrets or force API billing.

## Prompt Text

Install Mission Control from GitHub in headless mode, configure the daemon and MCP bridge, run plugin health, and summarize exactly what is ready and what still needs user action in Codex chat.
