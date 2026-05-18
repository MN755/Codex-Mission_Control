from __future__ import annotations

import os
from contextlib import asynccontextmanager
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
from diagnostics import open_folder
from manager import service
from models import Agent, AgentRun, InterviewSession, PathReservation, Plan, Project, Task
from schemas import (
    ApprovalRequestRead,
    ApprovalResolveRequest,
    AgentActionResponse,
    AgentRead,
    AppStateRead,
    AppProfileRead,
    AppProfileUpdate,
    ApiKeyLoginRequest,
    AuthJobRead,
    AuthStateRead,
    ChatGptLoginRequest,
    CompleteFirstRunRequest,
    CodexStatusRead,
    ChangeRequestCreate,
    ChangeRequestRead,
    DiagnosticReportRead,
    DiagnosticReportListItemRead,
    DashboardSummaryRead,
    DocGenerationResponse,
    EventRead,
    HandoffListItemRead,
    InterviewAnswerRequest,
    InterviewQuestionAnswerRequest,
    InterviewQuestionRead,
    InterviewSessionRead,
    InterviewStartRequest,
    LogRead,
    ManagerWorkerDecision,
    ManagerMessageCreate,
    ManagerMessageRead,
    ManagerMessageRequest,
    ManagerQuestionAnswer,
    ManagerQuestionRead,
    ManagerQueueRead,
    OpenPathResponse,
    PlanApproveRequest,
    PlanRead,
    PlanGenerateRequest,
    ProjectActionRead,
    ProjectActionResolveRequest,
    ProjectCreate,
    ProjectRead,
    ProjectUnderstandingRead,
    ProjectUpdate,
    ProjectWorkspaceRead,
    ProjectSettingsRead,
    ProjectSettingsUpdate,
    ReservationRead,
    RunReportRequest,
    StartupCheckRequest,
    StartupRetryRequest,
    StartupStatusRead,
    SystemStatusRead,
    SkillRead,
    SwarmEventRead,
    SwarmPlanRead,
    SwarmPlanRequest,
    SwarmPlanReviseRequest,
    SwarmPreferencesRead,
    SwarmPreferencesUpdate,
    SwarmScaleRequest,
    SwarmSpawnResponse,
    TaskRead,
    TaskGenerationResponse,
    ToolCatalogItemRead,
    ToolPermissionRead,
    ToolPermissionUpdate,
    WorkspaceWidgetsUpdate,
    AgentArchetypeRead,
    WidgetAddRequest,
    WidgetDataResponseRead,
    WidgetDefinitionRead,
    WidgetInstanceCreate,
    WidgetInstanceRead,
    WidgetInstanceUpdate,
    WidgetSummaryRead,
)
from startup import startup_service
from task_board import can_assign_task


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Codex Mission Control Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def _serialize_interview(project: Project, session: InterviewSession) -> InterviewSessionRead:
    understanding = service.get_project_understanding(project)
    questions = [
        InterviewQuestionRead(
            id=question.id,
            project_id=question.project_id or session.project_id,
            index=question.index,
            question=question.question,
            why=question.why,
            category=question.category,
            impact=question.impact,
            options=question.options_json,
            allow_custom_answer=question.allow_custom_answer,
            selected_option_id=question.selected_option_id or question.selected_option,
            selected_text=question.selected_text,
            custom_answer=question.custom_answer,
            affects=question.affects_json or [],
            status=question.status,
            question_source=question.question_source,
            answered_at=question.answered_at,
            rationale=question.rationale,
            selected_option=question.selected_option_id or question.selected_option,
        )
        for question in sorted(session.questions, key=lambda item: item.index)
    ]
    return InterviewSessionRead(
        id=session.id,
        project_id=session.project_id,
        question_budget=session.question_budget,
        questions_asked=session.questions_asked,
        questions_remaining=max(session.question_budget - session.questions_asked, 0),
        manager_mode=session.manager_mode,
        stopped_early=session.stopped_early,
        stop_reason=session.stop_reason,
        confidence=dict(session.confidence_json or {}),
        understanding_summary=understanding["summary"],
        known_facts=dict(session.known_facts_json or {}),
        unknowns=dict(session.unknowns_json or {}),
        assumptions=list(understanding["assumptions_json"] or []),
        constraints=list(understanding["constraints_json"] or []),
        generation_sources=sorted({question.question_source for question in session.questions if question.question_source}),
        question_count=session.question_count,
        current_index=session.current_index,
        status=session.status,
        questions=questions,
    )


def _serialize_understanding(project: Project) -> ProjectUnderstandingRead:
    return ProjectUnderstandingRead(**service.get_project_understanding(project))


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
async def system_status(
    project_id: int | None = Query(default=None),
    provider: str | None = Query(default=None),
    provider_endpoint: str | None = Query(default=None),
    adapter_command: str | None = Query(default=None),
    adapter_arg: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SystemStatusRead:
    project = _get_project_or_404(db, project_id) if project_id is not None else None
    return SystemStatusRead(
        **(
            await service.get_system_status(
                db,
                project,
                provider_override=provider,
                provider_endpoint_override=provider_endpoint,
                adapter_command_override=adapter_command,
                adapter_args_override=adapter_arg,
            )
        )
    )


@app.get("/api/system/auth-state", response_model=AuthStateRead)
async def auth_state() -> AuthStateRead:
    status = service.auth_state()
    return AuthStateRead(**status)


@app.get("/api/profile", response_model=AppProfileRead)
def get_profile(db: Session = Depends(get_db)) -> AppProfileRead:
    return service.get_app_profile(db)


@app.put("/api/profile", response_model=AppProfileRead)
def update_profile(payload: AppProfileUpdate, db: Session = Depends(get_db)) -> AppProfileRead:
    return service.update_app_profile(db, payload)


@app.get("/api/startup/status", response_model=StartupStatusRead)
def get_startup_status(db: Session = Depends(get_db)) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.get_status(db))


@app.post("/api/startup/check", response_model=StartupStatusRead)
def run_startup_check(payload: StartupCheckRequest, db: Session = Depends(get_db)) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.run_checks(db, attempt_number=payload.attempt_number, include_optional_checks=payload.include_optional_checks))


@app.post("/api/startup/retry", response_model=StartupStatusRead)
def retry_startup(payload: StartupRetryRequest, db: Session = Depends(get_db)) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.retry(db, attempt_number=payload.attempt_number, failed_check=payload.failed_check, retry_mode=payload.retry_mode))


@app.post("/api/startup/complete-first-run", response_model=AppStateRead)
def complete_startup_first_run(payload: CompleteFirstRunRequest, db: Session = Depends(get_db)) -> AppStateRead:
    return startup_service.complete_first_run(db, payload)


@app.post("/api/startup/diagnostics", response_model=DiagnosticReportRead)
def startup_diagnostics(db: Session = Depends(get_db)) -> DiagnosticReportRead:
    return DiagnosticReportRead(**startup_service.run_diagnostics(db))


@app.post("/api/startup/open-diagnostics-folder", response_model=OpenPathResponse)
def open_diagnostics_folder(db: Session = Depends(get_db)) -> OpenPathResponse:
    status = startup_service.get_status(db)
    diagnostics_path = status.get("diagnostic_report_path")
    if diagnostics_path:
        from pathlib import Path

        target = str(Path(diagnostics_path).parent)
    else:
        report = startup_service.run_diagnostics(db)
        from pathlib import Path

        target = str(Path(report["path"]).parent)
    return OpenPathResponse(**open_folder(target))


@app.get("/api/system/codex-status", response_model=CodexStatusRead)
async def codex_status(
    project_id: int | None = Query(default=None),
    provider: str | None = Query(default=None),
    provider_endpoint: str | None = Query(default=None),
    adapter_command: str | None = Query(default=None),
    adapter_arg: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CodexStatusRead:
    project = _get_project_or_404(db, project_id) if project_id is not None else None
    return CodexStatusRead(
        **(
            await service.get_system_status(
                db,
                project,
                provider_override=provider,
                provider_endpoint_override=provider_endpoint,
                adapter_command_override=adapter_command,
                adapter_args_override=adapter_arg,
            )
        )
    )


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


@app.get("/api/projects/{project_id}/swarm/preferences", response_model=SwarmPreferencesRead)
def get_swarm_preferences(project_id: int, db: Session = Depends(get_db)) -> SwarmPreferencesRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPreferencesRead(**service.get_swarm_preferences(db, project))


@app.put("/api/projects/{project_id}/swarm/preferences", response_model=SwarmPreferencesRead)
def update_swarm_preferences(project_id: int, payload: SwarmPreferencesUpdate, db: Session = Depends(get_db)) -> SwarmPreferencesRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPreferencesRead(**service.update_swarm_preferences(db, project, payload))


@app.post("/api/projects/{project_id}/swarm/plan", response_model=SwarmPlanRead)
async def create_swarm_plan(project_id: int, payload: SwarmPlanRequest, db: Session = Depends(get_db)) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPlanRead(**(await service.create_swarm_plan(db, project, goal=payload.goal, milestone_id=payload.milestone_id)))


@app.get("/api/projects/{project_id}/swarm/plan", response_model=SwarmPlanRead | None)
def get_swarm_plan(project_id: int, db: Session = Depends(get_db)) -> SwarmPlanRead | None:
    project = _get_project_or_404(db, project_id)
    payload = service.get_swarm_plan(db, project)
    return SwarmPlanRead(**payload) if payload else None


@app.post("/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/approve", response_model=SwarmPlanRead)
def approve_swarm_plan(project_id: int, swarm_plan_id: int, db: Session = Depends(get_db)) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPlanRead(**service.approve_swarm_plan(db, project, swarm_plan_id))


@app.post("/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/revise", response_model=SwarmPlanRead)
async def revise_swarm_plan(project_id: int, swarm_plan_id: int, payload: SwarmPlanReviseRequest, db: Session = Depends(get_db)) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPlanRead(**(await service.revise_swarm_plan(db, project, swarm_plan_id, payload.note)))


@app.post("/api/projects/{project_id}/swarm/spawn", response_model=SwarmSpawnResponse)
def spawn_swarm_agents(project_id: int, db: Session = Depends(get_db)) -> SwarmSpawnResponse:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmSpawnResponse(**service.spawn_swarm_agents(db, project))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/swarm/scale", response_model=SwarmSpawnResponse)
async def scale_swarm(project_id: int, payload: SwarmScaleRequest, db: Session = Depends(get_db)) -> SwarmSpawnResponse:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmSpawnResponse(**(await service.scale_swarm(db, project, direction=payload.direction, reason=payload.reason, count=payload.count)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/swarm/events", response_model=list[SwarmEventRead])
def get_swarm_events(project_id: int, db: Session = Depends(get_db)) -> list[SwarmEventRead]:
    project = _get_project_or_404(db, project_id)
    return [SwarmEventRead(**item) for item in service.list_swarm_events(db, project)]


@app.get("/api/agent-archetypes", response_model=list[AgentArchetypeRead])
def get_agent_archetypes(db: Session = Depends(get_db)) -> list[AgentArchetypeRead]:
    return [AgentArchetypeRead(**item) for item in service.list_agent_archetypes(db)]


@app.get("/api/widgets/catalog", response_model=list[WidgetDefinitionRead])
def get_widget_catalog(scope: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[WidgetDefinitionRead]:
    return [WidgetDefinitionRead(**item) for item in service.list_widget_catalog(db, scope)]


@app.get("/api/widgets/instances", response_model=list[WidgetInstanceRead])
def get_widget_instances(scope: str = Query(...), db: Session = Depends(get_db)) -> list[WidgetInstanceRead]:
    if scope != "dashboard":
        raise HTTPException(status_code=400, detail="Only dashboard scope is supported on this route.")
    return [WidgetInstanceRead(**item) for item in service.list_dashboard_widget_instances(db)]


@app.get("/api/projects/{project_id}/widgets/instances", response_model=list[WidgetInstanceRead])
def get_project_widget_instances(project_id: int, db: Session = Depends(get_db)) -> list[WidgetInstanceRead]:
    project = _get_project_or_404(db, project_id)
    return [WidgetInstanceRead(**item) for item in service.list_project_widget_instances(db, project)]


@app.post("/api/widgets/instances", response_model=WidgetInstanceRead)
def create_widget_instance(payload: WidgetInstanceCreate, db: Session = Depends(get_db)) -> WidgetInstanceRead:
    project = _get_project_or_404(db, payload.project_id) if payload.project_id is not None else None
    try:
        return WidgetInstanceRead(
            **service.create_widget_instance(
                db,
                scope=payload.scope,
                project=project,
                widget_type=payload.widget_type,
                area=payload.area,
                size=payload.size,
                order_index=payload.order_index,
                collapsed=payload.collapsed,
                enabled=payload.enabled,
                config_json=payload.config_json,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/widgets/instances/{instance_id}", response_model=WidgetInstanceRead)
def patch_widget_instance(instance_id: int, payload: WidgetInstanceUpdate, db: Session = Depends(get_db)) -> WidgetInstanceRead:
    try:
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return WidgetInstanceRead(**service.update_widget_instance(db, instance_id, data))
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.delete("/api/widgets/instances/{instance_id}", status_code=204)
def delete_widget_instance(instance_id: int, db: Session = Depends(get_db)) -> None:
    try:
        service.delete_widget_instance(db, instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/widgets/instances/{instance_id}/data", response_model=WidgetDataResponseRead)
async def get_widget_instance_data(instance_id: int, db: Session = Depends(get_db)) -> WidgetDataResponseRead:
    try:
        return WidgetDataResponseRead(**(await service.get_widget_instance_data(db, instance_id)))
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/widgets/summary", response_model=WidgetSummaryRead)
async def get_project_widgets_summary(project_id: int, db: Session = Depends(get_db)) -> WidgetSummaryRead:
    project = _get_project_or_404(db, project_id)
    return WidgetSummaryRead(**(await service.get_project_widget_summary(db, project)))


@app.post("/api/dashboard/widgets/add", response_model=WidgetInstanceRead)
def add_dashboard_widget(payload: WidgetAddRequest, db: Session = Depends(get_db)) -> WidgetInstanceRead:
    try:
        return WidgetInstanceRead(**service.add_dashboard_widget(db, payload.widget_type, payload.area, payload.size))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/widgets/add", response_model=WidgetInstanceRead)
def add_project_widget(project_id: int, payload: WidgetAddRequest, db: Session = Depends(get_db)) -> WidgetInstanceRead:
    project = _get_project_or_404(db, project_id)
    try:
        return WidgetInstanceRead(**service.add_project_widget(db, project, payload.widget_type, payload.area, payload.size))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/change-requests", response_model=ChangeRequestRead)
def create_change_request(project_id: int, payload: ChangeRequestCreate, db: Session = Depends(get_db)) -> ChangeRequestRead:
    project = _get_project_or_404(db, project_id)
    try:
        return service.create_change_request(db, project, payload.request_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/dashboard/stream")
async def stream_dashboard(after_id: int | None = Query(default=None)) -> StreamingResponse:
    generator = service.events.stream_app(after_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/api/dashboard/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryRead:
    return DashboardSummaryRead(**(await service.get_dashboard_summary(db)))


@app.post("/api/projects", response_model=ProjectRead)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = service.create_project(
        db,
        name=payload.name,
        idea=payload.idea,
        workspace_path=payload.workspace_path,
        provider=payload.provider,
        runner_mode=payload.runner_mode,
        manager_mode=payload.manager_mode,
    )
    db.flush()
    db.refresh(project)
    return ProjectRead(**service._serialize_project_card(db, project))


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(include_archived: bool = Query(default=False), db: Session = Depends(get_db)) -> list[ProjectRead]:
    return [ProjectRead(**project) for project in service.list_projects(db, include_archived=include_archived)]


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, project))


@app.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    updated = service.update_project(db, project, name=payload.name, idea=payload.idea)
    return ProjectRead(**service._serialize_project_card(db, updated))


@app.post("/api/projects/{project_id}/open", response_model=ProjectRead)
def open_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    opened = service.open_project(db, project)
    return ProjectRead(**service._serialize_project_card(db, opened))


@app.post("/api/projects/{project_id}/pause", response_model=ProjectRead)
def pause_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.pause_project(db, project)))


@app.post("/api/projects/{project_id}/resume", response_model=ProjectRead)
def resume_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.resume_project(db, project)))


@app.post("/api/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.archive_project(db, project)))


@app.post("/api/projects/{project_id}/unarchive", response_model=ProjectRead)
def unarchive_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.unarchive_project(db, project)))


@app.post("/api/projects/{project_id}/pin", response_model=ProjectRead)
def pin_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.pin_project(db, project)))


@app.post("/api/projects/{project_id}/unpin", response_model=ProjectRead)
def unpin_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.unpin_project(db, project)))


@app.get("/api/projects/{project_id}/workspace", response_model=ProjectWorkspaceRead)
async def get_project_workspace(project_id: int, db: Session = Depends(get_db)) -> ProjectWorkspaceRead:
    project = _get_project_or_404(db, project_id)
    payload = await service.get_project_workspace(db, project)
    return ProjectWorkspaceRead(**payload)


@app.get("/api/projects/{project_id}/action", response_model=ProjectActionRead)
async def get_project_action(project_id: int, db: Session = Depends(get_db)) -> ProjectActionRead:
    project = _get_project_or_404(db, project_id)
    return ProjectActionRead(**(await service.get_project_action(db, project)))


@app.get("/api/projects/{project_id}/actions", response_model=list[ProjectActionRead])
async def get_project_actions(project_id: int, db: Session = Depends(get_db)) -> list[ProjectActionRead]:
    project = _get_project_or_404(db, project_id)
    return [ProjectActionRead(**item) for item in await service.list_project_actions(db, project)]


@app.post("/api/projects/{project_id}/actions/{action_id}/resolve")
def resolve_project_action(project_id: int, action_id: str, payload: ProjectActionResolveRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    project = _get_project_or_404(db, project_id)
    try:
        return service.resolve_project_action(
            db,
            project,
            action_id,
            decision=payload.decision,
            option_id=payload.option_id,
            selected_text=payload.selected_text,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/manager/messages", response_model=list[ManagerMessageRead])
def get_manager_messages(project_id: int, db: Session = Depends(get_db)) -> list[ManagerMessageRead]:
    project = _get_project_or_404(db, project_id)
    return [ManagerMessageRead(**item) for item in service.list_manager_messages(db, project)]


@app.post("/api/projects/{project_id}/manager/messages", response_model=ManagerMessageRead)
async def create_manager_message(project_id: int, payload: ManagerMessageCreate, db: Session = Depends(get_db)) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    result = await service.manager_message(db, project, payload.message)
    return ManagerMessageRead(**result["message"])


@app.post("/api/projects/{project_id}/manager/ask-next", response_model=ManagerMessageRead)
async def ask_manager_next(project_id: int, db: Session = Depends(get_db)) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    return ManagerMessageRead(**(await service.manager_ask_next(db, project)))


@app.post("/api/projects/{project_id}/manager/generate-update", response_model=ManagerMessageRead)
async def generate_manager_update(project_id: int, db: Session = Depends(get_db)) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    return ManagerMessageRead(**(await service.manager_generate_update(db, project)))


@app.get("/api/projects/{project_id}/questions/pending", response_model=list[ManagerQuestionRead])
def get_pending_questions(project_id: int, db: Session = Depends(get_db)) -> list[ManagerQuestionRead]:
    project = _get_project_or_404(db, project_id)
    return [ManagerQuestionRead(**item) for item in service.list_pending_questions(db, project)]


@app.post("/api/questions/{question_id}/answer", response_model=ManagerQuestionRead)
def answer_question(question_id: int, payload: ManagerQuestionAnswer, db: Session = Depends(get_db)) -> ManagerQuestionRead:
    try:
        question = service.answer_question(
            db,
            question_id,
            option_id=payload.option_id,
            selected_text=payload.selected_text,
            project_id=payload.project_id,
        )
        return ManagerQuestionRead(**service._serialize_question(question))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/questions/{question_id}/auto-decide", response_model=ManagerQuestionRead)
def auto_decide_question(question_id: int, db: Session = Depends(get_db)) -> ManagerQuestionRead:
    try:
        question = service.auto_decide_question(db, question_id)
        return ManagerQuestionRead(**service._serialize_question(question))
    except ValueError as exc:
        status_code = 400 if "High-impact" in str(exc) or "no selectable options" in str(exc).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/approvals/pending", response_model=list[ApprovalRequestRead])
def get_pending_approvals(project_id: int, db: Session = Depends(get_db)) -> list[ApprovalRequestRead]:
    project = _get_project_or_404(db, project_id)
    return [ApprovalRequestRead(**item) for item in service.list_pending_approvals(db, project)]


@app.post("/api/approvals/{approval_id}/approve-once", response_model=ApprovalRequestRead)
def approve_once(approval_id: int, payload: ApprovalResolveRequest, db: Session = Depends(get_db)) -> ApprovalRequestRead:
    try:
        approval = service.approve_once(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/deny", response_model=ApprovalRequestRead)
def deny_approval(approval_id: int, payload: ApprovalResolveRequest, db: Session = Depends(get_db)) -> ApprovalRequestRead:
    try:
        approval = service.deny_approval(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/allow-for-project", response_model=ApprovalRequestRead)
def allow_approval_for_project(approval_id: int, payload: ApprovalResolveRequest, db: Session = Depends(get_db)) -> ApprovalRequestRead:
    try:
        approval = service.allow_approval_for_project(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/manager/queue", response_model=ManagerQueueRead)
def get_manager_queue(project_id: int, db: Session = Depends(get_db)) -> ManagerQueueRead:
    project = _get_project_or_404(db, project_id)
    return ManagerQueueRead(**service.get_manager_queue(db, project))


@app.post("/api/projects/{project_id}/widgets", response_model=ProjectSettingsRead)
def update_project_widgets(project_id: int, payload: WorkspaceWidgetsUpdate, db: Session = Depends(get_db)) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    return service.update_workspace_widgets(db, project, payload.widgets)


@app.get("/api/handoffs", response_model=list[HandoffListItemRead])
def list_handoffs(db: Session = Depends(get_db)) -> list[HandoffListItemRead]:
    return [HandoffListItemRead(**item) for item in service.list_handoffs(db)]


@app.get("/api/projects/{project_id}/handoff", response_model=HandoffListItemRead)
def get_project_handoff(project_id: int, db: Session = Depends(get_db)) -> HandoffListItemRead:
    project = _get_project_or_404(db, project_id)
    return HandoffListItemRead(**service.get_project_handoff_summary(db, project))


@app.get("/api/diagnostics/reports", response_model=list[DiagnosticReportListItemRead])
def diagnostics_reports() -> list[DiagnosticReportListItemRead]:
    return [DiagnosticReportListItemRead(**item) for item in service.recent_diagnostic_reports()]


@app.get("/api/tools", response_model=list[ToolCatalogItemRead])
def get_tools(db: Session = Depends(get_db)) -> list[ToolCatalogItemRead]:
    return [ToolCatalogItemRead(**item) for item in service.get_tool_catalog(db)]


@app.put("/api/tools/{tool_id}/permission", response_model=ToolPermissionRead)
def update_tool_permission(tool_id: str, payload: ToolPermissionUpdate, db: Session = Depends(get_db)) -> ToolPermissionRead:
    try:
        return ToolPermissionRead(**service.update_tool_permission(db, tool_id, payload.permission_policy))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/skills", response_model=list[SkillRead])
async def get_skills(db: Session = Depends(get_db)) -> list[SkillRead]:
    return [SkillRead(**item) for item in await service.list_skills(db)]


@app.post("/api/projects/{project_id}/docs/generate", response_model=DocGenerationResponse)
async def generate_docs(project_id: int, db: Session = Depends(get_db)) -> DocGenerationResponse:
    project = _get_project_or_404(db, project_id)
    result = await service.generate_project_docs(db, project)
    return DocGenerationResponse(**result)


@app.post("/api/projects/{project_id}/interview/start", response_model=InterviewSessionRead)
async def start_interview(project_id: int, payload: InterviewStartRequest, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    session = await service.start_interview(db, project, payload.question_budget, payload.question_count)
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.get("/api/projects/{project_id}/interview", response_model=InterviewSessionRead | None)
def get_interview(project_id: int, db: Session = Depends(get_db)) -> InterviewSessionRead | None:
    project = _get_project_or_404(db, project_id)
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))
    return _serialize_interview(project, session) if session else None


@app.post("/api/projects/{project_id}/interview/generate-next", response_model=InterviewSessionRead)
async def generate_next_interview(project_id: int, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    try:
        session = await service.generate_next_interview(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.post("/api/interview/questions/{question_id}/answer", response_model=InterviewSessionRead)
def answer_interview_question(question_id: int, payload: InterviewQuestionAnswerRequest, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, payload.project_id)
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project.id).order_by(InterviewSession.id.desc()))
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    try:
        updated = service.answer_interview(
            db,
            session,
            question_id,
            payload.option_id,
            payload.selected_text,
            custom_answer=payload.custom_answer,
            project_id=payload.project_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    db.flush()
    db.refresh(updated)
    return _serialize_interview(project, updated)


@app.post("/api/projects/{project_id}/interview/answer", response_model=InterviewSessionRead)
def answer_interview(project_id: int, payload: InterviewAnswerRequest, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    try:
        updated = service.answer_interview(
            db,
            session,
            payload.question_id,
            payload.option_id,
            payload.selected_text,
            custom_answer=payload.custom_answer,
            project_id=project_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    db.flush()
    db.refresh(updated)
    return _serialize_interview(project, updated)


@app.post("/api/projects/{project_id}/interview/finish", response_model=InterviewSessionRead)
def finish_interview(project_id: int, db: Session = Depends(get_db)) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    try:
        session = service.finish_interview(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.get("/api/projects/{project_id}/understanding", response_model=ProjectUnderstandingRead)
def get_project_understanding(project_id: int, db: Session = Depends(get_db)) -> ProjectUnderstandingRead:
    project = _get_project_or_404(db, project_id)
    return _serialize_understanding(project)


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
def get_agents(project_id: int, db: Session = Depends(get_db)) -> list[AgentRead]:
    _get_project_or_404(db, project_id)
    return [AgentRead(**item) for item in service._sorted_workspace_agents(db, project_id)]


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
