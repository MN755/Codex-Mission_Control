import { startTransition, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { MissionControlMark } from "../components/MissionControlMark";
import { SectionCard } from "../components/SectionCard";
import type { AuthJob, AuthState, CodexStatus, Project } from "../types";

export function StartupPage() {
  const navigate = useNavigate();
  const [authState, setAuthState] = useState<AuthState | null>(null);
  const [systemStatus, setSystemStatus] = useState<CodexStatus | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [working, setWorking] = useState<string | null>(null);

  async function loadState() {
    const [auth, status, projectList] = await Promise.all([api.getAuthState(), api.getSystemStatus(), api.listProjects()]);
    startTransition(() => {
      setAuthState(auth);
      setSystemStatus(status);
      setProjects(projectList);
      setLoading(false);
    });
  }

  useEffect(() => {
    void loadState().catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : "Failed to load startup state.");
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (authState?.current_job?.status !== "running") {
      return undefined;
    }
    const interval = window.setInterval(() => {
      void loadState().catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(interval);
  }, [authState?.current_job?.id, authState?.current_job?.status]);

  const currentJob: AuthJob | null = authState?.current_job ?? systemStatus?.current_auth_job ?? null;
  const canContinue = Boolean(authState?.authenticated);
  const latestProject = useMemo(() => projects[0] ?? null, [projects]);

  async function runAuthAction(action: Promise<AuthJob>, nextWorking: string) {
    setWorking(nextWorking);
    setError(null);
    try {
      const job = await action;
      setAuthState((current) =>
        current
          ? {
              ...current,
              current_job: job,
            }
          : current,
      );
      await loadState();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Authentication flow failed to start.");
    } finally {
      setWorking(null);
    }
  }

  return (
    <AppShell
      title="Desktop Launchpad"
      subtitle="Authenticate once, then orchestrate local Codex workers from a polished desktop shell."
    >
      <div className="startup-grid">
        <SectionCard
          title="Welcome aboard"
          subtitle="Codex Mission Control keeps the manager, workers, logs, and project docs local to your machine."
        >
          <div className="launchpad-hero">
            <MissionControlMark className="launchpad-hero__mark" />
            <div className="launchpad-hero__copy">
              <span className="eyebrow">Desktop-first</span>
              <h2>Sign in before you build.</h2>
              <p>
                The recommended path is <strong>ChatGPT sign-in</strong>, which keeps Codex usage tied to your local Codex or ChatGPT
                session. API-key login is optional, and it can use API billing depending on your account.
              </p>
              <div className="button-row">
                <button type="button" onClick={() => void runAuthAction(api.loginWithChatGpt(false), "chatgpt")} disabled={working !== null || !authState?.chatgpt_supported}>
                  {working === "chatgpt" ? "Starting sign-in..." : "Sign in with ChatGPT"}
                </button>
                <button type="button" className="button-ghost" onClick={() => void runAuthAction(api.loginWithDeviceCode(), "device_auth")} disabled={working !== null || !authState?.device_auth_supported}>
                  {working === "device_auth" ? "Opening device flow..." : "Use device code"}
                </button>
              </div>
            </div>
          </div>

          <div className="startup-banner">
            <div className="startup-indicator" />
            <div>
              <strong>{authState?.authenticated ? `Connected via ${authState.auth_mode ?? "local Codex auth"}` : "No Codex login detected yet"}</strong>
              <p>{authState?.authenticated ? "You can continue into the full manager workflow now." : "Complete one of the sign-in options below to unlock live manager and worker runs."}</p>
            </div>
          </div>

          <div className="launchpad-auth-grid">
            <div className="launchpad-auth-card">
              <h3>Optional API key login</h3>
              <p>Mission Control does not store the raw key. It passes the key once to the local Codex CLI login flow over localhost.</p>
              <label>
                OpenAI API key
                <input
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="sk-..."
                />
              </label>
              <div className="button-row">
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => void runAuthAction(api.loginWithApiKey(apiKey), "api_key")}
                  disabled={working !== null || !apiKey.trim()}
                >
                  {working === "api_key" ? "Sending key..." : "Use API key"}
                </button>
                {authState?.authenticated ? (
                  <button type="button" className="button-ghost" onClick={() => void runAuthAction(api.logoutCodex(), "logout")} disabled={working !== null}>
                    {working === "logout" ? "Signing out..." : "Sign out"}
                  </button>
                ) : null}
              </div>
            </div>

            <div className="launchpad-auth-card">
              <h3>What happens next</h3>
              <ul className="flat-list">
                <li>Manager mode can immediately use your local Codex session for docs, planning, routing, and handoff work.</li>
                <li>Worker agents inherit the same local session and respect per-project model settings instead of changing your global Codex config.</li>
                <li>Dry-run mode still works offline if you want to preview the full workflow before connecting live Codex workers.</li>
              </ul>
              <div className="button-row">
                <button type="button" onClick={() => navigate("/projects/new")} disabled={!canContinue}>
                  Continue to Mission Control
                </button>
                <button type="button" className="button-ghost" onClick={() => navigate("/projects/new?mode=demo")}>
                  Continue in offline demo mode
                </button>
              </div>
            </div>
          </div>

          {currentJob ? (
            <div className="auth-job-panel">
              <div className="event-feed__meta">
                <strong>Auth job: {currentJob.method}</strong>
                <span>{currentJob.status}</span>
              </div>
              <p>{currentJob.message}</p>
              {currentJob.output_lines.length ? <pre>{currentJob.output_lines.join("\n")}</pre> : null}
            </div>
          ) : null}

          {error ? <p className="error-text">{error}</p> : null}
        </SectionCard>

        <SectionCard title="Local environment" subtitle="Mission Control still prefers your existing local Codex session over API keys whenever possible.">
          {loading ? (
            <LoadingBlock label="Inspecting the local Codex install..." />
          ) : systemStatus ? (
            <div className="status-grid">
              <div className="metric-card">
                <span>CLI</span>
                <strong>{systemStatus.cli_detected ? systemStatus.cli_version ?? "Detected" : "Unavailable"}</strong>
              </div>
              <div className="metric-card">
                <span>Auth mode</span>
                <strong>{systemStatus.auth_mode ?? "Not signed in"}</strong>
              </div>
              <div className="metric-card">
                <span>Desktop runtime</span>
                <strong>{systemStatus.runtime_directory}</strong>
              </div>
              <div className="metric-card">
                <span>Auto runner</span>
                <strong>{systemStatus.effective_runner_mode}</strong>
              </div>
              <div className="status-list">
                <h3>Operational notes</h3>
                <ul>
                  {systemStatus.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
              <div className="status-list">
                <h3>Capabilities</h3>
                <ul>
                  <li>App server handshake: {systemStatus.app_server_handshake_status}</li>
                  <li>Dry-run available: {systemStatus.dry_run_available ? "yes" : "no"}</li>
                  <li>Plugins detected: {systemStatus.configured_plugins.length}</li>
                  <li>Local skills detected: {systemStatus.local_skills.length}</li>
                  <li>Active runs: {systemStatus.active_runs.length}</li>
                </ul>
              </div>
            </div>
          ) : (
            <p>System status is not available.</p>
          )}
        </SectionCard>

        <SectionCard title="Recent projects" subtitle="Jump back into the last orchestration run or start fresh.">
          <div className="resume-list">
            {latestProject ? (
              <button className="resume-item" onClick={() => navigate(`/projects/${latestProject.id}/build`)}>
                <strong>Resume latest: {latestProject.name}</strong>
                <span>{latestProject.status}</span>
                <small>{latestProject.workspace_path}</small>
              </button>
            ) : null}
            {projects.map((project) => (
              <button key={project.id} className="resume-item" onClick={() => navigate(`/projects/${project.id}/build`)}>
                <strong>{project.name}</strong>
                <span>{project.status}</span>
                <small>{project.workspace_path}</small>
              </button>
            ))}
            {!projects.length ? <p>No projects yet. Continue into Mission Control to create the first one.</p> : null}
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
