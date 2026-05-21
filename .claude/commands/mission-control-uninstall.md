Remove Mission Control bridge assets from Codex home with one command.

Workflow:

1. Run `python scripts/mission-control-manage.py uninstall`.
2. Let the workflow remove the Mission Control plugin bundle, synced `mission-control*` skills, and the managed Codex MCP registration.
3. Let the workflow stop the local Mission Control daemon when safe unless the user asked to keep it running.
4. Summarize exactly what was removed and what remained untouched.
5. Tell the user that already-open Codex or Claude sessions may still show stale Mission Control plugin or MCP state until the app is force-quit and reopened.

Do not delete the source repository checkout unless the user explicitly asks for that.
