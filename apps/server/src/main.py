from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from bridge_messages import bridge_runtime_service
from capabilities import capability_service
from codex_auth import auth_service
from config import frontend_dist_root
from context_packs import context_pack_service
from db import get_db, init_db
from diagnostics import open_folder
from daemon_state import read_daemon_token
from imported_codebase import import_service
from intelligence import reputation_service, scope_creep_service
from manager import service
from plugin_health import mission_control_plugin_health
from models import Agent, AgentRun, InterviewSession, OrchestrationSession, PathReservation, PendingDecision, Plan, Project, Task
from orchestration import coordinator
from playbooks import playbook_service
from preferences import preference_service
from risk import risk_service
from security import security_service
from schemas import (
    ApprovalRequestRead,
    ApprovalAuditLogRead,
    ApprovalResolveRequest,
    AgentActionResponse,
    AgentExecutionTraceRead,
    AgentLoadRebalanceRead,
    AgentLoadSnapshotRead,
    AgentRead,
    AgentPerformanceRecordCreate,
    AgentPerformanceRecordRead,
    AgentReputationSummaryRead,
    AppStateRead,
    AppProfileRead,
    AppProfileUpdate,
    ApiKeyLoginRequest,
    AuthJobRead,
    AuthStateRead,
    CapabilityBenchmarkCreate,
    CapabilityBenchmarkRead,
    CapabilityMatrixEntryRead,
    ChatGptLoginRequest,
    CompleteFirstRunRequest,
    ConflictRecordRead,
    ConflictResolveRequest,
    CodexStatusRead,
    ChangeRequestCreate,
    ChangeRequestRead,
    ChangeRequestTriageRead,
    ChangeRequestUpdate,
    CodebaseMapRead,
    CodebaseUnderstandingRead,
    ContextPackBuildRequest,
    ContextPackRead,
    DiagnosticReportRead,
    DiagnosticReportListItemRead,
    DaemonStatusRead,
    DashboardSummaryRead,
    DocGenerationResponse,
    EvidenceBasedHandoffRead,
    EventDigestWindow,
    EventRead,
    HandoffEvidenceCreate,
    HandoffEvidenceRead,
    HandoffListItemRead,
    ImportFolderRequest,
    ImportFolderResponse,
    ImportInterviewChoiceRequest,
    ImportInterviewChoiceResponse,
    ImportedCodebaseRequest,
    ImportedCodebaseRequestRead,
    ImportedCodebaseSafetyRead,
    ImportedCodebaseSafetyUpdate,
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
    AgentInstructionsStatusRead,
    AgentsMdProposalRead,
    OpenPathResponse,
    OrchestrationAttachRead,
    OrchestrationAttachRequest,
    OrchestrationCreateRequest,
    OrchestrationEventRead,
    OrchestrationHandoffRead,
    OrchestrationSessionRead,
    OrchestrationStatusRead,
    PlanApproveRequest,
    PlanRead,
    PluginHealthSummaryRead,
    PlanGenerateRequest,
    PendingDecisionAnswerRequest,
    PendingDecisionAnswerResultRead,
    PendingDecisionRead,
    ProjectPlaybookApplyRequest,
    ProjectPlaybookRead,
    ProjectPlaybookSuggestionRead,
    ProjectActionRead,
    ProjectActionResolveRequest,
    ProjectCreate,
    ProjectHealthRead,
    ProjectRead,
    ProjectSnapshotCreate,
    ProjectSnapshotRead,
    ProjectTimelineEventCreate,
    ProjectTimelineEventRead,
    ProjectUnderstandingRead,
    ProjectUpdate,
    ProjectWorkspaceRead,
    ProjectSettingsRead,
    ProjectSettingsUpdate,
    RecoveryPlanCreate,
    RecoveryPlanRead,
    RecoveryPlanSelectRequest,
    ReservationRead,
    ResumeWorkspaceRead,
    ResumeWorkspaceRequest,
    ReviewGateCreate,
    ReviewGateRead,
    ReviewGateUpdate,
    RiskAssessRequest,
    RiskAssessmentRead,
    RunReportRequest,
    RunbookRead,
    RunbookUpdate,
    SnapshotRestorePlanRead,
    StartupCheckRequest,
    StartupRetryRequest,
    StartupStatusRead,
    SystemStatusRead,
    SafeModeStatusRead,
    SecurityPolicyRead,
    SecurityPolicyUpdate,
    SkillRead,
    ScopeChangeAnalyzeRequest,
    ScopeChangeResolveRequest,
    ScopeChangeSignalRead,
    SwarmEventRead,
    SwarmLaunchSimulationRead,
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
    TargetedCodebaseScanRequest,
    UserPreferenceRead,
    UserPreferenceUpsert,
    ValidationCoverageAreaRead,
    RiskRecordCreate,
    RiskRecordRead,
    RiskRecordUpdate,
    WorkspaceWidgetsUpdate,
    AgentArchetypeRead,
    WidgetAddRequest,
    WidgetDataResponseRead,
    WidgetDefinitionRead,
    WidgetInstanceCreate,
    WidgetInstanceRead,
    WidgetInstanceUpdate,
    WidgetSummaryRead,
    WritePermissionRequest,
    BridgeMessageRead,
)
from startup import startup_service
from task_board import can_assign_task
from simulation import simulation_service
from validation_coverage import validation_coverage_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    coordinator.on_startup()
    try:
        yield
    finally:
        await coordinator.on_shutdown()


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


def _get_orchestration_or_404(db: Session, orchestration_id: int) -> OrchestrationSession:
    session = db.get(OrchestrationSession, orchestration_id)
    if not session:
        raise HTTPException(status_code=404, detail="Orchestration session not found")
    return session


def _get_pending_decision_or_404(db: Session, decision_id: int) -> PendingDecision:
    decision = db.get(PendingDecision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Pending decision not found")
    return decision


def _require_bridge_token(request: Request) -> None:
    token = read_daemon_token()
    if not token:
        raise HTTPException(status_code=503, detail="Mission Control bridge token is not configured.")
    supplied = request.headers.get("X-Mission-Control-Token", "").strip()
    if supplied != token:
        raise HTTPException(status_code=401, detail="Missing or invalid Mission Control bridge token.")


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


@app.get("/api/plugin/health", response_model=PluginHealthSummaryRead)
async def get_plugin_health() -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.post("/api/plugin/health/check", response_model=PluginHealthSummaryRead)
async def check_plugin_health() -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.get("/api/daemon/status", response_model=DaemonStatusRead)
async def daemon_status(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> DaemonStatusRead:
    return DaemonStatusRead(**(await coordinator.daemon_status(db)))


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


@app.get("/api/capabilities/benchmarks", response_model=list[CapabilityBenchmarkRead])
def get_capability_benchmarks(db: Session = Depends(get_db)) -> list[CapabilityBenchmarkRead]:
    return [CapabilityBenchmarkRead.model_validate(item) for item in capability_service.list_benchmarks(db)]


@app.post("/api/capabilities/benchmarks", response_model=CapabilityBenchmarkRead)
def create_capability_benchmark(payload: CapabilityBenchmarkCreate, db: Session = Depends(get_db)) -> CapabilityBenchmarkRead:
    record = capability_service.record_benchmark(db, payload.model_dump())
    return CapabilityBenchmarkRead.model_validate(record)


@app.get("/api/capabilities/matrix", response_model=list[CapabilityMatrixEntryRead])
def get_capability_matrix(db: Session = Depends(get_db)) -> list[CapabilityMatrixEntryRead]:
    return [CapabilityMatrixEntryRead(**item) for item in capability_service.capability_matrix(db)]


@app.get("/api/agents/reputation", response_model=list[AgentReputationSummaryRead])
def get_agent_reputation(db: Session = Depends(get_db)) -> list[AgentReputationSummaryRead]:
    return [AgentReputationSummaryRead(**item) for item in reputation_service.summarize(db)]


@app.get("/api/projects/{project_id}/agents/reputation", response_model=list[AgentReputationSummaryRead])
def get_project_agent_reputation(project_id: int, db: Session = Depends(get_db)) -> list[AgentReputationSummaryRead]:
    project = _get_project_or_404(db, project_id)
    return [AgentReputationSummaryRead(**item) for item in reputation_service.summarize(db, project)]


@app.post("/api/agents/performance-record", response_model=AgentPerformanceRecordRead)
def create_agent_performance_record(payload: AgentPerformanceRecordCreate, db: Session = Depends(get_db)) -> AgentPerformanceRecordRead:
    record = reputation_service.record(db, payload.model_dump())
    return AgentPerformanceRecordRead.model_validate(record)


@app.get("/api/playbooks", response_model=list[ProjectPlaybookRead])
def get_playbooks(db: Session = Depends(get_db)) -> list[ProjectPlaybookRead]:
    return [ProjectPlaybookRead.model_validate(item) for item in playbook_service.list_playbooks(db)]


@app.get("/api/playbooks/{playbook_key}", response_model=ProjectPlaybookRead)
def get_playbook(playbook_key: str, db: Session = Depends(get_db)) -> ProjectPlaybookRead:
    playbook = playbook_service.get_playbook(db, playbook_key)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return ProjectPlaybookRead.model_validate(playbook)


@app.post("/api/projects/{project_id}/playbook/suggest", response_model=ProjectPlaybookSuggestionRead)
def suggest_project_playbook(project_id: int, db: Session = Depends(get_db)) -> ProjectPlaybookSuggestionRead:
    project = _get_project_or_404(db, project_id)
    payload = playbook_service.suggest_playbook(db, project, persist=True)
    return ProjectPlaybookSuggestionRead(
        project_id=payload["project_id"],
        playbook_key=payload["playbook_key"],
        status=payload["status"],
        why=payload["why"],
        playbook=ProjectPlaybookRead.model_validate(payload["playbook"]) if payload.get("playbook") else None,
    )


@app.post("/api/projects/{project_id}/playbook/apply", response_model=ProjectPlaybookSuggestionRead)
def apply_project_playbook(project_id: int, payload: ProjectPlaybookApplyRequest, db: Session = Depends(get_db)) -> ProjectPlaybookSuggestionRead:
    project = _get_project_or_404(db, project_id)
    try:
        result = playbook_service.apply_playbook(db, project, payload.playbook_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectPlaybookSuggestionRead(
        project_id=result["project_id"],
        playbook_key=result["playbook_key"],
        status=result["status"],
        why=result["why"],
        playbook=ProjectPlaybookRead.model_validate(result["playbook"]) if result.get("playbook") else None,
    )


@app.post("/api/projects/{project_id}/context-packs/build", response_model=ContextPackRead)
def build_context_pack(project_id: int, payload: ContextPackBuildRequest, db: Session = Depends(get_db)) -> ContextPackRead:
    project = _get_project_or_404(db, project_id)
    pack = context_pack_service.build_context_pack(
        db,
        project,
        agent_id=payload.agent_id,
        task_id=payload.task_id,
        title=payload.title,
        goal=payload.goal,
        token_budget_hint=payload.token_budget_hint,
    )
    return ContextPackRead(**pack)


@app.get("/api/projects/{project_id}/context-packs", response_model=list[ContextPackRead])
def list_context_packs(project_id: int, db: Session = Depends(get_db)) -> list[ContextPackRead]:
    project = _get_project_or_404(db, project_id)
    return [ContextPackRead(**item) for item in context_pack_service.list_context_packs(db, project)]


@app.get("/api/context-packs/{context_pack_id}", response_model=ContextPackRead)
def get_context_pack(context_pack_id: int, db: Session = Depends(get_db)) -> ContextPackRead:
    try:
        return ContextPackRead(**context_pack_service.get_context_pack(db, context_pack_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/risks", response_model=list[RiskRecordRead])
def get_project_risks(project_id: int, db: Session = Depends(get_db)) -> list[RiskRecordRead]:
    project = _get_project_or_404(db, project_id)
    return [RiskRecordRead.model_validate(item) for item in risk_service.list_risks(db, project)]


@app.post("/api/projects/{project_id}/risks", response_model=RiskRecordRead)
def create_project_risk(project_id: int, payload: RiskRecordCreate, db: Session = Depends(get_db)) -> RiskRecordRead:
    project = _get_project_or_404(db, project_id)
    return RiskRecordRead.model_validate(risk_service.create_risk(db, project, payload.model_dump()))


@app.patch("/api/risks/{risk_id}", response_model=RiskRecordRead)
def update_project_risk(risk_id: int, payload: RiskRecordUpdate, db: Session = Depends(get_db)) -> RiskRecordRead:
    try:
        return RiskRecordRead.model_validate(risk_service.update_risk(db, risk_id, payload.model_dump(exclude_none=True)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/scope-creep", response_model=list[ScopeChangeSignalRead])
def get_scope_creep(project_id: int, db: Session = Depends(get_db)) -> list[ScopeChangeSignalRead]:
    project = _get_project_or_404(db, project_id)
    return [ScopeChangeSignalRead.model_validate(item) for item in scope_creep_service.list_signals(db, project)]


@app.post("/api/projects/{project_id}/scope-creep/analyze", response_model=list[ScopeChangeSignalRead])
def analyze_scope_creep(project_id: int, payload: ScopeChangeAnalyzeRequest, db: Session = Depends(get_db)) -> list[ScopeChangeSignalRead]:
    project = _get_project_or_404(db, project_id)
    return [ScopeChangeSignalRead.model_validate(item) for item in scope_creep_service.analyze(db, project, payload.model_dump())]


@app.post("/api/scope-creep/{signal_id}/resolve", response_model=ScopeChangeSignalRead)
def resolve_scope_creep(signal_id: int, payload: ScopeChangeResolveRequest, db: Session = Depends(get_db)) -> ScopeChangeSignalRead:
    try:
        return ScopeChangeSignalRead.model_validate(scope_creep_service.resolve(db, signal_id, payload.status))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/swarm/simulate-launch", response_model=SwarmLaunchSimulationRead)
def simulate_swarm_launch(project_id: int, db: Session = Depends(get_db)) -> SwarmLaunchSimulationRead:
    project = _get_project_or_404(db, project_id)
    return SwarmLaunchSimulationRead.model_validate(simulation_service.simulate_launch(db, project))


@app.get("/api/projects/{project_id}/swarm/simulations", response_model=list[SwarmLaunchSimulationRead])
def list_swarm_simulations(project_id: int, db: Session = Depends(get_db)) -> list[SwarmLaunchSimulationRead]:
    project = _get_project_or_404(db, project_id)
    return [SwarmLaunchSimulationRead.model_validate(item) for item in simulation_service.list_simulations(db, project)]


@app.get("/api/projects/{project_id}/validation-coverage", response_model=list[ValidationCoverageAreaRead])
def get_validation_coverage(project_id: int, db: Session = Depends(get_db)) -> list[ValidationCoverageAreaRead]:
    project = _get_project_or_404(db, project_id)
    coverage = validation_coverage_service.list_coverage(db, project) or validation_coverage_service.recompute(db, project)
    return [ValidationCoverageAreaRead.model_validate(item) for item in coverage]


@app.post("/api/projects/{project_id}/validation-coverage/recompute", response_model=list[ValidationCoverageAreaRead])
def recompute_validation_coverage(project_id: int, db: Session = Depends(get_db)) -> list[ValidationCoverageAreaRead]:
    project = _get_project_or_404(db, project_id)
    return [ValidationCoverageAreaRead.model_validate(item) for item in validation_coverage_service.recompute(db, project)]


@app.get("/api/preferences", response_model=list[UserPreferenceRead])
def get_preferences(db: Session = Depends(get_db)) -> list[UserPreferenceRead]:
    return [UserPreferenceRead.model_validate(item) for item in preference_service.list_preferences(db, project_id=None)]


@app.put("/api/preferences/{key}", response_model=UserPreferenceRead)
def put_preference(key: str, payload: UserPreferenceUpsert, db: Session = Depends(get_db)) -> UserPreferenceRead:
    record = preference_service.upsert_preference(
        db,
        key=key,
        value_json=payload.value_json,
        source=payload.source,
        editable=payload.editable,
        project_id=None,
    )
    return UserPreferenceRead.model_validate(record)


@app.get("/api/projects/{project_id}/preferences", response_model=list[UserPreferenceRead])
def get_project_preferences(project_id: int, db: Session = Depends(get_db)) -> list[UserPreferenceRead]:
    project = _get_project_or_404(db, project_id)
    return [UserPreferenceRead.model_validate(item) for item in preference_service.get_effective_preferences(db, project)]


@app.put("/api/projects/{project_id}/preferences/{key}", response_model=UserPreferenceRead)
def put_project_preference(project_id: int, key: str, payload: UserPreferenceUpsert, db: Session = Depends(get_db)) -> UserPreferenceRead:
    _get_project_or_404(db, project_id)
    record = preference_service.upsert_preference(
        db,
        key=key,
        value_json=payload.value_json,
        source=payload.source,
        editable=payload.editable,
        project_id=project_id,
    )
    return UserPreferenceRead.model_validate(record)


@app.get("/api/security/policy", response_model=SecurityPolicyRead)
def get_security_policy(db: Session = Depends(get_db)) -> SecurityPolicyRead:
    return SecurityPolicyRead.model_validate(security_service.get_policy(db))


@app.put("/api/security/policy", response_model=SecurityPolicyRead)
def put_security_policy(payload: SecurityPolicyUpdate, db: Session = Depends(get_db)) -> SecurityPolicyRead:
    record = security_service.update_policy(db, payload.model_dump())
    return SecurityPolicyRead.model_validate(record)


@app.get("/api/projects/{project_id}/security/policy", response_model=SecurityPolicyRead)
def get_project_security_policy(project_id: int, db: Session = Depends(get_db)) -> SecurityPolicyRead:
    project = _get_project_or_404(db, project_id)
    return SecurityPolicyRead.model_validate(security_service.get_policy(db, project=project))


@app.put("/api/projects/{project_id}/security/policy", response_model=SecurityPolicyRead)
def put_project_security_policy(project_id: int, payload: SecurityPolicyUpdate, db: Session = Depends(get_db)) -> SecurityPolicyRead:
    project = _get_project_or_404(db, project_id)
    record = security_service.update_policy(db, payload.model_dump(), project=project)
    return SecurityPolicyRead.model_validate(record)


@app.post("/api/security/risk-assess", response_model=RiskAssessmentRead)
def assess_security_risk(payload: RiskAssessRequest, db: Session = Depends(get_db)) -> RiskAssessmentRead:
    project = _get_project_or_404(db, payload.project_id) if payload.project_id is not None else None
    record = security_service.assess_risk(db, payload.model_dump(), project=project)
    return RiskAssessmentRead.model_validate(record)


@app.get("/api/security/audit-log", response_model=list[ApprovalAuditLogRead])
def get_security_audit_log(db: Session = Depends(get_db)) -> list[ApprovalAuditLogRead]:
    return [ApprovalAuditLogRead.model_validate(item) for item in security_service.list_audit_logs(db)]


@app.get("/api/projects/{project_id}/security/audit-log", response_model=list[ApprovalAuditLogRead])
def get_project_security_audit_log(project_id: int, db: Session = Depends(get_db)) -> list[ApprovalAuditLogRead]:
    project = _get_project_or_404(db, project_id)
    return [ApprovalAuditLogRead.model_validate(item) for item in security_service.list_audit_logs(db, project=project)]


@app.get("/api/dashboard/stream")
async def stream_dashboard(after_id: int | None = Query(default=None)) -> StreamingResponse:
    generator = service.events.stream_app(after_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/api/dashboard/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryRead:
    return DashboardSummaryRead(**(await service.get_dashboard_summary(db)))


@app.post("/api/orchestrations/attach-workspace", response_model=OrchestrationAttachRead)
def attach_workspace(
    payload: OrchestrationAttachRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationAttachRead:
    try:
        attached = coordinator.attach_workspace(
            db,
            workspace_path=payload.workspace_path,
            project_name=payload.project_name,
            mode=payload.mode,
            read_only_first=payload.read_only_first,
            attach_policy=payload.attach_policy,
            source="codex_plugin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrchestrationAttachRead(**attached)


@app.post("/api/orchestrations", response_model=OrchestrationSessionRead)
async def create_orchestration(
    payload: OrchestrationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    project = _get_project_or_404(db, payload.project_id)
    try:
        session = coordinator.start_orchestration(
            db,
            project=project,
            source=payload.source,
            user_request=payload.user_request,
            orchestration_id=payload.orchestration_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


@app.get("/api/orchestrations/plugin-health", response_model=PluginHealthSummaryRead)
async def get_bridge_plugin_health(
    request: Request,
    _: None = Depends(_require_bridge_token),
) -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.get("/api/orchestrations/{orchestration_id}", response_model=OrchestrationSessionRead)
def get_orchestration(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    return OrchestrationSessionRead(**coordinator._serialize_session(_get_orchestration_or_404(db, orchestration_id)))


@app.get("/api/projects/{project_id}/orchestrations/active", response_model=OrchestrationSessionRead | None)
def get_active_project_orchestration(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead | None:
    project = _get_project_or_404(db, project_id)
    session = coordinator.get_active_session_for_project(db, project)
    return OrchestrationSessionRead(**coordinator._serialize_session(session)) if session else None


@app.get("/api/orchestrations/{orchestration_id}/status", response_model=OrchestrationStatusRead)
async def get_orchestration_status(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationStatusRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    return OrchestrationStatusRead(**(await coordinator.get_status(db, session)))


@app.post("/api/orchestrations/{orchestration_id}/pause", response_model=OrchestrationSessionRead)
def pause_orchestration(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    session = coordinator.pause_orchestration(db, _get_orchestration_or_404(db, orchestration_id))
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


@app.post("/api/orchestrations/{orchestration_id}/resume", response_model=OrchestrationSessionRead)
async def resume_orchestration(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    try:
        session = coordinator.resume_orchestration(db, _get_orchestration_or_404(db, orchestration_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


@app.get("/api/orchestrations/{orchestration_id}/events", response_model=list[OrchestrationEventRead])
def get_orchestration_events(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[OrchestrationEventRead]:
    session = _get_orchestration_or_404(db, orchestration_id)
    return [OrchestrationEventRead(**event) for event in coordinator.list_events(db, session)]


@app.get("/api/orchestrations/{orchestration_id}/handoff", response_model=OrchestrationHandoffRead)
def get_orchestration_handoff(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationHandoffRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    return OrchestrationHandoffRead(**coordinator.get_handoff(db, session))


@app.get("/api/orchestrations/{orchestration_id}/pending-decisions", response_model=list[PendingDecisionRead])
def get_orchestration_pending_decisions(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[PendingDecisionRead]:
    session = _get_orchestration_or_404(db, orchestration_id)
    project = _get_project_or_404(db, session.project_id)
    return [PendingDecisionRead(**item) for item in bridge_runtime_service.get_pending_decisions(db, project=project, orchestration=session)]


@app.get("/api/projects/{project_id}/pending-decisions", response_model=list[PendingDecisionRead])
def get_project_pending_decisions(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[PendingDecisionRead]:
    project = _get_project_or_404(db, project_id)
    return [PendingDecisionRead(**item) for item in bridge_runtime_service.get_pending_decisions(db, project=project)]


@app.get("/api/decisions/{decision_id}/bridge-message", response_model=BridgeMessageRead)
def get_decision_bridge_message(
    decision_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    decision = _get_pending_decision_or_404(db, decision_id)
    return BridgeMessageRead(**bridge_runtime_service.get_bridge_message_for_decision(db, decision))


@app.post("/api/decisions/{decision_id}/answer", response_model=PendingDecisionAnswerResultRead)
async def answer_pending_decision(
    decision_id: int,
    payload: PendingDecisionAnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> PendingDecisionAnswerResultRead:
    decision = _get_pending_decision_or_404(db, decision_id)
    try:
        updated, next_summary = await bridge_runtime_service.answer_decision(
            db,
            decision,
            option_id=payload.option_id,
            selected_text=payload.selected_text,
            free_text=payload.free_text,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return PendingDecisionAnswerResultRead(
        decision=PendingDecisionRead(**updated),
        next_status_summary=BridgeMessageRead(**next_summary) if next_summary else None,
    )


@app.get("/api/orchestrations/{orchestration_id}/status-summary", response_model=BridgeMessageRead)
async def get_orchestration_status_summary(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    project = _get_project_or_404(db, session.project_id)
    return BridgeMessageRead(**(await bridge_runtime_service.get_status_summary(db, project=project, orchestration=session)))


@app.get("/api/projects/{project_id}/status-summary", response_model=BridgeMessageRead)
async def get_project_status_summary(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    project = _get_project_or_404(db, project_id)
    return BridgeMessageRead(**(await bridge_runtime_service.get_status_summary(db, project=project)))


@app.get("/api/orchestrations/{orchestration_id}/event-digest", response_model=BridgeMessageRead)
def get_orchestration_event_digest(
    orchestration_id: int,
    request: Request,
    window: EventDigestWindow = Query(default="last_15_minutes"),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    project = _get_project_or_404(db, session.project_id)
    return BridgeMessageRead(**bridge_runtime_service.get_event_digest(db, project=project, orchestration=session, window=window))


@app.get("/api/projects/{project_id}/event-digest", response_model=BridgeMessageRead)
def get_project_event_digest(
    project_id: int,
    request: Request,
    window: EventDigestWindow = Query(default="last_15_minutes"),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    project = _get_project_or_404(db, project_id)
    return BridgeMessageRead(**bridge_runtime_service.get_event_digest(db, project=project, window=window))


@app.get("/api/orchestrations/{orchestration_id}/handoff-summary", response_model=BridgeMessageRead)
def get_orchestration_handoff_summary(
    orchestration_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    project = _get_project_or_404(db, session.project_id)
    return BridgeMessageRead(**bridge_runtime_service.get_handoff_summary(db, project=project, orchestration=session))


@app.get("/api/projects/{project_id}/handoff-summary", response_model=BridgeMessageRead)
def get_project_handoff_summary(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    project = _get_project_or_404(db, project_id)
    return BridgeMessageRead(**bridge_runtime_service.get_handoff_summary(db, project=project))


@app.get("/api/projects/{project_id}/safe-mode", response_model=SafeModeStatusRead)
def get_project_safe_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SafeModeStatusRead:
    project = _get_project_or_404(db, project_id)
    return SafeModeStatusRead(**bridge_runtime_service.get_safe_mode(db, project=project))


@app.post("/api/projects/{project_id}/safe-mode", response_model=SafeModeStatusRead)
def enable_project_safe_mode(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SafeModeStatusRead:
    project = _get_project_or_404(db, project_id)
    return SafeModeStatusRead(**bridge_runtime_service.enable_safe_mode(db, project=project))


@app.post("/api/mission-control/resume-workspace", response_model=ResumeWorkspaceRead)
async def resume_workspace(
    payload: ResumeWorkspaceRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ResumeWorkspaceRead:
    try:
        result = await bridge_runtime_service.resume_workspace(
            db,
            workspace_path=payload.workspace_path,
            attach_policy=payload.attach_policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ResumeWorkspaceRead(**result)


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


@app.post("/api/projects/import-folder", response_model=ImportFolderResponse)
def import_existing_folder(payload: ImportFolderRequest, db: Session = Depends(get_db)) -> ImportFolderResponse:
    folder = Path(payload.folder_path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=400, detail="Folder path does not exist or is not a directory.")
    project_name = payload.name.strip() if payload.name and payload.name.strip() else folder.name
    project = service.create_project(
        db,
        name=project_name,
        idea=f"Imported existing codebase from {folder}.",
        workspace_path=str(folder),
        provider="codex",
        runner_mode="dry_run",
        manager_mode="deterministic",
    )
    import_service.configure_imported_project(db, project, folder_path=str(folder), import_mode=payload.import_mode)
    service.events.publish(db, project.id, "project_import_started", {"project_id": project.id, "source_path": str(folder)})
    warnings: list[str] = []
    if payload.start_read_only_scan:
        service.events.publish(db, project.id, "codebase_scan_started", {"project_id": project.id, "scan_depth": "initial"})
        codebase_map, understanding, agents_status, safety = import_service.initial_scan(db, project)
        service.events.publish(
            db,
            project.id,
            "codebase_scan_completed",
            {"project_id": project.id, "scan_depth": codebase_map.scan_depth, "codebase_size": codebase_map.codebase_size},
        )
        service.events.publish(
            db,
            project.id,
            "codebase_understanding_created",
            {"project_id": project.id, "generation_mode": understanding.generation_mode, "recommended_interview_mode": understanding.recommended_interview_mode},
        )
        service.events.publish(
            db,
            project.id,
            "agents_md_detected",
            {"project_id": project.id, "has_agents_md": agents_status.has_agents_md, "recommended_action": agents_status.recommended_action},
        )
        service.events.publish(
            db,
            project.id,
            "import_safety_updated",
            {"project_id": project.id, "write_permission_status": safety.write_permission_status},
        )
        service.events.publish(
            db,
            project.id,
            "scan_coverage_updated",
            {
                "project_id": project.id,
                "scan_depth": codebase_map.scan_depth,
                "indexed_areas": codebase_map.indexed_areas_json,
                "unindexed_areas": codebase_map.unindexed_areas_json,
            },
        )
        if codebase_map.codebase_size in {"large", "huge"}:
            warnings.append("This codebase is large. Progressive understanding is active, so deeper scan should be targeted.")
    db.flush()
    db.refresh(project)
    return ImportFolderResponse(
        project=ProjectRead(**service._serialize_project_card(db, project)),
        scan_started=payload.start_read_only_scan,
        warnings=warnings,
        recommended_next_route=f"/projects/{project.id}/import/review",
    )


@app.get("/api/projects", response_model=list[ProjectRead])
def list_projects(include_archived: bool = Query(default=False), db: Session = Depends(get_db)) -> list[ProjectRead]:
    return [ProjectRead(**project) for project in service.list_projects(db, include_archived=include_archived)]


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, project))


@app.post("/api/projects/{project_id}/scan-codebase", response_model=CodebaseMapRead)
def scan_codebase(project_id: int, db: Session = Depends(get_db)) -> CodebaseMapRead:
    project = _get_project_or_404(db, project_id)
    service.events.publish(db, project.id, "codebase_scan_started", {"project_id": project.id, "scan_depth": "standard"})
    codebase_map, understanding, agents_status, safety = import_service.scan_codebase(db, project, depth="standard")
    service.events.publish(
        db,
        project.id,
        "codebase_scan_completed",
        {"project_id": project.id, "scan_depth": codebase_map.scan_depth, "codebase_size": codebase_map.codebase_size},
    )
    service.events.publish(
        db,
        project.id,
        "codebase_understanding_created",
        {"project_id": project.id, "generation_mode": understanding.generation_mode, "recommended_interview_mode": understanding.recommended_interview_mode},
    )
    service.events.publish(
        db,
        project.id,
        "agents_md_detected",
        {"project_id": project.id, "has_agents_md": agents_status.has_agents_md, "recommended_action": agents_status.recommended_action},
    )
    service.events.publish(
        db,
        project.id,
        "import_safety_updated",
        {"project_id": project.id, "write_permission_status": safety.write_permission_status},
    )
    service.events.publish(
        db,
        project.id,
        "scan_coverage_updated",
        {"project_id": project.id, "indexed_areas": codebase_map.indexed_areas_json, "unindexed_areas": codebase_map.unindexed_areas_json},
    )
    return CodebaseMapRead.model_validate(codebase_map)


@app.post("/api/projects/{project_id}/scan-codebase/targeted", response_model=CodebaseMapRead)
def scan_codebase_targeted(project_id: int, payload: TargetedCodebaseScanRequest, db: Session = Depends(get_db)) -> CodebaseMapRead:
    project = _get_project_or_404(db, project_id)
    service.events.publish(db, project.id, "codebase_scan_started", {"project_id": project.id, "scan_depth": "targeted", "targets": payload.target_paths or []})
    codebase_map, _understanding, _agents_status, _safety = import_service.targeted_scan(
        db,
        project,
        target_paths=payload.target_paths,
        request_text=payload.request_text,
        scan_reason=payload.scan_reason,
    )
    service.events.publish(
        db,
        project.id,
        "targeted_scan_completed",
        {"project_id": project.id, "targets": payload.target_paths or [], "scan_depth": codebase_map.scan_depth},
    )
    service.events.publish(
        db,
        project.id,
        "scan_coverage_updated",
        {"project_id": project.id, "indexed_areas": codebase_map.indexed_areas_json, "unindexed_areas": codebase_map.unindexed_areas_json},
    )
    return CodebaseMapRead.model_validate(codebase_map)


@app.get("/api/projects/{project_id}/codebase-map", response_model=CodebaseMapRead)
def get_codebase_map(project_id: int, db: Session = Depends(get_db)) -> CodebaseMapRead:
    project = _get_project_or_404(db, project_id)
    return CodebaseMapRead.model_validate(import_service.get_codebase_map(db, project))


@app.get("/api/projects/{project_id}/codebase-understanding", response_model=CodebaseUnderstandingRead)
def get_codebase_understanding(project_id: int, db: Session = Depends(get_db)) -> CodebaseUnderstandingRead:
    project = _get_project_or_404(db, project_id)
    return CodebaseUnderstandingRead.model_validate(import_service.get_codebase_understanding(db, project))


@app.post("/api/projects/{project_id}/import/interview-choice", response_model=ImportInterviewChoiceResponse)
def choose_import_interview(project_id: int, payload: ImportInterviewChoiceRequest, db: Session = Depends(get_db)) -> ImportInterviewChoiceResponse:
    project = _get_project_or_404(db, project_id)
    next_route, questions, manager_note = import_service.choose_interview_mode(db, project, choice=payload.choice)
    return ImportInterviewChoiceResponse(
        next_route=next_route,
        questions=[
            InterviewQuestionRead(
                id=question.id,
                project_id=question.project_id or project.id,
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
            for question in questions
        ],
        manager_note=manager_note,
    )


@app.get("/api/projects/{project_id}/import-safety", response_model=ImportedCodebaseSafetyRead)
def get_import_safety(project_id: int, db: Session = Depends(get_db)) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    return ImportedCodebaseSafetyRead.model_validate(import_service.ensure_safety(db, project))


@app.patch("/api/projects/{project_id}/import-safety", response_model=ImportedCodebaseSafetyRead)
def patch_import_safety(project_id: int, payload: ImportedCodebaseSafetyUpdate, db: Session = Depends(get_db)) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    safety = import_service.update_safety(db, project, payload.model_dump(exclude_unset=True))
    service.events.publish(db, project.id, "import_safety_updated", {"project_id": project.id, "write_permission_status": safety.write_permission_status})
    return ImportedCodebaseSafetyRead.model_validate(safety)


@app.post("/api/projects/{project_id}/write-permission", response_model=ImportedCodebaseSafetyRead)
def update_write_permission(project_id: int, payload: WritePermissionRequest, db: Session = Depends(get_db)) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    safety = import_service.update_safety(db, project, {"write_permission_status": payload.write_permission_status})
    service.events.publish(db, project.id, "write_permission_updated", {"project_id": project.id, "write_permission_status": payload.write_permission_status})
    return ImportedCodebaseSafetyRead.model_validate(safety)


@app.get("/api/projects/{project_id}/agents-md/status", response_model=AgentInstructionsStatusRead)
def get_agents_md_status(project_id: int, db: Session = Depends(get_db)) -> AgentInstructionsStatusRead:
    project = _get_project_or_404(db, project_id)
    return AgentInstructionsStatusRead.model_validate(import_service.get_agents_status(db, project))


@app.post("/api/projects/{project_id}/agents-md/propose", response_model=AgentsMdProposalRead)
def propose_agents_md(project_id: int, db: Session = Depends(get_db)) -> AgentsMdProposalRead:
    project = _get_project_or_404(db, project_id)
    return AgentsMdProposalRead(**import_service.propose_agents_md(db, project))


@app.post("/api/projects/{project_id}/manager/imported-codebase-request", response_model=ImportedCodebaseRequestRead)
def imported_codebase_request(project_id: int, payload: ImportedCodebaseRequest, db: Session = Depends(get_db)) -> ImportedCodebaseRequestRead:
    project = _get_project_or_404(db, project_id)
    return ImportedCodebaseRequestRead(**import_service.analyze_manager_request(db, project, message=payload.message))


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
        status_code = 400 if "cannot be allowed for the whole project" in str(exc).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


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
