export type ProviderId = "codex" | "ollama" | "openai_api" | "anthropic_api" | "xai_api" | "claude_code" | "custom";
export type StartupProviderChoice = ProviderId;
export type StartupStartMode = "new_project" | "guided_walkthrough";
export type RunnerMode = "auto" | "cli" | "app_server" | "dry_run";
export type ManagerMode = "auto" | "provider" | "codex" | "deterministic";
export type ProjectSourceType = "idea" | "existing_folder" | "cloned_repo" | "docs_import";
export type ImportMode = "linked" | "copied" | "cloned";
export type ScanStatus = "not_started" | "in_progress" | "completed" | "failed";
export type WritePermissionStatus = "read_only" | "write_allowed" | "limited_write";
export type ScanDepth = "shallow" | "standard" | "targeted" | "deep";
export type CodebaseSize = "small" | "medium" | "large" | "huge";
export type ImportInterviewChoice = "skip" | "quick" | "full" | "manager_decides";
export type ReasoningEffort = "minimal" | "low" | "medium" | "high";
export type SandboxMode = "workspace-write" | "read-only";
export type ApprovalPolicy = "on-request" | "untrusted" | "never";
export type ThemeMode = "system" | "dark" | "light";
export type StartupBehavior = "dashboard" | "last_project" | "restore_previous_page";
export type AuthJobMethod = "chatgpt" | "device_auth" | "api_key" | "logout";
export type AuthJobStatus = "queued" | "running" | "succeeded" | "failed";
export type StartupMode = "first_time" | "regular" | "error" | "degraded";
export type StartupOverallStatus = "starting" | "ready" | "retrying" | "error" | "degraded";
export type StartupCheckStatus = "passed" | "failed" | "warning" | "skipped";
export type ManagerMessageType =
  | "normal_update"
  | "user_message"
  | "manager_question"
  | "command_approval"
  | "tool_approval"
  | "milestone_report"
  | "blocker_report"
  | "handoff_report"
  | "system_notice";
export type QuestionImpact = "low" | "medium" | "high";
export type QuestionStatus = "pending" | "answered" | "auto_decided" | "cancelled";
export type ApprovalRequestType = "command" | "tool" | "plugin" | "connected_app";
export type ApprovalRequestStatus = "pending" | "approved_once" | "denied" | "allowed_for_project" | "expired";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type ProjectActionType = "no_action" | "manager_question" | "command_approval" | "tool_approval" | "blocker" | "handoff_ready" | "degraded" | "paused" | "error";
export type ProjectActionSeverity = "info" | "warning" | "danger" | "success";
export type AgentDisplayStatus = "active" | "thinking" | "coding" | "running" | "reviewing" | "monitoring" | "waiting" | "idle" | "blocked" | "error" | "retired";
export type AgentStatus =
  | "idle"
  | "starting"
  | "working"
  | "waiting"
  | "needs_review"
  | "blocked"
  | "done"
  | "stopped"
  | "error";
export type TaskStatus = "backlog" | "assigned" | "working" | "waiting_on_paths" | "needs_review" | "done" | "blocked";
export type InterviewCategory =
  | "product goal"
  | "target users"
  | "MVP scope"
  | "core features"
  | "nice-to-have features"
  | "platform/runtime"
  | "UI/UX style"
  | "data/storage"
  | "authentication/security"
  | "integrations/connectors"
  | "agent/tool behavior"
  | "approvals/sandboxing"
  | "testing/validation"
  | "deployment/distribution"
  | "performance constraints"
  | "privacy/local-first constraints"
  | "future expansion"
  | "handoff format";
export type InterviewQuestionState = "pending" | "answered" | "superseded" | "cancelled";
export type InterviewQuestionSource = "manager_ai" | "fallback_generated";
export type SwarmOptimizationMode = "fastest_build" | "balanced" | "high_quality" | "documentation_heavy" | "research_planning" | "massive_codebase" | "manager_decides";
export type SwarmAggressiveness = "small" | "medium" | "large" | "maximum" | "manager_decides";
export type DocsDepth = "minimal" | "standard" | "detailed" | "publishable";
export type TestingDepth = "minimal" | "standard" | "extensive" | "release_grade";
export type SwarmRisk = "low" | "medium" | "high";
export type SwarmPlanStatus = "pending_approval" | "approved" | "active" | "spawned" | "superseded" | "rejected";
export type SwarmAgentSpecStatus = "planned" | "spawned" | "deferred" | "retire_pending" | "retired" | "cancelled";
export type SwarmEventType =
  | "swarm_plan_created"
  | "swarm_plan_approved"
  | "agent_spec_created"
  | "agent_spawned"
  | "agent_retired"
  | "agent_reassigned"
  | "swarm_scaled_up"
  | "swarm_scaled_down"
  | "path_conflict_detected"
  | "bottleneck_detected"
  | "strategy_changed";
export type WidgetScope = "dashboard" | "project";
export type WidgetArea =
  | "dashboard_main"
  | "dashboard_right"
  | "dashboard_bottom"
  | "dashboard_custom"
  | "project_right_sidebar"
  | "project_bottom"
  | "project_overview"
  | "project_custom";
export type WidgetSize = "small" | "medium" | "large" | "full";
export type WidgetDataStatus = "ready" | "warning" | "empty" | "coming_soon" | "needs_setup" | "unsupported";
export type WidgetCategory = "Attention" | "Swarm" | "Agents" | "Safety" | "Quality" | "Docs" | "Models" | "Tools" | "Diagnostics" | "Handoff" | "Change Management";

export interface Project {
  id: number;
  name: string;
  slug: string | null;
  idea: string;
  workspace_path: string;
  status: string;
  runner_mode: RunnerMode;
  manager_mode: ManagerMode;
  created_by: string | null;
  docs_path: string | null;
  final_report_json: Record<string, unknown> | null;
  pinned: boolean;
  archived_at: string | null;
  last_opened_at: string | null;
  latest_milestone: string | null;
  latest_activity: string | null;
  handoff_status: string | null;
  source_type: ProjectSourceType;
  source_path: string | null;
  import_mode: ImportMode | null;
  imported_at: string | null;
  scan_status: ScanStatus;
  last_indexed_at: string | null;
  write_permission_status: WritePermissionStatus;
  display_status: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectUpdatePayload {
  name?: string;
  idea?: string;
}

export interface InterviewOption {
  id: string;
  label: string;
  description: string;
}

export interface InterviewQuestion {
  id: number;
  project_id: number;
  index: number;
  question: string;
  why: string | null;
  category: InterviewCategory | null;
  impact: QuestionImpact;
  options: InterviewOption[];
  allow_custom_answer: boolean;
  selected_option_id: string | null;
  selected_text: string | null;
  custom_answer: string | null;
  affects: string[];
  status: InterviewQuestionState;
  question_source: InterviewQuestionSource;
  answered_at: string | null;
  rationale: string | null;
  selected_option: string | null;
}

export interface InterviewSession {
  id: number;
  project_id: number;
  question_budget: number;
  questions_asked: number;
  questions_remaining: number;
  manager_mode: ManagerMode;
  stopped_early: boolean;
  stop_reason: string | null;
  confidence: Record<string, number>;
  understanding_summary: string | null;
  known_facts: Record<string, unknown>;
  unknowns: Record<string, unknown>;
  assumptions: string[];
  constraints: string[];
  generation_sources: InterviewQuestionSource[];
  question_count: number;
  current_index: number;
  status: string;
  questions: InterviewQuestion[];
}

export interface ProjectUnderstanding {
  project_id: number;
  summary: string;
  known_facts_json: Record<string, unknown>;
  unknowns_json: Record<string, unknown>;
  assumptions_json: string[];
  constraints_json: string[];
  confidence_by_category_json: Record<string, number>;
  updated_at: string;
}

export interface ImportFolderResponse {
  project: Project;
  scan_started: boolean;
  warnings: string[];
  recommended_next_route: string;
}

export interface CodebaseMap {
  project_id: number;
  source_path: string;
  languages_json: string[];
  frameworks_json: string[];
  package_managers_json: string[];
  build_tools_json: string[];
  test_frameworks_json: string[];
  entry_points_json: string[];
  build_commands_json: string[];
  test_commands_json: string[];
  important_folders_json: string[];
  docs_json: string[];
  agent_instructions_json: Array<Record<string, unknown>>;
  config_files_json: string[];
  ci_config_json: string[];
  deployment_config_json: string[];
  git_status_json: Record<string, unknown>;
  risk_flags_json: string[];
  scan_depth: ScanDepth | string;
  codebase_size: CodebaseSize | string;
  recommended_scan_strategy: string;
  indexed_areas_json: string[];
  unindexed_areas_json: string[];
  created_at: string;
  updated_at: string;
}

export interface CodebaseUnderstanding {
  project_id: number;
  summary: string;
  architecture_summary: string;
  detected_stack_json: string[];
  likely_run_instructions_json: string[];
  likely_test_instructions_json: string[];
  risk_summary: string;
  missing_context_json: string[];
  suggested_next_steps_json: string[];
  recommended_interview_mode: ImportInterviewChoice;
  confidence_by_area_json: Record<string, number>;
  generation_mode: string;
  created_at: string;
  updated_at: string;
}

export interface ImportedCodebaseSafety {
  project_id: number;
  read_only_scan_completed: boolean;
  write_permission_status: WritePermissionStatus;
  require_snapshot_before_edits: boolean;
  require_approval_for_dependency_changes: boolean;
  require_approval_for_test_commands: boolean;
  require_approval_for_build_commands: boolean;
  require_approval_for_formatting: boolean;
  require_approval_for_package_file_changes: boolean;
  destructive_commands_blocked: boolean;
  updated_at: string;
}

export interface AgentInstructionsStatus {
  project_id: number;
  has_agents_md: boolean;
  agents_md_path: string | null;
  summary: string;
  recommended_action: "none" | "create" | "update" | "review";
  created_at: string;
  updated_at: string;
}

export interface AgentsMdProposal {
  project_id: number;
  recommended_path: string;
  summary: string;
  proposal_markdown: string;
}

export interface ImportInterviewChoiceResponse {
  next_route: string;
  questions: InterviewQuestion[];
  manager_note: string;
}

export interface ImportedCodebaseRequestResult {
  project_id: number;
  classification: "analysis" | "bugfix" | "feature" | "refactor" | "docs" | "test" | "security" | "performance" | "migration" | "cleanup" | "unknown";
  decision:
    | "answer_directly"
    | "ask_quick_question"
    | "create_task_plan"
    | "run_targeted_scan"
    | "request_command_approval"
    | "request_write_permission"
    | "recommend_snapshot_first";
  manager_note: string;
  suggested_questions: string[];
  targeted_scan_targets: string[];
  warnings: string[];
}

export interface Plan {
  id: number;
  project_id: number;
  version: number;
  content_markdown: string;
  status: string;
  summary_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: number;
  project_id: number;
  name: string;
  role: string;
  kind: string;
  status: AgentStatus;
  current_task_id: number | null;
  swarm_plan_id?: number | null;
  workspace_path: string;
  archetype?: string | null;
  mission?: string | null;
  retire_when?: string | null;
  session_ref: string | null;
  locked_paths_json: string[] | null;
  failure_count: number;
  last_report_summary: string | null;
  active_model: string | null;
  active_reasoning_effort: string | null;
  active_runner_type: string | null;
  current_action: string | null;
  current_task_title?: string | null;
  display_status?: AgentDisplayStatus | string;
  runner_mode?: string | null;
  needs_approval?: boolean;
  last_update: string;
}

export interface Task {
  id: number;
  project_id: number;
  assigned_agent_id: number | null;
  title: string;
  goal: string;
  scope: string;
  agent_role: string | null;
  milestone: string | null;
  allowed_paths_json: string[];
  forbidden_paths_json: string[];
  validation_steps_json: string[];
  success_criteria_json: string[];
  estimated_complexity: "small" | "medium" | "large";
  dependencies_json: number[];
  status: TaskStatus;
  failure_count: number;
  waiting_reason: string | null;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface Reservation {
  id: number;
  project_id: number;
  task_id: number;
  agent_id: number;
  path: string;
  created_at: string;
  released_at: string | null;
}

export interface ProjectEvent {
  id: number;
  project_id: number;
  event_type: string;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface AppEvent {
  id: number;
  type: string;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface WidgetDefinition {
  id: number;
  widget_type: string;
  title: string;
  description: string;
  scope: WidgetScope;
  default_area: WidgetArea;
  default_size: WidgetSize;
  category: WidgetCategory | string;
  requires_project: boolean;
  requires_tool: string | null;
  coming_soon: boolean;
  risk_level: RiskLevel | null;
}

export interface WidgetInstance {
  id: number;
  scope: WidgetScope;
  project_id: number | null;
  widget_type: string;
  area: WidgetArea;
  order_index: number;
  size: WidgetSize;
  collapsed: boolean;
  enabled: boolean;
  config_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WidgetDataResponse {
  widget_instance_id: number;
  widget_type: string;
  title: string;
  status: WidgetDataStatus;
  data_json: Record<string, unknown>;
  empty_state: string | null;
  warnings_json: string[];
  updated_at: string;
}

export interface WidgetSummary {
  scope: WidgetScope;
  project_id: number | null;
  instances: WidgetInstance[];
  data: WidgetDataResponse[];
  catalog: WidgetDefinition[];
}

export interface CodexStatus {
  selected_provider: ProviderId;
  selected_provider_label: string;
  cli_detected: boolean;
  cli_version: string | null;
  login_status: string;
  auth_mode: string | null;
  authenticated: boolean;
  runtime_ready: boolean;
  runtime_summary: string | null;
  app_server_supported: boolean;
  app_server_handshake_status: string;
  app_server_transport: string;
  effective_runner_mode: string;
  dry_run_available: boolean;
  runtime_directory: string;
  diagnostics_directory: string | null;
  backend_port: number;
  frontend_port: number | null;
  active_runs: Array<Record<string, unknown>>;
  current_settings_summary: ProjectSettings | null;
  selected_manager_model: string | null;
  selected_default_worker_model: string | null;
  available_models: string[];
  provider_statuses: ProviderStatus[];
  mcp_servers: Array<Record<string, unknown>>;
  configured_plugins: string[];
  local_skills: string[];
  current_auth_job: AuthJob | null;
  notes: string[];
  startup_summary: StartupStatus | null;
  app_state_summary: AppState | null;
}

export interface AuthJob {
  id: string;
  method: AuthJobMethod;
  status: AuthJobStatus;
  started_at: string;
  finished_at: string | null;
  exit_code: number | null;
  message: string;
  auth_mode_after: string | null;
  log_path: string | null;
  output_lines: string[];
}

export interface AuthState {
  authenticated: boolean;
  auth_mode: string | null;
  login_status: string;
  cli_detected: boolean;
  provider: ProviderId;
  current_job: AuthJob | null;
  chatgpt_supported: boolean;
  device_auth_supported: boolean;
  api_key_supported: boolean;
  provider_statuses: ProviderStatus[];
  notes: string[];
}

export interface ProviderStatus {
  provider: ProviderId;
  label: string;
  cli_detected: boolean;
  cli_version: string | null;
  authenticated: boolean;
  auth_mode: string | null;
  auth_status_detectable: boolean;
  login_status: string;
  supports_model_override: boolean;
  supports_reasoning_effort: boolean;
  supports_app_server: boolean;
  supports_builtin_auth: boolean;
  runtime_ready: boolean;
  runtime_summary: string | null;
  requires_adapter_command: boolean;
  adapter_command_configured: boolean;
  adapter_command_detected: boolean;
  provider_endpoint_configured: boolean;
  available_models: string[];
  notes: string[];
}

export interface ProjectSettings {
  project_id: number;
  provider: ProviderId;
  manager_model: string | null;
  default_worker_model: string | null;
  manager_reasoning_effort: ReasoningEffort | null;
  default_worker_reasoning_effort: ReasoningEffort | null;
  per_role_model_overrides_json: Record<string, string>;
  per_role_reasoning_overrides_json: Record<string, string>;
  provider_endpoint: string | null;
  adapter_command: string | null;
  adapter_args_json: string[];
  runner_mode: RunnerMode;
  sandbox_mode: SandboxMode;
  approval_policy: ApprovalPolicy;
  workspace_widgets_json: string[];
  approval_overrides_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SwarmPreferences {
  project_id: number;
  optimization_mode: SwarmOptimizationMode;
  swarm_aggressiveness: SwarmAggressiveness;
  max_agents: number;
  require_approval_above_agent_count: number;
  allow_dynamic_spawning: boolean;
  allow_dynamic_retirement: boolean;
  docs_depth: DocsDepth;
  testing_depth: TestingDepth;
  created_at: string;
  updated_at: string;
}

export interface AgentArchetype {
  id: number;
  name: string;
  purpose: string;
  default_guidelines: string;
  default_tools_json: string[];
  default_permissions_json: Record<string, unknown>;
  spawn_triggers_json: string[];
  retirement_triggers_json: string[];
  risk_profile: SwarmRisk;
}

export interface SwarmAgentSpec {
  id: number;
  swarm_plan_id: number;
  project_id: number;
  archetype: string;
  name: string;
  mission: string;
  model_policy: string;
  toolset_json: string[];
  allowed_paths_json: string[];
  forbidden_paths_json: string[];
  spawn_phase: string;
  retire_when: string;
  priority: number;
  status: SwarmAgentSpecStatus;
}

export interface SwarmPlan {
  id: number;
  project_id: number;
  milestone_id: number | null;
  mode: SwarmOptimizationMode | string;
  goal: string;
  recommended_agent_count: number;
  max_agent_count: number;
  coordination_risk: SwarmRisk | string;
  path_conflict_risk: SwarmRisk | string;
  expected_bottlenecks_json: string[];
  validation_strategy_json: string[];
  strategy_summary: string;
  approved_by_user: boolean;
  status: SwarmPlanStatus | string;
  created_at: string;
  updated_at: string;
  approval_required: boolean;
  usage_warning: string | null;
  active_agent_count: number;
  current_bottleneck: string | null;
  dynamic_spawning_enabled: boolean;
  dynamic_retirement_enabled: boolean;
  specs: SwarmAgentSpec[];
}

export interface SwarmEvent {
  id: number;
  project_id: number;
  swarm_plan_id: number | null;
  event_type: SwarmEventType | string;
  message: string;
  agent_id: number | null;
  created_at: string;
  metadata_json: Record<string, unknown>;
}

export interface SwarmSpawnResponse {
  ok: boolean;
  message: string;
  swarm_plan: SwarmPlan;
  agents_spawned: number;
  agents_retired: number;
}

export interface ManagerMessage {
  id: number;
  project_id: number;
  role: "user" | "manager" | "system" | "agent";
  message_type: ManagerMessageType;
  content_markdown: string;
  created_at: string;
  related_agent_id: number | null;
  related_task_id: number | null;
  actions_json: Array<Record<string, unknown>> | null;
  resolved_at: string | null;
  metadata_json: Record<string, unknown> | null;
}

export interface ManagerQuestion {
  id: number;
  project_id: number;
  question: string;
  options_json: Array<Record<string, unknown>>;
  impact: QuestionImpact;
  status: QuestionStatus;
  selected_option_id: string | null;
  selected_text: string | null;
  manager_recommendation: string | null;
  auto_decide_at: string | null;
  created_at: string;
  resolved_at: string | null;
  related_task_id: number | null;
  related_agent_id: number | null;
  metadata_json: Record<string, unknown> | null;
}

export interface ApprovalRequest {
  id: number;
  project_id: number;
  request_type: ApprovalRequestType;
  requesting_agent_id: number | null;
  task_id: number | null;
  title: string;
  reason_short: string;
  risk_level: RiskLevel;
  status: ApprovalRequestStatus;
  cwd: string | null;
  request_payload_json: Record<string, unknown>;
  runner_ref: string | null;
  resolved_by: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ProjectAction {
  id: string;
  project_id: number;
  type: ProjectActionType;
  severity: ProjectActionSeverity;
  title: string;
  message: string;
  requesting_agent_id: number | null;
  related_task_id: number | null;
  command_id: number | null;
  tool_request_id: number | null;
  question_id: number | null;
  created_at: string;
  expires_at: string | null;
  auto_decide_at: string | null;
  resolved_at: string | null;
  actions_json: Array<Record<string, unknown>>;
}

export interface ManagerQueueItem {
  id: string;
  type: string;
  title: string;
  status: string;
  related_task_id: number | null;
  related_agent_id: number | null;
  created_at: string;
}

export interface ManagerQueue {
  next_up: ManagerQueueItem[];
  waiting_on_user: ManagerQueueItem[];
  recently_decided: ManagerQueueItem[];
  deferred: ManagerQueueItem[];
}

export interface ProjectWorkflowStep {
  id: string;
  label: string;
  state: "complete" | "current" | "upcoming";
  ordinal: number;
}

export interface ProjectWorkflow {
  current_phase: string;
  current_label: string;
  steps: ProjectWorkflowStep[];
}

export interface ProjectOverviewChecklistItem {
  id: string;
  label: string;
  status: "complete" | "in_progress" | "blocked" | "planned";
  detail: string;
}

export interface ProjectOverview {
  handoff_progress: number;
  readiness_label: string;
  readiness_tone: "good" | "warning" | "danger" | "neutral";
  checklist: ProjectOverviewChecklistItem[];
}

export interface ActivityLogEntry {
  id: number;
  event_type: string;
  created_at: string;
  summary: string;
  detail: string | null;
  severity: ProjectActionSeverity;
  agent_id: number | null;
  agent_name: string | null;
  task_id: number | null;
}

export interface ProjectWorkspace {
  project: Project;
  current_action: ProjectAction;
  action_history: ProjectAction[];
  manager_messages: ManagerMessage[];
  pending_question: ManagerQuestion | null;
  pending_approvals: ApprovalRequest[];
  agents: Agent[];
  manager_queue: ManagerQueue;
  widgets: string[];
  available_widgets: string[];
  widget_instances: WidgetInstance[];
  widget_data: WidgetDataResponse[];
  widget_catalog: WidgetDefinition[];
  reservations: Reservation[];
  task_summary: Record<string, unknown>;
  milestone_summary: Record<string, unknown>;
  workflow: ProjectWorkflow;
  overview: ProjectOverview;
  tasks: Task[];
  activity_log: ActivityLogEntry[];
  degraded_notices: string[];
  swarm_preferences: SwarmPreferences;
  swarm_plan: SwarmPlan | null;
  swarm_events: SwarmEvent[];
}

export interface AppProfile {
  id: number;
  install_id: string | null;
  display_name: string | null;
  preferred_provider_choice: StartupProviderChoice;
  preferred_start_mode: StartupStartMode;
  selected_provider: ProviderId;
  auth_mode: string | null;
  connected_accounts_json: Record<string, unknown>;
  first_run_completed: boolean;
  setup_version_completed: string | null;
  onboarding_completed: boolean;
  default_runner_mode: RunnerMode;
  manager_model: string | null;
  default_worker_model: string | null;
  manager_reasoning_effort: ReasoningEffort | null;
  default_worker_reasoning_effort: ReasoningEffort | null;
  sandbox_mode: SandboxMode;
  approval_policy: ApprovalPolicy;
  theme: ThemeMode;
  startup_behavior: StartupBehavior;
  notification_preferences_json: Record<string, unknown>;
  dashboard_widgets_json: string[];
  dashboard_widget_preferences_json: Record<string, unknown>;
  tool_permission_overrides_json: Record<string, unknown>;
  provider_endpoint: string | null;
  adapter_command: string | null;
  adapter_args_json: string[];
  recent_startup_error_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  last_opened_at: string | null;
}

export interface AppState extends AppProfile {}

export interface StartupCheck {
  name: string;
  required: boolean;
  status: StartupCheckStatus;
  summary: string;
  error_code: string | null;
  details: Record<string, unknown>;
}

export interface StartupStatus {
  mode: StartupMode;
  first_run_completed: boolean;
  setup_version_completed: string | null;
  current_setup_version: string;
  install_id: string;
  startup_attempt: number;
  max_startup_attempts: number;
  overall_status: StartupOverallStatus;
  checks: StartupCheck[];
  recommended_route: "/setup" | "/dashboard" | "/startup-error" | "/startup";
  error_code: string | null;
  error_summary: string | null;
  diagnostic_report_path: string | null;
  degraded_reasons: string[];
  failed_checks: string[];
  startup_started_at: string;
  last_completed_at: string | null;
}

export interface DiagnosticReport {
  path: string;
  summary: string;
  error_code: string | null;
  recommended_fixes: string[];
}

export interface DashboardAttentionItem {
  id: string;
  project_id: number;
  project_name: string;
  project_slug: string | null;
  kind: ProjectActionType | string;
  summary: string;
  detail: string;
  severity: ProjectActionSeverity;
  target: string;
  created_at: string;
}

export interface DashboardBuildItem {
  project_id: number;
  project_name: string;
  project_slug: string | null;
  task_id: number | null;
  task_title: string;
  stage: string;
  agent_name: string | null;
  runner_type: string | null;
  updated_at: string;
}

export interface DashboardSummary {
  sidebar_projects: Project[];
  recent_projects: Project[];
  archive_count: number;
  active_builds: DashboardBuildItem[];
  attention_items: DashboardAttentionItem[];
  blocked_agents: Agent[];
  recent_handoffs: HandoffListItem[];
  runner_status: Record<string, unknown>;
  connected_accounts: Record<string, unknown>;
  model_defaults: Record<string, unknown>;
  widgets: string[];
  available_widgets: string[];
  widget_instances: WidgetInstance[];
  widget_data: WidgetDataResponse[];
  widget_catalog: WidgetDefinition[];
}

export interface HandoffListItem {
  project_id: number;
  project_name: string;
  project_slug: string | null;
  created_at: string;
  status: string;
  summary: string;
  artifacts_path: string | null;
  tests_count: number;
  run_instructions: string[];
  known_limitations: string[];
}

export interface ChangeRequest {
  id: number;
  project_id: number;
  request_text: string;
  classification: string;
  impact_estimate: string;
  status: string;
  related_tasks_json: number[];
  created_at: string;
  updated_at: string;
}

export interface CapabilityBenchmark {
  id: number;
  provider: string;
  model: string;
  runner_mode: RunnerMode | string;
  category: string;
  score: number;
  sample_size: number;
  notes: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CapabilityMatrixEntry {
  provider: string;
  model: string;
  runner_mode: RunnerMode | string;
  scores: Record<string, number | null>;
  sample_size: number;
  notes: string[];
  recommendation_note: string;
}

export interface AgentPerformanceRecord {
  id: number;
  project_id: number | null;
  agent_archetype: string;
  agent_name: string | null;
  provider: string | null;
  model: string | null;
  runner_mode: RunnerMode | string;
  task_category: string;
  task_id: number | null;
  outcome: string;
  duration_seconds: number | null;
  review_passed: boolean | null;
  tests_passed: boolean | null;
  failure_summary: string | null;
  created_at: string;
}

export interface AgentReputationSummary {
  archetype: string;
  provider: string | null;
  model: string | null;
  total_tasks: number;
  success_rate: number;
  common_failure_modes: string[];
  recommended_for: string[];
  avoid_for: string[];
  confidence: number;
}

export interface ProjectPlaybook {
  id: number;
  key: string;
  name: string;
  description: string;
  suggested_interview_categories_json: string[];
  suggested_swarm_mode: string | null;
  suggested_agent_archetypes_json: string[];
  suggested_validation_recipe_json: Array<Record<string, unknown>>;
  common_risks_json: string[];
  suggested_docs_json: string[];
  typical_structure_json: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectPlaybookSuggestion {
  project_id: number;
  playbook_key: string | null;
  status: string;
  why: string;
  playbook: ProjectPlaybook | null;
}

export interface ContextPackSection {
  id: number;
  context_pack_id: number;
  section_type: string;
  title: string;
  content_markdown: string;
  source_refs_json: string[];
  created_at: string;
}

export interface ContextPack {
  id: number;
  project_id: number;
  agent_id: number | null;
  task_id: number | null;
  title: string;
  goal: string;
  included_docs_json: string[];
  included_files_json: string[];
  excluded_files_json: string[];
  known_decisions_json: string[];
  relevant_assumptions_json: string[];
  validation_steps_json: string[];
  token_budget_hint: number | null;
  warnings_json: string[];
  sections: ContextPackSection[];
  created_at: string;
  updated_at: string;
}

export interface RiskRecord {
  id: number;
  project_id: number;
  title: string;
  description: string;
  severity: RiskLevel;
  likelihood: "low" | "medium" | "high";
  owner_agent_id: number | null;
  mitigation: string | null;
  status: "open" | "monitoring" | "mitigated" | "accepted" | "closed";
  related_task_id: number | null;
  created_by: "manager" | "user" | "agent" | "system";
  created_at: string;
  updated_at: string;
}

export interface ScopeChangeSignal {
  id: number;
  project_id: number;
  source: string;
  summary: string;
  severity: "low" | "medium" | "high";
  related_task_id: number | null;
  related_message_id: number | null;
  suggested_action: "include_now" | "defer" | "create_future_milestone" | "ask_user";
  status: "open" | "accepted" | "deferred" | "dismissed";
  created_at: string;
  resolved_at: string | null;
}

export interface SwarmLaunchSimulation {
  id: number;
  project_id: number;
  swarm_plan_id: number | null;
  safe_to_launch_count: number;
  should_wait_count: number;
  needs_user_approval_count: number;
  conflict_warnings_json: string[];
  bottlenecks_json: string[];
  recommended_launch_order_json: Array<Record<string, unknown>>;
  created_at: string;
}

export interface ValidationCoverageArea {
  id: number;
  project_id: number;
  area: string;
  coverage_status: "none" | "planned" | "partial" | "validated" | "failed" | "skipped";
  evidence_summary: string | null;
  related_validation_step_id: number | null;
  last_updated: string;
}

export interface UserPreference {
  id: number;
  key: string;
  value_json: unknown;
  source: "setup" | "user" | "manager_observed" | "imported";
  scope: "global" | "project";
  project_id: number | null;
  editable: boolean;
  created_at: string;
  updated_at: string;
}

export interface DiagnosticReportListItem {
  path: string;
  json_path: string | null;
  created_at: string;
  error_code: string | null;
  summary: string;
}

export type ToolAvailability = "available" | "needs_setup" | "experimental" | "unsupported_on_device" | "coming_soon";
export type ToolPermissionPolicy = "ask_every_time" | "ask_once_per_project" | "allow_for_project" | "never_allow";

export interface ToolCatalogItem {
  id: string;
  name: string;
  category: string;
  summary: string;
  availability: ToolAvailability;
  permission_policy: ToolPermissionPolicy;
  risk_level: RiskLevel;
  notes: string[];
}

export interface ToolPermission {
  tool_id: string;
  permission_policy: ToolPermissionPolicy;
}

export interface SkillEntry {
  name: string;
  source: string;
  available: boolean;
  summary: string | null;
}

export interface OpenPathResult {
  ok: boolean;
  path: string;
  message: string;
}

export interface AgentActionResponse {
  ok: boolean;
  message: string;
  run_id?: number | null;
}

export interface LogRead {
  agent_id: number;
  logs_path: string | null;
  content: string;
}
