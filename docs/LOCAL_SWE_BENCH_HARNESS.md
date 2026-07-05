# Local SWE-bench Lite Harness

This harness runs Mission Control headlessly against a local JSON or JSONL task manifest and writes full benchmark artifacts under `Tests/swe-bench-lite-runs/`.

## Purpose

Use this when you want a local-only coding-agent benchmark path driven through Mission Control with:

- local prepared repos
- local Ollama models
- manager + worker execution routed through Mission Control
- saved trajectories, logs, diffs, validation output, and summary metrics

The harness can now read:

- JSON manifests
- JSONL manifests
- a local SWE-bench parquet file
- a local SWE-bench dataset directory such as `SWE-bench_Lite/`

For upstream SWE-bench Lite parquet data, it can also prepare a reusable local repo cache automatically.

## Command

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\path\to\swe-bench-lite-local.jsonl `
  --model qwen2.5-coder:7b `
  --approval-policy never
```

Default output root:

```text
Tests/swe-bench-lite-runs/<run-label>/
```

Before task execution, the harness writes `preflight.json` and refuses to start when strict Ollama mode requests an exact model that is not installed locally.

`preflight.json` now audits more than model availability. It also checks the selected tasks for:

- missing local repo snapshots
- duplicate `instance_id` values
- unreachable `base_commit` values inside prepared git repos
- tasks with no detectable validation command

Useful chunking flags for larger local manifests:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\path\to\swe-bench-lite-local.jsonl `
  --model qwen2.5-coder:7b `
  --start-index 100 `
  --max-tasks 25
```

You can also target exact tasks without rewriting the manifest:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\path\to\swe-bench-lite-local.jsonl `
  --model qwen2.5-coder:7b `
  --task-id django__12345 `
  --task-id sympy__67890
```

If you want to audit a local dataset export before spending time on a real run, use:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\bench\swe-bench-lite.jsonl `
  --prepared-repos-root C:\bench\prepared-repos `
  --model qwen2.5-coder:7b `
  --preflight-only
```

For upstream SWE-bench Lite style records that only include `repo`, `instance_id`, and `base_commit`, point the harness at a local prepared-repos root:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\bench\swe-bench-lite.jsonl `
  --prepared-repos-root C:\bench\prepared-repos `
  --model qwen2.5-coder:7b
```

If your task source is the downloaded parquet dataset itself, point `--tasks` at the dataset directory and choose a split:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\bench\SWE-bench_Lite `
  --dataset-split test `
  --prepared-repos-root C:\bench\prepared-repos `
  --model qwen2.5-coder:7b
```

If you only downloaded the dataset and do not already have the upstream repos cloned locally, use the automatic repo-cache path:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\bench\SWE-bench_Lite `
  --dataset-split test `
  --repo-cache-root C:\bench\swe-bench-repos `
  --auto-prepare-repos `
  --model qwen2.5-coder:7b `
  --preflight-only
```

That mode clones each unique upstream repo once into the local cache using `owner__repo` folder names, then reuses those clones across future runs.

The loader checks these local names under `--prepared-repos-root`:

- `<instance_id>`
- sanitized `<instance_id>`
- `<owner>/<repo>`
- `<owner>__<repo>`
- `<owner>-<repo>`
- `<repo>`

If your local layout is weirder than that, use a repo map instead:

```powershell
python scripts/run_swe_bench_harness.py `
  --tasks C:\bench\swe-bench-lite.jsonl `
  --repo-map C:\bench\repo-map.json `
  --model qwen2.5-coder:7b
```

## Manifest shape

Each task record should include:

- `instance_id`
- `problem_statement`
- one of:
  - `repo_path`
  - `workspace_path`
  - a resolvable local repo via `--prepared-repos-root`
  - a match in `--repo-map`

Optional fields:

- `repo`
- `base_commit`
- `hints_text`
- `validation_commands`
- `setup_commands`
- `FAIL_TO_PASS`
- `PASS_TO_PASS`

Example:

```json
{
  "instance_id": "django__12345",
  "repo": "django/django",
  "repo_path": "C:/bench/repos/django__12345",
  "base_commit": "abc123",
  "problem_statement": "Fix the queryset regression described in the issue.",
  "validation_commands": [
    "python -m pytest tests/queries/test_regression.py"
  ],
  "FAIL_TO_PASS": [
    "tests/queries/test_regression.py::test_queryset_bug"
  ]
}
```

Upstream-style local exports without `repo_path` also work when combined with `--prepared-repos-root` or `--repo-map`:

```json
{
  "instance_id": "django__12345",
  "repo": "django/django",
  "base_commit": "abc123",
  "problem_statement": "Fix the queryset regression described in the issue.",
  "FAIL_TO_PASS": [
    "tests/queries/test_regression.py::test_queryset_bug"
  ]
}
```

Repo map files accept either a flat mapping or nested `repos` / `instances` maps. Relative paths are resolved from the repo-map file location.

```json
{
  "repos": {
    "django/django": "../prepared/django"
  },
  "instances": {
    "sympy__67890": "../prepared/sympy__67890"
  }
}
```

## Output artifacts

Per task the harness records:

- staged workspace copy
- prompt sent through the manager bridge
- API trajectory JSONL
- generated tasks, agents, events, approvals, and pending decisions
- agent logs
- workspace diff
- validation stdout/stderr
- per-task result JSON

If a task includes `base_commit` and the prepared repo snapshot still has `.git` metadata, the harness resets the copied workspace to that commit before Mission Control starts. If `.git` is missing, the run stays honest and records that the snapshot was used as-is.

Run-level outputs include:

- `summary.json`
- `report.md`

## Honesty rules

The harness reports:

- `validation_not_run` when no validation command was available or executed
- `timeout` when the harness or task loop timed out
- `setup_failed` when repo staging or runtime setup failed
- `approval_blocked` or `pending_decision` when automation could not continue cleanly

It also pins strict-model mode by default so the Ollama adapter does not quietly fall back to a different local model during a benchmark run.
