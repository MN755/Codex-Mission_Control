Update or repair Mission Control for this repository with one command.

Workflow:

1. Run `python scripts/mission-control-manage.py update`.
2. Let the workflow refresh backend and MCP Python packages unless the user explicitly asked to skip package setup.
3. Let the workflow resync the Codex plugin bundle and `mission-control*` skills into Codex home.
4. Let the workflow refresh the managed Codex MCP registration and rerun repair/bootstrap.
5. Summarize:
   - overall status
   - daemon and bridge readiness
   - runner readiness, including Ollama if available
   - any remaining user actions
6. Tell the user to force-quit and reopen Claude Code and Codex before trying to use Mission Control, because MCP and plugin changes are not live until the host app reloads them.
7. Tell the user that after the reload Codex should show `Mission Control` as an available plugin, not just as standalone Mission Control skills.
8. Tell the user to approve the project MCP server from `.mcp.json` if Claude Code prompts for it after reload.
9. If Codex still does not show the plugin after reload, tell the user to rerun `python scripts/mission-control-manage.py update` and restart Codex again instead of acting like skills-only mode is close enough.

Do not require the standalone UI.
