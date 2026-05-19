# Handoffs

> Status: Current

Mission Control handoffs are the final user-facing summaries returned through Codex chat when a task reaches a review point or completion point.

## Required sections

- status
- confidence or evidence level
- what changed
- how to run
- validation or evidence
- known limitations
- next recommended tasks
- important files or artifacts

## Evidence rules

- do not claim tests passed without recorded evidence
- if validation was not run, say so directly
- if the run was dry-run only, say so directly
- if important evidence is missing, include a warning

## Typical handoff use

The handoff is where the user decides whether to stop, request changes, or continue into another iteration. It should be concise, specific, and honest about what was and was not validated.

## Related docs

- [Chat-Native Handoffs](CHAT_NATIVE_HANDOFFS.md)
- [Pending Decisions](PENDING_DECISIONS.md)
- [Security](SECURITY.md)
- [Troubleshooting](TROUBLESHOOTING.md)
