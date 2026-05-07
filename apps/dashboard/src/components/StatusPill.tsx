import type { AgentStatus, TaskStatus } from "../types";

const STATUS_LABELS: Record<string, string> = {
  idle: "Idle",
  starting: "Starting",
  working: "Working",
  waiting: "Waiting",
  needs_review: "Needs Review",
  blocked: "Blocked",
  done: "Done",
  stopped: "Stopped",
  error: "Error",
  backlog: "Backlog",
  assigned: "Assigned",
};

export function StatusPill({ status }: { status: AgentStatus | TaskStatus | string }) {
  return <span className={`status-pill status-${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}

