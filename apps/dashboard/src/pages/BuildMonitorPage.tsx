import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { AgentSidebar } from "../components/AgentSidebar";
import { AppShell } from "../components/AppShell";
import { EventFeed } from "../components/EventFeed";
import { LoadingBlock } from "../components/LoadingBlock";
import { ManagerPanel } from "../components/ManagerPanel";
import { SectionCard } from "../components/SectionCard";
import { TaskBoard } from "../components/TaskBoard";
import { useProjectStream } from "../state/useProjectStream";
import type { Agent, CodexStatus, LogRead, Plan, Project, ProjectEvent, ProjectSettings, Reservation, Task } from "../types";

function providerDefaultLabel(provider: string | null | undefined) {
  if (provider === "claude_code") {
    return "Claude Code default";
  }
  if (provider === "external_adapter") {
    return "Adapter default";
  }
  return "Codex default";
}

export function BuildMonitorPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<ProjectEvent[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [logs, setLogs] = useState<LogRead | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [status, setStatus] = useState<CodexStatus | null>(null);
  const [managerReply, setManagerReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyMessage, setBusyMessage] = useState<string | null>("Starting up agents...");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [loadedProject, loadedPlan, loadedAgents, loadedTasks, loadedEvents, loadedReservations, loadedSettings, loadedStatus] = await Promise.all([
        api.getProject(numericProjectId),
        api.getPlan(numericProjectId),
        api.getAgents(numericProjectId),
        api.getTasks(numericProjectId),
        api.getEvents(numericProjectId),
        api.getReservations(numericProjectId),
        api.getSettings(numericProjectId),
        api.getSystemStatus(numericProjectId),
      ]);
      setProject(loadedProject);
      setPlan(loadedPlan);
      setAgents(loadedAgents);
      setTasks(loadedTasks);
      setEvents(loadedEvents);
      setReservations(loadedReservations);
      setSettings(loadedSettings);
      setStatus(loadedStatus);
      if (loadedAgents.some((agent) => agent.status === "working" || agent.status === "starting")) {
        setBusyMessage("Starting up agents...");
      } else {
        setBusyMessage(null);
      }
      if (loadedProject.status === "handoff_ready") {
        navigate(`/projects/${numericProjectId}/handoff`);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load build monitor.");
    } finally {
      setLoading(false);
    }
  }, [navigate, numericProjectId]);

  useEffect(() => {
    void load();
  }, [load]);

  useProjectStream(numericProjectId, () => {
    void load();
  });

  const managerAgent = agents.find((agent) => agent.kind === "manager") ?? null;
  const workerAgents = agents.filter((agent) => agent.kind === "worker");

  async function act(action: () => Promise<unknown>) {
    try {
      await action();
      await load();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Action failed.");
    }
  }

  async function handleLogs(agentId: number) {
    try {
      const nextLogs = await api.getAgentLogs(agentId);
      setLogs(nextLogs);
    } catch (logError) {
      setError(logError instanceof Error ? logError.message : "Could not load logs.");
    }
  }

  return (
    <AppShell
      projectId={numericProjectId}
      title="Build Monitor"
      subtitle="Manager AI coordinates the worker roster, task routing, and validation while the user stays in one chat."
      rightRail={
        project ? (
          <div className="header-stack">
            <span className="header-chip">Provider: {settings?.provider ?? status?.selected_provider ?? "codex"}</span>
            <span className="header-chip">Runner: {settings?.runner_mode ?? project.runner_mode}</span>
            <span className="header-chip">Status: {project.status}</span>
          </div>
        ) : null
      }
    >
      {loading ? (
        <LoadingBlock label="Loading build monitor..." />
      ) : (
        <div className="monitor-grid">
          <AgentSidebar
            agents={workerAgents}
            tasks={tasks}
            onStart={(agentId) => void act(() => api.startAgent(agentId))}
            onPause={(agentId) => void act(() => api.pauseAgent(agentId))}
            onStop={(agentId) => void act(() => api.stopAgent(agentId))}
            onLogs={(agentId) => void handleLogs(agentId)}
          />

          <div className="monitor-main">
            {busyMessage ? (
              <div className="startup-banner">
                <div className="startup-indicator" />
                <span>{busyMessage}</span>
              </div>
            ) : null}

            <div className="monitor-metrics">
              <article className="metric-card">
                <span>Agents</span>
                <strong>{workerAgents.length}</strong>
              </article>
              <article className="metric-card">
                <span>Open tasks</span>
                <strong>{tasks.filter((task) => task.status !== "done").length}</strong>
              </article>
              <article className="metric-card">
                <span>Events</span>
                <strong>{events.length}</strong>
              </article>
              <article className="metric-card">
                <span>Reserved paths</span>
                <strong>{reservations.length}</strong>
              </article>
            </div>

            <SectionCard
              title="Manager chat panel"
              subtitle="Send high-level direction here. The manager handles worker coordination."
              actions={
                <div className="button-row">
                  <button className="button-ghost" onClick={() => void act(() => api.generateTasks(numericProjectId))}>
                    Generate next tasks
                  </button>
                  <button className="button-ghost" onClick={() => void act(() => api.askManagerNextStep(numericProjectId))}>
                    Ask Manager for next step
                  </button>
                  <button className="button-ghost" onClick={() => void act(() => api.startProjectAgents(numericProjectId))}>
                    Start all idle agents
                  </button>
                </div>
              }
            >
              <ManagerPanel
                managerMode={project?.manager_mode ?? "auto"}
                managerModel={managerAgent?.active_model ?? settings?.manager_model ?? providerDefaultLabel(settings?.provider)}
                managerReasoning={managerAgent?.active_reasoning_effort ?? settings?.manager_reasoning_effort ?? providerDefaultLabel(settings?.provider)}
                currentAction={managerAgent?.current_action ?? "Standing by"}
                reply={managerReply}
                onSend={async (message) => {
                  const response = await api.sendManagerMessage(numericProjectId, message);
                  setManagerReply(response.reply);
                }}
              />
            </SectionCard>

            <SectionCard title="Task board" subtitle="Worker assignments stay non-overlapping and visible.">
              <TaskBoard tasks={tasks} onStartTask={(taskId) => void act(() => api.startTask(taskId))} />
            </SectionCard>

            <div className="monitor-lower-grid">
              <SectionCard title="Activity stream" subtitle="Persistent backend events feed the live monitor.">
                <EventFeed events={events} />
              </SectionCard>
              <SectionCard title="Logs drawer" subtitle="Open the latest worker log without leaving the dashboard.">
                {logs ? (
                  <div className="logs-panel">
                    <strong>{logs.logs_path ?? "No log file"}</strong>
                    <pre>{logs.content || "No log content available yet."}</pre>
                  </div>
                ) : (
                  <p>Select "View logs" on an agent card to inspect runner output.</p>
                )}
              </SectionCard>
            </div>
            {status ? (
              <SectionCard title="Effective defaults" subtitle="These are the current per-project runner and model settings that new turns inherit.">
                <div className="status-grid">
                  <div className="metric-card">
                    <span>Provider</span>
                    <strong>{settings?.provider ?? status.selected_provider}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Manager model</span>
                    <strong>{settings?.manager_model ?? providerDefaultLabel(settings?.provider)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Worker model</span>
                    <strong>{settings?.default_worker_model ?? providerDefaultLabel(settings?.provider)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Reasoning</span>
                    <strong>{settings?.default_worker_reasoning_effort ?? providerDefaultLabel(settings?.provider)}</strong>
                  </div>
                  <div className="metric-card">
                    <span>Runner status</span>
                    <strong>{status.effective_runner_mode}</strong>
                  </div>
                </div>
              </SectionCard>
            ) : null}
            {error ? <p className="error-text">{error}</p> : null}
          </div>
        </div>
      )}
    </AppShell>
  );
}
