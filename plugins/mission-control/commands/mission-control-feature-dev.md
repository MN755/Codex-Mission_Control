---
description: Run a manager-led feature development workflow
disable-model-invocation: false
---

Route feature development through Mission Control.

Ask Mission Control to plan, decompose, assign workers, validate, and produce a handoff for this feature request:

`$ARGUMENTS`

Use these built-in worker lanes when useful:

- Code explorer for repo mapping and constraints.
- Architect for design and integration boundaries.
- Implementer for focused file changes.
- Reviewer for behavioral bugs and instruction compliance.
- Test engineer for validation gaps.

Do not spawn independent Claude-only workers outside Mission Control. That would create two bosses, which is how projects become archaeology.
