# Feature Status

> Status: Current

This page separates shipped behavior from planned behavior so the repo stops pretending every idea is equally real.

## Shipped And Validated

- one-command install: `python scripts/mission-control-manage.py install`
- daemon health smoke: `python scripts/mission-control-manage.py codex-smoke --json`
- small headless happy path:
  - attach repo
  - start task
  - surface approval
  - answer approval
  - produce handoff
  - show approval audit log
- recursive improvement lane:
  - create isolated target copy
  - install target instance with separate runtime and port
  - validate target instance on its own repo copy
  - validate controller instance against that target repo copy
- runner lanes marked `working` in [RUNNERS.md](RUNNERS.md):
  - `codex_cli`
  - `claude_cli`
  - `ollama`
  - `openai_api`
  - `dry_run`
- daemon + MCP bridge resource surface
- approval logging and approval audit resources

Proof:

- [Headless Happy Path](HEADLESS_HAPPY_PATH.md)
- [Recursive Improvement](RECURSIVE_IMPROVEMENT.md)
- [Terminal Transcript](TERMINAL_TRANSCRIPT.md)
- [Headless happy path test](../apps/server/tests/test_headless_happy_path.py)
- [MCP server test](../apps/mcp-server/tests/test_mcp_server.py)

## Shipped But Prerequisite-Dependent

- `codex_cli` requires local Codex CLI install and login
- `claude_cli` requires local Claude CLI install and auth
- `ollama` requires a reachable local Ollama endpoint
- `openai_api` requires `OPENAI_API_KEY`
- advanced provider lanes such as `anthropic_api`, `xai_api`, `nvidia_dynamo`, and `nvidia_nim` remain implemented but are not part of the smallest validated quickstart

These are real features. They are just environment-dependent, which is normal and not a moral failing.

## Planned Or Explicitly Not The Product Center

- dashboard-first workflow as the primary product path
- any flow that skips Mission Control approvals
- any demo that claims real edits or real test execution when it only ran in `dry_run`
- automatic provisioning of third-party CLI tools or API keys on behalf of the user

The dashboard is optional. The headless chat-native bridge is the product.
