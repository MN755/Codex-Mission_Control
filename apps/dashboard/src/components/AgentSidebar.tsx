import type { Agent, Task } from "../types";
import { providerDefaultLabel } from "../lib/providers";
import { StatusPill } from "./StatusPill";

export function AgentSidebar({
  agents,
  tasks,
  onStart,
  onPause,
  onStop,
  onLogs,
}: {
  agents: Agent[];
  tasks: Task[];
  onStart: (agentId: number) => void;
  onPause: (agentId: number) => void;
  onStop: (agentId: number) => void;
  onLogs: (agentId: number) => void;
}) {
  return (
    <aside className="agent-sidebar">
      <div className="agent-sidebar__title-row">
        <div>
          <span className="eyebrow">Active Agents</span>
          <h3>Agent roster</h3>
        </div>
        <span className="count-badge">{agents.length}</span>
      </div>
      <div className="agent-sidebar__list">
        {agents.map((agent) => {
          const currentTask = tasks.find((task) => task.id === agent.current_task_id);
          return (
            <article key={agent.id} className="agent-card">
              <div className="agent-card__top">
                <div>
                  <h4>{agent.name}</h4>
                  <p>{agent.role}</p>
                </div>
                <StatusPill status={agent.status} />
              </div>
              <dl className="agent-card__meta">
                <div>
                  <dt>Task</dt>
                  <dd>{currentTask ? currentTask.title : "Unassigned"}</dd>
                </div>
                <div>
                  <dt>Runner</dt>
                  <dd>{agent.active_runner_type ?? "Not started"}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{agent.active_model ?? providerDefaultLabel(agent.active_runner_type)}</dd>
                </div>
                <div>
                  <dt>Reasoning</dt>
                  <dd>{agent.active_reasoning_effort ?? providerDefaultLabel(agent.active_runner_type)}</dd>
                </div>
                <div>
                  <dt>Milestone</dt>
                  <dd>{currentTask?.milestone ?? "Waiting"}</dd>
                </div>
                <div>
                  <dt>Reserved paths</dt>
                  <dd>{agent.locked_paths_json?.join(", ") || "None"}</dd>
                </div>
                <div>
                  <dt>Last report</dt>
                  <dd>{agent.last_report_summary ?? "No report yet"}</dd>
                </div>
                <div>
                  <dt>Workspace</dt>
                  <dd title={agent.workspace_path}>{agent.workspace_path}</dd>
                </div>
              </dl>
              <div className="agent-card__actions">
                <button onClick={() => onStart(agent.id)}>Start</button>
                <button className="button-ghost" onClick={() => onPause(agent.id)}>
                  Mark waiting
                </button>
                <button className="button-ghost" onClick={() => onStop(agent.id)}>
                  Stop
                </button>
                <button className="button-ghost" onClick={() => onLogs(agent.id)}>
                  View logs
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </aside>
  );
}
