export type RunnerMode = "auto" | "cli" | "app_server" | "dry_run";
export type ManagerMode = "auto" | "codex" | "deterministic";
export type ReasoningEffort = "minimal" | "low" | "medium" | "high";
export type SandboxMode = "workspace-write" | "read-only";
export type ApprovalPolicy = "on-request" | "untrusted" | "never";
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

export interface Project {
  id: number;
  name: string;
  idea: string;
  workspace_path: string;
  status: string;
  runner_mode: RunnerMode;
  manager_mode: ManagerMode;
  docs_path: string | null;
  final_report_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface InterviewOption {
  id: string;
  label: string;
  description: string;
}

export interface InterviewQuestion {
  id: number;
  index: number;
  question: string;
  options: InterviewOption[];
  selected_option: string | null;
  selected_text: string | null;
  rationale: string | null;
}

export interface InterviewSession {
  id: number;
  project_id: number;
  question_count: number;
  current_index: number;
  status: string;
  questions: InterviewQuestion[];
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
  workspace_path: string;
  session_ref: string | null;
  locked_paths_json: string[] | null;
  failure_count: number;
  last_report_summary: string | null;
  active_model: string | null;
  active_reasoning_effort: string | null;
  active_runner_type: string | null;
  current_action: string | null;
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

export interface CodexStatus {
  cli_detected: boolean;
  cli_version: string | null;
  login_status: string;
  auth_mode: string | null;
  app_server_supported: boolean;
  app_server_handshake_status: string;
  app_server_transport: string;
  effective_runner_mode: string;
  dry_run_available: boolean;
  runtime_directory: string;
  backend_port: number;
  frontend_port: number | null;
  active_runs: Array<Record<string, unknown>>;
  current_settings_summary: ProjectSettings | null;
  selected_manager_model: string | null;
  selected_default_worker_model: string | null;
  available_models: string[];
  mcp_servers: Array<Record<string, unknown>>;
  configured_plugins: string[];
  local_skills: string[];
  notes: string[];
}

export interface ProjectSettings {
  project_id: number;
  manager_model: string | null;
  default_worker_model: string | null;
  manager_reasoning_effort: ReasoningEffort | null;
  default_worker_reasoning_effort: ReasoningEffort | null;
  per_role_model_overrides_json: Record<string, string>;
  per_role_reasoning_overrides_json: Record<string, string>;
  runner_mode: RunnerMode;
  sandbox_mode: SandboxMode;
  approval_policy: ApprovalPolicy;
  created_at: string;
  updated_at: string;
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
