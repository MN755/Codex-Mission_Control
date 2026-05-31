# Review project capability section


Canonical prompt: `review_project_capability_section`
Invocation name: `review_project_capability_section`

## Purpose

Load one named capability-report section so Codex can focus on a single Mission Control lane without dragging the other fourteen around.

## Tool Sequence

- `mission_control_get_capability_section`

## Resource Sequence

- `mission-control://projects/{project_id}/capability-report/{section_key}`

## Safety Notes

Keep the output scoped to the requested capability section and do not pretend the section proves unrelated parts of the system are healthy.

## Prompt Text

Review one named Mission Control capability-report section for the attached project. Load only the requested section, summarize its current status, safe commands, artifacts, and setup gaps, and explain what still limits that lane if anything remains partial.
