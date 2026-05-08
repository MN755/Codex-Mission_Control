from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from codex_auth import auth_service
from config import frontend_dist_root
from db import get_db, init_db
from manager import service
from models import Agent, AgentRun, InterviewSession, PathReservation, Plan, Project, Task
from schemas import (
    AgentActionResponse,
    AgentRead,
    ApiKeyLoginRequest,
    AuthJobRead,
    AuthStateRead,
    ChatGptLoginRequest,
    CodexStatusRead,
    DocGenerationResponse,
    EventRead,
    InterviewAnswerRequest,
    InterviewQuestionRead,
    InterviewSessionRead,
    InterviewStartRequest,
    LogRead,
    ManagerWorkerDecision,
    ManagerMessageRequest,
    PlanApproveRequest,
    PlanRead,
    PlanGenerateRequest,
    ProjectCreate,
    ProjectRead,
    ProjectSettingsRead,
    ProjectSettingsUpdate,
    ReservationRead,
    RunReportRequest,
    SystemStatusRead,
    TaskRead,
    TaskGenerationResponse,
)
from task_board import can_assign_task


app = FastAPI(title="Codex Mission Control Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _get_project_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_agent_or_404(db: Session, agent_id: int) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _serialize_interview(session: InterviewSession) -> InterviewSessionRead:
    questions = [
        InterviewQuestionRead(
            id=question.id,
            index=question.index,
            question=question.question,
            options=question.options_json,
            selected_option=question.selected_option,
            selected_text=question.selected_text,
            rationale=question.rationale,
        )
        for question in sorted(session.questions, key=lambda item: item.index)
    ]
    return InterviewSessionRead(
        id=session.id,
        project_id=session.project_id,
        question_count=session.question_count,
        current_index=session.current_index,
        status=session.status,
        questions=questions,
    )


def _frontend_dist_dir() -> Path | None:
    candidates: list[Path] = []
    if os.environ.get("MISSION_CONTROL_FRONTEND_DIST"):
        candidates.append(Path(os.environ["MISSION_CONTROL_FRONTEND_DIST"]))
    candidates.append(frontend_dist_root())
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _frontend_file_for_path(requested_path: str) -> Path | None:
    dist_dir = _frontend_dist_dir()
    if dist_dir is None:
        return None
    normalized = requested_path.strip("/")
    if not normalized:
        index_path = dist_dir / "index.html"
        return index_path if index_path.exists() else None
    candidate = (dist_dir / normalized).resolve()
    dist_root = dist_dir.resolve()
    if str(candidate).startswith(str(dist_root)) and candidate.exists() and candidate.is_file():
        return candidate
    index_path = dist_dir / "index.html"
    return index_path if index_path.exists() else None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/system/status", response_model=SystemStatusRead)
async def system_status(project_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> SystemStatusRead:
    project = _get_project_or_404(db, project_id) if project_id is not None else None
    return SystemStatusRead(**(await service.get_system_status(db, project)))


@app.get("/api/system/auth-state", response_model=AuthStateRead)
async def auth_state() -> AuthStateRead:
    status = service.auth_state()
    return AuthStateRead(**status)


@app.get("/api/system/codex-status", response_model=CodexStatusRead)
async def codex_status(project_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> CodexStatusRead:
    project = _get_project_or_404(db, project_id) if project_id is not None else None
    return CodexStatusRead(**(await service.get_system_status(db, project)))


@app.post("/api/system/auth/login/chatgpt", response_model=AuthJobRead)
async def login_with_chatgpt(payload: ChatGptLoginRequest) -> AuthJobRead:
    job = await auth_service.start_chatgpt_login(device_auth=payload.device_auth)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/login/device", response_model=AuthJobRead)
async def login_with_device_code() -> AuthJobRead:
    job = await auth_service.start_chatgpt_login(device_auth=True)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/login/api-key", response_model=AuthJobRead)
async def login_with_api_key(payload: ApiKeyLoginRequest) -> AuthJobRead:
    job = await auth_service.start_api_key_login(payload.api_key)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/logout", response_model=AuthJobRead)
async def logout_codex() -> AuthJobRead:
    job = await auth_service.start_logout()
    return AuthJobRead(**auth_service.job_payload(job))


@app.get("/api/system/auth-jobs/{job_id}", response_model=AuthJobRead)
async def get_auth_job(job_id: str) -> AuthJobRead:
    job = auth_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Auth job not found")
    return AuthJobRead(**auth_service.job_payload(job))


@app.get("/api/settings", response_model=ProjectSettingsRead)
def get_settings(project_id: int = Query(...), db: Session = Depends(get_db)) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    return service._project_settings(db, project)


@app.put("/api/settings", response_model=ProjectSettingsRead)
def update_settings(payload: ProjectSettingsUpdate, project_id: int = Query(...), db: Session = Depends(get_db)) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    return service.update_settings(db, project, payload)


@app.post("/api/projects", response_model=ProjectRead)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = service.create_project(
        db,
        name=payload.name,
        idea=payload.idea,
        workspace_path=payload.workspace_path,
        runner_mode=payload.runner_mode,
        manager_mode=payload.manager_mode,
    )
    db.flush()
    db.refresh(project)
    return project


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.created_at.desc())))


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    return _get_project_or_404(db, project_id)


@app.post("/api/projects/{project_id}/docs/generate", response_model=DocGenerationResponse)
async def generate_docs(project_id: int, db: Session = Depends(get_db)) -> DocGenerationResponse:
    project = _get_project_or_404(db, project_id)
    result = await service.generate_project_docs(db, project)
    return DocGenerationResponse(**result)


@app.post("/api/projects/{project_id}/interview/start", response_model=InterviewSessionRead)
async def start_interview(project_id: int, payload: InterviewStartRequest, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    session = await service.start_interview(db, project, payload.question_count)
    db.flush()
    db.refresh(session)
    return _serialize_interview(session)


@app.get("/api/projects/{project_id}/interview", response_model=InterviewSessionRead | None)
def get_interview(project_id: int, db: Session = Depends(get_db)) -> InterviewSessionRead | None:
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))
    return _serialize_interview(session) if session else None


@app.post("/api/projects/{project_id}/interview/answer", response_model=InterviewSessionRead)
def answer_interview(project_id: int, payload: InterviewAnswerRequest, db: Session = Depends(get_db)) -> InterviewSessionRead:
    _get_project_or_404(db, project_id)
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    updated = service.answer_interview(db, session, payload.question_id, payload.option_id, payload.selected_text)
    db.flush()
    db.refresh(updated)
    return _serialize_interview(updated)


@app.post("/api/projects/{project_id}/plan/generate", response_model=PlanRead)
async def generate_plan(project_id: int, payload: PlanGenerateRequest, db: Session = Depends(get_db)) -> Plan:
    project = _get_project_or_404(db, project_id)
    plan = await service.generate_plan(db, project)
    db.flush()
    db.refresh(plan)
    return plan


@app.get("/api/projects/{project_id}/plan", response_model=PlanRead | None)
def get_plan(project_id: int, db: Session = Depends(get_db)) -> Plan | None:
    return db.scalar(select(Plan).where(Plan.project_id == project_id).order_by(Plan.version.desc()))


@app.post("/api/projects/{project_id}/plan/approve", response_model=PlanRead)
async def approve_plan(project_id: int, payload: PlanApproveRequest, db: Session = Depends(get_db)) -> Plan:
    project = _get_project_or_404(db, project_id)
    plan = await service.approve_plan(db, project, payload.action, payload.note)
    db.flush()
    db.refresh(plan)
    return plan


@app.get("/api/projects/{project_id}/agents", response_model=list[AgentRead])
def get_agents(project_id: int, db: Session = Depends(get_db)) -> list[Agent]:
    _get_project_or_404(db, project_id)
    return list(db.scalars(select(Agent).where(Agent.project_id == project_id).order_by(Agent.kind.desc(), Agent.id.asc())))


@app.get("/api/projects/{project_id}/reservations", response_model=list[ReservationRead])
def get_reservations(project_id: int, db: Session = Depends(get_db)) -> list[PathReservation]:
    _get_project_or_404(db, project_id)
    return service.list_reservations(db, project_id)


@app.post("/api/projects/{project_id}/agents/start", response_model=AgentActionResponse)
async def start_project_agents(project_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    await service.start_idle_agents(db, project)
    return AgentActionResponse(ok=True, message="Started idle agents where work was available.")


@app.post("/api/agents/{agent_id}/start", response_model=AgentActionResponse)
async def start_agent(agent_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    agent = _get_agent_or_404(db, agent_id)
    project = _get_project_or_404(db, agent.project_id)
    task = service._find_next_safe_task(db, project, agent)
    if task:
        run = await service.start_agent_task(db, project, agent, task)
        return AgentActionResponse(ok=True, message="Agent started.", run_id=run.id)
    await service.start_idle_agents(db, project)
    refreshed_task = service._find_next_safe_task(db, project, agent)
    if refreshed_task:
        run = await service.start_agent_task(db, project, agent, refreshed_task)
        return AgentActionResponse(ok=True, message="Agent started.", run_id=run.id)
    blocked_task = db.scalar(select(Task).where(Task.project_id == project.id, Task.status == "waiting_on_paths").order_by(Task.priority.asc()))
    if blocked_task:
        return AgentActionResponse(ok=False, message=f"Agent is waiting on path ownership: {blocked_task.waiting_reason or 'conflicting path reservation.'}")
    return AgentActionResponse(ok=False, message="No compatible task is available for this agent.")


@app.post("/api/agents/{agent_id}/stop", response_model=AgentActionResponse)
async def stop_agent(agent_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    agent = _get_agent_or_404(db, agent_id)
    await service.stop_agent(db, agent)
    return AgentActionResponse(ok=True, message="Agent stop requested.")


@app.post("/api/agents/{agent_id}/pause", response_model=AgentActionResponse)
async def pause_agent(agent_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    agent = _get_agent_or_404(db, agent_id)
    await service.pause_agent(db, agent)
    return AgentActionResponse(ok=True, message="Agent paused.")


@app.get("/api/agents/{agent_id}/logs", response_model=LogRead)
def get_agent_logs(agent_id: int, db: Session = Depends(get_db)) -> LogRead:
    agent = _get_agent_or_404(db, agent_id)
    path, content = service.read_logs(db, agent)
    return LogRead(agent_id=agent_id, logs_path=path, content=content)


@app.get("/api/projects/{project_id}/tasks", response_model=list[TaskRead])
def get_tasks(project_id: int, db: Session = Depends(get_db)) -> list[Task]:
    _get_project_or_404(db, project_id)
    return list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.priority.asc(), Task.id.asc())))


@app.post("/api/projects/{project_id}/tasks/generate", response_model=TaskGenerationResponse)
async def generate_tasks(project_id: int, db: Session = Depends(get_db)) -> TaskGenerationResponse:
    project = _get_project_or_404(db, project_id)
    tasks, manager_mode_used = await service.generate_tasks(db, project)
    return TaskGenerationResponse(count=len(tasks), manager_mode_used=manager_mode_used)


@app.post("/api/tasks/{task_id}/start", response_model=AgentActionResponse)
async def start_task(task_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    task = _get_task_or_404(db, task_id)
    project = _get_project_or_404(db, task.project_id)
    workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
    for agent in workers:
        if agent.status in {"idle", "waiting", "done", "stopped"} and service._agent_matches_task(agent, task):
            if not service._dependencies_met(db, task):
                return AgentActionResponse(ok=False, message="Task is waiting on dependencies.")
            if not can_assign_task(agent, task, workers, service._is_git_workspace(project)):
                task.status = "waiting_on_paths"
                task.waiting_reason = task.waiting_reason or "Another agent owns overlapping paths."
                return AgentActionResponse(ok=False, message=task.waiting_reason)
            run = await service.start_agent_task(db, project, agent, task)
            return AgentActionResponse(ok=True, message="Task started.", run_id=run.id)
    return AgentActionResponse(ok=False, message="No idle worker is available.")


@app.post("/api/tasks/{task_id}/complete", response_model=AgentActionResponse)
async def complete_task(task_id: int, db: Session = Depends(get_db)) -> AgentActionResponse:
    task = _get_task_or_404(db, task_id)
    task.status = "done"
    project = _get_project_or_404(db, task.project_id)
    await service._maybe_finalize_handoff(db, project)
    return AgentActionResponse(ok=True, message="Task marked done.")


@app.post("/api/runs/{run_id}/report", response_model=ManagerWorkerDecision)
async def submit_run_report(run_id: int, payload: RunReportRequest, db: Session = Depends(get_db)) -> ManagerWorkerDecision:
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return await service.ingest_worker_report(db, run, payload)


@app.get("/api/projects/{project_id}/events", response_model=list[EventRead])
def get_events(project_id: int, after_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> list[EventRead]:
    _get_project_or_404(db, project_id)
    return service.events.list_events(db, project_id, after_id)


@app.get("/api/projects/{project_id}/stream")
async def stream_events(project_id: int, after_id: int | None = Query(default=None), db: Session = Depends(get_db)) -> StreamingResponse:
    _get_project_or_404(db, project_id)
    generator = service.events.stream(project_id, after_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.post("/api/projects/{project_id}/manager/message")
async def manager_message(project_id: int, payload: ManagerMessageRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = _get_project_or_404(db, project_id)
    reply = await service.manager_message(db, project, payload.message)
    return {"reply": reply}


@app.post("/api/projects/{project_id}/manager/next-step", response_model=ManagerWorkerDecision)
async def manager_next_step(project_id: int, db: Session = Depends(get_db)) -> ManagerWorkerDecision:
    project = _get_project_or_404(db, project_id)
    return await service.manager_next_step(db, project)


@app.get("/", include_in_schema=False)
def frontend_root() -> FileResponse:
    file_path = _frontend_file_for_path("")
    if file_path is None:
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(file_path)


@app.get("/{path:path}", include_in_schema=False)
def frontend_path(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    file_path = _frontend_file_for_path(path)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(file_path)
