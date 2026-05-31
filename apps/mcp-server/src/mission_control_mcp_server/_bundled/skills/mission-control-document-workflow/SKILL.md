---
name: mission-control-document-workflow
description: Coordinate document, PDF, Word, slide, spreadsheet, and report workflows through Mission Control. Use for document generation, conversion plans, extraction, validation, and evidence-backed summaries.
---

# Mission Control Document Workflow

## Purpose

Plan document-heavy work without pretending Mission Control owns every file-format implementation internally.

The Codex chat agent is not the Mission Control Manager. It is the bridge between the user and the Mission Control Manager.

## Use when

- The user asks for PDF, DOCX, PPTX, XLSX, report, or document workflow help.
- A document needs extraction, validation, summarization, or generated output.
- The workflow depends on external document tooling.

## Workflow

1. Ask Mission Control to classify the document task and required tools.
2. Identify whether built-in host document plugins or local libraries are needed.
3. Route extraction, generation, or validation through approved runners.
4. Return evidence, outputs, limitations, and next steps.

## Mission Control calls

Tools:
- `mission_control_start_task`
- `mission_control_get_status`

Resources:
- `mission-control://projects/{project_id}/handoff`
- `mission-control://projects/{project_id}/validation-summary`
- `mission-control://projects/{project_id}/status`

## User-facing output

- State document type, requested operation, tool path used, files created or inspected, and validation status.

## Approval behavior

Ask before overwriting documents, exporting sensitive data, or using external services.

## Never do

- Do not claim document fidelity without checking the generated artifact.
- Do not expose private document contents unnecessarily.
- Do not reimplement specialized document tooling when an approved plugin already exists.

## Failure and fallback

If document tooling is unavailable, produce a plan and list the exact missing capability.

## Example invocation

`Use Mission Control to extract the key claims from this PDF and create a validation checklist.`
