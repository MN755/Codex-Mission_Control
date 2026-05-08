import { startTransition, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import type { CodexStatus, ManagerMode, Project, ProviderId, RunnerMode } from "../types";

const DEMO_WORKSPACE = "C:\\Users\\mike\\OneDrive\\Desktop\\Codex Mission Control\\apps\\server\\.runtime\\demo-project";

export function ProjectIntakePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const demoMode = searchParams.get("mode") === "demo";
  const [projects, setProjects] = useState<Project[]>([]);
  const [codexStatus, setCodexStatus] = useState<CodexStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    idea: "",
    workspace_path: DEMO_WORKSPACE,
    provider: "codex" as ProviderId,
    runner_mode: (demoMode ? "dry_run" : "auto") as RunnerMode,
    manager_mode: (demoMode ? "deterministic" : "auto") as ManagerMode,
  });

  useEffect(() => {
    if (!demoMode) {
      return;
    }
    setForm((current) => ({
      ...current,
      runner_mode: "dry_run",
      manager_mode: "deterministic",
      workspace_path: current.workspace_path || DEMO_WORKSPACE,
    }));
  }, [demoMode]);

  useEffect(() => {
    async function load() {
      try {
        const [status, projectList] = await Promise.all([api.getSystemStatus(), api.listProjects()]);
        startTransition(() => {
          setCodexStatus(status);
          setProjects(projectList);
          setLoading(false);
        });
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load app state.");
        setLoading(false);
      }
    }
    void load();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const project = await api.createProject(form);
      await api.generateDocs(project.id);
      navigate(`/projects/${project.id}/interview`);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to create project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell
      title="Project Intake"
      subtitle={demoMode ? "Dry-run demo mode is active. The form defaults to a safe local simulation flow." : "Turn a raw idea into local project docs, an interview flow, and a buildable plan."}
    >
      <div className="intake-grid">
        <SectionCard title="Create project docs" subtitle="The manager will create local planning docs before any coding starts.">
          <form className="stack-form" onSubmit={handleSubmit}>
            <label>
              Project name
              <input
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Codex Mission Control"
                required
              />
            </label>
            <label>
              Project idea
              <textarea
                value={form.idea}
                onChange={(event) => setForm((current) => ({ ...current, idea: event.target.value }))}
                placeholder="Describe the software idea, the user problem, and any constraints."
                required
              />
            </label>
            <label>
              Workspace path
              <input
                value={form.workspace_path}
                onChange={(event) => setForm((current) => ({ ...current, workspace_path: event.target.value }))}
                required
              />
            </label>
            <div className="form-row">
              <label>
                Live provider
                <select
                  value={form.provider}
                  onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value as ProviderId }))}
                >
                  <option value="codex">Codex</option>
                  <option value="claude_code">Claude Code</option>
                  <option value="external_adapter">External adapter</option>
                </select>
              </label>
              <label>
                Runner mode
                <select
                  value={form.runner_mode}
                  onChange={(event) => setForm((current) => ({ ...current, runner_mode: event.target.value as RunnerMode }))}
                >
                  <option value="auto">auto</option>
                  <option value="cli">cli</option>
                  <option value="app_server" disabled={form.provider !== "codex"}>
                    app_server {form.provider !== "codex" ? "(Codex only)" : ""}
                  </option>
                  <option value="dry_run">dry_run</option>
                </select>
              </label>
              <label>
                Manager mode
                <select
                  value={form.manager_mode}
                  onChange={(event) => setForm((current) => ({ ...current, manager_mode: event.target.value as ManagerMode }))}
                >
                  <option value="auto">auto</option>
                  <option value="provider">provider</option>
                  <option value="deterministic">deterministic</option>
                </select>
              </label>
            </div>
            <div className="button-row">
              <button type="button" className="button-ghost" onClick={() => setForm((current) => ({ ...current, workspace_path: DEMO_WORKSPACE }))}>
                Use demo path
              </button>
              <button type="submit" disabled={submitting}>
                {submitting ? "Creating..." : "Create project docs"}
              </button>
            </div>
            {error ? <p className="error-text">{error}</p> : null}
          </form>
        </SectionCard>

        <SectionCard title="Local provider status" subtitle="Mission Control has built-in auth for Codex. Claude Code and external adapters use their own local login or credential flow.">
          {loading ? (
            <LoadingBlock label="Checking local provider environment..." />
          ) : codexStatus ? (
            <div className="status-grid">
              <div className="metric-card">
                <span>Selected provider</span>
                <strong>{codexStatus.selected_provider_label}</strong>
              </div>
              <div className="metric-card">
                <span>CLI</span>
                <strong>{codexStatus.cli_detected ? codexStatus.cli_version ?? "Detected" : "Unavailable"}</strong>
              </div>
              <div className="metric-card">
                <span>App server handshake</span>
                <strong>{codexStatus.app_server_handshake_status}</strong>
              </div>
              <div className="metric-card">
                <span>Auto runner</span>
                <strong>{codexStatus.effective_runner_mode}</strong>
              </div>
              <div className="status-list">
                <h3>Runtime</h3>
                <ul>
                  <li>{codexStatus.runtime_directory}</li>
                  <li>Backend port: {codexStatus.backend_port}</li>
                  <li>Frontend port: {codexStatus.frontend_port ?? "Unknown"}</li>
                  <li>Dry-run available: {codexStatus.dry_run_available ? "yes" : "no"}</li>
                  <li>Active runs: {codexStatus.active_runs.length}</li>
                  <li>{codexStatus.authenticated ? "Codex launchpad auth is ready." : "Codex sign-in is optional unless you choose the Codex provider."}</li>
                </ul>
              </div>
              <div className="status-list">
                <h3>Providers</h3>
                <ul>
                  {codexStatus.provider_statuses.map((provider) => (
                    <li key={provider.provider}>
                      {provider.label}: {provider.cli_detected ? "CLI detected" : "CLI missing"}; {provider.auth_status_detectable ? provider.login_status : "auth managed externally"}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p>Codex status is not available.</p>
          )}
        </SectionCard>

        <SectionCard title="Existing projects" subtitle="Resume a previous orchestration run.">
          <div className="resume-list">
            {projects.map((project) => (
              <button key={project.id} className="resume-item" onClick={() => navigate(`/projects/${project.id}/build`)}>
                <strong>{project.name}</strong>
                <span>{project.status}</span>
                <small>{project.workspace_path}</small>
              </button>
            ))}
            {!projects.length ? <p>No projects yet. Create the first one above.</p> : null}
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
