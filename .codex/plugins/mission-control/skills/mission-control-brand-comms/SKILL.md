---
name: mission-control-brand-comms
description: Coordinate brand-guideline, internal-communications, announcement, and stakeholder-message work through Mission Control with tone, audience, and evidence constraints.
---

# Mission Control Brand And Communications

## Purpose

Use Mission Control to produce communication drafts that respect audience, tone, claims, and evidence boundaries.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user wants release notes, announcements, stakeholder updates, or internal comms.
- Brand tone or style constraints matter.
- Technical work needs an audience-specific summary.

## Workflow

1. Ask Mission Control to identify audience, tone, facts, claims, and source evidence.
2. Draft the communication through the Manager workflow.
3. Check for unsupported claims, secrets, or overpromising.
4. Return the draft plus evidence notes and open questions.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_handoff_summary`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/decision-ledger`
- `mission-control://projects/{project_id}/status`

## User-facing output

- Provide the message draft, audience, tone assumptions, evidence sources, and unresolved claims.

## Approval behavior

Ask before posting, emailing, publishing, or committing communications.

## Never do

- Do not invent metrics, customer claims, or release guarantees.
- Do not leak internal paths, secrets, or private incident details.
- Do not turn uncertainty into marketing fog.

## Failure and fallback

If evidence is thin, produce a draft marked as unverified and ask for source material.

## Example invocation

`Use Mission Control to draft a release announcement from the latest handoff.`
