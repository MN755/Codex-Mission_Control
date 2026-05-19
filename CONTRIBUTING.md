# Contributing to Codex Mission Control

Thank you for contributing. Codex Mission Control is designed first for background running, so the primary product surface is Codex chat plus the local Mission Control daemon.

## Current direction

- Codex chat is the user-facing bridge
- Mission Control daemon owns orchestration
- the Manager AI lives inside Mission Control
- worker agents stay behind approval and runner policy
- standalone dashboard work is optional unless explicitly requested

## Development setup

```powershell
cd apps/server
python -m pip install -e .[dev]
python -m pytest
```

## Contribution expectations

- keep changes aligned with the current background-running direction
- do not introduce fake claims in docs or tests
- do not expose secrets in code, docs, diagnostics, or examples
- keep README and docs concise and accurate
- avoid standalone UI work unless the task explicitly asks for it

## Pull request checklist

- code or docs match the current product direction
- tests or validation were run when practical
- new docs link to related docs
- secrets are redacted
- known limitations are called out clearly

## More detail

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for project-specific development guidance.
