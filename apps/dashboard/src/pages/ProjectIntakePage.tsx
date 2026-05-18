import { startTransition, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { PROVIDER_OPTIONS, providerLabel, providerUsesAdapter } from "../lib/providers";
import type { AppProfile, CodexStatus, ManagerMode, Project, ProviderId, RunnerMode } from "../types";

function normalizePath(value: string): string {
  return value.replace(/\\/g, "/").replace(/\/+$/, "");
}

function deriveDemoWorkspace(runtimeDirectory?: string | null): string {
  if (!runtimeDirectory) {
    return "workspace/demo-project";
  }
  return `${normalizePath(runtimeDirectory)}/demo-project`;
}

export function ProjectIntakePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const demoMode = searchParams.get("mode") === "demo";
  const guidedMode = searchParams.get("guided") === "1";
  const startupProviderChoice = (searchParams.get("providerChoice") as ProviderId | null) ?? null;
  const [intakeMode, setIntakeMode] = useState<"idea" | "import" | "docs" | "clone">("idea");
  const [projects, setProjects] = useState<Project[]>([]);
  const [codexStatus, setCodexStatus] = useState<CodexStatus | null>(null);
  const [profile, setProfile] = useState<AppProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    idea: "",
    workspace_path: "workspace/demo-project",
    provider: (startupProviderChoice ?? "codex") as ProviderId,
    runner_mode: (demoMode ? "dry_run" : "auto") as RunnerMode,
    manager_mode: (demoMode ? "deterministic" : "auto") as ManagerMode,
  });
  const [importForm, setImportForm] = useState({
    name: "",
    folder_path: "",
    import_mode: "linked" as const,
    start_read_only_scan: true,
  });

  useEffect(() => {
    if (!demoMode) {
      return;
    }
    setForm((current) => ({
      ...current,
      runner_mode: "dry_run",
      manager_mode: "deterministic",
      workspace_path: current.workspace_path || deriveDemoWorkspace(codexStatus?.runtime_directory),
    }));
  }, [codexStatus?.runtime_directory, demoMode]);

  useEffect(() => {
    async function load() {
      try {
        const [status, projectList, workspaceProfile] = await Promise.all([api.getSystemStatus(), api.listProjects(), api.getProfile()]);
        const demoWorkspace = deriveDemoWorkspace(status.runtime_directory);
        startTransition(() => {
          setCodexStatus(status);
          setProjects(projectList);
          setProfile(workspaceProfile);
          setForm((current) => ({
            ...current,
            provider: startupProviderChoice ?? workspaceProfile.selected_provider ?? workspaceProfile.preferred_provider_choice,
            runner_mode:
              demoMode || workspaceProfile.preferred_start_mode === "guided_walkthrough"
                ? "dry_run"
                : workspaceProfile.default_runner_mode ?? current.runner_mode,
            workspace_path: demoMode || current.workspace_path === "workspace/demo-project" ? demoWorkspace : current.workspace_path,
          }));
          setLoading(false);
        });
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load app state.");
        setLoading(false);
      }
    }
    void load();
  }, [demoMode, startupProviderChoice]);

  async function handleIdeaSubmit(event: React.FormEvent<HTMLFormElement>) {
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

  async function handleImportSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.importExistingFolder(importForm);
      navigate(response.recommended_next_route);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to import existing folder.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell
      title="Project Intake"
      subtitle={
        guidedMode
          ? "Guided walkthrough mode is active. Mission Control will keep the first pass safe, local, and easier to inspect."
          : demoMode
            ? "Dry-run demo mode is active. The form defaults to a safe local simulation flow."
            : "Start from an idea or import an existing local codebase without pretending every project begins life inside Mission Control."
      }
    >
      <div className="intake-grid">
        <SectionCard title="New Project" subtitle="Pick the intake path that matches reality instead of forcing every repo through the same ceremonial questionnaire.">
          <div className="button-row">
            <button type="button" className={intakeMode === "idea" ? "" : "button-ghost"} onClick={() => setIntakeMode("idea")}>
              Start from idea
            </button>
            <button type="button" className={intakeMode === "import" ? "" : "button-ghost"} onClick={() => setIntakeMode("import")}>
              Import existing folder/repo
            </button>
            <button type="button" className="button-ghost" onClick={() => setIntakeMode("docs")}>
              Continue from docs
            </button>
            <button type="button" className="button-ghost" onClick={() => setIntakeMode("clone")}>
              Clone from GitHub
            </button>
          </div>

          {intakeMode === "idea" ? (
            <form className="stack-form" onSubmit={handleIdeaSubmit}>
              {profile?.display_name ? (
                <div className="startup-note-card">
                  <strong>Created by {profile.display_name}</strong>
                  <p>The manager will address you by this name. You can change it later from the project Settings page.</p>
                </div>
              ) : null}
              {startupProviderChoice || profile?.selected_provider ? (
                <div className="startup-note-card">
                  <strong>Starting tool: {providerLabel(startupProviderChoice ?? profile?.selected_provider ?? "codex")}</strong>
                  <p>
                    {providerUsesAdapter(startupProviderChoice ?? profile?.selected_provider ?? "codex")
                      ? "This project uses an adapter-based provider path. Configure the exact local command in Settings before you launch live agents."
                      : "This project inherited your startup provider choice and is ready for local setup."}
                  </p>
                </div>
              ) : null}
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
                  <select value={form.provider} onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value as ProviderId }))}>
                    {PROVIDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Runner mode
                  <select value={form.runner_mode} onChange={(event) => setForm((current) => ({ ...current, runner_mode: event.target.value as RunnerMode }))}>
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
                  <select value={form.manager_mode} onChange={(event) => setForm((current) => ({ ...current, manager_mode: event.target.value as ManagerMode }))}>
                    <option value="auto">auto</option>
                    <option value="provider">provider</option>
                    <option value="deterministic">deterministic</option>
                  </select>
                </label>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() =>
                    setForm((current) => ({
                      ...current,
                      workspace_path: deriveDemoWorkspace(codexStatus?.runtime_directory),
                    }))
                  }
                >
                  Use demo path
                </button>
                <button type="submit" disabled={submitting}>
                  {submitting ? "Creating..." : "Create project docs"}
                </button>
              </div>
            </form>
          ) : null}

          {intakeMode === "import" ? (
            <form className="stack-form" onSubmit={handleImportSubmit}>
              <div className="startup-note-card">
                <strong>Initial scan is read-only</strong>
                <p>No commands are run, no files are edited, and the existing folder is linked in place by default.</p>
              </div>
              <div className="startup-note-card">
                <strong>Desktop folder picker support can be added later.</strong>
                <p>For now, paste the local folder path.</p>
              </div>
              <label>
                Project name
                <input
                  value={importForm.name}
                  onChange={(event) => setImportForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="Optional. Defaults to the folder name."
                />
              </label>
              <label>
                Local folder path
                <input
                  value={importForm.folder_path}
                  onChange={(event) => setImportForm((current) => ({ ...current, folder_path: event.target.value }))}
                  placeholder="C:/Users/you/projects/existing-repo"
                  required
                />
              </label>
              <div className="form-row">
                <label>
                  Import mode
                  <select value={importForm.import_mode} onChange={(event) => setImportForm((current) => ({ ...current, import_mode: event.target.value as "linked" }))}>
                    <option value="linked">Use folder in place</option>
                  </select>
                </label>
                <label>
                  Scan policy
                  <select
                    value={importForm.start_read_only_scan ? "scan_now" : "scan_later"}
                    onChange={(event) => setImportForm((current) => ({ ...current, start_read_only_scan: event.target.value === "scan_now" }))}
                  >
                    <option value="scan_now">Read-only scan now</option>
                    <option value="scan_later">Scan later</option>
                  </select>
                </label>
              </div>
              <div className="button-row">
                <button type="submit" disabled={submitting}>
                  {submitting ? "Importing and scanning..." : "Import existing folder"}
                </button>
              </div>
            </form>
          ) : null}

          {intakeMode === "docs" ? (
            <div className="startup-note-card">
              <strong>Continue from docs</strong>
              <p>This route is intentionally not wired in this pass. Use import mode for existing repos or start from idea for a clean Mission Control project.</p>
            </div>
          ) : null}

          {intakeMode === "clone" ? (
            <div className="startup-note-card">
              <strong>Clone from GitHub</strong>
              <p>Clone support should only appear when configured. This pass does not fake it.</p>
            </div>
          ) : null}

          {error ? <p className="error-text">{error}</p> : null}
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
                  <li>Managed local runtime folder</li>
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
              <button key={project.id} className="resume-item" onClick={() => navigate(project.slug ? `/projects/${project.id}/${project.slug}` : `/projects/${project.id}`)}>
                <strong>{project.name}</strong>
                <span>{project.status}</span>
                <small>{project.created_by ? `Created by ${project.created_by}` : project.workspace_path}</small>
              </button>
            ))}
            {!projects.length ? <p>No projects yet. Create the first one above.</p> : null}
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
