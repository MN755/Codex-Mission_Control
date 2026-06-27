# Quick Start

> Status: Current

This page covers the fastest path from repo clone to a validated Mission Control session in Codex chat.

## Install

```powershell
python scripts/mission-control-manage.py install
```

## Validate

```powershell
python scripts/mission-control-manage.py codex-smoke --json
powershell -ExecutionPolicy Bypass -File scripts/smoke-headless-happy-path.ps1
```

The second command proves the real bridge flow:

1. attach repo
2. start task
3. surface approval
4. answer approval
5. produce handoff
6. show approval audit log

Transcript proof:

- [Terminal Transcript](TERMINAL_TRANSCRIPT.md)

## Use From Chat

From a Codex chat in your repo folder:

```text
Use Mission Control for this repo and fix the failing tests.
```

## Common prompts

Attach the workspace:

```text
Attach the current workspace to Mission Control.
```

Check status:

```text
Show Mission Control status.
```

Review pending decisions:

```text
Show pending Mission Control approvals.
```

Get the handoff:

```text
Get the latest Mission Control handoff.
```

## Read next

- [Background Install](HEADLESS_INSTALL.md)
- [Headless Happy Path](HEADLESS_HAPPY_PATH.md)
- [Runner Support Matrix](RUNNERS.md)
- [Feature Status](FEATURE_STATUS.md)
- [Troubleshooting](TROUBLESHOOTING.md)
