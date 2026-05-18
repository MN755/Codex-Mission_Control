import { useEffect, useState } from "react";

import { api } from "../api/client";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { useHomeState } from "../state/useHomeState";
import type { AppProfile, ThemeMode, StartupBehavior } from "../types";

const THEME_OPTIONS: ThemeMode[] = ["system", "dark", "light"];
const STARTUP_BEHAVIOR_OPTIONS: StartupBehavior[] = ["dashboard", "last_project", "restore_previous_page"];

export function SettingsPage() {
  const { summary, systemStatus, profile, loading, error, reload, toggleProjectPin } = useHomeState();
  const [draft, setDraft] = useState<AppProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const effectiveProfile = draft ?? profile;

  useEffect(() => {
    if (profile && !draft) {
      setDraft(profile);
    }
  }, [draft, profile]);

  async function save() {
    if (!effectiveProfile) {
      return;
    }
    setSaving(true);
    setNotice(null);
    try {
      await api.updateProfile({
        display_name: effectiveProfile.display_name ?? "Operator",
        preferred_provider_choice: effectiveProfile.preferred_provider_choice,
        preferred_start_mode: effectiveProfile.preferred_start_mode,
        onboarding_completed: effectiveProfile.onboarding_completed,
        theme: effectiveProfile.theme,
        startup_behavior: effectiveProfile.startup_behavior,
        notification_preferences_json: effectiveProfile.notification_preferences_json,
        dashboard_widgets_json: effectiveProfile.dashboard_widgets_json,
        dashboard_widget_preferences_json: effectiveProfile.dashboard_widget_preferences_json,
      });
      setNotice("App settings saved.");
      await reload();
    } finally {
      setSaving(false);
    }
  }

  function setNotificationPreference(key: string, checked: boolean) {
    if (!effectiveProfile) {
      return;
    }
    setDraft({
      ...effectiveProfile,
      notification_preferences_json: {
        ...effectiveProfile.notification_preferences_json,
        [key]: checked,
      },
    });
  }

  return (
    <HomeShell
      title="Settings"
      subtitle="General app preferences stay here. Project-specific provider and runner controls live under Models & Runners."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
    >
      {loading || !effectiveProfile ? (
        <LoadingBlock label="Loading app settings..." />
      ) : (
        <div className="intake-grid">
          <SectionCard title="Operator profile" subtitle="Mission Control uses this name in project authorship and manager responses.">
            <div className="stack-form">
              <label>
                Display name
                <input
                  maxLength={50}
                  value={effectiveProfile.display_name ?? ""}
                  onChange={(event) => setDraft({ ...effectiveProfile, display_name: event.target.value.slice(0, 50) })}
                  placeholder="Enter your name"
                />
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Appearance and startup" subtitle="Choose how Mission Control opens after the startup coordinator completes.">
            <div className="stack-form">
              <div className="form-row">
                <label>
                  Theme
                  <select
                    value={effectiveProfile.theme}
                    onChange={(event) => setDraft({ ...effectiveProfile, theme: event.target.value as ThemeMode })}
                  >
                    {THEME_OPTIONS.map((theme) => (
                      <option key={theme} value={theme}>
                        {theme}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Startup behavior
                  <select
                    value={effectiveProfile.startup_behavior}
                    onChange={(event) => setDraft({ ...effectiveProfile, startup_behavior: event.target.value as StartupBehavior })}
                  >
                    {STARTUP_BEHAVIOR_OPTIONS.map((behavior) => (
                      <option key={behavior} value={behavior}>
                        {behavior.replace(/_/g, " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="section-footnote">Startup routing still passes through `/startup`. This setting controls where Mission Control should land once startup is healthy.</p>
            </div>
          </SectionCard>

          <SectionCard title="Notifications" subtitle="Keep alerts practical and local.">
            <div className="stack-form">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(effectiveProfile.notification_preferences_json.desktop_toasts)}
                  onChange={(event) => setNotificationPreference("desktop_toasts", event.target.checked)}
                />
                Show desktop notifications when action is required
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(effectiveProfile.notification_preferences_json.sound)}
                  onChange={(event) => setNotificationPreference("sound", event.target.checked)}
                />
                Play a sound for action-required events
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(effectiveProfile.notification_preferences_json.action_required_only ?? true)}
                  onChange={(event) => setNotificationPreference("action_required_only", event.target.checked)}
                />
                Notify only when the manager or a tool needs the user
              </label>
            </div>
          </SectionCard>

          <SectionCard title="Widget preferences" subtitle="Dashboard widgets are intentionally lightweight and stored locally with the app profile.">
            <div className="stack-form">
              <p className="section-footnote">
                Current dashboard widgets: {effectiveProfile.dashboard_widgets_json.length ? effectiveProfile.dashboard_widgets_json.join(", ") : "None selected yet."}
              </p>
            </div>
          </SectionCard>

          <SectionCard title="Privacy and runtime" subtitle="Mission Control stays local-first and does not require API keys for the Codex login flow.">
            <div className="status-list">
              <ul>
                <li>Runtime directory: {systemStatus?.runtime_directory ?? "Unknown"}</li>
                <li>Diagnostics directory: {systemStatus?.diagnostics_directory ?? "Unknown"}</li>
                <li>Selected provider: {systemStatus?.selected_provider_label ?? "Unknown"}</li>
                <li>Codex or ChatGPT session usage is preserved where supported.</li>
              </ul>
            </div>
          </SectionCard>

          <SectionCard title="Reset setup" subtitle="This pass keeps reset behavior safe and explicit.">
            <div className="stack-form">
              <p className="section-footnote">Rerunning first-time setup is not one-click yet. Use the diagnostics page first, then make an intentional reset only when you want to rebuild the app state.</p>
              <button type="button" className="button-ghost" disabled>
                Safe reset flow coming soon
              </button>
            </div>
          </SectionCard>

          <div className="button-row">
            <button type="button" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving..." : "Save app settings"}
            </button>
            {notice ? <span className="header-chip">{notice}</span> : null}
            {error ? <span className="error-text">{error}</span> : null}
          </div>
        </div>
      )}
    </HomeShell>
  );
}
