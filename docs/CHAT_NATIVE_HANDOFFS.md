# Chat-Native Handoffs

> Status: Current

This page describes the handoff format Mission Control should return to Codex chat at the end of a task or iteration.

## Required sections

- status
- confidence or evidence level
- what changed
- how to run
- validation or evidence
- known limitations
- next recommended tasks
- important files or artifacts

## Minimal example

```md
## Mission Control handoff ready

**Status:** ready for review
**Confidence / evidence:** medium

### What changed
- Updated the bridge runtime formatting layer.

### How to run
- python -m pytest apps/server/tests/test_headless_happy_path.py

### Validation / evidence
- Not run.

### Known limitations
- This summary is based on dry-run evidence only.
```

## Related docs

- [Handoffs](HANDOFFS.md)
- [Pending Decisions](PENDING_DECISIONS.md)
