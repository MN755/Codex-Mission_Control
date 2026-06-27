# Recursive Improvement

> Status: Current

This workflow lets one Mission Control instance act as the controller while an isolated second Mission Control copy acts as the target.

The point is simple:

- the controller stays stable
- the target stays isolated
- both instances produce evidence
- Mission Control gets a real case study instead of another fake demo

## One-command workflow

```powershell
python scripts/mission-control-manage.py recursive-improvement --json
```

## What it does

1. Creates an isolated shadow copy of the current Mission Control repo.
2. Assigns it a separate runtime root, launcher root, Codex home, Agents home, and backend port.
3. Installs Mission Control into that isolated target.
4. Runs the target instance through the validated headless happy path on its own repo copy.
5. Runs the controller instance through the same headless happy path against that target repo copy.
6. Saves transcripts and JSON artifacts for both runs.

## Collision controls

The workflow refuses to treat the controller checkout and the target checkout as the same instance.

Isolation is enforced through:

- separate repo path
- separate runtime root
- separate launcher metadata
- separate backend port
- separate Codex and Agents homes for the target instance

## Artifacts

The workflow writes its artifacts under:

- `.runtime/recursive-improvement/<shadow-name>/`

Important files:

- `profile.json`
- `target-install.json`
- `target-smoke.json`
- `target-transcript.md`
- `controller-transcript.md`
- `controller-identity.json`
- `target-identity.json`

## What success means

Success here means:

- the isolated target instance installs cleanly
- the target daemon starts on its own port
- the target instance can attach its own repo copy, surface an approval, and produce a handoff plus approval log
- the controller instance can do the same against that target repo

That is the real recursive-improvement case study.

## Related docs

- [Quick Start](QUICK_START.md)
- [Headless Happy Path](HEADLESS_HAPPY_PATH.md)
- [Runner Support Matrix](RUNNERS.md)
- [Feature Status](FEATURE_STATUS.md)
