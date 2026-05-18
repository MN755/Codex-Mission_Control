import type {
  Agent,
  AgentActionResponse,
  AppState,
  ApprovalPolicy,
  AppProfile,
  AuthJob,
  AuthState,
  ChangeRequest,
  CodexStatus,
  DashboardSummary,
  DiagnosticReport,
  DiagnosticReportListItem,
  HandoffListItem,
  InterviewSession,
  LogRead,
  ManagerMessage,
  ManagerQuestion,
  ManagerQueue,
  OpenPathResult,
  ApprovalRequest,
  ProjectSettings,
  Plan,
  ProjectAction,
  Project,
  ProjectUnderstanding,
  ProjectUpdatePayload,
  ProjectEvent,
  ProjectWorkspace,
  ProviderId,
  Reservation,
  SandboxMode,
  SkillEntry,
  RunnerMode,
  SwarmAggressiveness,
  SwarmEvent,
  SwarmOptimizationMode,
  SwarmPlan,
  SwarmPreferences,
  SwarmSpawnResponse,
  StartupStatus,
  Task,
  TestingDepth,
  ThemeMode,
  ToolCatalogItem,
  ToolPermission,
  ToolPermissionPolicy,
  ReasoningEffort,
  StartupBehavior,
  DocsDepth,
  AgentArchetype,
  AppEvent,
  WidgetDataResponse,
  WidgetDefinition,
  WidgetInstance,
  WidgetSummary,
  WidgetArea,
  WidgetScope,
  WidgetSize,
} from "../types";

function defaultApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) {
    return configured;
  }
  if (typeof window === "undefined") {
    return "";
  }
  const { hostname, protocol, port } = window.location;
  const isLocalHost = hostname === "localhost" || hostname === "127.0.0.1";
  if (isLocalHost && port && port !== "8000") {
    return `${protocol}//${hostname}:8000`;
  }
  return "";
}

const API_BASE_URL = defaultApiBaseUrl();

function withQuery(
  path: string,
  params: Record<string, string | number | string[] | null | undefined>,
): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item) {
          query.append(key, item);
        }
      });
      return;
    }
    query.set(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
      },
      ...init,
    });
  } catch (error) {
    const base = API_BASE_URL || (typeof window !== "undefined" ? window.location.origin : "same-origin");
    const reason = error instanceof Error ? error.message : "Failed to fetch";
    throw new Error(`${path} failed against ${base}: ${reason}`);
  }

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  apiBaseUrl: API_BASE_URL,
  getSystemStatus: (
    query?:
      | number
      | {
          projectId?: number;
          provider?: ProviderId;
          provider_endpoint?: string | null;
          adapter_command?: string | null;
          adapter_args?: string[];
        },
  ) => {
    const params =
      typeof query === "number"
        ? { project_id: query }
        : {
            project_id: query?.projectId,
            provider: query?.provider,
            provider_endpoint: query?.provider_endpoint,
            adapter_command: query?.adapter_command,
            adapter_arg: query?.adapter_args,
          };
    return request<CodexStatus>(withQuery("/api/system/status", params));
  },
  getStartupStatus: () => request<StartupStatus>("/api/startup/status"),
  runStartupCheck: (payload: { attempt_number: number; include_optional_checks: boolean }) =>
    request<StartupStatus>("/api/startup/check", { method: "POST", body: JSON.stringify(payload) }),
  retryStartup: (payload: { attempt_number: number; failed_check?: string | null; retry_mode: "targeted" | "full" }) =>
    request<StartupStatus>("/api/startup/retry", { method: "POST", body: JSON.stringify(payload) }),
  completeFirstRun: (payload: {
    username: string;
    provider: ProviderId;
    auth_mode?: string | null;
    connected_accounts_summary?: Record<string, unknown>;
    default_runner_mode?: RunnerMode | null;
    manager_model?: string | null;
    default_worker_model?: string | null;
    manager_reasoning_effort?: ReasoningEffort | null;
    default_worker_reasoning_effort?: ReasoningEffort | null;
    sandbox_mode?: SandboxMode | null;
    approval_policy?: ApprovalPolicy | null;
    provider_endpoint?: string | null;
    adapter_command?: string | null;
    adapter_args?: string[];
    start_mode?: "new_project" | "guided_walkthrough" | null;
  }) => request<AppState>("/api/startup/complete-first-run", { method: "POST", body: JSON.stringify(payload) }),
  runDiagnostics: () => request<DiagnosticReport>("/api/startup/diagnostics", { method: "POST" }),
  openDiagnosticsFolder: () => request<OpenPathResult>("/api/startup/open-diagnostics-folder", { method: "POST" }),
  getProfile: () => request<AppProfile>("/api/profile"),
  updateProfile: (payload: {
    display_name?: string | null;
    preferred_provider_choice?: ProviderId | null;
    preferred_start_mode?: "new_project" | "guided_walkthrough" | null;
    onboarding_completed?: boolean | null;
    theme?: ThemeMode | null;
    startup_behavior?: StartupBehavior | null;
    notification_preferences_json?: Record<string, unknown> | null;
    dashboard_widgets_json?: string[] | null;
    dashboard_widget_preferences_json?: Record<string, unknown> | null;
  }) => request<AppProfile>("/api/profile", { method: "PUT", body: JSON.stringify(payload) }),
  getAuthState: () => request<AuthState>("/api/system/auth-state"),
  loginWithChatGpt: (deviceAuth = false) =>
    request<AuthJob>("/api/system/auth/login/chatgpt", { method: "POST", body: JSON.stringify({ device_auth: deviceAuth }) }),
  loginWithDeviceCode: () => request<AuthJob>("/api/system/auth/login/device", { method: "POST" }),
  loginWithApiKey: (apiKey: string) =>
    request<AuthJob>("/api/system/auth/login/api-key", { method: "POST", body: JSON.stringify({ api_key: apiKey }) }),
  logoutCodex: () => request<AuthJob>("/api/system/auth/logout", { method: "POST" }),
  getAuthJob: (jobId: string) => request<AuthJob>(`/api/system/auth-jobs/${jobId}`),
  getCodexStatus: (projectId?: number) =>
    request<CodexStatus>(withQuery("/api/system/codex-status", { project_id: projectId })),
  getSettings: (projectId: number) => request<ProjectSettings>(`/api/settings?project_id=${projectId}`),
  updateSettings: (
    projectId: number,
    payload: {
      provider: ProviderId;
      manager_model: string | null;
      default_worker_model: string | null;
      manager_reasoning_effort: ReasoningEffort | null;
      default_worker_reasoning_effort: ReasoningEffort | null;
      per_role_model_overrides_json: Record<string, string>;
      per_role_reasoning_overrides_json: Record<string, string>;
      adapter_command: string | null;
      adapter_args_json: string[];
      runner_mode: RunnerMode;
      sandbox_mode: SandboxMode;
      approval_policy: ApprovalPolicy;
      workspace_widgets_json: string[];
      approval_overrides_json: Record<string, unknown>;
    },
  ) => request<ProjectSettings>(`/api/settings?project_id=${projectId}`, { method: "PUT", body: JSON.stringify(payload) }),
  getSwarmPreferences: (projectId: number) => request<SwarmPreferences>(`/api/projects/${projectId}/swarm/preferences`),
  updateSwarmPreferences: (
    projectId: number,
    payload: {
      optimization_mode: SwarmOptimizationMode;
      swarm_aggressiveness: SwarmAggressiveness;
      max_agents: number;
      require_approval_above_agent_count: number;
      allow_dynamic_spawning: boolean;
      allow_dynamic_retirement: boolean;
      docs_depth: DocsDepth;
      testing_depth: TestingDepth;
    },
  ) => request<SwarmPreferences>(`/api/projects/${projectId}/swarm/preferences`, { method: "PUT", body: JSON.stringify(payload) }),
  createSwarmPlan: (projectId: number, payload?: { goal?: string | null; milestone_id?: number | null }) =>
    request<SwarmPlan>(`/api/projects/${projectId}/swarm/plan`, { method: "POST", body: JSON.stringify(payload ?? {}) }),
  getSwarmPlan: (projectId: number) => request<SwarmPlan | null>(`/api/projects/${projectId}/swarm/plan`),
  approveSwarmPlan: (projectId: number, swarmPlanId: number) =>
    request<SwarmPlan>(`/api/projects/${projectId}/swarm/plan/${swarmPlanId}/approve`, { method: "POST" }),
  reviseSwarmPlan: (projectId: number, swarmPlanId: number, note?: string | null) =>
    request<SwarmPlan>(`/api/projects/${projectId}/swarm/plan/${swarmPlanId}/revise`, { method: "POST", body: JSON.stringify({ note }) }),
  spawnSwarmAgents: (projectId: number) => request<SwarmSpawnResponse>(`/api/projects/${projectId}/swarm/spawn`, { method: "POST" }),
  scaleSwarm: (projectId: number, payload: { direction: "up" | "down"; reason?: string | null; count?: number }) =>
    request<SwarmSpawnResponse>(`/api/projects/${projectId}/swarm/scale`, { method: "POST", body: JSON.stringify(payload) }),
  getSwarmEvents: (projectId: number) => request<SwarmEvent[]>(`/api/projects/${projectId}/swarm/events`),
  getAgentArchetypes: () => request<AgentArchetype[]>("/api/agent-archetypes"),
  getDashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),
  getWidgetCatalog: (scope?: WidgetScope) => request<WidgetDefinition[]>(scope ? `/api/widgets/catalog?scope=${scope}` : "/api/widgets/catalog"),
  getDashboardWidgetInstances: () => request<WidgetInstance[]>("/api/widgets/instances?scope=dashboard"),
  getProjectWidgetInstances: (projectId: number) => request<WidgetInstance[]>(`/api/projects/${projectId}/widgets/instances`),
  createWidgetInstance: (payload: {
    scope: WidgetScope;
    project_id?: number | null;
    widget_type: string;
    area?: WidgetArea | null;
    order_index?: number | null;
    size?: WidgetSize | null;
    collapsed?: boolean;
    enabled?: boolean;
    config_json?: Record<string, unknown>;
  }) => request<WidgetInstance>("/api/widgets/instances", { method: "POST", body: JSON.stringify(payload) }),
  updateWidgetInstance: (
    instanceId: number,
    payload: {
      area?: WidgetArea | null;
      order_index?: number | null;
      size?: WidgetSize | null;
      collapsed?: boolean;
      enabled?: boolean;
      config_json?: Record<string, unknown> | null;
    },
  ) => request<WidgetInstance>(`/api/widgets/instances/${instanceId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteWidgetInstance: (instanceId: number) => request<void>(`/api/widgets/instances/${instanceId}`, { method: "DELETE" }),
  getWidgetInstanceData: (instanceId: number) => request<WidgetDataResponse>(`/api/widgets/instances/${instanceId}/data`),
  getProjectWidgetSummary: (projectId: number) => request<WidgetSummary>(`/api/projects/${projectId}/widgets/summary`),
  addDashboardWidget: (payload: { widget_type: string; area?: WidgetArea | null; size?: WidgetSize | null }) =>
    request<WidgetInstance>("/api/dashboard/widgets/add", { method: "POST", body: JSON.stringify(payload) }),
  addProjectWidget: (projectId: number, payload: { widget_type: string; area?: WidgetArea | null; size?: WidgetSize | null }) =>
    request<WidgetInstance>(`/api/projects/${projectId}/widgets/add`, { method: "POST", body: JSON.stringify(payload) }),
  createChangeRequest: (projectId: number, payload: { request_text: string }) =>
    request<ChangeRequest>(`/api/projects/${projectId}/change-requests`, { method: "POST", body: JSON.stringify(payload) }),
  listProjects: (includeArchived = false) => request<Project[]>(`/api/projects${includeArchived ? "?include_archived=true" : ""}`),
  getProject: (projectId: number) => request<Project>(`/api/projects/${projectId}`),
  updateProject: (projectId: number, payload: ProjectUpdatePayload) =>
    request<Project>(`/api/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  openProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/open`, { method: "POST" }),
  pauseProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/pause`, { method: "POST" }),
  resumeProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/resume`, { method: "POST" }),
  archiveProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/archive`, { method: "POST" }),
  unarchiveProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/unarchive`, { method: "POST" }),
  pinProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/pin`, { method: "POST" }),
  unpinProject: (projectId: number) => request<Project>(`/api/projects/${projectId}/unpin`, { method: "POST" }),
  getProjectWorkspace: (projectId: number) => request<ProjectWorkspace>(`/api/projects/${projectId}/workspace`),
  getProjectAction: (projectId: number) => request<ProjectAction>(`/api/projects/${projectId}/action`),
  getProjectActions: (projectId: number) => request<ProjectAction[]>(`/api/projects/${projectId}/actions`),
  resolveProjectAction: (
    projectId: number,
    actionId: string,
    payload: { decision: "approve_once" | "deny" | "allow_for_project" | "choose_option" | "dismiss"; option_id?: string | null; selected_text?: string | null },
  ) => request<Record<string, unknown>>(`/api/projects/${projectId}/actions/${actionId}/resolve`, { method: "POST", body: JSON.stringify(payload) }),
  getManagerMessages: (projectId: number) => request<ManagerMessage[]>(`/api/projects/${projectId}/manager/messages`),
  createManagerMessage: (projectId: number, message: string) =>
    request<ManagerMessage>(`/api/projects/${projectId}/manager/messages`, { method: "POST", body: JSON.stringify({ message }) }),
  askManagerNext: (projectId: number) => request<ManagerMessage>(`/api/projects/${projectId}/manager/ask-next`, { method: "POST" }),
  generateManagerUpdate: (projectId: number) => request<ManagerMessage>(`/api/projects/${projectId}/manager/generate-update`, { method: "POST" }),
  getPendingQuestions: (projectId: number) => request<ManagerQuestion[]>(`/api/projects/${projectId}/questions/pending`),
  answerQuestion: (questionId: number, payload: { project_id?: number | null; option_id: string; selected_text: string }) =>
    request<ManagerQuestion>(`/api/questions/${questionId}/answer`, { method: "POST", body: JSON.stringify(payload) }),
  autoDecideQuestion: (questionId: number) => request<ManagerQuestion>(`/api/questions/${questionId}/auto-decide`, { method: "POST" }),
  getPendingApprovals: (projectId: number) => request<ApprovalRequest[]>(`/api/projects/${projectId}/approvals/pending`),
  approveOnce: (approvalId: number, projectId: number) =>
    request<ApprovalRequest>(`/api/approvals/${approvalId}/approve-once`, { method: "POST", body: JSON.stringify({ project_id: projectId }) }),
  denyApproval: (approvalId: number, projectId: number) =>
    request<ApprovalRequest>(`/api/approvals/${approvalId}/deny`, { method: "POST", body: JSON.stringify({ project_id: projectId }) }),
  allowApprovalForProject: (approvalId: number, projectId: number) =>
    request<ApprovalRequest>(`/api/approvals/${approvalId}/allow-for-project`, { method: "POST", body: JSON.stringify({ project_id: projectId }) }),
  getManagerQueue: (projectId: number) => request<ManagerQueue>(`/api/projects/${projectId}/manager/queue`),
  updateWorkspaceWidgets: (projectId: number, widgets: string[]) =>
    request<ProjectSettings>(`/api/projects/${projectId}/widgets`, { method: "POST", body: JSON.stringify({ widgets }) }),
  listHandoffs: () => request<HandoffListItem[]>("/api/handoffs"),
  getProjectHandoffSummary: (projectId: number) => request<HandoffListItem>(`/api/projects/${projectId}/handoff`),
  listDiagnosticReports: () => request<DiagnosticReportListItem[]>("/api/diagnostics/reports"),
  getTools: () => request<ToolCatalogItem[]>("/api/tools"),
  updateToolPermission: (toolId: string, permissionPolicy: ToolPermissionPolicy) =>
    request<ToolPermission>(`/api/tools/${toolId}/permission`, { method: "PUT", body: JSON.stringify({ permission_policy: permissionPolicy }) }),
  getSkills: () => request<SkillEntry[]>("/api/skills"),
  createProject: (payload: {
    name: string;
    idea: string;
    workspace_path: string;
    provider: ProviderId;
    runner_mode: RunnerMode;
    manager_mode: "auto" | "provider" | "codex" | "deterministic";
  }) => request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  generateDocs: (projectId: number) => request<{ docs_path: string; files: string[]; used_live_manager: boolean }>(`/api/projects/${projectId}/docs/generate`, { method: "POST" }),
  startInterview: (projectId: number, questionBudget: number) =>
    request<InterviewSession>(`/api/projects/${projectId}/interview/start`, { method: "POST", body: JSON.stringify({ question_budget: questionBudget }) }),
  getInterview: (projectId: number) => request<InterviewSession | null>(`/api/projects/${projectId}/interview`),
  generateNextInterview: (projectId: number) => request<InterviewSession>(`/api/projects/${projectId}/interview/generate-next`, { method: "POST" }),
  answerInterviewQuestion: (questionId: number, payload: { project_id: number; option_id: string; selected_text: string; custom_answer?: string | null }) =>
    request<InterviewSession>(`/api/interview/questions/${questionId}/answer`, { method: "POST", body: JSON.stringify(payload) }),
  answerInterview: (projectId: number, payload: { question_id: number; option_id: string; selected_text: string; custom_answer?: string | null }) =>
    request<InterviewSession>(`/api/projects/${projectId}/interview/answer`, { method: "POST", body: JSON.stringify(payload) }),
  finishInterview: (projectId: number) => request<InterviewSession>(`/api/projects/${projectId}/interview/finish`, { method: "POST" }),
  getProjectUnderstanding: (projectId: number) => request<ProjectUnderstanding>(`/api/projects/${projectId}/understanding`),
  generatePlan: (projectId: number) => request<Plan>(`/api/projects/${projectId}/plan/generate`, { method: "POST", body: JSON.stringify({ force_rebuild: true }) }),
  getPlan: (projectId: number) => request<Plan | null>(`/api/projects/${projectId}/plan`),
  approvePlan: (projectId: number, payload: { action: string; note?: string }) =>
    request<Plan>(`/api/projects/${projectId}/plan/approve`, { method: "POST", body: JSON.stringify(payload) }),
  getAgents: (projectId: number) => request<Agent[]>(`/api/projects/${projectId}/agents`),
  getReservations: (projectId: number) => request<Reservation[]>(`/api/projects/${projectId}/reservations`),
  startProjectAgents: (projectId: number) => request<AgentActionResponse>(`/api/projects/${projectId}/agents/start`, { method: "POST" }),
  startAgent: (agentId: number) => request<AgentActionResponse>(`/api/agents/${agentId}/start`, { method: "POST" }),
  pauseAgent: (agentId: number) => request<AgentActionResponse>(`/api/agents/${agentId}/pause`, { method: "POST" }),
  stopAgent: (agentId: number) => request<AgentActionResponse>(`/api/agents/${agentId}/stop`, { method: "POST" }),
  getAgentLogs: (agentId: number) => request<LogRead>(`/api/agents/${agentId}/logs`),
  getTasks: (projectId: number) => request<Task[]>(`/api/projects/${projectId}/tasks`),
  generateTasks: (projectId: number) => request<{ count: number; manager_mode_used: string }>(`/api/projects/${projectId}/tasks/generate`, { method: "POST" }),
  startTask: (taskId: number) => request<AgentActionResponse>(`/api/tasks/${taskId}/start`, { method: "POST" }),
  completeTask: (taskId: number) => request<AgentActionResponse>(`/api/tasks/${taskId}/complete`, { method: "POST" }),
  getEvents: (projectId: number, afterId?: number) =>
    request<ProjectEvent[]>(`/api/projects/${projectId}/events${afterId ? `?after_id=${afterId}` : ""}`),
  parseEventPayload: (raw: MessageEvent<string>): AppEvent | null => {
    try {
      return JSON.parse(raw.data) as AppEvent;
    } catch {
      return null;
    }
  },
  sendManagerMessage: (projectId: number, message: string) =>
    request<{ reply: string; message: ManagerMessage }>(`/api/projects/${projectId}/manager/message`, { method: "POST", body: JSON.stringify({ message }) }),
  askManagerNextStep: (projectId: number) => request<Record<string, unknown>>(`/api/projects/${projectId}/manager/next-step`, { method: "POST" }),
};
