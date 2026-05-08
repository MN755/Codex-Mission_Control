import type { ProjectEvent } from "../types";

export function EventFeed({ events }: { events: ProjectEvent[] }) {
  function defaultLabel(provider: unknown) {
    if (provider === "claude_code") {
      return "Claude Code default";
    }
    if (provider === "external_adapter") {
      return "Adapter default";
    }
    return "Codex default";
  }

  function renderSummary(event: ProjectEvent) {
    const payload = event.payload_json;
    if (event.event_type === "agent.started") {
      const settings = (payload.effective_settings as Record<string, unknown> | undefined) ?? {};
      const provider = settings.provider;
      const providerDefault = defaultLabel(provider);
      return `${payload.agent_name ?? "Agent"} started task #${payload.task_id ?? "?"} with ${String(settings.model ?? providerDefault)} / ${String(settings.reasoning_effort ?? providerDefault)} on ${payload.runner ?? "runner"}.`;
    }
    if (event.event_type === "manager.mode.provider" || event.event_type === "manager.mode.codex") {
      const settings = (payload.effective_settings as Record<string, unknown> | undefined) ?? {};
      const provider = payload.provider ?? settings.provider;
      return `Manager used ${payload.runner ?? "runner"} for ${payload.action ?? "a turn"} via ${String(provider ?? "live provider")} with ${String(settings.model ?? defaultLabel(provider))}.`;
    }
    if (event.event_type === "settings.updated") {
      return `Settings saved for ${String(payload.provider ?? "provider")}. Manager model: ${String(payload.manager_model ?? "provider default")}. Worker model: ${String(payload.default_worker_model ?? "provider default")}.`;
    }
    if (typeof payload.summary === "string") {
      return payload.summary;
    }
    if (typeof payload.message === "string") {
      return payload.message;
    }
    if (typeof payload.reason === "string") {
      return payload.reason;
    }
    if (typeof payload.reply === "string") {
      return payload.reply;
    }
    if (payload.task_id) {
      return `Task #${payload.task_id}`;
    }
    return JSON.stringify(payload);
  }

  return (
    <div className="event-feed">
      {events.slice().reverse().map((event) => (
        <article key={event.id} className="event-feed__item">
          <div className="event-feed__meta">
            <span>{event.event_type.replace(/\./g, " ").replace(/_/g, " ")}</span>
            <time>{new Date(event.created_at).toLocaleString()}</time>
          </div>
          <p>{renderSummary(event)}</p>
        </article>
      ))}
    </div>
  );
}
