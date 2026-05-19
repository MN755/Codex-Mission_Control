# Custom Codex Agents

Mission Control can generate project-scoped custom agent TOML files under `.codex/agents/`.

## Purpose

These files give Codex subagents a narrow, repeatable role for burst work.

## Safety Defaults

- read-only sandbox
- no file edits
- no commands
- no recursive delegation
- expected report format is explicit

## Generated Agent Files

- `mc-repo-mapper.toml`
- `mc-test-finder.toml`
- `mc-docs-reader.toml`
- `mc-risk-scanner.toml`
- `mc-dependency-mapper.toml`
- `mc-correctness-reviewer.toml`
- `mc-security-reviewer.toml`
- `mc-test-coverage-reviewer.toml`
- `mc-maintainability-reviewer.toml`
- `mc-handoff-auditor.toml`

## Generation Behavior

- existing files are not overwritten by default
- generation is project-scoped
- the output is narrow on purpose

## Result Ingestion

Generated agents are expected to report:

- summary
- evidence
- risks
- recommendations
- confidence

Mission Control stores those results against the subagent batch so the Manager can consume them later.
