import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { LoadingBlock } from "../components/LoadingBlock";
import { ModelPicker } from "../components/ModelPicker";
import { ProjectShell } from "../components/ProjectShell";
import { SectionCard } from "../components/SectionCard";
import { PROVIDER_OPTIONS, providerUsesAdapter, providerUsesEndpoint } from "../lib/providers";
import type {
  Agent,
  ApprovalPolicy,
  CodexStatus,
  Project,
  ProjectSettings,
  ReasoningEffort,
  RunnerMode,
  SandboxMode,
  ProviderId,
} from "../types";

const FALLBACK_WORKER_ROLES = [
  "Primary implementation",
  "Secondary implementation",
  "Validation, docs, and handoff",
];

const REASONING_OPTIONS: Array<{ value: ReasoningEffort | ""; label: string }> = [
  { value: "", label: "Use provider default" },
  { value: "minimal", label: "minimal" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
];

function projectPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}` : `/projects/${projectId}`;
}

export function ModelsRunnersPage() {
  const { projectId, projectSlug } = useParams();
  const navigate = useNavigate();
  const numericProjectId = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [status, setStatus] = useState<CodexStatus | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [loadedProject, loadedAgents, loadedSettings, loadedStatus] = await Promise.all([
          api.getProject(numericProjectId),
          api.getAgents(numericProjectId),
          api.getSettings(numericProjectId),
          api.getSystemStatus(numericProjectId),
        ]);
        setProject(loadedProject);
        setAgents(loadedAgents);
        setSettings(loadedSettings);
        setStatus(loadedStatus);
        const canonicalPath = loadedProject.slug
          ? `/projects/${loadedProject.id}/${loadedProject.slug}/models-runners`
          : `/projects/${loadedProject.id}/models-runners`;
        const requestedPath = projectSlug
          ? `/projects/${loadedProject.id}/${projectSlug}/models-runners`
          : `/projects/${loadedProject.id}/models-runners`;
        if (canonicalPath !== requestedPath) {
          navigate(canonicalPath, { replace: true });
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load project models and runners.");
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, [navigate, numericProjectId, projectSlug]);

  useEffect(() => {
    if (!settings) {
      return undefined;
    }
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      void api
        .getSystemStatus({
          projectId: numericProjectId,
          provider: settings.provider,
          provider_endpoint: settings.provider_endpoint,
          adapter_command: settings.adapter_command,
          adapter_args: settings.adapter_args_json,
        })
        .then((nextStatus) => {
          if (!cancelled) {
            setStatus(nextStatus);
          }
        })
        .catch(() => undefined);
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [numericProjectId, settings?.adapter_args_json, settings?.adapter_command, settings?.provider, settings?.provider_endpoint]);

  const roleOptions = useMemo(() => {
    const activeWorkerRoles = agents.filter((agent) => agent.kind === "worker").map((agent) => agent.role);
    const savedRoles = Object.keys(settings?.per_role_model_overrides_json ?? {}).concat(
      Object.keys(settings?.per_role_reasoning_overrides_json ?? {}),
    );
    return Array.from(new Set([...FALLBACK_WORKER_ROLES, ...activeWorkerRoles, ...savedRoles]));
  }, [agents, settings]);

  const selectedProviderStatus = useMemo(
    () => status?.provider_statuses.find((entry) => entry.provider === settings?.provider) ?? null,
    [settings?.provider, status?.provider_statuses],
  );

  const modelSuggestions = selectedProviderStatus?.available_models ?? status?.available_models ?? [];
  const modelHelperText = useMemo(() => {
    if (!settings) {
      return "Model availability depends on the selected provider and active local session.";
    }
    if (settings.provider === "ollama") {
      return modelSuggestions.length
        ? `Detected ${modelSuggestions.length} Ollama model${modelSuggestions.length === 1 ? "" : "s"} from the configured local endpoint.`
        : "No Ollama models were detected from the configured local endpoint yet.";
    }
    return modelSuggestions.length
      ? `Detected ${modelSuggestions.length} suggested model${modelSuggestions.length === 1 ? "" : "s"} for ${selectedProviderStatus?.label ?? "the selected provider"}.`
      : "Model availability depends on the selected provider and active local session.";
  }, [modelSuggestions.length, selectedProviderStatus?.label, settings]);

  function updateField<Key extends keyof ProjectSettings>(key: Key, value: ProjectSettings[Key]) {
    if (!settings) {
      return;
    }
    setSettings({ ...settings, [key]: value });
  }

  function updateRoleModel(role: string, value: string) {
    if (!settings) {
      return;
    }
    const next = { ...settings.per_role_model_overrides_json };
    if (value.trim()) {
      next[role] = value;
    } else {
      delete next[role];
    }
    setSettings({ ...settings, per_role_model_overrides_json: next });
  }

  function updateRoleReasoning(role: string, value: ReasoningEffort | "") {
    if (!settings) {
      return;
    }
    const next = { ...settings.per_role_reasoning_overrides_json };
    if (value) {
      next[role] = value;
    } else {
      delete next[role];
    }
    setSettings({ ...settings, per_role_reasoning_overrides_json: next });
  }

  async function saveSettings() {
    if (!settings) {
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.updateSettings(numericProjectId, settings);
      setSettings(saved);
      setStatus(await api.getSystemStatus(numericProjectId));
      setNotice("Project model and runner settings saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save project settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProjectShell
      project={project}
      title="Models & Runners"
      subtitle="Project-scoped model, reasoning, runner, sandbox, and approval controls."
      rightRail={
        project ? (
          <div className="header-stack">
            <span className="header-chip">Project ID: {project.id}</span>
            <span className="header-chip">Status: {project.display_status}</span>
          </div>
        ) : null
      }
    >
      {loading || !settings ? (
        <LoadingBlock label="Loading model and runner settings..." />
      ) : (
        <div className="intake-grid">
          <SectionCard title="Provider and models" subtitle="Empty model or reasoning values mean the selected provider's current default stays in charge.">
            <div className="stack-form">
              <div className="form-row">
                <label>
                  Live provider
                  <select value={settings.provider} onChange={(event) => updateField("provider", event.target.value as ProviderId)}>
                    {PROVIDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Manager mode
                  <input value={project?.manager_mode ?? "auto"} disabled />
                </label>
              </div>
              <div className="form-row">
                <ModelPicker
                  label="Manager model"
                  value={settings.manager_model ?? ""}
                  onChange={(nextValue) => updateField("manager_model", nextValue || null)}
                  placeholder="Use provider default for manager"
                  suggestions={modelSuggestions}
                  helperText={modelHelperText}
                />
                <ModelPicker
                  label="Default worker model"
                  value={settings.default_worker_model ?? ""}
                  onChange={(nextValue) => updateField("default_worker_model", nextValue || null)}
                  placeholder="Use provider default for workers"
                  suggestions={modelSuggestions}
                  helperText={modelHelperText}
                />
              </div>
              <div className="form-row">
                <label>
                  Manager reasoning effort
                  <select
                    value={settings.manager_reasoning_effort ?? ""}
                    onChange={(event) => updateField("manager_reasoning_effort", (event.target.value || null) as ReasoningEffort | null)}
                  >
                    {REASONING_OPTIONS.map((option) => (
                      <option key={option.label} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Worker reasoning effort
                  <select
                    value={settings.default_worker_reasoning_effort ?? ""}
                    onChange={(event) => updateField("default_worker_reasoning_effort", (event.target.value || null) as ReasoningEffort | null)}
                  >
                    {REASONING_OPTIONS.map((option) => (
                      <option key={option.label} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {providerUsesAdapter(settings.provider) ? (
                <div className="form-row">
                  {providerUsesEndpoint(settings.provider) ? (
                    <label>
                      Provider endpoint
                      <input
                        value={settings.provider_endpoint ?? ""}
                        onChange={(event) => updateField("provider_endpoint", event.target.value || null)}
                        placeholder={settings.provider === "ollama" ? "http://127.0.0.1:11434" : "Optional provider base URL override"}
                      />
                    </label>
                  ) : null}
                  <label>
                    Adapter command
                    <input
                      value={settings.adapter_command ?? ""}
                      onChange={(event) => updateField("adapter_command", event.target.value || null)}
                      placeholder="python, node, llm-runner, etc."
                    />
                  </label>
                  <label>
                    Adapter args
                    <input
                      value={settings.adapter_args_json.join(" ")}
                      onChange={(event) =>
                        updateField(
                          "adapter_args_json",
                          event.target.value
                            .split(" ")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        )
                      }
                      placeholder="--json --project mission-control"
                    />
                  </label>
                </div>
              ) : null}
              <p className="section-footnote">Model availability depends on your selected provider and active local session. Per-run overrides take precedence over global CLI config for the run itself.</p>
            </div>
          </SectionCard>

          <SectionCard title="Run controls" subtitle="Mission Control passes these through the local runner layer instead of editing global provider config by default.">
            <div className="stack-form">
              <div className="form-row">
                <label>
                  Runner mode
                  <select value={settings.runner_mode} onChange={(event) => updateField("runner_mode", event.target.value as RunnerMode)}>
                    <option value="auto">auto</option>
                    <option value="cli">cli</option>
                    <option value="app_server" disabled={settings.provider !== "codex"}>
                      app_server {settings.provider !== "codex" ? "(Codex only)" : ""}
                    </option>
                    <option value="dry_run">dry_run</option>
                  </select>
                </label>
                <label>
                  Sandbox mode
                  <select value={settings.sandbox_mode} onChange={(event) => updateField("sandbox_mode", event.target.value as SandboxMode)}>
                    <option value="workspace-write">workspace-write</option>
                    <option value="read-only">read-only</option>
                  </select>
                </label>
              </div>
              <label>
                Approval policy
                <select value={settings.approval_policy} onChange={(event) => updateField("approval_policy", event.target.value as ApprovalPolicy)}>
                  <option value="on-request">on-request</option>
                  <option value="untrusted">untrusted</option>
                  <option value="never">never (risky)</option>
                </select>
              </label>
              <div className="button-row">
                <button type="button" onClick={() => void saveSettings()} disabled={saving}>
                  {saving ? "Saving..." : "Save project settings"}
                </button>
                {notice ? <span className="header-chip">{notice}</span> : null}
              </div>
              {error ? <p className="error-text">{error}</p> : null}
            </div>
          </SectionCard>

          <SectionCard title="Per-role overrides" subtitle="Role-specific overrides fall back to the default worker settings when left blank.">
            <div className="settings-table">
              <div className="settings-table__header">
                <span>Role</span>
                <span>Model override</span>
                <span>Reasoning override</span>
                <span>Action</span>
              </div>
              {roleOptions.map((role) => (
                <div key={role} className="settings-table__row">
                  <strong>{role}</strong>
                  <ModelPicker
                    label="Model override"
                    value={settings.per_role_model_overrides_json[role] ?? ""}
                    onChange={(nextValue) => updateRoleModel(role, nextValue)}
                    placeholder="Use worker default"
                    suggestions={modelSuggestions}
                  />
                  <select
                    value={settings.per_role_reasoning_overrides_json[role] ?? ""}
                    onChange={(event) => updateRoleReasoning(role, event.target.value as ReasoningEffort | "")}
                  >
                    {REASONING_OPTIONS.map((option) => (
                      <option key={option.label} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="button-ghost"
                    onClick={() => {
                      updateRoleModel(role, "");
                      updateRoleReasoning(role, "");
                    }}
                  >
                    Clear override
                  </button>
                </div>
              ))}
            </div>
          </SectionCard>

          <SectionCard title="Provider runtime status" subtitle="Mission Control preserves Codex or ChatGPT sign-in usage for Codex and reports the local runtime state honestly.">
            {status ? (
              <div className="status-grid">
                <div className="metric-card">
                  <span>Selected provider</span>
                  <strong>{status.selected_provider_label}</strong>
                </div>
                <div className="metric-card">
                  <span>CLI</span>
                  <strong>{status.cli_detected ? status.cli_version ?? "Detected" : "Unavailable"}</strong>
                </div>
                <div className="metric-card">
                  <span>Auth</span>
                  <strong>
                    {selectedProviderStatus?.auth_status_detectable
                      ? status.authenticated
                        ? status.auth_mode ?? "Connected"
                        : "Not signed in"
                      : "Managed outside Mission Control"}
                  </strong>
                </div>
                <div className="metric-card">
                  <span>App-server</span>
                  <strong>{status.app_server_handshake_status}</strong>
                </div>
                <div className="status-list">
                  <h3>Provider capabilities</h3>
                  <ul>
                    {status.provider_statuses.map((provider) => (
                      <li key={provider.provider}>
                        {provider.label}: {provider.cli_detected ? "CLI detected" : "CLI missing"}; model override {provider.supports_model_override ? "yes" : "no"}; app-server {provider.supports_app_server ? "yes" : "no"}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="status-list">
                  <h3>Project context</h3>
                  <ul>
                    <li>Project route: {projectPath(project?.id ?? numericProjectId, project?.slug)}</li>
                    <li>Workspace path: {project?.workspace_path ?? "Unknown"}</li>
                    <li>Diagnostics directory: {status.diagnostics_directory ?? "Unknown"}</li>
                  </ul>
                </div>
              </div>
            ) : (
              <p className="section-footnote">System status is not available.</p>
            )}
          </SectionCard>
        </div>
      )}
    </ProjectShell>
  );
}
