# Logs and Runtime Folders

This page explains where Mission Control stores runtime state, diagnostics, logs, and install reports, and what should not be shared publicly.

> Status: Current

## What lives in runtime folders

Expect runtime storage for:

- SQLite state
- daemon token or bridge runtime metadata
- diagnostics reports
- event summaries
- install or repair reports
- local configuration snapshots

## What not to share

Do not share publicly:

- daemon tokens
- raw approval payloads with secrets
- private paths that reveal local user details
- unredacted diagnostics bundles

## Collecting a safe debug bundle

Safe debug bundle guidance:

1. prefer summarized diagnostics
2. redact usernames, tokens, and paths where needed
3. include health doctor output, not raw logs first
4. include the exact command or step that failed

## Related pages

Read [Diagnostics and Health Checks](Diagnostics-and-Health-Checks), [Plugin Health Doctor](Plugin-Health-Doctor), and [Safety and Security Model](Safety-and-Security-Model).
