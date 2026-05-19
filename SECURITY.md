# Security Policy

Codex Mission Control is a local-first, background-running orchestration platform. Please report security issues responsibly and do not post secrets, exploit details, or private keys in public issues.

## Supported versions

| Version | Supported |
| --- | --- |
| Current `main` branch | Yes |
| Older snapshots and local forks | Best effort only |

## Reporting a vulnerability

If GitHub private vulnerability reporting is available for this repository, use it. If it is not available, open a GitHub issue only for minimal coordination and avoid posting sensitive details publicly.

When reporting:

- include affected commit or branch information
- include a concise description of impact
- include safe reproduction steps without secrets
- redact tokens, keys, cookies, and private paths

## Current security posture

- Mission Control is intended to run locally
- the daemon should stay on localhost by default
- bridge summaries should be redacted and compact
- API-backed runners require explicit secure configuration

## Related documentation

- [Detailed security guide](docs/SECURITY.md)
- [Support](SUPPORT.md)
