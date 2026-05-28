# Codex Mission Control

<p align="center">
  <img src="apps/desktop/assets/mission-control-logo.png" alt="Mission Control logo" width="112" />
</p>

Codex Mission Control is a background-running orchestration platform that lets a single Codex chat coordinate a Manager AI and multiple background coding agents.

Mission Control runs as a local daemon. Codex interacts with it through a plugin and MCP bridge, reusable skills, and chat-native approval flows. The Manager AI plans work, coordinates worker agents, relays user decisions, and returns evidence-backed handoffs.

## Why it exists

Large coding tasks usually fail for boring reasons: unclear scope, conflicting edits, missing approvals, weak validation, and lost context between iterations. Mission Control keeps the user in one Codex chat while moving orchestration, worker coordination, approvals, and handoff generation into a dedicated local runtime.

## Core features

- Background-running Codex-native workflow
- Manager AI orchestration behind a local daemon
- Adaptive worker swarms with coordination guardrails
- Runner autowiring for local CLI and API-backed providers
- Operator-ready project surfaces such as status, operator snapshot, instincts, and verification brief
- Existing codebase import with read-only intake
- Pending decisions and approval relay through Codex chat
- Safe local-first defaults and secret redaction
- Chat-native handoffs with validation and evidence summaries
- Optional Webwright browser-agent readiness and browser-task routing
- Diagnostics and health checks for daemon, bridge, and runners

## Quick start

From a Codex chat in your project folder:

```text
Install Mission Control from https://github.com/MN755/Codex-Mission_Control and wire it up.
```

Then:

```text
Use Mission Control for this repo and fix the failing tests.
```

Useful follow-up prompts:

```text
Show Mission Control status.
Show Mission Control operator snapshot.
Show Mission Control verification brief.
Show pending Mission Control approvals.
Get the latest Mission Control handoff.
Use Mission Control for a browser task with Webwright when available.
```

## Example Codex chat workflow

1. Attach the current workspace to Mission Control.
2. Start or resume a task through the MCP bridge.
3. Review pending decisions and answer them in chat.
4. Check status or event digests while work continues.
5. Review the final handoff with validation and next steps.

## Architecture

```text
Codex chat
  ->
Mission Control plugin / MCP bridge
  ->
Mission Control daemon
  ->
Manager AI
  ->
Worker agents / runners
```

Core boundaries:

- Codex chat is the user-facing bridge.
- Mission Control daemon owns orchestration state.
- The Manager AI lives inside Mission Control.
- MCP tools act, MCP resources summarize, and MCP prompts guide.
- Worker agents stay behind Mission Control approvals and runner policy.

## Safety model

- Local-first by default, with loopback daemon binding
- No raw secrets or raw logs in bridge summaries by default
- Explicit pending decisions for high-risk actions
- Read-only resource summaries for status, diagnostics, and handoff context
- API-backed runners require explicit configuration and user awareness

## Documentation

- [Overview](docs/OVERVIEW.md)
- [Quick Start](docs/QUICK_START.md)
- [Background Install](docs/HEADLESS_INSTALL.md)
- [Codex Chat Mode](docs/CODEX_CHAT_MODE.md)
- [Codex Chat UX Spec](docs/CODEX_CHAT_UX_SPEC.md)
- [Background Architecture](docs/HEADLESS_ARCHITECTURE.md)
- [MCP Plugin Bridge](docs/MCP_PLUGIN_BRIDGE.md)
- [MCP Tools](docs/MCP_TOOLS.md)
- [MCP Resources](docs/MCP_RESOURCES.md)
- [MCP Prompts](docs/MCP_PROMPTS.md)
- [Runners](docs/RUNNERS.md)
- [Webwright Companion](docs/WEBWRIGHT.md)
- [Autowire Providers](docs/AUTOWIRE_PROVIDERS.md)
- [Background Health](docs/HEADLESS_HEALTH.md)
- [Security](docs/SECURITY.md)
- [Docs Index](docs/README.md)
- [GitHub Wiki](https://github.com/MN755/Codex-Mission_Control/wiki)

## Current status

Mission Control is designed first for background running through Codex chat.

- Current: daemon-oriented orchestration, plugin and MCP bridge packaging, skill library, pending decision relay, diagnostics, and chat-native handoffs
- Partial / experimental: some runner integrations, deeper autowiring coverage, app-server paths, and orchestration hardening
- Optional / future: standalone dashboard observability

## Contributing

Contributions should follow the current product direction: Codex chat is the user-facing surface, and Mission Control daemon is the orchestration platform.

- [Contributing guide](CONTRIBUTING.md)
- [Development docs](docs/CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Support](SUPPORT.md)
- [Changelog](CHANGELOG.md)

## License

This project is licensed under the [MIT License](LICENSE).
