from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from bridge_messages import bridge_runtime_service
from bootstrap.runner_autowire import autowire_headless, get_headless_config, get_headless_health, repair_headless
from bootstrap.runner_probe import summarize_runner_status
from capabilities import capability_service
from codex_auth import auth_service
from config import DEFAULT_FRONTEND_PORT, frontend_dist_root, load_launcher_config
from context_packs import context_pack_service
from db import get_db, init_db
from diagnostics import open_folder
from daemon_state import daemon_identity_snapshot, read_daemon_token, resolve_backend_binding, update_daemon_metadata_status
from errors import MissionControlError, as_mission_control_error, format_problem_details
from imported_codebase import import_service
from intelligence import reputation_service, scope_creep_service
from manager import service
from plugin_health import mission_control_plugin_health
from models import (
    Agent,
    AgentRun,
    InterviewSession,
    ManagerMessage,
    OrchestrationSession,
    PathReservation,
    PendingDecision,
    Plan,
    Project,
    ProjectSnapshot,
    RecoveryPlan,
    SubagentBatch,
    Task,
)
from orchestration import coordinator
from playbooks import playbook_service
from preferences import preference_service
from risk import risk_service
from runtime_paths import diagnostics_root
from security import security_service
from security.path_validation import PathValidationError, resolve_local_path
from schemas import (
    ApprovalRequestRead,
    ApprovalAuditLogRead,
    ApprovalResolveRequest,
    AgentActionResponse,
    AgentContractRead,
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
    DecisionRecordRead,
    DocGenerationResponse,
    EvidenceBasedHandoffRead,
    EventDigestWindow,
    EventRead,
    HandoffEvidenceCreate,
    HandoffEvidencePreviewSummaryRead,
    HandoffEvidenceRead,
    HandoffListItemRead,
    HeadlessAutowireRequest,
    HeadlessConfigRead,
    HeadlessHappyPathDemoRead,
    HeadlessHappyPathDemoRequest,
    HeadlessStartTaskRead,
    HeadlessStartTaskRequest,
    HeadlessRepairRequest,
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
    InstallReportRead,
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
    OperationalInstinctPreviewRead,
    OperatorSnapshotRead,
    OpenPathResponse,
    OrchestrationAttachRead,
    OrchestrationAttachRequest,
    OrchestrationCreateRequest,
    OrchestrationEventRead,
    OrchestrationHandoffRead,
    OrchestrationSessionRead,
    OrchestrationStatusRead,
    PathLockRead,
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
    RecoveryPlanPreviewSummaryRead,
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
    RunnersStatusRead,
    SafeModeStatusRead,
    SubagentBatchRead,
    SubagentBatchResultsIngestRequest,
    SubagentBurstRecommendationRead,
    SubagentBurstRecommendRequest,
    SubagentPolicyRead,
    SubagentPolicyUpdate,
    CustomCodexAgentsGenerateRead,
    CustomCodexAgentsGenerateRequest,
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
    VerificationBriefRead,
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
from subagent_planner import subagent_planner_service
from task_board import can_assign_task
from simulation import simulation_service
from validation_coverage import validation_coverage_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    coordinator.on_startup()
    if os.environ.get("MISSION_CONTROL_SERVER_MODE") == "daemon":
        binding = resolve_backend_binding(prefer_live_metadata=False)
        update_daemon_metadata_status(
            status="ok",
            host=str(binding["host"]),
            port=int(binding["port"]),
            pid=os.getpid(),
            mode="daemon",
        )
    try:
        yield
    finally:
        await service.on_shutdown()
        await coordinator.on_shutdown()
        if os.environ.get("MISSION_CONTROL_SERVER_MODE") == "daemon":
            binding = resolve_backend_binding(prefer_live_metadata=False)
            update_daemon_metadata_status(
                status="stopped",
                host=str(binding["host"]),
                port=int(binding["port"]),
                pid=os.getpid(),
                mode="daemon",
            )


def _url_host(host: str) -> str:
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _cors_allow_origins() -> list[str]:
    config = load_launcher_config()
    frontend_port = int(config.get("frontendPort") or DEFAULT_FRONTEND_PORT)
    hosts = ["localhost", "127.0.0.1", "::1"]
    return [f"http://{_url_host(host)}:{frontend_port}" for host in hosts]


app = FastAPI(title="Codex Mission Control Server", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MissionControlError)
async def mission_control_error_handler(request: Request, exc: MissionControlError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status or 500,
        content=format_problem_details(exc, instance=str(request.url.path)),
        media_type="application/problem+json",
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


def _get_plan_or_404(db: Session, plan_id: int) -> Plan:
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


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


def _get_snapshot_or_404(db: Session, snapshot_id: int) -> ProjectSnapshot:
    snapshot = db.get(ProjectSnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Project snapshot not found")
    return snapshot


def _get_recovery_plan_or_404(db: Session, plan_id: int) -> RecoveryPlan:
    plan = db.get(RecoveryPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Recovery plan not found")
    return plan


def _get_subagent_batch_or_404(db: Session, batch_id: int) -> SubagentBatch:
    batch = db.get(SubagentBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Subagent batch not found")
    return batch


def _get_manager_message_or_404(db: Session, message_id: int) -> ManagerMessage:
    message = db.get(ManagerMessage, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Manager message not found")
    return message


def _require_project_scope(resource_name: str, actual_project_id: int | None, requested_project_id: int) -> None:
    if actual_project_id != requested_project_id:
        raise HTTPException(status_code=404, detail=f"{resource_name} not found in this project")


def _require_project_agent(db: Session, project: Project, agent_id: int, *, resource_name: str = "Agent") -> Agent:
    agent = _get_agent_or_404(db, agent_id)
    _require_project_scope(resource_name, agent.project_id, project.id)
    return agent


def _require_project_task(db: Session, project: Project, task_id: int, *, resource_name: str = "Task") -> Task:
    task = _get_task_or_404(db, task_id)
    _require_project_scope(resource_name, task.project_id, project.id)
    return task


def _require_project_message(db: Session, project: Project, message_id: int, *, resource_name: str = "Manager message") -> ManagerMessage:
    message = _get_manager_message_or_404(db, message_id)
    _require_project_scope(resource_name, message.project_id, project.id)
    return message


def _require_imported_project(project: Project) -> None:
    if project.source_type != "existing_folder":
        raise HTTPException(status_code=400, detail="Import safety is only available for imported codebases")


def _require_bridge_token(request: Request) -> None:
    token = read_daemon_token()
    if not token:
        raise MissionControlError(
            code="MC-AUTH-BRIDGE-TOKEN-MISSING-001",
            breakpoint="mcp.handshake",
            safe_details={"path": str(request.url.path)},
        )
    supplied = request.headers.get("X-Mission-Control-Token", "").strip()
    if supplied != token:
        raise MissionControlError(
            code="MC-AUTH-BRIDGE-TOKEN-INVALID-001",
            breakpoint="mcp.handshake",
            safe_details={"path": str(request.url.path)},
        )


def _serialize_interview(project: Project, session: InterviewSession) -> InterviewSessionRead:
    understanding = service.get_project_understanding(project)
    generated_questions = session.questions_asked
    answered_questions = sum(1 for question in session.questions if question.status in {"answered", "auto_decided"} or question.answered_at is not None)
    pending_questions = sum(1 for question in session.questions if question.status == "pending")
    generation_budget_remaining = max(session.question_budget - generated_questions, 0)
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
        questions_asked=generated_questions,
        questions_remaining=generation_budget_remaining,
        questions_generated=generated_questions,
        questions_answered=answered_questions,
        pending_questions=pending_questions,
        generation_budget_remaining=generation_budget_remaining,
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
    try:
        candidate.relative_to(dist_root)
        inside_dist = True
    except ValueError:
        inside_dist = False
    if inside_dist and candidate.exists() and candidate.is_file():
        return candidate
    index_path = dist_dir / "index.html"
    return index_path if index_path.exists() else None


def _attach_workspace_via_bridge(db: Session, payload: OrchestrationAttachRequest) -> dict[str, Any]:
    return bridge_runtime_service.attach_workspace(
        db,
        workspace_path=payload.workspace_path,
        project_name=payload.project_name,
        mode=payload.mode,
        read_only_first=payload.read_only_first,
        attach_policy=payload.attach_policy,
        source="codex_plugin",
    )


async def _enrich_attach_with_status_summary(db: Session, attached: dict[str, Any]) -> dict[str, Any]:
    project_id = attached.get("project_id")
    if project_id is None:
        return attached
    project = db.get(Project, int(project_id))
    if project is None:
        return attached
    orchestration_payload = attached.get("orchestration") or None
    orchestration = None
    if orchestration_payload and orchestration_payload.get("id") is not None:
        orchestration = db.get(OrchestrationSession, int(orchestration_payload["id"]))
    try:
        summary = await bridge_runtime_service.get_status_summary(db, project=project, orchestration=orchestration)
    except ValueError:
        return attached
    attached["status_summary_markdown"] = summary["fallback_markdown"]
    return attached


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/diagnostics/identity")
def daemon_identity(_: None = Depends(_require_bridge_token)) -> dict[str, Any]:
    return daemon_identity_snapshot()


@app.get("/api/plugin/health", response_model=PluginHealthSummaryRead)
async def get_plugin_health(_: None = Depends(_require_bridge_token)) -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.post("/api/plugin/health/check", response_model=PluginHealthSummaryRead)
async def check_plugin_health(_: None = Depends(_require_bridge_token)) -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.get("/api/headless/health", response_model=PluginHealthSummaryRead)
async def get_headless_runtime_health(_: None = Depends(_require_bridge_token)) -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await get_headless_health()))


@app.get("/api/headless/config", response_model=HeadlessConfigRead)
def get_headless_runtime_config(_: None = Depends(_require_bridge_token)) -> HeadlessConfigRead:
    return HeadlessConfigRead(**get_headless_config())


@app.post("/api/headless/autowire", response_model=InstallReportRead)
async def autowire_headless_runtime(
    payload: HeadlessAutowireRequest | None = None,
    _: None = Depends(_require_bridge_token),
) -> InstallReportRead:
    payload = payload or HeadlessAutowireRequest()
    report = await autowire_headless(
        workspace_path=payload.workspace_path,
        install_path=payload.install_path,
        runtime_path=payload.runtime_path,
        daemon_host=payload.daemon_host,
        daemon_port=payload.daemon_port,
        mcp_transport=payload.mcp_transport,
        mcp_port=payload.mcp_port,
        headless_only=payload.headless_only,
        dry_run=payload.dry_run,
    )
    return InstallReportRead(**report)


@app.post("/api/headless/repair", response_model=InstallReportRead)
async def repair_headless_runtime(
    payload: HeadlessRepairRequest | None = None,
    _: None = Depends(_require_bridge_token),
) -> InstallReportRead:
    payload = payload or HeadlessRepairRequest()
    report = await repair_headless(
        workspace_path=None,
        install_path=payload.install_path,
        runtime_path=payload.runtime_path,
        daemon_host=payload.daemon_host,
        daemon_port=payload.daemon_port,
        mcp_transport=payload.mcp_transport,
        mcp_port=payload.mcp_port,
        headless_only=payload.headless_only,
        preserve_config=payload.preserve_config,
    )
    return InstallReportRead(**report)


@app.get("/api/runners/status", response_model=RunnersStatusRead)
def get_runners_status(_: None = Depends(_require_bridge_token)) -> RunnersStatusRead:
    return RunnersStatusRead(**summarize_runner_status())


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
    adapter_args: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
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
                adapter_args_override=adapter_args if adapter_args is not None else adapter_arg,
            )
        )
    )


@app.get("/api/system/auth-state", response_model=AuthStateRead)
async def auth_state(_: None = Depends(_require_bridge_token)) -> AuthStateRead:
    status = service.auth_state()
    return AuthStateRead(**status)


@app.get("/api/profile", response_model=AppProfileRead)
def get_profile(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AppProfileRead:
    return service.get_app_profile(db)


@app.put("/api/profile", response_model=AppProfileRead)
def update_profile(
    payload: AppProfileUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AppProfileRead:
    try:
        return service.update_app_profile(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/startup/status", response_model=StartupStatusRead)
def get_startup_status(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.get_status(db))


@app.post("/api/startup/check", response_model=StartupStatusRead)
def run_startup_check(
    payload: StartupCheckRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.run_checks(db, attempt_number=payload.attempt_number, include_optional_checks=payload.include_optional_checks))


@app.post("/api/startup/retry", response_model=StartupStatusRead)
def retry_startup(
    payload: StartupRetryRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> StartupStatusRead:
    return StartupStatusRead(**startup_service.retry(db, attempt_number=payload.attempt_number, failed_check=payload.failed_check, retry_mode=payload.retry_mode))


@app.post("/api/startup/complete-first-run", response_model=AppStateRead)
def complete_startup_first_run(
    payload: CompleteFirstRunRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AppStateRead:
    return startup_service.complete_first_run(db, payload)


@app.post("/api/startup/diagnostics", response_model=DiagnosticReportRead)
def startup_diagnostics(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> DiagnosticReportRead:
    return DiagnosticReportRead(**startup_service.run_diagnostics(db))


@app.post("/api/startup/open-diagnostics-folder", response_model=OpenPathResponse)
def open_diagnostics_folder(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OpenPathResponse:
    status = startup_service.get_status(db)
    diagnostics_path = status.get("diagnostic_report_path")
    if diagnostics_path:
        from pathlib import Path

        target = str(Path(diagnostics_path).parent)
    else:
        report = startup_service.run_diagnostics(db)
        from pathlib import Path

        target = str(Path(report["path"]).parent)
    return OpenPathResponse(**open_folder(target, allowed_roots=[diagnostics_root()]))


@app.get("/api/system/codex-status", response_model=CodexStatusRead)
async def codex_status(
    project_id: int | None = Query(default=None),
    provider: str | None = Query(default=None),
    provider_endpoint: str | None = Query(default=None),
    adapter_command: str | None = Query(default=None),
    adapter_arg: list[str] | None = Query(default=None),
    adapter_args: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
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
                adapter_args_override=adapter_args if adapter_args is not None else adapter_arg,
            )
        )
    )


@app.post("/api/system/auth/login/chatgpt", response_model=AuthJobRead)
async def login_with_chatgpt(
    payload: ChatGptLoginRequest,
    _: None = Depends(_require_bridge_token),
) -> AuthJobRead:
    job = await auth_service.start_chatgpt_login(device_auth=payload.device_auth)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/login/device", response_model=AuthJobRead)
async def login_with_device_code(_: None = Depends(_require_bridge_token)) -> AuthJobRead:
    job = await auth_service.start_chatgpt_login(device_auth=True)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/login/api-key", response_model=AuthJobRead)
async def login_with_api_key(
    payload: ApiKeyLoginRequest,
    _: None = Depends(_require_bridge_token),
) -> AuthJobRead:
    job = await auth_service.start_api_key_login(payload.api_key)
    return AuthJobRead(**auth_service.job_payload(job))


@app.post("/api/system/auth/logout", response_model=AuthJobRead)
async def logout_codex(_: None = Depends(_require_bridge_token)) -> AuthJobRead:
    job = await auth_service.start_logout()
    return AuthJobRead(**auth_service.job_payload(job))


@app.get("/api/system/auth-jobs/{job_id}", response_model=AuthJobRead)
async def get_auth_job(job_id: str, _: None = Depends(_require_bridge_token)) -> AuthJobRead:
    job = auth_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Auth job not found")
    return AuthJobRead(**auth_service.job_payload(job))


@app.get("/api/settings", response_model=ProjectSettingsRead)
def get_settings(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    return service._project_settings_preview(db, project)


@app.put("/api/settings", response_model=ProjectSettingsRead)
def update_settings(
    payload: ProjectSettingsUpdate,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    try:
        return service.update_settings(db, project, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/swarm/preferences", response_model=SwarmPreferencesRead)
def get_swarm_preferences(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPreferencesRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPreferencesRead(**service.get_swarm_preferences(db, project))


@app.put("/api/projects/{project_id}/swarm/preferences", response_model=SwarmPreferencesRead)
def update_swarm_preferences(
    project_id: int,
    payload: SwarmPreferencesUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPreferencesRead:
    project = _get_project_or_404(db, project_id)
    return SwarmPreferencesRead(**service.update_swarm_preferences(db, project, payload))


@app.post("/api/projects/{project_id}/swarm/plan", response_model=SwarmPlanRead)
async def create_swarm_plan(
    project_id: int,
    payload: SwarmPlanRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    if payload.milestone_id is not None:
        milestone_plan = _get_plan_or_404(db, payload.milestone_id)
        _require_project_scope("Plan", milestone_plan.project_id, project.id)
    return SwarmPlanRead(**(await service.create_swarm_plan(db, project, goal=payload.goal, milestone_id=payload.milestone_id)))


@app.get("/api/projects/{project_id}/swarm/plan", response_model=SwarmPlanRead | None)
def get_swarm_plan(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPlanRead | None:
    project = _get_project_or_404(db, project_id)
    payload = service.get_swarm_plan(db, project)
    return SwarmPlanRead(**payload) if payload else None


@app.post("/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/approve", response_model=SwarmPlanRead)
def approve_swarm_plan(
    project_id: int,
    swarm_plan_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmPlanRead(**service.approve_swarm_plan(db, project, swarm_plan_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/swarm/plan/{swarm_plan_id}/revise", response_model=SwarmPlanRead)
async def revise_swarm_plan(
    project_id: int,
    swarm_plan_id: int,
    payload: SwarmPlanReviseRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmPlanRead:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmPlanRead(**(await service.revise_swarm_plan(db, project, swarm_plan_id, payload.note)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/swarm/spawn", response_model=SwarmSpawnResponse)
def spawn_swarm_agents(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmSpawnResponse:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmSpawnResponse(**service.spawn_swarm_agents(db, project))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/swarm/scale", response_model=SwarmSpawnResponse)
async def scale_swarm(
    project_id: int,
    payload: SwarmScaleRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmSpawnResponse:
    project = _get_project_or_404(db, project_id)
    try:
        return SwarmSpawnResponse(**(await service.scale_swarm(db, project, direction=payload.direction, reason=payload.reason, count=payload.count)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/swarm/events", response_model=list[SwarmEventRead])
def get_swarm_events(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[SwarmEventRead]:
    project = _get_project_or_404(db, project_id)
    return [SwarmEventRead(**item) for item in service.list_swarm_events(db, project)]


@app.get("/api/agent-archetypes", response_model=list[AgentArchetypeRead])
def get_agent_archetypes(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[AgentArchetypeRead]:
    return [AgentArchetypeRead(**item) for item in service.list_agent_archetypes(db)]


@app.get("/api/widgets/catalog", response_model=list[WidgetDefinitionRead])
def get_widget_catalog(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[WidgetDefinitionRead]:
    return [WidgetDefinitionRead(**item) for item in service.list_widget_catalog(db, scope)]


@app.get("/api/widgets/instances", response_model=list[WidgetInstanceRead])
def get_widget_instances(
    scope: str = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[WidgetInstanceRead]:
    if scope != "dashboard":
        raise HTTPException(status_code=400, detail="Only dashboard scope is supported on this route.")
    return [WidgetInstanceRead(**item) for item in service.list_dashboard_widget_instances(db)]


@app.get("/api/projects/{project_id}/widgets/instances", response_model=list[WidgetInstanceRead])
def get_project_widget_instances(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[WidgetInstanceRead]:
    project = _get_project_or_404(db, project_id)
    return [WidgetInstanceRead(**item) for item in service.list_project_widget_instances(db, project)]


@app.post("/api/widgets/instances", response_model=WidgetInstanceRead)
def create_widget_instance(
    payload: WidgetInstanceCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetInstanceRead:
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
def patch_widget_instance(
    instance_id: int,
    payload: WidgetInstanceUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetInstanceRead:
    try:
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload.dict(exclude_unset=True)
        return WidgetInstanceRead(**service.update_widget_instance(db, instance_id, data))
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.delete("/api/widgets/instances/{instance_id}", status_code=204)
def delete_widget_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> None:
    try:
        service.delete_widget_instance(db, instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/widgets/instances/{instance_id}/data", response_model=WidgetDataResponseRead)
async def get_widget_instance_data(
    instance_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetDataResponseRead:
    try:
        return WidgetDataResponseRead(**(await service.get_widget_instance_data(db, instance_id)))
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/widgets/summary", response_model=WidgetSummaryRead)
async def get_project_widgets_summary(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetSummaryRead:
    project = _get_project_or_404(db, project_id)
    return WidgetSummaryRead(**(await service.get_project_widget_summary(db, project)))


@app.post("/api/dashboard/widgets/add", response_model=WidgetInstanceRead)
def add_dashboard_widget(
    payload: WidgetAddRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetInstanceRead:
    try:
        return WidgetInstanceRead(**service.add_dashboard_widget(db, payload.widget_type, payload.area, payload.size))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/widgets/add", response_model=WidgetInstanceRead)
def add_project_widget(
    project_id: int,
    payload: WidgetAddRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> WidgetInstanceRead:
    project = _get_project_or_404(db, project_id)
    try:
        return WidgetInstanceRead(**service.add_project_widget(db, project, payload.widget_type, payload.area, payload.size))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/change-requests", response_model=ChangeRequestRead)
def create_change_request(
    project_id: int,
    payload: ChangeRequestCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ChangeRequestRead:
    project = _get_project_or_404(db, project_id)
    try:
        return service.create_change_request(db, project, payload.request_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/capabilities/benchmarks", response_model=list[CapabilityBenchmarkRead])
def get_capability_benchmarks(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[CapabilityBenchmarkRead]:
    return [CapabilityBenchmarkRead.model_validate(item) for item in capability_service.list_benchmarks(db)]


@app.post("/api/capabilities/benchmarks", response_model=CapabilityBenchmarkRead)
def create_capability_benchmark(
    payload: CapabilityBenchmarkCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CapabilityBenchmarkRead:
    record = capability_service.record_benchmark(db, payload.model_dump())
    return CapabilityBenchmarkRead.model_validate(record)


@app.get("/api/capabilities/matrix", response_model=list[CapabilityMatrixEntryRead])
def get_capability_matrix(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[CapabilityMatrixEntryRead]:
    return [CapabilityMatrixEntryRead(**item) for item in capability_service.capability_matrix(db)]


@app.get("/api/agents/reputation", response_model=list[AgentReputationSummaryRead])
def get_agent_reputation(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[AgentReputationSummaryRead]:
    return [AgentReputationSummaryRead(**item) for item in reputation_service.summarize(db)]


@app.get("/api/projects/{project_id}/agents/reputation", response_model=list[AgentReputationSummaryRead])
def get_project_agent_reputation(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[AgentReputationSummaryRead]:
    project = _get_project_or_404(db, project_id)
    return [AgentReputationSummaryRead(**item) for item in reputation_service.summarize(db, project)]


@app.post("/api/agents/performance-record", response_model=AgentPerformanceRecordRead)
def create_agent_performance_record(
    payload: AgentPerformanceRecordCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentPerformanceRecordRead:
    record = reputation_service.record(db, payload.model_dump())
    return AgentPerformanceRecordRead.model_validate(record)


@app.get("/api/playbooks", response_model=list[ProjectPlaybookRead])
def get_playbooks(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ProjectPlaybookRead]:
    return [ProjectPlaybookRead.model_validate(item) for item in playbook_service.list_playbooks(db)]


@app.get("/api/playbooks/{playbook_key}", response_model=ProjectPlaybookRead)
def get_playbook(
    playbook_key: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectPlaybookRead:
    playbook = playbook_service.get_playbook(db, playbook_key)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return ProjectPlaybookRead.model_validate(playbook)


@app.post("/api/projects/{project_id}/playbook/suggest", response_model=ProjectPlaybookSuggestionRead)
def suggest_project_playbook(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectPlaybookSuggestionRead:
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
def apply_project_playbook(
    project_id: int,
    payload: ProjectPlaybookApplyRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectPlaybookSuggestionRead:
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
def build_context_pack(
    project_id: int,
    payload: ContextPackBuildRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ContextPackRead:
    project = _get_project_or_404(db, project_id)
    if payload.agent_id is not None:
        _require_project_agent(db, project, payload.agent_id)
    if payload.task_id is not None:
        _require_project_task(db, project, payload.task_id)
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
def list_context_packs(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ContextPackRead]:
    project = _get_project_or_404(db, project_id)
    return [ContextPackRead(**item) for item in context_pack_service.list_context_packs(db, project)]


@app.get("/api/context-packs/{context_pack_id}", response_model=ContextPackRead)
def get_context_pack(
    context_pack_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ContextPackRead:
    try:
        pack = context_pack_service.get_context_pack(db, context_pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _require_project_scope("Context pack", pack.get("project_id"), project_id)
    return ContextPackRead(**pack)


@app.get("/api/projects/{project_id}/risks", response_model=list[RiskRecordRead])
def get_project_risks(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[RiskRecordRead]:
    project = _get_project_or_404(db, project_id)
    return [RiskRecordRead.model_validate(item) for item in risk_service.list_risks(db, project)]


@app.post("/api/projects/{project_id}/risks", response_model=RiskRecordRead)
def create_project_risk(
    project_id: int,
    payload: RiskRecordCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RiskRecordRead:
    project = _get_project_or_404(db, project_id)
    if payload.owner_agent_id is not None:
        _require_project_agent(db, project, payload.owner_agent_id, resource_name="Risk owner agent")
    if payload.related_task_id is not None:
        _require_project_task(db, project, payload.related_task_id, resource_name="Risk related task")
    return RiskRecordRead.model_validate(risk_service.create_risk(db, project, payload.model_dump()))


@app.patch("/api/risks/{risk_id}", response_model=RiskRecordRead)
def update_project_risk(
    risk_id: int,
    payload: RiskRecordUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RiskRecordRead:
    try:
        return RiskRecordRead.model_validate(risk_service.update_risk(db, risk_id, payload.model_dump(exclude_none=True)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/scope-creep", response_model=list[ScopeChangeSignalRead])
def get_scope_creep(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ScopeChangeSignalRead]:
    project = _get_project_or_404(db, project_id)
    return [ScopeChangeSignalRead.model_validate(item) for item in scope_creep_service.list_signals(db, project)]


@app.post("/api/projects/{project_id}/scope-creep/analyze", response_model=list[ScopeChangeSignalRead])
def analyze_scope_creep(
    project_id: int,
    payload: ScopeChangeAnalyzeRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ScopeChangeSignalRead]:
    project = _get_project_or_404(db, project_id)
    if payload.related_task_id is not None:
        _require_project_task(db, project, payload.related_task_id, resource_name="Scope change related task")
    if payload.related_message_id is not None:
        _require_project_message(db, project, payload.related_message_id, resource_name="Scope change related message")
    return [ScopeChangeSignalRead.model_validate(item) for item in scope_creep_service.analyze(db, project, payload.model_dump())]


@app.post("/api/scope-creep/{signal_id}/resolve", response_model=ScopeChangeSignalRead)
def resolve_scope_creep(
    signal_id: int,
    payload: ScopeChangeResolveRequest,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ScopeChangeSignalRead:
    try:
        signal = scope_creep_service.resolve(db, signal_id, payload.status, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScopeChangeSignalRead.model_validate(signal)


@app.post("/api/projects/{project_id}/swarm/simulate-launch", response_model=SwarmLaunchSimulationRead)
def simulate_swarm_launch(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SwarmLaunchSimulationRead:
    project = _get_project_or_404(db, project_id)
    return SwarmLaunchSimulationRead.model_validate(simulation_service.simulate_launch(db, project))


@app.get("/api/projects/{project_id}/swarm/simulations", response_model=list[SwarmLaunchSimulationRead])
def list_swarm_simulations(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[SwarmLaunchSimulationRead]:
    project = _get_project_or_404(db, project_id)
    return [SwarmLaunchSimulationRead.model_validate(item) for item in simulation_service.list_simulations(db, project)]


@app.get("/api/projects/{project_id}/validation-coverage", response_model=list[ValidationCoverageAreaRead])
def get_validation_coverage(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ValidationCoverageAreaRead]:
    project = _get_project_or_404(db, project_id)
    coverage = validation_coverage_service.list_coverage(db, project)
    if coverage:
        return [ValidationCoverageAreaRead.model_validate(item) for item in coverage]
    return [ValidationCoverageAreaRead.model_validate(item) for item in validation_coverage_service.preview_coverage(db, project)]


@app.post("/api/projects/{project_id}/validation-coverage/recompute", response_model=list[ValidationCoverageAreaRead])
def recompute_validation_coverage(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ValidationCoverageAreaRead]:
    project = _get_project_or_404(db, project_id)
    return [ValidationCoverageAreaRead.model_validate(item) for item in validation_coverage_service.recompute(db, project)]


@app.get("/api/preferences", response_model=list[UserPreferenceRead])
def get_preferences(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[UserPreferenceRead]:
    return [UserPreferenceRead.model_validate(item) for item in preference_service.list_preferences(db, project_id=None)]


@app.put("/api/preferences/{key}", response_model=UserPreferenceRead)
def put_preference(
    key: str,
    payload: UserPreferenceUpsert,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> UserPreferenceRead:
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
def get_project_preferences(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[UserPreferenceRead]:
    project = _get_project_or_404(db, project_id)
    return [UserPreferenceRead.model_validate(item) for item in preference_service.get_effective_preferences(db, project)]


@app.put("/api/projects/{project_id}/preferences/{key}", response_model=UserPreferenceRead)
def put_project_preference(
    project_id: int,
    key: str,
    payload: UserPreferenceUpsert,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> UserPreferenceRead:
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
def get_security_policy(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SecurityPolicyRead:
    return SecurityPolicyRead.model_validate(security_service.get_policy(db))


@app.put("/api/security/policy", response_model=SecurityPolicyRead)
def put_security_policy(
    payload: SecurityPolicyUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SecurityPolicyRead:
    record = security_service.update_policy(db, payload.model_dump())
    return SecurityPolicyRead.model_validate(record)


@app.get("/api/projects/{project_id}/security/policy", response_model=SecurityPolicyRead)
def get_project_security_policy(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SecurityPolicyRead:
    project = _get_project_or_404(db, project_id)
    return SecurityPolicyRead.model_validate(security_service.get_policy(db, project=project))


@app.put("/api/projects/{project_id}/security/policy", response_model=SecurityPolicyRead)
def put_project_security_policy(
    project_id: int,
    payload: SecurityPolicyUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SecurityPolicyRead:
    project = _get_project_or_404(db, project_id)
    record = security_service.update_policy(db, payload.model_dump(), project=project)
    return SecurityPolicyRead.model_validate(record)


@app.post("/api/security/risk-assess", response_model=RiskAssessmentRead)
def assess_security_risk(
    payload: RiskAssessRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RiskAssessmentRead:
    project = _get_project_or_404(db, payload.project_id) if payload.project_id is not None else None
    record = security_service.assess_risk(db, payload.model_dump(), project=project)
    return RiskAssessmentRead.model_validate(record)


@app.get("/api/security/audit-log", response_model=list[ApprovalAuditLogRead])
def get_security_audit_log(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ApprovalAuditLogRead]:
    return [ApprovalAuditLogRead.model_validate(item) for item in security_service.list_audit_logs(db)]


@app.get("/api/projects/{project_id}/security/audit-log", response_model=list[ApprovalAuditLogRead])
def get_project_security_audit_log(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ApprovalAuditLogRead]:
    project = _get_project_or_404(db, project_id)
    return [ApprovalAuditLogRead.model_validate(item) for item in security_service.list_audit_logs(db, project=project)]


@app.get("/api/dashboard/stream")
async def stream_dashboard(
    after_id: int | None = Query(default=None),
    _: None = Depends(_require_bridge_token),
) -> StreamingResponse:
    generator = service.events.stream_app(after_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.get("/api/dashboard/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> DashboardSummaryRead:
    return DashboardSummaryRead(**(await service.get_dashboard_summary(db)))


@app.post("/api/orchestrations/attach-workspace", response_model=OrchestrationAttachRead)
async def attach_workspace(
    payload: OrchestrationAttachRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationAttachRead:
    try:
        attached = _attach_workspace_via_bridge(db, payload)
    except MissionControlError:
        raise
    except ValueError as exc:
        raise MissionControlError(
            code="MC-WORKSPACE-PATH-MISSING-001",
            detail=str(exc),
            breakpoint="workspace.attach",
            safe_details={"workspace_path": payload.workspace_path},
            caused_by=exc,
        ) from exc
    attached = await _enrich_attach_with_status_summary(db, attached)
    return OrchestrationAttachRead(**attached)


@app.post("/api/headless/attach-workspace", response_model=OrchestrationAttachRead)
async def attach_headless_workspace(
    payload: OrchestrationAttachRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationAttachRead:
    try:
        attached = _attach_workspace_via_bridge(db, payload)
    except MissionControlError:
        raise
    except ValueError as exc:
        raise MissionControlError(
            code="MC-WORKSPACE-PATH-MISSING-001",
            detail=str(exc),
            breakpoint="workspace.attach",
            safe_details={"workspace_path": payload.workspace_path},
            caused_by=exc,
        ) from exc
    attached = await _enrich_attach_with_status_summary(db, attached)
    return OrchestrationAttachRead(**attached)


@app.post("/api/orchestrations", response_model=OrchestrationSessionRead)
async def create_orchestration(
    payload: OrchestrationCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    project = _get_project_or_404(db, payload.project_id)
    run_initial_turn_inline = (payload.mode or "unknown") != "dry_run" and project.runner_mode != "dry_run"
    try:
        session = bridge_runtime_service.start_orchestration(
            db,
            project=project,
            source=payload.source,
            user_request=payload.user_request,
            orchestration_id=payload.orchestration_id,
            mode=payload.mode or "unknown",
            metadata_json=payload.metadata_json,
            schedule_background_turn=not run_initial_turn_inline,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run_initial_turn_inline:
        session_record = coordinator.get_session(db, int(session["id"]))
        db.commit()
        await coordinator._run_background_turn(session_record.id, "user_request")
        db.expire_all()
        refreshed = coordinator.get_session(db, session_record.id)
        session = coordinator._serialize_session(refreshed)
    return OrchestrationSessionRead(**session)


@app.post("/api/headless/start-task", response_model=HeadlessStartTaskRead)
async def start_headless_task(
    payload: HeadlessStartTaskRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> HeadlessStartTaskRead:
    if payload.project_id is None and not payload.workspace_path:
        raise MissionControlError(
            code="MC-WORKSPACE-PATH-MISSING-001",
            detail="Mission Control needs either a workspace_path or a project_id to start a background task.",
            breakpoint="workspace.attach",
        )
    try:
        result = await bridge_runtime_service.start_headless_task(
            db,
            workspace_path=payload.workspace_path,
            project_id=payload.project_id,
            user_request=payload.user_request,
            strategy=payload.strategy,
            mode=payload.mode,
            interview_mode=payload.interview_mode,
            attach_policy=payload.attach_policy,
        )
    except MissionControlError:
        raise
    except ValueError as exc:
        raise MissionControlError(
            code="MC-ORCH-START-FAILED-001",
            detail=str(exc),
            breakpoint="orchestration.create",
            safe_details={"workspace_path": payload.workspace_path, "project_id": payload.project_id},
            caused_by=exc,
        ) from exc
    return HeadlessStartTaskRead(
        project=result["project"],
        orchestration=OrchestrationSessionRead(**result["orchestration"]) if result.get("orchestration") else None,
        attach=OrchestrationAttachRead(**result["attach"]) if result.get("attach") else None,
        status_summary=BridgeMessageRead(**result["status_summary"]) if result.get("status_summary") else None,
        pending_decisions=[PendingDecisionRead(**item) for item in result.get("pending_decisions", [])],
        next_action=result.get("next_action"),
        user_action_required=bool(result.get("user_action_required")),
        mode_used=result.get("mode_used", "unknown"),
    )


@app.get("/api/orchestrations/plugin-health", response_model=PluginHealthSummaryRead)
async def get_bridge_plugin_health(
    request: Request,
    _: None = Depends(_require_bridge_token),
) -> PluginHealthSummaryRead:
    return PluginHealthSummaryRead(**(await mission_control_plugin_health()))


@app.get("/api/headless/diagnostic-summary", response_model=BridgeMessageRead)
async def get_headless_diagnostic_summary(
    request: Request,
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    return BridgeMessageRead(**(await bridge_runtime_service.get_diagnostic_summary()))


@app.post("/api/headless/happy-path-demo", response_model=HeadlessHappyPathDemoRead)
async def run_headless_happy_path_demo(
    payload: HeadlessHappyPathDemoRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> HeadlessHappyPathDemoRead:
    try:
        demo = await bridge_runtime_service.happy_path_demo(
            db,
            workspace_path=payload.workspace_path,
            project_name=payload.project_name,
            user_request=payload.user_request,
            mode=payload.mode,
            read_only_first=payload.read_only_first,
            attach_policy=payload.attach_policy,
            create_pending_decision=payload.create_pending_decision,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HeadlessHappyPathDemoRead(**demo)


@app.get("/api/orchestrations/{orchestration_id}", response_model=OrchestrationSessionRead)
def get_orchestration(
    orchestration_id: int,
    request: Request,
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    if project_id is not None:
        _require_project_scope("Orchestration session", session.project_id, project_id)
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


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
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationStatusRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
    return OrchestrationStatusRead(**(await coordinator.get_status(db, session)))


@app.post("/api/orchestrations/{orchestration_id}/pause", response_model=OrchestrationSessionRead)
def pause_orchestration(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
    session = coordinator.pause_orchestration(db, session)
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


@app.post("/api/orchestrations/{orchestration_id}/resume", response_model=OrchestrationSessionRead)
async def resume_orchestration(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationSessionRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
    try:
        session = coordinator.resume_orchestration(db, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrchestrationSessionRead(**coordinator._serialize_session(session))


@app.get("/api/orchestrations/{orchestration_id}/events", response_model=list[OrchestrationEventRead])
def get_orchestration_events(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[OrchestrationEventRead]:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
    return [OrchestrationEventRead(**event) for event in coordinator.list_events(db, session)]


@app.get("/api/orchestrations/{orchestration_id}/handoff", response_model=OrchestrationHandoffRead)
def get_orchestration_handoff(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OrchestrationHandoffRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
    return OrchestrationHandoffRead(**coordinator.get_handoff(db, session))


@app.get("/api/orchestrations/{orchestration_id}/pending-decisions", response_model=list[PendingDecisionRead])
def get_orchestration_pending_decisions(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[PendingDecisionRead]:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
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
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    decision = _get_pending_decision_or_404(db, decision_id)
    _require_project_scope("Pending decision", decision.project_id, project_id)
    return BridgeMessageRead(**bridge_runtime_service.get_bridge_message_for_decision(db, decision))


@app.post("/api/decisions/{decision_id}/answer", response_model=PendingDecisionAnswerResultRead)
async def answer_pending_decision(
    decision_id: int,
    payload: PendingDecisionAnswerRequest,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> PendingDecisionAnswerResultRead:
    decision = _get_pending_decision_or_404(db, decision_id)
    _require_project_scope("Pending decision", decision.project_id, project_id)
    try:
        updated, next_summary = await bridge_runtime_service.answer_decision(
            db,
            decision,
            option_id=payload.option_id,
            selected_text=payload.selected_text,
            free_text=payload.free_text,
        )
    except MissionControlError:
        raise
    except Exception as exc:
        raise as_mission_control_error(
            exc,
            breakpoint="decision.answer",
            project_id=decision.project_id,
            orchestration_id=decision.orchestration_id,
            safe_details={"decision_id": decision.id, "option_id": payload.option_id},
        ) from exc
    return PendingDecisionAnswerResultRead(
        decision=PendingDecisionRead(**updated),
        next_status_summary=BridgeMessageRead(**next_summary) if next_summary else None,
    )


@app.get("/api/orchestrations/{orchestration_id}/status-summary", response_model=BridgeMessageRead)
async def get_orchestration_status_summary(
    orchestration_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
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
    project_id: int = Query(...),
    window: EventDigestWindow = Query(default="last_15_minutes"),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
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
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> BridgeMessageRead:
    session = _get_orchestration_or_404(db, orchestration_id)
    _require_project_scope("Orchestration session", session.project_id, project_id)
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


@app.get("/api/projects/{project_id}/handoff/evidence", response_model=list[HandoffEvidenceRead])
def get_project_handoff_evidence(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[HandoffEvidenceRead]:
    project = _get_project_or_404(db, project_id)
    return [HandoffEvidenceRead.model_validate(item) for item in service.list_handoff_evidence(db, project)]


@app.get("/api/projects/{project_id}/handoff/evidence/preview", response_model=HandoffEvidencePreviewSummaryRead)
def preview_project_handoff_evidence(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> HandoffEvidencePreviewSummaryRead:
    project = _get_project_or_404(db, project_id)
    preview = service.preview_handoff_evidence(db, project)
    return HandoffEvidencePreviewSummaryRead(
        project_id=project.id,
        persisted=[HandoffEvidenceRead.model_validate(item) for item in preview["persisted"]],
        derived_candidates=preview["derived_candidates"],
        stored_count=preview["stored_count"],
        derived_candidate_count=preview["derived_candidate_count"],
        generated_at=preview["generated_at"],
    )


@app.post("/api/projects/{project_id}/handoff/evidence", response_model=HandoffEvidenceRead)
def create_project_handoff_evidence(
    project_id: int,
    payload: HandoffEvidenceCreate,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> HandoffEvidenceRead:
    project = _get_project_or_404(db, project_id)
    return HandoffEvidenceRead.model_validate(service.add_handoff_evidence(db, project, payload.model_dump()))


@app.post("/api/projects/{project_id}/handoff/generate", response_model=EvidenceBasedHandoffRead)
def generate_project_handoff_record(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> EvidenceBasedHandoffRead:
    project = _get_project_or_404(db, project_id)
    return EvidenceBasedHandoffRead.model_validate(service.generate_evidence_handoff(db, project))


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


@app.get("/api/subagent-policy", response_model=SubagentPolicyRead)
def get_subagent_policy(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SubagentPolicyRead:
    return SubagentPolicyRead(**subagent_planner_service._serialize_policy(subagent_planner_service.ensure_policy(db)))


@app.put("/api/subagent-policy", response_model=SubagentPolicyRead)
def update_subagent_policy(
    payload: SubagentPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SubagentPolicyRead:
    policy = subagent_planner_service.update_policy(db, payload.model_dump(exclude_none=True))
    return SubagentPolicyRead(**subagent_planner_service._serialize_policy(policy))


@app.post("/api/projects/{project_id}/subagent-bursts/recommend", response_model=SubagentBurstRecommendationRead)
def recommend_subagent_burst(
    project_id: int,
    payload: SubagentBurstRecommendRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SubagentBurstRecommendationRead:
    project = _get_project_or_404(db, project_id)
    orchestration = coordinator.get_active_session_for_project(db, project)
    recommendation = subagent_planner_service.recommend_burst(
        db,
        project=project,
        payload=payload.model_dump(),
        orchestration_id=orchestration.id if orchestration is not None else None,
    )
    return SubagentBurstRecommendationRead(**recommendation)


@app.get("/api/projects/{project_id}/subagent-batches", response_model=list[SubagentBatchRead])
def list_project_subagent_batches(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[SubagentBatchRead]:
    project = _get_project_or_404(db, project_id)
    return [SubagentBatchRead(**item) for item in subagent_planner_service.list_batches(db, project)]


@app.get("/api/subagents/batches/{batch_id}", response_model=SubagentBatchRead)
def get_subagent_batch(
    batch_id: int,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SubagentBatchRead:
    batch = _get_subagent_batch_or_404(db, batch_id)
    _require_project_scope("Subagent batch", batch.project_id, project_id)
    return SubagentBatchRead(**subagent_planner_service.serialize_batch(db, batch))


@app.post("/api/subagents/batches/{batch_id}/results", response_model=SubagentBatchRead)
def ingest_subagent_batch_results(
    batch_id: int,
    payload: SubagentBatchResultsIngestRequest,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SubagentBatchRead:
    batch = _get_subagent_batch_or_404(db, batch_id)
    _require_project_scope("Subagent batch", batch.project_id, project_id)
    try:
        updated = subagent_planner_service.ingest_results(db, batch, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SubagentBatchRead(**subagent_planner_service.serialize_batch(db, updated))


@app.post("/api/projects/{project_id}/subagent-agents/generate", response_model=CustomCodexAgentsGenerateRead)
def generate_custom_codex_agents(
    project_id: int,
    payload: CustomCodexAgentsGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CustomCodexAgentsGenerateRead:
    project = _get_project_or_404(db, project_id)
    try:
        result = subagent_planner_service.generate_custom_agents(
            db,
            project,
            overwrite_existing=payload.overwrite_existing,
            template_names=payload.template_names,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CustomCodexAgentsGenerateRead(**result)


@app.get("/api/projects/{project_id}/agent-contracts", response_model=list[AgentContractRead])
def get_project_agent_contracts(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[AgentContractRead]:
    project = _get_project_or_404(db, project_id)
    contracts = service._sync_agent_contracts(db, project)
    return [AgentContractRead.model_validate(contract) for contract in contracts]


@app.get("/api/projects/{project_id}/decision-ledger", response_model=list[DecisionRecordRead])
def get_project_decision_ledger(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[DecisionRecordRead]:
    project = _get_project_or_404(db, project_id)
    decisions = service._sync_decision_records(db, project)
    return [DecisionRecordRead.model_validate(entry) for entry in decisions]


@app.get("/api/projects/{project_id}/path-locks", response_model=list[PathLockRead])
def get_project_path_locks(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[PathLockRead]:
    project = _get_project_or_404(db, project_id)
    locks = service._sync_path_locks(db, project)
    return [PathLockRead.model_validate(lock) for lock in locks]


@app.get("/api/projects/{project_id}/operator-snapshot", response_model=OperatorSnapshotRead)
def get_project_operator_snapshot(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OperatorSnapshotRead:
    project = _get_project_or_404(db, project_id)
    return OperatorSnapshotRead(**service.build_operator_snapshot(db, project))


@app.get("/api/projects/{project_id}/instincts/preview", response_model=OperationalInstinctPreviewRead)
def get_project_operational_instincts_preview(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> OperationalInstinctPreviewRead:
    project = _get_project_or_404(db, project_id)
    return OperationalInstinctPreviewRead(**service.preview_operational_instincts(db, project))


@app.get("/api/projects/{project_id}/verification-brief", response_model=VerificationBriefRead)
def get_project_verification_brief(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> VerificationBriefRead:
    project = _get_project_or_404(db, project_id)
    return VerificationBriefRead(**service.build_verification_brief(db, project))


@app.get("/api/projects/{project_id}/snapshots", response_model=list[ProjectSnapshotRead])
def get_project_snapshots(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ProjectSnapshotRead]:
    project = _get_project_or_404(db, project_id)
    return [ProjectSnapshotRead.model_validate(snapshot) for snapshot in service.list_snapshots(db, project)]


@app.post("/api/projects/{project_id}/snapshots", response_model=ProjectSnapshotRead)
def create_project_snapshot(
    project_id: int,
    payload: ProjectSnapshotCreate,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectSnapshotRead:
    project = _get_project_or_404(db, project_id)
    if payload.created_before_task_id is not None:
        _require_project_task(db, project, payload.created_before_task_id, resource_name="Snapshot task")
    if payload.created_before_agent_id is not None:
        _require_project_agent(db, project, payload.created_before_agent_id, resource_name="Snapshot agent")
    snapshot = service.create_project_snapshot(
        db,
        project,
        label=payload.label,
        description=payload.description,
        created_before_task_id=payload.created_before_task_id,
        created_before_agent_id=payload.created_before_agent_id,
    )
    return ProjectSnapshotRead.model_validate(snapshot)


@app.get("/api/projects/{project_id}/snapshots/{snapshot_id}/restore-plan", response_model=SnapshotRestorePlanRead)
def get_snapshot_restore_plan(
    project_id: int,
    snapshot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> SnapshotRestorePlanRead:
    project = _get_project_or_404(db, project_id)
    snapshot = _get_snapshot_or_404(db, snapshot_id)
    if snapshot.project_id != project.id:
        raise HTTPException(status_code=404, detail="Project snapshot not found")
    return SnapshotRestorePlanRead(**service.build_restore_plan(db, snapshot_id))


@app.get("/api/projects/{project_id}/recovery-plans", response_model=list[RecoveryPlanRead])
def get_project_recovery_plans(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[RecoveryPlanRead]:
    project = _get_project_or_404(db, project_id)
    return [RecoveryPlanRead.model_validate(plan) for plan in service.list_recovery_plans(db, project)]


@app.get("/api/projects/{project_id}/recovery-plans/preview", response_model=RecoveryPlanPreviewSummaryRead)
def preview_project_recovery_plans(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RecoveryPlanPreviewSummaryRead:
    project = _get_project_or_404(db, project_id)
    preview = service.preview_recovery_plans(db, project)
    return RecoveryPlanPreviewSummaryRead(
        project_id=project.id,
        current_action=preview["current_action"],
        blocked_task_count=preview["blocked_task_count"],
        stuck_signal_count=preview["stuck_signal_count"],
        persisted=[RecoveryPlanRead.model_validate(item) for item in preview["persisted"]],
        derived_candidates=preview["derived_candidates"],
        stored_count=preview["stored_count"],
        derived_candidate_count=preview["derived_candidate_count"],
        generated_at=preview["generated_at"],
    )


@app.post("/api/projects/{project_id}/recovery-plans", response_model=RecoveryPlanRead)
def create_project_recovery_plan(
    project_id: int,
    payload: RecoveryPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RecoveryPlanRead:
    project = _get_project_or_404(db, project_id)
    if payload.related_agent_id is not None:
        _require_project_agent(db, project, payload.related_agent_id, resource_name="Recovery plan agent")
    if payload.related_task_id is not None:
        _require_project_task(db, project, payload.related_task_id, resource_name="Recovery plan task")
    plan = service.create_recovery_plan(db, project, payload.model_dump())
    return RecoveryPlanRead.model_validate(plan)


@app.post("/api/recovery-plans/{plan_id}/select", response_model=RecoveryPlanRead)
def select_project_recovery_plan(
    plan_id: int,
    payload: RecoveryPlanSelectRequest,
    request: Request,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> RecoveryPlanRead:
    plan = _get_recovery_plan_or_404(db, plan_id)
    _require_project_scope("Recovery plan", plan.project_id, project_id)
    try:
        plan = service.select_recovery_action(db, plan_id, payload.action)
    except ValueError as exc:
        raise HTTPException(status_code=400 if "not found" not in str(exc).lower() else 404, detail=str(exc)) from exc
    return RecoveryPlanRead.model_validate(plan)


@app.post("/api/projects", response_model=ProjectRead)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> Project:
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
def import_existing_folder(
    payload: ImportFolderRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportFolderResponse:
    try:
        folder = resolve_local_path(payload.folder_path, must_exist=True, must_be_dir=True)
    except PathValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    project_name = payload.name.strip() if payload.name and payload.name.strip() else folder.name
    existing_matches = coordinator._workspace_projects(db, folder)
    project = existing_matches[0] if existing_matches else service.create_project(
        db,
        name=project_name,
        idea=f"Imported existing codebase from {folder.as_posix()}.",
        workspace_path=folder.as_posix(),
        provider="codex",
        runner_mode="dry_run",
        manager_mode="deterministic",
    )
    project.runner_mode = "dry_run"
    project.manager_mode = "deterministic"
    if project.settings is not None:
        project.settings.runner_mode = "dry_run"
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
def list_projects(
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ProjectRead]:
    return [ProjectRead(**project) for project in service.list_projects(db, include_archived=include_archived)]


@app.get("/api/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, project))


@app.post("/api/projects/{project_id}/scan-codebase", response_model=CodebaseMapRead)
def scan_codebase(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CodebaseMapRead:
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
def scan_codebase_targeted(
    project_id: int,
    payload: TargetedCodebaseScanRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CodebaseMapRead:
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
def get_codebase_map(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CodebaseMapRead:
    project = _get_project_or_404(db, project_id)
    return CodebaseMapRead.model_validate(import_service.get_codebase_map(db, project))


@app.get("/api/projects/{project_id}/codebase-understanding", response_model=CodebaseUnderstandingRead)
def get_codebase_understanding(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> CodebaseUnderstandingRead:
    project = _get_project_or_404(db, project_id)
    return CodebaseUnderstandingRead.model_validate(import_service.get_codebase_understanding(db, project))


@app.post("/api/projects/{project_id}/import/interview-choice", response_model=ImportInterviewChoiceResponse)
def choose_import_interview(
    project_id: int,
    payload: ImportInterviewChoiceRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportInterviewChoiceResponse:
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
def get_import_safety(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    _require_imported_project(project)
    safety = import_service.ensure_safety(db, project, create_if_missing=False)
    if safety is None:
        raise HTTPException(status_code=404, detail="Import safety not found")
    return ImportedCodebaseSafetyRead.model_validate(safety)


@app.patch("/api/projects/{project_id}/import-safety", response_model=ImportedCodebaseSafetyRead)
def patch_import_safety(
    project_id: int,
    payload: ImportedCodebaseSafetyUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    _require_imported_project(project)
    safety = import_service.update_safety(db, project, payload.model_dump(exclude_unset=True))
    service.events.publish(db, project.id, "import_safety_updated", {"project_id": project.id, "write_permission_status": safety.write_permission_status})
    return ImportedCodebaseSafetyRead.model_validate(safety)


@app.post("/api/projects/{project_id}/write-permission", response_model=ImportedCodebaseSafetyRead)
def update_write_permission(
    project_id: int,
    payload: WritePermissionRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportedCodebaseSafetyRead:
    project = _get_project_or_404(db, project_id)
    _require_imported_project(project)
    safety = import_service.update_safety(db, project, {"write_permission_status": payload.write_permission_status})
    service.events.publish(db, project.id, "write_permission_updated", {"project_id": project.id, "write_permission_status": payload.write_permission_status})
    return ImportedCodebaseSafetyRead.model_validate(safety)


@app.get("/api/projects/{project_id}/agents-md/status", response_model=AgentInstructionsStatusRead)
def get_agents_md_status(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentInstructionsStatusRead:
    project = _get_project_or_404(db, project_id)
    return AgentInstructionsStatusRead.model_validate(import_service.get_agents_status(db, project))


@app.post("/api/projects/{project_id}/agents-md/propose", response_model=AgentsMdProposalRead)
def propose_agents_md(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentsMdProposalRead:
    project = _get_project_or_404(db, project_id)
    return AgentsMdProposalRead(**import_service.propose_agents_md(db, project))


@app.post("/api/projects/{project_id}/manager/imported-codebase-request", response_model=ImportedCodebaseRequestRead)
def imported_codebase_request(
    project_id: int,
    payload: ImportedCodebaseRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ImportedCodebaseRequestRead:
    project = _get_project_or_404(db, project_id)
    return ImportedCodebaseRequestRead(**import_service.analyze_manager_request(db, project, message=payload.message))


@app.patch("/api/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    updated = service.update_project(db, project, name=payload.name, idea=payload.idea)
    return ProjectRead(**service._serialize_project_card(db, updated))


@app.post("/api/projects/{project_id}/open", response_model=ProjectRead)
def open_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    opened = service.open_project(db, project)
    return ProjectRead(**service._serialize_project_card(db, opened))


@app.post("/api/projects/{project_id}/pause", response_model=ProjectRead)
def pause_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.pause_project(db, project)))


@app.post("/api/projects/{project_id}/resume", response_model=ProjectRead)
def resume_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.resume_project(db, project)))


@app.post("/api/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.archive_project(db, project)))


@app.post("/api/projects/{project_id}/unarchive", response_model=ProjectRead)
def unarchive_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.unarchive_project(db, project)))


@app.post("/api/projects/{project_id}/pin", response_model=ProjectRead)
def pin_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.pin_project(db, project)))


@app.post("/api/projects/{project_id}/unpin", response_model=ProjectRead)
def unpin_project(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectRead:
    project = _get_project_or_404(db, project_id)
    return ProjectRead(**service._serialize_project_card(db, service.unpin_project(db, project)))


@app.get("/api/projects/{project_id}/workspace", response_model=ProjectWorkspaceRead)
async def get_project_workspace(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectWorkspaceRead:
    project = _get_project_or_404(db, project_id)
    payload = await service.get_project_workspace(db, project)
    return ProjectWorkspaceRead(**payload)


@app.get("/api/projects/{project_id}/action", response_model=ProjectActionRead)
async def get_project_action(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectActionRead:
    project = _get_project_or_404(db, project_id)
    return ProjectActionRead(**(await service.get_project_action(db, project)))


@app.get("/api/projects/{project_id}/actions", response_model=list[ProjectActionRead])
async def get_project_actions(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ProjectActionRead]:
    project = _get_project_or_404(db, project_id)
    return [ProjectActionRead(**item) for item in await service.list_project_actions(db, project)]


@app.post("/api/projects/{project_id}/actions/{action_id}/resolve")
def resolve_project_action(
    project_id: int,
    action_id: str,
    payload: ProjectActionResolveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> dict[str, Any]:
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
def get_manager_messages(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ManagerMessageRead]:
    project = _get_project_or_404(db, project_id)
    return [ManagerMessageRead(**item) for item in service.list_manager_messages(db, project)]


@app.post("/api/projects/{project_id}/manager/messages", response_model=ManagerMessageRead)
async def create_manager_message(
    project_id: int,
    payload: ManagerMessageCreate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    result = await service.manager_message(db, project, payload.message)
    return ManagerMessageRead(**result["message"])


@app.post("/api/projects/{project_id}/manager/ask-next", response_model=ManagerMessageRead)
async def ask_manager_next(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    return ManagerMessageRead(**(await service.manager_ask_next(db, project)))


@app.post("/api/projects/{project_id}/manager/generate-update", response_model=ManagerMessageRead)
async def generate_manager_update(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerMessageRead:
    project = _get_project_or_404(db, project_id)
    return ManagerMessageRead(**(await service.manager_generate_update(db, project)))


@app.get("/api/projects/{project_id}/questions/pending", response_model=list[ManagerQuestionRead])
def get_pending_questions(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ManagerQuestionRead]:
    project = _get_project_or_404(db, project_id)
    return [ManagerQuestionRead(**item) for item in service.list_pending_questions(db, project, mutate=False)]


@app.post("/api/questions/{question_id}/answer", response_model=ManagerQuestionRead)
def answer_question(
    question_id: int,
    payload: ManagerQuestionAnswer,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerQuestionRead:
    if payload.project_id is None:
        raise HTTPException(status_code=400, detail="project_id is required")
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
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.post("/api/questions/{question_id}/auto-decide", response_model=ManagerQuestionRead)
def auto_decide_question(
    question_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerQuestionRead:
    try:
        question = service.auto_decide_question(db, question_id, project_id=project_id)
        return ManagerQuestionRead(**service._serialize_question(question))
    except ValueError as exc:
        status_code = 400 if "High-impact" in str(exc) or "no selectable options" in str(exc).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/approvals/pending", response_model=list[ApprovalRequestRead])
def get_pending_approvals(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ApprovalRequestRead]:
    project = _get_project_or_404(db, project_id)
    return [ApprovalRequestRead(**item) for item in service.list_pending_approvals(db, project)]


@app.post("/api/approvals/{approval_id}/approve-once", response_model=ApprovalRequestRead)
def approve_once(
    approval_id: int,
    payload: ApprovalResolveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ApprovalRequestRead:
    try:
        approval = service.approve_once(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/deny", response_model=ApprovalRequestRead)
def deny_approval(
    approval_id: int,
    payload: ApprovalResolveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ApprovalRequestRead:
    try:
        approval = service.deny_approval(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/approvals/{approval_id}/allow-for-project", response_model=ApprovalRequestRead)
def allow_approval_for_project(
    approval_id: int,
    payload: ApprovalResolveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ApprovalRequestRead:
    try:
        approval = service.allow_approval_for_project(db, approval_id, project_id=payload.project_id)
        return ApprovalRequestRead(**service._serialize_approval(approval))
    except ValueError as exc:
        status_code = 400 if "cannot be allowed for the whole project" in str(exc).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/manager/queue", response_model=ManagerQueueRead)
def get_manager_queue(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerQueueRead:
    project = _get_project_or_404(db, project_id)
    return ManagerQueueRead(**service.get_manager_queue(db, project, mutate=False))


@app.post("/api/projects/{project_id}/widgets", response_model=ProjectSettingsRead)
def update_project_widgets(
    project_id: int,
    payload: WorkspaceWidgetsUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectSettingsRead:
    project = _get_project_or_404(db, project_id)
    try:
        return service.update_workspace_widgets(db, project, payload.widgets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/handoffs", response_model=list[HandoffListItemRead])
def list_handoffs(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[HandoffListItemRead]:
    return [HandoffListItemRead(**item) for item in service.list_handoffs(db)]


@app.get("/api/projects/{project_id}/handoff", response_model=HandoffListItemRead)
def get_project_handoff(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> HandoffListItemRead:
    project = _get_project_or_404(db, project_id)
    return HandoffListItemRead(**service.get_project_handoff_summary(db, project))


@app.get("/api/diagnostics/reports", response_model=list[DiagnosticReportListItemRead])
def diagnostics_reports(_: None = Depends(_require_bridge_token)) -> list[DiagnosticReportListItemRead]:
    return [DiagnosticReportListItemRead(**item) for item in service.recent_diagnostic_reports()]


@app.get("/api/tools", response_model=list[ToolCatalogItemRead])
def get_tools(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[ToolCatalogItemRead]:
    return [ToolCatalogItemRead(**item) for item in service.get_tool_catalog(db)]


@app.put("/api/tools/{tool_id}/permission", response_model=ToolPermissionRead)
def update_tool_permission(
    tool_id: str,
    payload: ToolPermissionUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ToolPermissionRead:
    try:
        return ToolPermissionRead(**service.update_tool_permission(db, tool_id, payload.permission_policy))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/skills", response_model=list[SkillRead])
async def get_skills(
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[SkillRead]:
    return [SkillRead(**item) for item in await service.list_skills(db)]


@app.post("/api/projects/{project_id}/docs/generate", response_model=DocGenerationResponse)
async def generate_docs(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> DocGenerationResponse:
    project = _get_project_or_404(db, project_id)
    try:
        result = await service.generate_project_docs(db, project)
        return DocGenerationResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/interview/start", response_model=InterviewSessionRead)
async def start_interview(
    project_id: int,
    payload: InterviewStartRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    session = await service.start_interview(db, project, payload.question_budget, payload.question_count)
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.get("/api/projects/{project_id}/interview", response_model=InterviewSessionRead | None)
def get_interview(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead | None:
    project = _get_project_or_404(db, project_id)
    session = db.scalar(select(InterviewSession).where(InterviewSession.project_id == project_id).order_by(InterviewSession.id.desc()))
    return _serialize_interview(project, session) if session else None


@app.post("/api/projects/{project_id}/interview/generate-next", response_model=InterviewSessionRead)
async def generate_next_interview(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    try:
        session = await service.generate_next_interview(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.post("/api/interview/questions/{question_id}/answer", response_model=InterviewSessionRead)
def answer_interview_question(
    question_id: int,
    payload: InterviewQuestionAnswerRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead:
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
def answer_interview(
    project_id: int,
    payload: InterviewAnswerRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead:
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
def finish_interview(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> InterviewSessionRead:
    project = _get_project_or_404(db, project_id)
    try:
        session = service.finish_interview(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.flush()
    db.refresh(session)
    return _serialize_interview(project, session)


@app.get("/api/projects/{project_id}/understanding", response_model=ProjectUnderstandingRead)
def get_project_understanding(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ProjectUnderstandingRead:
    project = _get_project_or_404(db, project_id)
    return _serialize_understanding(project)


@app.post("/api/projects/{project_id}/plan/generate", response_model=PlanRead)
async def generate_plan(
    project_id: int,
    payload: PlanGenerateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> Plan:
    project = _get_project_or_404(db, project_id)
    try:
        plan = await service.generate_plan(db, project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.flush()
    db.refresh(plan)
    return plan


@app.get("/api/projects/{project_id}/plan", response_model=PlanRead | None)
def get_plan(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> Plan | None:
    return db.scalar(select(Plan).where(Plan.project_id == project_id).order_by(Plan.version.desc()))


@app.post("/api/projects/{project_id}/plan/approve", response_model=PlanRead)
async def approve_plan(
    project_id: int,
    payload: PlanApproveRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> Plan:
    project = _get_project_or_404(db, project_id)
    try:
        plan = await service.approve_plan(db, project, payload.action, payload.note)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    db.flush()
    db.refresh(plan)
    return plan


@app.get("/api/projects/{project_id}/agents", response_model=list[AgentRead])
def get_agents(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[AgentRead]:
    _get_project_or_404(db, project_id)
    return [AgentRead(**item) for item in service._sorted_workspace_agents(db, project_id)]


@app.get("/api/projects/{project_id}/reservations", response_model=list[ReservationRead])
def get_reservations(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[PathReservation]:
    _get_project_or_404(db, project_id)
    return service.list_reservations(db, project_id)


@app.post("/api/projects/{project_id}/agents/start", response_model=AgentActionResponse)
async def start_project_agents(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    await service.start_idle_agents(db, project)
    return AgentActionResponse(ok=True, message="Started idle agents where work was available.")


@app.post("/api/agents/{agent_id}/start", response_model=AgentActionResponse)
async def start_agent(
    agent_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    agent = _require_project_agent(db, project, agent_id)
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
async def stop_agent(
    agent_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    agent = _require_project_agent(db, project, agent_id)
    await service.stop_agent(db, agent)
    return AgentActionResponse(ok=True, message="Agent stop requested.")


@app.post("/api/agents/{agent_id}/pause", response_model=AgentActionResponse)
async def pause_agent(
    agent_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    agent = _require_project_agent(db, project, agent_id)
    await service.pause_agent(db, agent)
    return AgentActionResponse(ok=True, message="Agent paused.")


@app.get("/api/agents/{agent_id}/logs", response_model=LogRead)
def get_agent_logs(
    agent_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> LogRead:
    project = _get_project_or_404(db, project_id)
    agent = _require_project_agent(db, project, agent_id)
    path, content = service.read_logs(db, agent)
    return LogRead(agent_id=agent_id, logs_path=path, content=content)


@app.get("/api/projects/{project_id}/tasks", response_model=list[TaskRead])
def get_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[Task]:
    _get_project_or_404(db, project_id)
    return list(db.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.priority.asc(), Task.id.asc())))


@app.post("/api/projects/{project_id}/tasks/generate", response_model=TaskGenerationResponse)
async def generate_tasks(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> TaskGenerationResponse:
    project = _get_project_or_404(db, project_id)
    tasks, manager_mode_used = await service.generate_tasks(db, project)
    return TaskGenerationResponse(count=len(tasks), manager_mode_used=manager_mode_used)


@app.post("/api/tasks/{task_id}/start", response_model=AgentActionResponse)
async def start_task(
    task_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    task = _require_project_task(db, project, task_id)
    workers = list(db.scalars(select(Agent).where(Agent.project_id == project.id, Agent.kind == "worker")))
    if not workers:
        workers = service.initialize_build_roster(db, project)
        if not workers:
            return AgentActionResponse(ok=False, message="No worker roster is available yet. Approve the swarm plan or initialize the build roster first.")
    candidates = sorted(
        [
            agent
            for agent in workers
            if agent.status in {"idle", "waiting", "done", "stopped"} and service._agent_matches_task(agent, task)
        ],
        key=lambda agent: (service._agent_task_match_score(agent, task), -agent.id),
        reverse=True,
    )
    for agent in candidates:
        if not service._dependencies_met(db, task):
            return AgentActionResponse(ok=False, message="Task is waiting on dependencies.")
        if not can_assign_task(agent, task, workers, service._is_git_workspace(project)):
            continue
        run = await service.start_agent_task(db, project, agent, task)
        return AgentActionResponse(ok=True, message="Task started.", run_id=run.id)
    if candidates:
        task.status = "waiting_on_paths"
        task.waiting_reason = task.waiting_reason or "Another agent owns overlapping paths."
        return AgentActionResponse(ok=False, message=task.waiting_reason)
    return AgentActionResponse(ok=False, message="No idle worker is available.")


@app.post("/api/tasks/{task_id}/complete", response_model=AgentActionResponse)
async def complete_task(
    task_id: int,
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> AgentActionResponse:
    project = _get_project_or_404(db, project_id)
    task = _require_project_task(db, project, task_id)
    await service.complete_task_by_user(db, task)
    return AgentActionResponse(ok=True, message="Task marked done.")


@app.post("/api/runs/{run_id}/report", response_model=ManagerWorkerDecision)
async def submit_run_report(
    run_id: int,
    payload: RunReportRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerWorkerDecision:
    run = db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        return await service.ingest_worker_report(db, run, payload)
    except ValueError as exc:
        status_code = 409 if "already recorded" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/events", response_model=list[EventRead])
def get_events(
    project_id: int,
    after_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> list[EventRead]:
    _get_project_or_404(db, project_id)
    return service.events.list_events(db, project_id, after_id)


@app.get("/api/projects/{project_id}/stream")
async def stream_events(
    project_id: int,
    after_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> StreamingResponse:
    _get_project_or_404(db, project_id)
    generator = service.events.stream(project_id, after_id)
    return StreamingResponse(generator, media_type="text/event-stream")


@app.post("/api/projects/{project_id}/manager/message")
async def manager_message(
    project_id: int,
    payload: ManagerMessageRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> dict[str, Any]:
    project = _get_project_or_404(db, project_id)
    reply = await service.manager_message(db, project, payload.message)
    return {"reply": reply}


@app.post("/api/projects/{project_id}/manager/next-step", response_model=ManagerWorkerDecision)
async def manager_next_step(
    project_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(_require_bridge_token),
) -> ManagerWorkerDecision:
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
