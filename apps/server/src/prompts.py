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

MANAGER_INTERVIEW_SCHEMA = {
    "understanding": {
        "summary": "string",
        "known_facts": {},
        "unknowns": {},
        "assumptions": ["string"],
        "constraints": ["string"],
        "confidence_by_category": {"product goal": 0.0},
    },
    "next_questions": [
        {
            "question": "string",
            "why": "string",
            "category": "product goal|target users|MVP scope|core features|nice-to-have features|platform/runtime|UI/UX style|data/storage|authentication/security|integrations/connectors|agent/tool behavior|approvals/sandboxing|testing/validation|deployment/distribution|performance constraints|privacy/local-first constraints|future expansion|handoff format",
            "impact": "low|medium|high",
            "options": [{"id": "string", "label": "string", "description": "string"}],
            "allow_custom_answer": False,
            "affects": ["string"],
        }
    ],
    "more_questions_needed": True,
    "stop_reason": "string or null",
}

MANAGER_SWARM_PLAN_SCHEMA = {
    "mode": "fastest_build|balanced|high_quality|documentation_heavy|research_planning|massive_codebase|manager_decides",
    "goal": "string",
    "recommended_agent_count": 5,
    "coordination_risk": "low|medium|high",
    "path_conflict_risk": "low|medium|high",
    "expected_bottlenecks": ["string"],
    "strategy_summary": "string",
    "validation_strategy": ["string"],
    "specs": [
        {
            "archetype": "frontend|backend|feature|docs|test|reviewer|security|planner|architect|integration|ops|research|migration|refactor|performance|data|ui_polish|release_handoff",
            "name": "string",
            "mission": "string",
            "model_policy": "string",
            "toolset": ["string"],
            "allowed_paths": ["string"],
            "forbidden_paths": ["string"],
            "spawn_phase": "string",
            "retire_when": "string",
            "priority": 50,
        }
    ],
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


def project_context_block(project: Project, docs_path: str, plan_markdown: str | None = None, user_name: str | None = None) -> str:
    plan_section = f"\nCurrent approved plan:\n{plan_markdown}\n" if plan_markdown else ""
    return f"""Project: {project.name}
Workspace path: {project.workspace_path}
Project docs path: {docs_path}
Preferred user name: {user_name or project.created_by or "Operator"}
Primary goal: ship a usable MVP quickly without fake demos.
{plan_section}
"""


def worker_task_prompt(
    project: Project,
    agent: Agent,
    task: Task,
    docs_path: str,
    plan_markdown: str | None = None,
    context_pack_markdown: str | None = None,
) -> str:
    context = project_context_block(project, docs_path, plan_markdown)
    context_pack_section = f"\nRelevant context pack:\n{context_pack_markdown}\n" if context_pack_markdown else ""
    return f"""You are a Codex worker agent operating under Codex Mission Control.

Task ID: {task.id}
Agent name: {agent.name}
Agent role: {agent.role}

{context}
{context_pack_section}

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


def manager_message_prompt(project: Project, docs_path: str, user_message: str, user_name: str | None = None) -> str:
    return f"""You are the Manager AI for the project "{project.name}".

Project docs live at: {docs_path}
Call the user "{user_name or project.created_by or "Operator"}" unless they ask you to change that.

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
    user_name: str | None = None,
) -> str:
    context = project_context_block(project, docs_path, plan_markdown, user_name)
    return f"""You are the Manager AI for Codex Mission Control.

Action: {action}
Objective:
{objective}

{context}

Input payload:
{json.dumps(payload, indent=2, default=str)}

Response rules:
- Return only valid JSON.
- Do not wrap the JSON in markdown fences.
- Match this schema exactly:
{json.dumps(response_schema, indent=2, default=str)}

Manager priorities, in order:
1. Usability for the user
2. Speed of building
3. Quality
"""


def manager_interview_prompt(
    project: Project,
    *,
    action: str,
    objective: str,
    payload: dict,
    response_schema: dict,
    user_name: str | None = None,
) -> str:
    return f"""You are the Manager AI for Codex Mission Control.

Project: {project.name}
Project idea:
{project.idea}

Action: {action}
Objective:
{objective}

Preferred user name: {user_name or project.created_by or "Operator"}

Interview requirements:
- You are interviewing the user to gather project-specific requirements.
- Do not ask generic questions unless they are clearly relevant to this project.
- Use the project idea, current docs, tool availability, provider settings, prior answers, and known constraints.
- Ask the highest-impact unknowns first.
- Avoid asking about topics that are already answered or already confident enough.
- Every question must be multiple choice and materially affect implementation or handoff quality.
- Include "Not sure, recommend one" only when it genuinely helps unblock the user.
- Stop early when enough information exists to plan the project responsibly.
- Return only valid JSON matching the schema exactly.

Input payload:
{json.dumps(payload, indent=2, default=str)}

Response schema:
{json.dumps(response_schema, indent=2, default=str)}
"""


def manager_swarm_prompt(
    project: Project,
    *,
    payload: dict,
    response_schema: dict,
    user_name: str | None = None,
) -> str:
    return f"""You are the Manager AI for Codex Mission Control.

Project: {project.name}
Project idea:
{project.idea}

Preferred user name: {user_name or project.created_by or "Operator"}

You are producing an adaptive swarm plan for this specific project.

Swarm planning rules:
- Choose the largest useful swarm, not the largest possible swarm.
- More agents are not automatically better.
- Avoid spawning vague agents or multiple agents that will obviously fight over the same files.
- Use the project idea, docs, repo shape, interview understanding, runner/tool limits, and project preferences.
- Multiple agents from the same archetype are allowed only when they have distinct missions and path ownership.
- Documentation-heavy projects may use multiple docs specialists.
- High-quality projects should emphasize review, testing, and security.
- Massive codebases should assign subsystem or path ownership before aggressive parallel edits.
- If architecture is still unclear, bias toward planner, architect, and research help before broad implementation parallelism.
- Explain the strategy, coordination risk, path conflict risk, and likely bottlenecks.
- Return only valid JSON matching the schema exactly.

Input payload:
{json.dumps(payload, indent=2, default=str)}

Response schema:
{json.dumps(response_schema, indent=2, default=str)}
"""


def app_server_input_items(text: str) -> list[dict]:
    return [{"type": "text", "text": text}]


def docs_manifest_path(project: Project) -> Path:
    return Path(project.docs_path or "") / "MANIFEST.json"
