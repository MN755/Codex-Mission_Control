# Mission Control Skill Library

Mission Control is the headless or background orchestrator. Codex chat is the bridge surface inside the Codex desktop app.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## How the library is grouped

- Core bridge workflows handle attach, start, status, approvals, handoff, pause, resume, and stop.
- Planning and intake workflows handle import, interviews, clarifications, plans, and scoped follow-up requests.
- Execution and swarm workflows handle swarm plans, contracts, path locks, snapshots, and conflict or stuck-agent handling.
- Validation, evidence, docs, and release workflows keep proof, runbooks, public docs, and release readiness explicit.
- Diagnostics and policy workflows cover recovery, health, headless install or autowire, model or tool policy, local-first posture, and provider modes.

## How Codex should use these skills

- Trigger the narrowest skill that matches the user request.
- Prefer Mission Control tools for actions and Mission Control resources for read-only summaries.
- Use MCP prompts when a flow already exists instead of reinventing the workflow in chat.
- Keep summaries compact, bridge-safe, and honest about unknowns.
- If a tool or resource is missing, mark it as expected or future and fall back gracefully without faking execution.

## Bridge rule

- The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.
- Codex chat should not independently spawn worker agents while Mission Control mode is active.
- Codex chat should not bypass Mission Control approvals, write gates, or swarm controls.

## Approval relay

- Use `mission-control-approve` whenever pending decisions exist.
- Explain risk, options, and likely impact before asking the user to choose.
- Confirm the recorded answer after `mission_control_answer_decision` succeeds.

## Headless mode

- This library is designed for Codex desktop chat and headless Mission Control orchestration.
- It does not depend on dashboard UI flows, widget reading, or frontend layout state.
- Status, diagnostics, handoff, and event summaries should stay useful even when only MCP tools and resources are available.

## Examples

- `Use Mission Control for this repo.` -> `mission-control-orchestrate`
- `Attach this existing repo and let the Manager understand it.` -> `mission-control-import-codebase`
- `What is blocked right now?` -> `mission-control-status` or `mission-control-approve`
- `Give me the final handoff.` -> `mission-control-handoff`
- `The run looks stuck.` -> `mission-control-debug` or `mission-control-recovery-plan`
- `Make this local-first and prefer Ollama if available.` -> `mission-control-local-first` plus `mission-control-ollama-mode`

## Index

See `plugins/mission-control/SKILL_INDEX.md` for the grouped index of all 53 skills.
