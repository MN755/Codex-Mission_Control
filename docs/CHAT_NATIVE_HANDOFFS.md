# Chat-Native Handoffs

Mission Control handoffs are evidence-backed summaries for Codex chat.

They are not victory speeches.

## Required sections

- status
- confidence / evidence level
- what changed
- how to run
- validation / evidence
- known limitations
- next recommended tasks
- important files / artifacts

## Evidence rules

- do not claim tests passed without evidence
- if validation was not run, say `not run`
- if the handoff is dry-run, say so clearly
- if evidence is missing, include an evidence warning section

## Example

```md
## Mission Control handoff ready

**Status:** ready (dry-run)
**Confidence / evidence:** medium / missing
**Dry-run:** This summary is based on simulated execution and recorded dry-run evidence only.

### What changed
- Updated the bridge runtime formatting layer.
- Added a deterministic headless acceptance test.

### How to run
- python -m pytest apps/server/tests/test_headless_happy_path.py

### Validation / evidence
- Not run.

### Evidence warnings
- No passing build or test evidence is recorded.
- Required gate unresolved: test gate

### Known limitations
- This handoff was produced in dry-run mode.

### Next recommended tasks
- Run real validation with a live runner before calling this production-ready.

### Important files / artifacts
- apps/server/src/bridge_messages.py
- docs/CHAT_NATIVE_HANDOFFS.md
```

## Routes

- `GET /api/orchestrations/{orchestration_id}/handoff-summary`
- `GET /api/projects/{project_id}/handoff-summary`
- `POST /api/projects/{project_id}/handoff/generate`
- `GET /api/projects/{project_id}/handoff/evidence`
- `POST /api/projects/{project_id}/handoff/evidence`

The dry-run bridge demo at `POST /api/headless/happy-path-demo` ends by returning this handoff format. It is explicitly a dry-run handoff, not fake proof that real validation happened.
