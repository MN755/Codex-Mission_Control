# Security

> Status: Current

Mission Control is designed to be local-first, explicit about trust boundaries, and conservative by default.

## Default posture

- daemon bound to loopback by default
- local runtime folders and local state
- local CLI or local endpoint runners preferred
- no required cloud control plane
- secret redaction in chat-facing summaries

## Approval and execution model

- high-risk actions should remain pending until the user answers
- MCP resources are read-only summaries
- MCP tools perform actions and must respect approval policy
- Mission Control should not execute arbitrary commands through resource reads
- destructive or billed actions require explicit user awareness

## Secret handling

Mission Control documentation, diagnostics, and bridge summaries should not expose:

- raw API keys
- bearer tokens
- cookie values
- private key material
- raw `.env` contents
- full unredacted logs by default

## Provider posture

- Codex CLI login is the preferred non-API-key path
- Ollama is treated as a local endpoint
- API-backed runners require explicit secure configuration
- Mission Control should not silently move a project onto a billed provider

## Network exposure

Mission Control is intended for local use. Keep the daemon on localhost unless you have added additional controls intentionally.

## Related docs

- [Pending Decisions](PENDING_DECISIONS.md)
- [Autowire Providers](AUTOWIRE_PROVIDERS.md)
- [Background Health](HEADLESS_HEALTH.md)
- [Security Model](SECURITY_MODEL.md)
