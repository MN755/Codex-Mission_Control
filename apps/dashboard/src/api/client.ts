import type {
  Agent,
  AgentActionResponse,
  ApprovalPolicy,
  CodexStatus,
  InterviewSession,
  LogRead,
  ProjectSettings,
  Plan,
  Project,
  ProjectEvent,
  Reservation,
  SandboxMode,
  RunnerMode,
  Task,
  ReasoningEffort,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
    ...init,
  });

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
  getSystemStatus: (projectId?: number) =>
    request<CodexStatus>(`/api/system/status${projectId ? `?project_id=${projectId}` : ""}`),
  getCodexStatus: (projectId?: number) =>
    request<CodexStatus>(`/api/system/codex-status${projectId ? `?project_id=${projectId}` : ""}`),
  getSettings: (projectId: number) => request<ProjectSettings>(`/api/settings?project_id=${projectId}`),
  updateSettings: (
    projectId: number,
    payload: {
      manager_model: string | null;
      default_worker_model: string | null;
      manager_reasoning_effort: ReasoningEffort | null;
      default_worker_reasoning_effort: ReasoningEffort | null;
      per_role_model_overrides_json: Record<string, string>;
      per_role_reasoning_overrides_json: Record<string, string>;
      runner_mode: RunnerMode;
      sandbox_mode: SandboxMode;
      approval_policy: ApprovalPolicy;
    },
  ) => request<ProjectSettings>(`/api/settings?project_id=${projectId}`, { method: "PUT", body: JSON.stringify(payload) }),
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (projectId: number) => request<Project>(`/api/projects/${projectId}`),
  createProject: (payload: {
    name: string;
    idea: string;
    workspace_path: string;
    runner_mode: RunnerMode;
    manager_mode: "auto" | "codex" | "deterministic";
  }) => request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  generateDocs: (projectId: number) => request<{ docs_path: string; files: string[]; used_live_manager: boolean }>(`/api/projects/${projectId}/docs/generate`, { method: "POST" }),
  startInterview: (projectId: number, questionCount: 6 | 20 | 50) =>
    request<InterviewSession>(`/api/projects/${projectId}/interview/start`, { method: "POST", body: JSON.stringify({ question_count: questionCount }) }),
  getInterview: (projectId: number) => request<InterviewSession | null>(`/api/projects/${projectId}/interview`),
  answerInterview: (projectId: number, payload: { question_id: number; option_id: string; selected_text: string }) =>
    request<InterviewSession>(`/api/projects/${projectId}/interview/answer`, { method: "POST", body: JSON.stringify(payload) }),
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
  sendManagerMessage: (projectId: number, message: string) =>
    request<{ reply: string }>(`/api/projects/${projectId}/manager/message`, { method: "POST", body: JSON.stringify({ message }) }),
  askManagerNextStep: (projectId: number) => request<Record<string, unknown>>(`/api/projects/${projectId}/manager/next-step`, { method: "POST" }),
};
