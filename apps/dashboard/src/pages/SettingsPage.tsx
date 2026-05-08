import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import type { Agent, ApprovalPolicy, CodexStatus, Project, ProjectSettings, ReasoningEffort, RunnerMode, SandboxMode } from "../types";

const FALLBACK_WORKER_ROLES = [
  "Primary implementation",
  "Secondary implementation",
  "Validation, docs, and handoff",
];

const REASONING_OPTIONS: Array<{ value: ReasoningEffort | ""; label: string }> = [
  { value: "", label: "Use Codex default" },
  { value: "minimal", label: "minimal" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
];

export function SettingsPage() {
  const { projectId } = useParams();
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
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load settings.");
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, [numericProjectId]);

  const roleOptions = useMemo(() => {
    const activeWorkerRoles = agents.filter((agent) => agent.kind === "worker").map((agent) => agent.role);
    const savedRoles = Object.keys(settings?.per_role_model_overrides_json ?? {}).concat(
      Object.keys(settings?.per_role_reasoning_overrides_json ?? {}),
    );
    return Array.from(new Set([...FALLBACK_WORKER_ROLES, ...activeWorkerRoles, ...savedRoles]));
  }, [agents, settings]);

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
      setNotice("Settings saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
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

  function updateField<Key extends keyof ProjectSettings>(key: Key, value: ProjectSettings[Key]) {
    if (!settings) {
      return;
    }
    setSettings({ ...settings, [key]: value });
  }

  return (
    <AppShell
      projectId={numericProjectId}
      title="Project Settings"
      subtitle="Choose manager and worker run defaults without touching your global Codex config."
      rightRail={
        project ? (
          <div className="header-stack">
            <span className="header-chip">Manager: {project.manager_mode}</span>
            <span className="header-chip">Runner: {settings?.runner_mode ?? project.runner_mode}</span>
          </div>
        ) : null
      }
    >
      {loading || !settings ? (
        <LoadingBlock label="Loading settings..." />
      ) : (
        <div className="intake-grid">
          <SectionCard title="Model controls" subtitle="Leave model or reasoning blank to use the current Codex default from your local session.">
            <div className="stack-form">
              <div className="form-row">
                <label>
                  Manager model
                  <input
                    list="model-suggestions"
                    value={settings.manager_model ?? ""}
                    onChange={(event) => updateField("manager_model", event.target.value || null)}
                    placeholder="Use Codex default"
                  />
                </label>
                <label>
                  Default worker model
                  <input
                    list="model-suggestions"
                    value={settings.default_worker_model ?? ""}
                    onChange={(event) => updateField("default_worker_model", event.target.value || null)}
                    placeholder="Use Codex default"
                  />
                </label>
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
              <datalist id="model-suggestions">
                {(status?.available_models ?? []).map((model) => (
                  <option key={model} value={model} />
                ))}
              </datalist>
            </div>
          </SectionCard>

          <SectionCard title="Run controls" subtitle="These apply to both manager turns and worker tasks unless a role override changes the model or reasoning.">
            <div className="stack-form">
              <div className="form-row">
                <label>
                  Runner mode
                  <select value={settings.runner_mode} onChange={(event) => updateField("runner_mode", event.target.value as RunnerMode)}>
                    <option value="auto">auto</option>
                    <option value="cli">cli</option>
                    <option value="app_server">app_server</option>
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
                <button onClick={() => void saveSettings()} disabled={saving}>
                  {saving ? "Saving..." : "Save settings"}
                </button>
                {notice ? <span className="header-chip">{notice}</span> : null}
              </div>
              {error ? <p className="error-text">{error}</p> : null}
            </div>
          </SectionCard>

          <SectionCard title="Role overrides" subtitle="Overrides are keyed by worker role. Blank values fall back to the default worker settings.">
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
                  <input
                    list="model-suggestions"
                    value={settings.per_role_model_overrides_json[role] ?? ""}
                    onChange={(event) => updateRoleModel(role, event.target.value)}
                    placeholder="Use worker default"
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

          <SectionCard title="Local Codex status" subtitle="These controls prefer your existing Codex or ChatGPT sign-in. API-key auth is optional and only used if you chose it from the desktop launchpad.">
            {status ? (
              <div className="status-grid">
                <div className="metric-card">
                  <span>CLI</span>
                  <strong>{status.cli_detected ? status.cli_version ?? "Detected" : "Unavailable"}</strong>
                </div>
                <div className="metric-card">
                  <span>Auth</span>
                  <strong>{status.authenticated ? status.auth_mode ?? "Connected" : "Not signed in"}</strong>
                </div>
                <div className="metric-card">
                  <span>Backend port</span>
                  <strong>{status.backend_port}</strong>
                </div>
                <div className="metric-card">
                  <span>Frontend port</span>
                  <strong>{status.frontend_port ?? "Unknown"}</strong>
                </div>
              </div>
            ) : (
              <p>System status is not available.</p>
            )}
          </SectionCard>
        </div>
      )}
    </AppShell>
  );
}
