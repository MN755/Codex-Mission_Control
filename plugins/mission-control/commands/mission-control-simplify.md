---
description: Find simplification opportunities without reckless rewrites
disable-model-invocation: false
---

Ask Mission Control to inspect the target and propose simplifications:

`$ARGUMENTS`

Bias toward:

- Removing dead paths.
- Collapsing duplicate logic.
- Reducing unnecessary abstractions.
- Improving names and boundaries.
- Preserving behavior with tests.

Require evidence before deleting code. "Looks unused" is not a proof; it is a bug report waiting to hatch.
