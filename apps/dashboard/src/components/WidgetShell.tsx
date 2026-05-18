import type { ReactNode } from "react";

import type { WidgetDataStatus, WidgetSize } from "../types";

function statusLabel(status: WidgetDataStatus): string {
  switch (status) {
    case "warning":
      return "Warning";
    case "empty":
      return "Empty";
    case "coming_soon":
      return "Coming soon";
    case "needs_setup":
      return "Needs setup";
    case "unsupported":
      return "Unsupported";
    default:
      return "Ready";
  }
}

export function WidgetShell({
  title,
  status,
  size,
  collapsed,
  actions,
  children,
}: {
  title: string;
  status: WidgetDataStatus;
  size: WidgetSize;
  collapsed: boolean;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className={`mission-widget mission-widget--${size}${collapsed ? " mission-widget--collapsed" : ""}`}>
      <header className="mission-widget__header">
        <div className="mission-widget__title">
          <strong>{title}</strong>
          <span className={`status-pill status-${status === "ready" ? "done" : status === "warning" ? "needs_review" : "idle"}`}>
            {statusLabel(status)}
          </span>
        </div>
        <div className="mission-widget__actions">{actions}</div>
      </header>
      {!collapsed ? <div className="mission-widget__body">{children}</div> : null}
    </article>
  );
}
