# Codex Mission Control

<p align="center">
  <img src="apps/desktop/assets/mission-control-logo.png" alt="Mission Control logo" width="128" />
</p>

<p align="center">
  <a href="https://github.com/MN755/Codex-Mission_Control/actions/workflows/package-desktop.yml"><img alt="Build" src="https://github.com/MN755/Codex-Mission_Control/actions/workflows/package-desktop.yml/badge.svg"></a>
  <a href="https://github.com/MN755/Codex-Mission_Control/releases"><img alt="Version" src="https://img.shields.io/github/v/tag/MN755/Codex-Mission_Control?sort=semver"></a>
  <a href="https://www.python.org"><img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue"></a>
</p>

Codex Mission Control is a headless orchestration bridge for real repo work.

The product path is: `Codex chat -> Mission Control plugin/MCP bridge -> Mission Control daemon -> Manager AI -> worker runners`.

The dashboard exists, but it is not the product center. If the chat-native path is broken, the product is broken. Anything softer than that is just cope.

## Quick Start

```powershell
python scripts/mission-control-manage.py install
python scripts/mission-control-manage.py codex-smoke --json
powershell -ExecutionPolicy Bypass -File scripts/smoke-headless-happy-path.ps1
```

Then in Codex chat:

```text
Use Mission Control for this repo and fix the failing tests.
```

## Validated Headless Path

The smallest validated workflow is: attach repo -> start task -> dry-run/worker step -> approval -> handoff -> approval log.

Proof lives in:

- [Headless happy path test](apps/server/tests/test_headless_happy_path.py)
- [Bridge runtime test](apps/server/tests/test_bridge_runtime.py)
- [MCP server test](apps/mcp-server/tests/test_mcp_server.py)
- [docs/TERMINAL_TRANSCRIPT.md](docs/TERMINAL_TRANSCRIPT.md)

## Runner Support

`working` here means the runner path is implemented, selected by the runtime, and covered by tests when its prerequisites are present. It does not mean your machine was magically preconfigured for you.

| Runner | Status | Requirements |
| --- | --- | --- |
| `codex_cli` | working | local Codex CLI installed and logged in |
| `claude_cli` | working | local Claude CLI executable |
| `ollama` | working | reachable Ollama endpoint plus built-in adapter recipe |
| `openai_api` | working | `OPENAI_API_KEY` plus built-in adapter recipe |
| `dry_run` | working | none |

Full matrix:

- [Runner Support Matrix](docs/RUNNERS.md)

## Recursive Improvement

Mission Control can now build and evaluate an isolated recursive-improvement copy of itself without colliding with the controller instance.

```powershell
python scripts/mission-control-manage.py recursive-improvement --json
```

That workflow creates a separate target repo/runtime/port, validates the target instance on its own repo copy, then runs the controller against that same target repo and saves both transcripts.

## Docs

- [Quick Start](docs/QUICK_START.md)
- [Headless Install](docs/HEADLESS_INSTALL.md)
- [Headless Happy Path](docs/HEADLESS_HAPPY_PATH.md)
- [Recursive Improvement](docs/RECURSIVE_IMPROVEMENT.md)
- [Feature Status](docs/FEATURE_STATUS.md)
- [Runner Support Matrix](docs/RUNNERS.md)
- [Terminal Transcript](docs/TERMINAL_TRANSCRIPT.md)
- [Docs Index](docs/README.md)

## Contributing

- [Contributing guide](CONTRIBUTING.md)
- [Development docs](docs/CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

This project is licensed under the [MIT License](LICENSE).
