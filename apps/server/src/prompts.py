from __future__ import annotations

import json
from pathlib import Path

from models import Agent, Project, Task


WORKER_REPORT_SCHEMA = {
    "agent": "string",
    "task_id": "string",
    "status": "done|blocked|needs_review|error",
    "summary": "string",
    "files_changed": ["string"],
    "tests_run": ["string"],
    "blockers": ["string"],
    "risks": ["string"],
    "recommended_next_task": "string",
}

MANAGER_DOC_UPDATE_SCHEMA = {
    "summary_markdown": "string",
    "files": [{"filename": "string", "content": "string"}],
}

MANAGER_PLAN_SCHEMA = {
    "refined_summary": "string",
    "mvp_scope": ["string"],
    "milestones": ["string"],
    "recommended_architecture": ["string"],
    "agent_roster": [{"name": "string", "role": "string"}],
    "task_breakdown": ["string"],
    "validation_plan": ["string"],
    "risks": ["string"],
    "definition_of_done": ["string"],
    "content_markdown": "string",
    "summary_json": {},
}

MANAGER_TASK_DECOMPOSITION_SCHEMA = {
    "summary_markdown": "string",
    "milestones": ["string"],
    "tasks": [
        {
            "title": "string",
            "goal": "string",
            "scope": "string",
            "agent_role": "string",
            "milestone": "string",
            "priority": 10,
            "allowed_paths": ["string"],
            "forbidden_paths": ["string"],
            "validation_steps": ["string"],
            "success_criteria": ["string"],
            "estimated_complexity": "small|medium|large",
            "dependencies": [1],
            "status": "backlog|assigned|working|waiting_on_paths|needs_review|done|blocked",
        }
    ],
}

MANAGER_WORKER_DECISION_SCHEMA = {
    "decision_type": "assign_next_task|request_fix|mark_done|mark_blocked|retire_agent|escalate_to_user|wait",
    "summary_markdown": "string",
    "task_id": 1,
    "assign_to_agent_id": 1,
    "follow_up_title": "string",
    "follow_up_goal": "string",
    "escalation_message": "string",
}

MANAGER_HANDOFF_SCHEMA = {
    "summary_markdown": "string",
    "what_was_built": ["string"],
    "how_to_run": ["string"],
    "how_to_use": ["string"],
    "tests_builds_run": ["string"],
    "known_limitations": ["string"],
    "remaining_risks": ["string"],
    "suggested_next_improvements": ["string"],
}


def manager_system_prompt(project: Project) -> str:
    return f"""You are the Manager AI for Codex Mission Control.

Project name: {project.name}
Project idea:
{project.idea}

Responsibilities:
- Restate and refine the project idea.
- Ask interview questions when needed.
- Convert answers into project docs.
- Produce and revise plans.
- Create worker tasks.
- Assign non-overlapping tasks.
- Track worker reports.
- Decide the next action for finished workers.
- Prioritize usability, speed, and quality.
- Never claim a project is done unless validation was performed or explicitly marked as not run.

When you reply with structured content, keep it concise and machine-friendly.
"""


def project_context_block(project: Project, docs_path: str, plan_markdown: str | None = None) -> str:
    plan_section = f"\nCurrent approved plan:\n{plan_markdown}\n" if plan_markdown else ""
    return f"""Project: {project.name}
Workspace path: {project.workspace_path}
Project docs path: {docs_path}
Primary goal: ship a usable MVP quickly without fake demos.
{plan_section}
"""


def worker_task_prompt(project: Project, agent: Agent, task: Task, docs_path: str, plan_markdown: str | None = None) -> str:
    context = project_context_block(project, docs_path, plan_markdown)
    return f"""You are a Codex worker agent operating under Codex Mission Control.

Task ID: {task.id}
Agent name: {agent.name}
Agent role: {agent.role}

{context}

Goal:
{task.goal}

Scope:
{task.scope}

Allowed files/areas:
{json.dumps(task.allowed_paths_json, indent=2)}

Forbidden files/areas:
{json.dumps(task.forbidden_paths_json, indent=2)}

Requirements:
- Stay inside the task scope.
- Do not touch forbidden paths.
- If a required action needs approval, stop and report it.
- Prefer the smallest coherent set of changes.
- Do not claim testing was run if it was not run.

Validation steps:
{json.dumps(task.validation_steps_json, indent=2)}

Completion report JSON schema:
{json.dumps(WORKER_REPORT_SCHEMA, indent=2)}

Return only a JSON object matching the schema as your final answer.
"""


def manager_message_prompt(project: Project, docs_path: str, user_message: str) -> str:
    return f"""You are the Manager AI for the project "{project.name}".

Project docs live at: {docs_path}

The user sent this message:
{user_message}

Respond as the manager coordinating the project. If the message requests changes, outline the next step clearly.
"""


def manager_action_prompt(
    project: Project,
    docs_path: str,
    *,
    action: str,
    objective: str,
    response_schema: dict,
    payload: dict,
    plan_markdown: str | None = None,
) -> str:
    context = project_context_block(project, docs_path, plan_markdown)
    return f"""You are the Manager AI for Codex Mission Control.

Action: {action}
Objective:
{objective}

{context}

Input payload:
{json.dumps(payload, indent=2)}

Response rules:
- Return only valid JSON.
- Do not wrap the JSON in markdown fences.
- Match this schema exactly:
{json.dumps(response_schema, indent=2)}

Manager priorities, in order:
1. Usability for the user
2. Speed of building
3. Quality
"""


def app_server_input_items(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def docs_manifest_path(project: Project) -> Path:
    return Path(project.docs_path or "") / "MANIFEST.json"
