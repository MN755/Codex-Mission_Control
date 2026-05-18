import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { AppShell } from "../components/AppShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { ModelPicker } from "../components/ModelPicker";
import { MissionControlMark } from "../components/MissionControlMark";
import { SectionCard } from "../components/SectionCard";
import { PROVIDER_OPTIONS, providerLabel } from "../lib/providers";
import type { AppProfile, ApprovalPolicy, AuthJob, AuthState, CodexStatus, ProviderId, ReasoningEffort, RunnerMode, SandboxMode, StartupStartMode } from "../types";

const REASONING_OPTIONS = [
  { value: "", label: "Use provider default" },
  { value: "minimal", label: "minimal" },
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
] as const;

const RUNNER_OPTIONS = [
  { value: "auto", label: "auto" },
  { value: "cli", label: "cli" },
  { value: "app_server", label: "app_server" },
  { value: "dry_run", label: "dry_run" },
] as const;

const START_MODE_OPTIONS: Array<{ value: StartupStartMode; label: string; description: string }> = [
  { value: "new_project", label: "Start a new project", description: "Jump directly into project intake and build a real workspace." },
  { value: "guided_walkthrough", label: "Take the guided walkthrough", description: "Use a safer intro path first, then move into live project work." },
];

type SetupStep = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export function SetupPage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<AppProfile | null>(null);
  const [authState, setAuthState] = useState<AuthState | null>(null);
  const [systemStatus, setSystemStatus] = useState<CodexStatus | null>(null);
  const [providerPreviewStatus, setProviderPreviewStatus] = useState<CodexStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<SetupStep>(0);
  const [apiKey, setApiKey] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [form, setForm] = useState({
    username: "",
    provider: "codex" as ProviderId,
    start_mode: "new_project" as StartupStartMode,
    auth_mode: "pending" as string,
    provider_endpoint: "http://localhost:11434",
    adapter_command: "",
    adapter_args: "",
    github_status: "not_connected",
    vercel_status: "coming_soon",
    notion_status: "configure_manually",
    manager_model: "",
    default_worker_model: "",
    manager_reasoning_effort: "" as ReasoningEffort | "",
    default_worker_reasoning_effort: "" as ReasoningEffort | "",
    runner_mode: "auto" as RunnerMode,
    sandbox_mode: "workspace-write" as SandboxMode,
    approval_policy: "on-request" as ApprovalPolicy,
  });

  async function loadState() {
    const [workspaceProfile, auth, status] = await Promise.all([api.getProfile(), api.getAuthState(), api.getSystemStatus()]);
    setProfile(workspaceProfile);
    setAuthState(auth);
    setSystemStatus(status);
    setProviderPreviewStatus(status);
    setForm((current) => ({
      ...current,
      username: workspaceProfile.display_name ?? current.username,
      provider: workspaceProfile.selected_provider ?? current.provider,
      start_mode: workspaceProfile.preferred_start_mode ?? current.start_mode,
      auth_mode: workspaceProfile.auth_mode ?? current.auth_mode,
      provider_endpoint: workspaceProfile.provider_endpoint ?? current.provider_endpoint,
      adapter_command: workspaceProfile.adapter_command ?? current.adapter_command,
      adapter_args: workspaceProfile.adapter_args_json.join(" ") || current.adapter_args,
      manager_model: workspaceProfile.manager_model ?? current.manager_model,
      default_worker_model: workspaceProfile.default_worker_model ?? current.default_worker_model,
      manager_reasoning_effort: workspaceProfile.manager_reasoning_effort ?? current.manager_reasoning_effort,
      default_worker_reasoning_effort: workspaceProfile.default_worker_reasoning_effort ?? current.default_worker_reasoning_effort,
      runner_mode: workspaceProfile.default_runner_mode ?? current.runner_mode,
      sandbox_mode: workspaceProfile.sandbox_mode ?? current.sandbox_mode,
      approval_policy: workspaceProfile.approval_policy ?? current.approval_policy,
      github_status: String((workspaceProfile.connected_accounts_json.github as { status?: string } | undefined)?.status ?? current.github_status),
      vercel_status: String((workspaceProfile.connected_accounts_json.vercel as { status?: string } | undefined)?.status ?? current.vercel_status),
      notion_status: String((workspaceProfile.connected_accounts_json.notion as { status?: string } | undefined)?.status ?? current.notion_status),
    }));
    setLoading(false);
  }

  useEffect(() => {
    void loadState().catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : "Failed to load first-time setup state.");
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

  useEffect(() => {
    if (loading) {
      return undefined;
    }
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      void api
        .getSystemStatus({
          provider: form.provider,
          provider_endpoint: form.provider === "ollama" ? form.provider_endpoint : null,
          adapter_command: form.provider === "custom" ? form.adapter_command : null,
          adapter_args:
            form.provider === "custom"
              ? form.adapter_args
                  .split(" ")
                  .map((item) => item.trim())
                  .filter(Boolean)
              : [],
        })
        .then((status) => {
          if (!cancelled) {
            setProviderPreviewStatus(status);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setProviderPreviewStatus(null);
          }
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [form.adapter_args, form.adapter_command, form.provider, form.provider_endpoint, loading]);

  const stepTitle = useMemo(() => {
    return ["Welcome", "Username", "Provider", "API or Login", "Connect Accounts", "Model / Runner Defaults", "Finish"][step];
  }, [step]);

  const currentJob: AuthJob | null = authState?.current_job ?? systemStatus?.current_auth_job ?? null;
  const effectiveSystemStatus = providerPreviewStatus ?? systemStatus;
  const selectedProviderStatus = useMemo(
    () => effectiveSystemStatus?.provider_statuses.find((entry) => entry.provider === form.provider) ?? null,
    [effectiveSystemStatus?.provider_statuses, form.provider],
  );
  const modelSuggestions = selectedProviderStatus?.available_models ?? effectiveSystemStatus?.available_models ?? [];
  const modelHelperText = useMemo(() => {
    if (form.provider === "ollama") {
      if (modelSuggestions.length) {
        return `Detected ${modelSuggestions.length} Ollama model${modelSuggestions.length === 1 ? "" : "s"} from ${form.provider_endpoint}. You can still type a custom model string.`;
      }
      return `No Ollama models were detected at ${form.provider_endpoint}. You can still type a custom model string.`;
    }
    if (modelSuggestions.length) {
      return `Detected ${modelSuggestions.length} suggested model${modelSuggestions.length === 1 ? "" : "s"} for ${providerLabel(form.provider)}.`;
    }
    return "Model availability depends on your selected provider and active session. You can still type a custom model string.";
  }, [form.provider, form.provider_endpoint, modelSuggestions.length]);

  async function runAuthAction(action: Promise<AuthJob>, nextWorking: string, nextAuthMode: string) {
    setWorking(nextWorking);
    setError(null);
    try {
      const job = await action;
      setAuthState((current) => (current ? { ...current, current_job: job } : current));
      setForm((current) => ({ ...current, auth_mode: nextAuthMode }));
      await loadState();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Authentication flow failed to start.");
    } finally {
      setWorking(null);
    }
  }

  async function finishSetup() {
    setSaving(true);
    setError(null);
    try {
      await api.completeFirstRun({
        username: form.username.trim(),
        provider: form.provider,
        auth_mode: form.auth_mode,
        connected_accounts_summary: {
          github: { status: form.github_status },
          vercel: { status: form.vercel_status },
          notion: { status: form.notion_status },
        },
        default_runner_mode: form.runner_mode,
        manager_model: form.manager_model || null,
        default_worker_model: form.default_worker_model || null,
        manager_reasoning_effort: (form.manager_reasoning_effort || null) as "minimal" | "low" | "medium" | "high" | null,
        default_worker_reasoning_effort: (form.default_worker_reasoning_effort || null) as "minimal" | "low" | "medium" | "high" | null,
        sandbox_mode: form.sandbox_mode as "workspace-write" | "read-only",
        approval_policy: form.approval_policy as "on-request" | "untrusted" | "never",
        provider_endpoint: form.provider === "ollama" ? form.provider_endpoint : null,
        adapter_command: form.provider !== "codex" && form.provider !== "claude_code" ? form.adapter_command || null : null,
        adapter_args: form.adapter_args
          .split(" ")
          .map((item) => item.trim())
          .filter(Boolean),
        start_mode: form.start_mode,
      });
      navigate("/dashboard", { replace: true });
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Could not complete setup.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <AppShell title="Setup" subtitle="Preparing the first-time setup wizard.">
        <LoadingBlock label="Loading setup state..." />
      </AppShell>
    );
  }

  return (
    <AppShell title="First-time setup" subtitle="Configure Mission Control once, then launch directly into the dashboard on future starts.">
      <div className="setup-shell">
        <SectionCard
          title={stepTitle}
          subtitle={`Step ${step + 1} of 7`}
          actions={
            <div className="button-row">
              {step > 0 ? (
                <button type="button" className="button-ghost" onClick={() => setStep((current) => Math.max(0, current - 1) as SetupStep)}>
                  Back
                </button>
              ) : null}
              {step < 6 ? (
                <button
                  type="button"
                  onClick={() => setStep((current) => Math.min(6, current + 1) as SetupStep)}
                  disabled={(step === 1 && !form.username.trim()) || (step === 3 && form.provider === "codex" && !authState?.authenticated && form.auth_mode !== "dry_run")}
                >
                  Continue
                </button>
              ) : (
                <button type="button" onClick={() => void finishSetup()} disabled={saving || !form.username.trim()}>
                  {saving ? "Finishing..." : "Finish and open Dashboard"}
                </button>
              )}
            </div>
          }
        >
          {step === 0 ? (
            <div className="stack-form">
              <div className="launchpad-hero launchpad-hero--compact">
                <MissionControlMark className="launchpad-hero__mark launchpad-hero__mark--halo" />
                <div className="launchpad-hero__copy">
                  <span className="eyebrow">Welcome</span>
                  <h2>Mission Control manages coding agents through one Manager AI.</h2>
                  <p>You can use dry-run mode, Codex via ChatGPT login, or other configured providers. No API key is required for dry-run or Codex login flows.</p>
                </div>
              </div>
              <label>
                How would you like to begin?
                <select value={form.start_mode} onChange={(event) => setForm((current) => ({ ...current, start_mode: event.target.value as StartupStartMode }))}>
                  {START_MODE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <span className="section-footnote">{START_MODE_OPTIONS.find((option) => option.value === form.start_mode)?.description}</span>
              </label>
            </div>
          ) : null}

          {step === 1 ? (
            <div className="stack-form">
              <label>
                Display name
                <input
                  maxLength={50}
                  value={form.username}
                  onChange={(event) => setForm((current) => ({ ...current, username: event.target.value.slice(0, 50) }))}
                  placeholder="What should the manager call you?"
                />
                <span className="section-footnote">{form.username.length}/50 characters. This becomes the project author stamp and the name the manager uses.</span>
              </label>
            </div>
          ) : null}

          {step === 2 ? (
            <div className="option-grid">
              {PROVIDER_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`selection-card ${form.provider === option.value ? "selection-card--active" : ""}`}
                  onClick={() => setForm((current) => ({ ...current, provider: option.value }))}
                >
                  <strong>{option.label}</strong>
                  <span>{option.description}</span>
                </button>
              ))}
            </div>
          ) : null}

          {step === 3 ? (
            <div className="stack-form">
              {form.provider === "codex" ? (
                <>
                  <div className="startup-note-card">
                    <strong>Codex via ChatGPT Login</strong>
                    <p>Check your local Codex login state. Mission Control uses the local Codex session and does not require an API key for this path.</p>
                  </div>
                  <div className="button-row">
                    <button type="button" onClick={() => void loadState()} className="button-ghost">
                      Check Codex login status
                    </button>
                    <button type="button" onClick={() => setForm((current) => ({ ...current, auth_mode: authState?.auth_mode ?? "chatgpt" }))} disabled={!authState?.authenticated}>
                      I am signed in
                    </button>
                    <button type="button" className="button-ghost" onClick={() => setForm((current) => ({ ...current, auth_mode: "dry_run" }))}>
                      Use dry-run for now
                    </button>
                  </div>
                  <div className="launchpad-auth-grid">
                    <div className="launchpad-auth-card">
                      <h3>Local sign-in</h3>
                      <p>{authState?.login_status ?? "Codex login status is not available yet."}</p>
                      <div className="button-row">
                        <button type="button" onClick={() => void runAuthAction(api.loginWithChatGpt(false), "chatgpt", "chatgpt")} disabled={working !== null || !authState?.chatgpt_supported}>
                          {working === "chatgpt" ? "Starting sign-in..." : "Sign in with ChatGPT"}
                        </button>
                        <button type="button" className="button-ghost" onClick={() => void runAuthAction(api.loginWithDeviceCode(), "device_auth", "device_auth")} disabled={working !== null || !authState?.device_auth_supported}>
                          {working === "device_auth" ? "Opening device flow..." : "Use device code"}
                        </button>
                      </div>
                    </div>
                    <div className="launchpad-auth-card">
                      <h3>Optional API key path</h3>
                      <p>If you explicitly want API billing, Mission Control can hand a key once to the local Codex CLI login flow. The raw key is not stored here.</p>
                      <label>
                        OpenAI API key
                        <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="sk-..." />
                      </label>
                      <button type="button" className="button-ghost" onClick={() => void runAuthAction(api.loginWithApiKey(apiKey), "api_key", "api_key")} disabled={working !== null || !apiKey.trim()}>
                        {working === "api_key" ? "Sending key..." : "Use API key"}
                      </button>
                    </div>
                  </div>
                </>
              ) : null}

              {form.provider === "ollama" ? (
                <>
                  <label>
                    Ollama endpoint
                    <input value={form.provider_endpoint} onChange={(event) => setForm((current) => ({ ...current, provider_endpoint: event.target.value }))} />
                  </label>
                  <div className="startup-note-card">
                    <strong>Local-first setup</strong>
                    <p>Mission Control will save this endpoint for startup checks. Live execution still uses your local adapter or wrapper command.</p>
                  </div>
                </>
              ) : null}

              {["openai_api", "anthropic_api", "xai_api"].includes(form.provider) ? (
                <>
                  <label>
                    API key
                    <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="Enter key for validation only" />
                  </label>
                  <div className="startup-note-card">
                    <strong>API key storage is not implemented in Mission Control.</strong>
                    <p>Keep this provider configured outside the app. The key you type here is not persisted to SQLite or logs.</p>
                  </div>
                </>
              ) : null}

              {form.provider === "claude_code" ? (
                <div className="startup-note-card">
                  <strong>Claude Code login stays outside Mission Control.</strong>
                  <p>Sign in with the local Claude Code CLI if needed, then continue.</p>
                </div>
              ) : null}

              {form.provider === "custom" ? (
                <>
                  <label>
                    Adapter command
                    <input value={form.adapter_command} onChange={(event) => setForm((current) => ({ ...current, adapter_command: event.target.value }))} placeholder="python, node, llm-runner, etc." />
                  </label>
                  <label>
                    Adapter args
                    <input value={form.adapter_args} onChange={(event) => setForm((current) => ({ ...current, adapter_args: event.target.value }))} placeholder="--json --profile mission-control" />
                  </label>
                  <div className="startup-note-card">
                    <strong>Custom providers use local adapter commands.</strong>
                    <p>Mission Control will not fake OAuth or hide credential requirements. Configure your adapter honestly and keep secrets outside the app.</p>
                  </div>
                </>
              ) : null}

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
            </div>
          ) : null}

          {step === 4 ? (
            <div className="option-grid">
              {[
                { key: "github_status", title: "GitHub", description: "Connect later or configure manually." },
                { key: "vercel_status", title: "Vercel", description: "Optional deployment and preview workflows." },
                { key: "notion_status", title: "Notion", description: "Optional research and documentation handoff." },
              ].map((item) => (
                <div key={item.key} className="selection-card">
                  <strong>{item.title}</strong>
                  <span>{item.description}</span>
                  <label>
                    Status
                    <select
                      value={String(form[item.key as keyof typeof form])}
                      onChange={(event) => setForm((current) => ({ ...current, [item.key]: event.target.value }))}
                    >
                      <option value="not_connected">Not connected</option>
                      <option value="configure_manually">Configure manually</option>
                      <option value="coming_soon">Coming soon</option>
                      <option value="connected">Connected</option>
                    </select>
                  </label>
                </div>
              ))}
              <div className="button-row">
                <button type="button" className="button-ghost" onClick={() => setStep(5)}>
                  Skip for now
                </button>
              </div>
            </div>
          ) : null}

          {step === 5 ? (
            <div className="stack-form">
              <div className="form-row">
                <ModelPicker
                  label="Manager model"
                  value={form.manager_model}
                  onChange={(nextValue) => setForm((current) => ({ ...current, manager_model: nextValue }))}
                  placeholder="Use provider default"
                  suggestions={modelSuggestions}
                  helperText={modelHelperText}
                />
                <ModelPicker
                  label="Default worker model"
                  value={form.default_worker_model}
                  onChange={(nextValue) => setForm((current) => ({ ...current, default_worker_model: nextValue }))}
                  placeholder="Use provider default"
                  suggestions={modelSuggestions}
                  helperText={modelHelperText}
                />
              </div>
              <div className="form-row">
                <label>
                  Manager reasoning effort
                  <select
                    value={form.manager_reasoning_effort}
                    onChange={(event) => setForm((current) => ({ ...current, manager_reasoning_effort: event.target.value as ReasoningEffort | "" }))}
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
                    value={form.default_worker_reasoning_effort}
                    onChange={(event) => setForm((current) => ({ ...current, default_worker_reasoning_effort: event.target.value as ReasoningEffort | "" }))}
                  >
                    {REASONING_OPTIONS.map((option) => (
                      <option key={option.label} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="form-row">
                <label>
                  Runner mode
                  <select value={form.runner_mode} onChange={(event) => setForm((current) => ({ ...current, runner_mode: event.target.value as RunnerMode }))}>
                    {RUNNER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value} disabled={option.value === "app_server" && form.provider !== "codex"}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Sandbox mode
                  <select value={form.sandbox_mode} onChange={(event) => setForm((current) => ({ ...current, sandbox_mode: event.target.value as SandboxMode }))}>
                    <option value="workspace-write">workspace-write</option>
                    <option value="read-only">read-only</option>
                  </select>
                </label>
                <label>
                  Approval policy
                  <select value={form.approval_policy} onChange={(event) => setForm((current) => ({ ...current, approval_policy: event.target.value as ApprovalPolicy }))}>
                    <option value="on-request">on-request</option>
                    <option value="untrusted">untrusted</option>
                    <option value="never">never (risky)</option>
                  </select>
                </label>
              </div>
              <p className="section-footnote">Leaving model fields empty uses the provider default. Runner and approval settings still stay local and do not rewrite global Codex config.</p>
            </div>
          ) : null}

          {step === 6 ? (
            <div className="stack-form">
              <div className="startup-note-card">
                <strong>Setup summary</strong>
                <p>Review this once, then finish and open the dashboard.</p>
              </div>
              <ul className="flat-list">
                <li>Username: {form.username || "Not set"}</li>
                <li>Provider: {providerLabel(form.provider)}</li>
                <li>Auth mode: {form.auth_mode}</li>
                <li>Start mode: {START_MODE_OPTIONS.find((option) => option.value === form.start_mode)?.label}</li>
                <li>GitHub: {form.github_status}</li>
                <li>Vercel: {form.vercel_status}</li>
                <li>Notion: {form.notion_status}</li>
                <li>Runner mode: {form.runner_mode}</li>
                <li>Manager model: {form.manager_model || "Use provider default"}</li>
                <li>Default worker model: {form.default_worker_model || "Use provider default"}</li>
              </ul>
            </div>
          ) : null}

          {error ? <p className="error-text">{error}</p> : null}
        </SectionCard>
      </div>
    </AppShell>
  );
}
