---
description: Run a Mission Control security review
disable-model-invocation: false
---

Ask Mission Control to run a security-focused review for:

`$ARGUMENTS`

Check for:

- Secret exposure.
- Unsafe command execution.
- Auth and token boundary mistakes.
- Localhost and MCP trust assumptions.
- Destructive file operations.
- User approval bypasses.

Do not print secrets. Redact paths or tokens when needed.
