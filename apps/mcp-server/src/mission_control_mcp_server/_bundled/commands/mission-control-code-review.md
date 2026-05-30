---
description: Review a branch, diff, or pull request through Mission Control
disable-model-invocation: false
---

Ask Mission Control to run a review workflow for:

`$ARGUMENTS`

Expected review lanes:

- Instruction compliance.
- Diff-level bug scan.
- Historical context and touched-file risk.
- Test and validation adequacy.
- Security-sensitive behavior.

Return only high-confidence findings with file/line references when available. If no findings survive review, say so and list residual validation gaps.
