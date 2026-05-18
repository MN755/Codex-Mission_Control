import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { CommandIcon } from "../components/CommandIcon";
import { HomeShell } from "../components/HomeShell";
import { LoadingBlock } from "../components/LoadingBlock";
import { SectionCard } from "../components/SectionCard";
import { WidgetGrid } from "../components/WidgetGrid";
import { WidgetSelectorPanel } from "../components/WidgetSelectorPanel";
import { useHomeState } from "../state/useHomeState";
import type { CodexStatus, DashboardSummary, Project, WidgetDataResponse, WidgetDefinition, WidgetInstance, WidgetSize } from "../types";

const LEGACY_DASHBOARD_WIDGET_AREA = "dashboard_main";
const LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH = "Diagnostics Summary";

function legacyDashboardCatalog(summary: DashboardSummary | null): WidgetDefinition[] {
  const types = new Set<string>();
  const legacyWidgets = Array.isArray(summary?.widgets) ? summary?.widgets : [];
  const availableWidgets = Array.isArray(summary?.available_widgets) ? summary?.available_widgets : [];
  if (legacyWidgets.length) {
    types.add(LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH);
  }
  for (const widgetType of [...legacyWidgets, ...availableWidgets]) {
    if (typeof widgetType === "string" && widgetType.trim()) {
      types.add(widgetType);
    }
  }

  return [...types].map((widgetType, index) => ({
    id: -(index + 1),
    widget_type: widgetType,
    title: widgetType === LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH ? "System Health" : widgetType,
    description: `Legacy compatibility widget for ${widgetType}.`,
    scope: "dashboard",
    default_area: LEGACY_DASHBOARD_WIDGET_AREA,
    default_size: widgetType === LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH ? "medium" : "large",
    category: widgetType === LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH ? "Diagnostics" : "Attention",
    requires_project: false,
    requires_tool: null,
    coming_soon: false,
    risk_level: null,
  }));
}

function legacyDashboardInstances(summary: DashboardSummary | null): WidgetInstance[] {
  const legacyWidgets = Array.isArray(summary?.widgets) ? summary?.widgets : [];
  if (!legacyWidgets.length) {
    return [];
  }

  const types = [LEGACY_DASHBOARD_WIDGETS_WITH_SYSTEM_HEALTH, ...legacyWidgets].filter(
    (widgetType, index, items) => items.indexOf(widgetType) === index,
  );
  const now = new Date().toISOString();

  return types.map((widgetType, index) => ({
    id: -(index + 1),
    scope: "dashboard",
    project_id: null,
    widget_type: widgetType,
    area: LEGACY_DASHBOARD_WIDGET_AREA,
    order_index: index,
    size: widgetType === "Needs Attention" || widgetType === "Active Builds" ? "large" : "medium",
    collapsed: false,
    enabled: true,
    config_json: { legacy: true },
    created_at: now,
    updated_at: now,
  }));
}

function legacyDashboardData(
  summary: DashboardSummary | null,
  systemStatus: CodexStatus | null,
  instances: WidgetInstance[],
): WidgetDataResponse[] {
  const now = new Date().toISOString();

  return instances.map((instance) => {
    switch (instance.widget_type) {
      case "Diagnostics Summary":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: "System Health",
          status: systemStatus?.startup_summary?.overall_status === "error" ? "warning" : "ready",
          data_json: {
            startup_summary: systemStatus?.startup_summary ?? {},
            runtime_directory: systemStatus?.runtime_directory ?? "Unknown",
            notes: systemStatus?.notes ?? [],
          },
          empty_state: null,
          warnings_json: [],
          updated_at: now,
        };
      case "Needs Attention":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: (summary?.attention_items?.length ?? 0) > 0 ? "warning" : "empty",
          data_json: { items: summary?.attention_items ?? [] },
          empty_state: "No attention items are blocking progress right now.",
          warnings_json: [],
          updated_at: now,
        };
      case "Active Builds":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: (summary?.active_builds?.length ?? 0) > 0 ? "ready" : "empty",
          data_json: { items: summary?.active_builds ?? [] },
          empty_state: "No active builds are running right now.",
          warnings_json: [],
          updated_at: now,
        };
      case "Recent Handoffs":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: (summary?.recent_handoffs?.length ?? 0) > 0 ? "ready" : "empty",
          data_json: {
            items:
              summary?.recent_handoffs?.map((handoff) => ({
                title: handoff.project_name,
                detail: handoff.summary,
                status: handoff.status,
              })) ?? [],
          },
          empty_state: "No recent handoffs are available yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Runner & Provider Status":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: systemStatus ? "ready" : "empty",
          data_json: {
            selected_provider: systemStatus?.selected_provider_label ?? systemStatus?.selected_provider ?? "Unknown",
            effective_runner_mode: systemStatus?.effective_runner_mode ?? summary?.runner_status?.effective_runner_mode ?? "Unknown",
            cli_detected: systemStatus?.cli_detected ?? false,
            app_server_handshake_status:
              systemStatus?.app_server_handshake_status ?? String(summary?.runner_status?.app_server_handshake_status ?? "Unknown"),
          },
          empty_state: "Runtime status is not available yet.",
          warnings_json: [],
          updated_at: now,
        };
      case "Connected Accounts":
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: Object.keys(summary?.connected_accounts ?? {}).length ? "ready" : "empty",
          data_json: {
            items: Object.entries(summary?.connected_accounts ?? {}).map(([name, state]) => ({
              title: name,
              detail: String(state),
            })),
          },
          empty_state: "No connected accounts are recorded yet.",
          warnings_json: [],
          updated_at: now,
        };
      default:
        return {
          widget_instance_id: instance.id,
          widget_type: instance.widget_type,
          title: instance.widget_type,
          status: "empty",
          data_json: { items: [] },
          empty_state: "No widget data is available yet.",
          warnings_json: [],
          updated_at: now,
        };
    }
  });
}

function projectPath(project: Project): string {
  return project.slug ? `/projects/${project.id}/${project.slug}` : `/projects/${project.id}`;
}

function humanizeStatus(value: string | null | undefined): string {
  return String(value ?? "planning")
    .split("_")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function formatLastOpened(value: string | null, fallback: string | null): string {
  const timestamp = value ?? fallback;
  if (!timestamp) {
    return "Never opened";
  }
  const seconds = Math.max(1, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
  if (seconds < 60) {
    return "Last opened just now";
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `Last opened ${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `Last opened ${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `Last opened ${days}d ago`;
}

function statusVariant(status: string): string {
  if (status === "blocked") {
    return "danger";
  }
  if (status === "ready_for_handoff" || status === "completed") {
    return "success";
  }
  if (status === "building" || status === "interviewing" || status === "planning" || status === "testing" || status === "reviewing") {
    return "info";
  }
  if (status === "waiting_on_user" || status === "waiting" || status === "paused") {
    return "warning";
  }
  return "muted";
}

function titleCase(value: string | null | undefined): string {
  return String(value ?? "")
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function widgetRowLabel(item: Record<string, unknown>): string {
  return String(
    item.project_name ??
      item.title ??
      item.label ??
      item.name ??
      item.agent_name ??
      item.request_text ??
      item.trigger_summary ??
      "Widget item",
  );
}

function widgetRowDetail(item: Record<string, unknown>): string {
  return String(
    item.detail ??
      item.summary ??
      item.status ??
      item.stage ??
      item.reason ??
      item.message ??
      item.decision ??
      item.impact_estimate ??
      "",
  );
}

function WidgetList({ items }: { items: Array<Record<string, unknown>> }) {
  return (
    <div className="mission-widget-list">
      {items.map((item, index) => (
        <article key={`${widgetRowLabel(item)}-${index}`} className="mission-widget-list__item">
          <strong>{widgetRowLabel(item)}</strong>
          <span>{widgetRowDetail(item)}</span>
        </article>
      ))}
    </div>
  );
}

function WidgetFacts({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <div className="mission-widget-facts">
      {rows.map((row) => (
        <div key={row.label} className="mission-widget-facts__row">
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function RecentProjectCard({
  project,
  onArchive,
  onPin,
}: {
  project: Project;
  onArchive: (projectId: number) => Promise<void>;
  onPin: (projectId: number, pinned: boolean) => Promise<void>;
}) {
  const navigate = useNavigate();

  return (
    <article className="dashboard-project-card">
      <div className="dashboard-project-card__header">
        <span className="dashboard-project-card__icon" aria-hidden="true">
          <CommandIcon name="project" />
        </span>
        <div className="dashboard-project-card__title">
          <strong>{project.name}</strong>
          <span className={`status-pill status-pill--${statusVariant(project.display_status)}`}>{humanizeStatus(project.display_status)}</span>
        </div>
      </div>
      <p className="dashboard-project-card__activity">{project.latest_milestone ?? project.latest_activity ?? project.idea}</p>
      <span className="dashboard-project-card__timestamp">{formatLastOpened(project.last_opened_at, project.updated_at)}</span>
      <div className="dashboard-project-card__footer">
        <button type="button" className="button-ghost dashboard-project-card__open" onClick={() => navigate(projectPath(project))}>
          Open {"->"}
        </button>
        <details className="dashboard-project-card__menu">
          <summary aria-label={`Project actions for ${project.name}`}>...</summary>
          <div className="dashboard-project-card__menu-list">
            <button type="button" className="button-ghost" onClick={() => void onPin(project.id, project.pinned)}>
              {project.pinned ? "Unpin from sidebar" : "Pin to sidebar"}
            </button>
            <button type="button" className="button-ghost" onClick={() => void onArchive(project.id)}>
              Archive
            </button>
            <button
              type="button"
              className="button-ghost"
              onClick={() => navigate(`/projects/${project.id}/handoff`)}
              disabled={project.display_status !== "ready_for_handoff"}
            >
              View handoff
            </button>
          </div>
        </details>
      </div>
    </article>
  );
}

function renderDashboardWidgetBody(instance: WidgetInstance, data: WidgetDataResponse | undefined) {
  if (!data || data.status === "empty" || data.status === "coming_soon" || data.status === "needs_setup" || data.status === "unsupported") {
    return <p className="section-footnote">{data?.empty_state ?? "No widget data is available yet."}</p>;
  }

  const payload = data.data_json;
  const items = Array.isArray(payload.items) ? (payload.items as Array<Record<string, unknown>>) : [];

  switch (instance.widget_type) {
    case "Needs Attention":
    case "Active Builds":
    case "Recent Handoffs":
    case "Blocked Agents":
    case "Recent Decisions":
    case "Project Health Overview":
    case "Recent Change Requests":
      return items.length ? <WidgetList items={items} /> : <p className="section-footnote">{data.empty_state ?? "Nothing to show."}</p>;
    case "Runner & Provider Status":
      return (
        <WidgetFacts
          rows={[
            { label: "Selected provider", value: String(payload.selected_provider ?? "Unknown") },
            { label: "Runner mode", value: String(payload.effective_runner_mode ?? "Unknown") },
            { label: "CLI", value: payload.cli_detected ? "Detected" : "Missing" },
            { label: "App Server", value: String(payload.app_server_handshake_status ?? "Unknown") },
          ]}
        />
      );
    case "Connected Accounts":
      return items.length ? <WidgetList items={items} /> : <p className="section-footnote">{data.empty_state ?? "No connected accounts recorded."}</p>;
    case "Model Defaults":
      return (
        <WidgetFacts
          rows={[
            { label: "Manager", value: String(payload.manager_model ?? "Use provider default") },
            { label: "Workers", value: String(payload.default_worker_model ?? "Use provider default") },
            { label: "Manager reasoning", value: String(payload.manager_reasoning_effort ?? "Default") },
            { label: "Worker reasoning", value: String(payload.default_worker_reasoning_effort ?? "Default") },
          ]}
        />
      );
    case "Diagnostics Summary": {
      const startupSummary = (payload.startup_summary as Record<string, unknown> | undefined) ?? {};
      return (
        <>
          <WidgetFacts
            rows={[
              { label: "Startup mode", value: String(startupSummary.mode ?? "Unknown") },
              { label: "Overall status", value: String(startupSummary.overall_status ?? "Unknown") },
              { label: "Runtime directory", value: String(payload.runtime_directory ?? "Unknown") },
            ]}
          />
          {Array.isArray(payload.notes) && (payload.notes as string[]).length ? (
            <div className="mission-widget-note-list">
              {(payload.notes as string[]).slice(0, 4).map((note) => (
                <p key={note} className="section-footnote">
                  {note}
                </p>
              ))}
            </div>
          ) : null}
        </>
      );
    }
    case "Swarm Budget Overview":
      return items.length ? <WidgetList items={items} /> : <p className="section-footnote">{data.empty_state ?? "No swarm budgets recorded yet."}</p>;
    default:
      return <p className="section-footnote">This widget is live but does not have a richer dashboard renderer yet.</p>;
  }
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { summary, systemStatus, profile, loading, error, reload, toggleProjectPin } = useHomeState();
  const [showWidgetPicker, setShowWidgetPicker] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [widgetDataState, setWidgetDataState] = useState<WidgetDataResponse[]>([]);

  useEffect(() => {
    if (!summary) {
      return;
    }
    setWidgetDataState(summary.widget_data ?? []);
  }, [summary]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.EventSource === "undefined") {
      return;
    }
    const source = new window.EventSource(`${api.apiBaseUrl}/api/dashboard/stream`);
    source.onmessage = () => {
      void reload();
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [reload]);

  const fallbackWidgetInstances = useMemo(() => {
    return summary && !(summary.widget_instances?.length ?? 0) ? legacyDashboardInstances(summary) : [];
  }, [summary]);
  const widgetInstances = (summary?.widget_instances?.length ?? 0) > 0 ? summary?.widget_instances ?? [] : fallbackWidgetInstances;
  const fallbackWidgetCatalog = useMemo(() => {
    return summary && !(summary.widget_catalog?.length ?? 0) ? legacyDashboardCatalog(summary) : [];
  }, [summary]);
  const widgetCatalog = (summary?.widget_catalog?.length ?? 0) > 0 ? summary?.widget_catalog ?? [] : fallbackWidgetCatalog;
  const fallbackWidgetData = useMemo(() => {
    return summary && fallbackWidgetInstances.length ? legacyDashboardData(summary, systemStatus, fallbackWidgetInstances) : [];
  }, [fallbackWidgetInstances, summary, systemStatus]);
  const widgetDataByInstance = useMemo(() => {
    const entries = new Map<number, WidgetDataResponse>();
    for (const entry of fallbackWidgetData) {
      entries.set(entry.widget_instance_id, entry);
    }
    for (const entry of widgetDataState) {
      entries.set(entry.widget_instance_id, entry);
    }
    return entries;
  }, [fallbackWidgetData, widgetDataState]);

  async function archiveProject(projectId: number) {
    setBusy("Updating project archive state...");
    try {
      await api.archiveProject(projectId);
      await reload();
    } finally {
      setBusy(null);
    }
  }

  async function addWidget(widgetType: string) {
    setBusy(`Adding ${widgetType}...`);
    try {
      await api.addDashboardWidget({ widget_type: widgetType });
      await reload();
      setShowWidgetPicker(false);
    } finally {
      setBusy(null);
    }
  }

  async function refreshWidget(instance: WidgetInstance) {
    const nextData = await api.getWidgetInstanceData(instance.id);
    setWidgetDataState((current) => {
      const remaining = current.filter((entry) => entry.widget_instance_id !== instance.id);
      return [...remaining, nextData];
    });
  }

  async function updateWidget(instance: WidgetInstance, payload: Partial<Pick<WidgetInstance, "collapsed" | "size" | "order_index">>) {
    setBusy(`Updating ${instance.widget_type}...`);
    try {
      await api.updateWidgetInstance(instance.id, payload);
      await reload();
    } finally {
      setBusy(null);
    }
  }

  async function removeWidget(instance: WidgetInstance) {
    setBusy(`Removing ${instance.widget_type}...`);
    try {
      await api.deleteWidgetInstance(instance.id);
      await reload();
    } finally {
      setBusy(null);
    }
  }

  const recentProjects = summary?.recent_projects.slice(0, 3) ?? [];

  return (
    <HomeShell
      title="Dashboard"
      subtitle="Your home base for recent builds, active projects, and command-center insights."
      summary={summary}
      systemStatus={systemStatus}
      profile={profile}
      onProjectPinToggle={toggleProjectPin}
      actions={
        <Link className="dashboard-primary-action" to="/projects/new">
          + New Project
        </Link>
      }
    >
      {loading ? (
        <LoadingBlock label="Loading dashboard..." />
      ) : !summary ? (
        <SectionCard title="Dashboard unavailable" subtitle="Mission Control could not load the home summary.">
          <p className="error-text">{error}</p>
          <div className="button-row">
            <button type="button" onClick={() => void reload()}>
              Retry
            </button>
          </div>
        </SectionCard>
      ) : (
        <div className="dashboard-command-center">
          {error ? (
            <div className="startup-note-card startup-note-card--danger">
              <strong>Home data partially degraded</strong>
              <p>{error}</p>
            </div>
          ) : null}

          <SectionCard
            title="Recent Projects"
            subtitle="Resume the work that matters now, then archive the rest without turning the home view into a storage unit with gradients."
            actions={
              <button type="button" className="button-ghost" onClick={() => navigate("/archive")}>
                View all projects {"->"}
              </button>
            }
          >
            <div className="dashboard-recent-grid" id="recent-projects">
              {recentProjects.map((project) => (
                <RecentProjectCard key={project.id} project={project} onArchive={archiveProject} onPin={toggleProjectPin} />
              ))}
              <button type="button" className="dashboard-new-project-card" onClick={() => navigate("/projects/new")}>
                <span className="dashboard-new-project-card__plus" aria-hidden="true">
                  <CommandIcon name="plus" />
                </span>
                <strong>New Project</strong>
                <span>Start something new</span>
              </button>
            </div>
          </SectionCard>

          <section className="dashboard-widget-zone">
            {busy ? <p className="section-footnote">{busy}</p> : null}
            <WidgetGrid
              instances={widgetInstances.filter((instance) => instance.area === "dashboard_main" || instance.area === "dashboard_bottom")}
              dataByInstance={widgetDataByInstance}
              onCollapseToggle={(instance) => void updateWidget(instance, { collapsed: !instance.collapsed })}
              onMove={(instance, direction) =>
                void updateWidget(instance, {
                  order_index: Math.max(0, instance.order_index + (direction === "up" ? -1 : 1)),
                })
              }
              onRemove={(instance) => void removeWidget(instance)}
              onRefresh={(instance) => void refreshWidget(instance)}
              onSizeChange={(instance, size) => void updateWidget(instance, { size })}
              renderBody={renderDashboardWidgetBody}
            />

            <button type="button" className="widget-fab" onClick={() => setShowWidgetPicker((current) => !current)} aria-label="Add widget">
              <CommandIcon name="plus" />
            </button>

            {showWidgetPicker ? (
              <WidgetSelectorPanel
                scope="dashboard"
                catalog={widgetCatalog}
                addedWidgetTypes={widgetInstances.map((instance) => instance.widget_type)}
                onAdd={(widgetType) => void addWidget(widgetType)}
              />
            ) : null}
          </section>
        </div>
      )}
    </HomeShell>
  );
}
