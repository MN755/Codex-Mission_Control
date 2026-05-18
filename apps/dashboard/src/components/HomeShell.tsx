import { useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import type { AppProfile, CodexStatus, DashboardSummary } from "../types";
import { CommandIcon } from "./CommandIcon";
import { MissionControlMark } from "./MissionControlMark";

function projectPath(projectId: number, slug?: string | null): string {
  return slug ? `/projects/${projectId}/${slug}` : `/projects/${projectId}`;
}

function statusLabel(value: string | null | undefined): string {
  return String(value ?? "planning")
    .split("_")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function initialsForName(name: string | null | undefined): string {
  const parts = String(name ?? "Local User")
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "LU";
}

function secondaryIdentityText(profile: AppProfile | null, systemStatus: CodexStatus | null): string {
  if (systemStatus?.authenticated && systemStatus.selected_provider === "codex") {
    return "Codex connected";
  }
  if (profile?.selected_provider === "ollama") {
    return "Local profile";
  }
  return "Local user";
}

export function HomeShell({
  title,
  subtitle,
  summary,
  systemStatus,
  profile,
  actions,
  children,
  onProjectPinToggle,
  hideHeader = false,
}: {
  title: string;
  subtitle: string;
  summary: DashboardSummary | null;
  systemStatus: CodexStatus | null;
  profile?: AppProfile | null;
  actions?: ReactNode;
  children: ReactNode;
  onProjectPinToggle?: (projectId: number, pinned: boolean) => Promise<void> | void;
  hideHeader?: boolean;
}) {
  const location = useLocation();
  const degraded = systemStatus?.startup_summary?.overall_status === "degraded";
  const [pendingPinId, setPendingPinId] = useState<number | null>(null);
  const pageLinks = [
    { to: "/dashboard", label: "Dashboard", icon: "dashboard" as const },
    { to: "/handoffs", label: "Handoffs", icon: "handoffs" as const },
    { to: "/models-runners", label: "Models & Runners", icon: "models" as const },
    { to: "/skills-tools", label: "Skills & Tools", icon: "tools" as const },
    { to: "/diagnostics", label: "Diagnostics", icon: "diagnostics" as const, badge: degraded ? "Warning" : null },
    { to: "/settings", label: "Settings", icon: "settings" as const },
  ];

  async function togglePin(projectId: number, pinned: boolean) {
    if (!onProjectPinToggle) {
      return;
    }
    setPendingPinId(projectId);
    try {
      await onProjectPinToggle(projectId, pinned);
    } finally {
      setPendingPinId(null);
    }
  }

  return (
    <div className="home-shell">
      <aside className="home-shell__sidebar">
        <Link className="brand brand--sidebar" to="/dashboard">
          <MissionControlMark className="brand__mark" />
          <span className="brand__copy">
            <strong>Codex</strong>
            <span>Mission Control</span>
          </span>
        </Link>

        <nav className="shell-nav" aria-label="Main navigation">
          <div className="shell-nav__section">
            <span className="shell-nav__label">Home</span>
            {pageLinks.map((link) => (
              <NavLink key={link.to} className={({ isActive }) => `shell-nav__link${isActive ? " active" : ""}`} to={link.to}>
                <span className="shell-nav__icon" aria-hidden="true">
                  <CommandIcon name={link.icon} />
                </span>
                <span className="shell-nav__text">{link.label}</span>
                {link.badge ? <small>{link.badge}</small> : null}
              </NavLink>
            ))}
          </div>

          <div className="shell-nav__section">
            <div className="shell-nav__section-header">
              <span className="shell-nav__label">Projects</span>
            </div>
            {summary?.sidebar_projects.length ? (
              <>
                {summary.sidebar_projects.map((project) => {
                  const target = projectPath(project.id, project.slug);
                  const active =
                    location.pathname === target ||
                    location.pathname.startsWith(`${target}/`) ||
                    location.pathname === `/projects/${project.id}` ||
                    location.pathname.startsWith(`/projects/${project.id}/`);
                  return (
                    <div key={project.id} className={`project-sidebar__item${active ? " project-sidebar__item--active" : ""}`}>
                      <Link className="project-sidebar__link" to={target}>
                        <span className="project-sidebar__icon" aria-hidden="true">
                          {project.name.slice(0, 2).toUpperCase()}
                        </span>
                        <div className="project-sidebar__content">
                          <strong>{project.name}</strong>
                          <div className="project-sidebar__status">
                            <span className={`project-sidebar__dot project-sidebar__dot--${project.display_status}`} />
                            <small>{statusLabel(project.display_status)}</small>
                          </div>
                        </div>
                      </Link>
                      <button
                        type="button"
                        className="project-sidebar__pin"
                        disabled={!onProjectPinToggle || pendingPinId === project.id}
                        onClick={() => void togglePin(project.id, project.pinned)}
                        aria-label={project.pinned ? `Unpin ${project.name}` : `Pin ${project.name}`}
                      >
                        <CommandIcon name={project.pinned ? "pin" : "pinOff"} />
                      </button>
                    </div>
                  );
                })}
                {summary.archive_count > 0 ? (
                  <Link className="project-sidebar__archive" to="/archive">
                    <span className="project-sidebar__icon" aria-hidden="true">
                      <CommandIcon name="archive" />
                    </span>
                    <div className="project-sidebar__content">
                      <strong>Archive</strong>
                      <small>{summary.archive_count} older project{summary.archive_count === 1 ? "" : "s"}</small>
                    </div>
                  </Link>
                ) : null}
              </>
            ) : (
              <div className="project-sidebar__empty">
                <strong>No projects yet.</strong>
                <small>Create your first project from the Dashboard.</small>
              </div>
            )}
          </div>
        </nav>

        <details className="profile-dock">
          <summary className="profile-dock__summary">
            <span className="profile-dock__avatar">{initialsForName(profile?.display_name)}</span>
            <span className="profile-dock__identity">
              <strong>{profile?.display_name ?? "Local User"}</strong>
              <small>{secondaryIdentityText(profile ?? null, systemStatus)}</small>
            </span>
            <span className="profile-dock__chevron" aria-hidden="true">
              v
            </span>
          </summary>
          <div className="profile-dock__menu">
            <Link to="/settings">Profile Settings</Link>
            <Link to="/settings">Connected Accounts</Link>
            <Link to="/models-runners">Provider Login Status</Link>
            <Link to="/diagnostics">Diagnostics</Link>
            <Link to="/archive">Open Project Archive</Link>
          </div>
        </details>
      </aside>

      <div className="home-shell__main">
        {!hideHeader ? (
          <header className="home-shell__header">
            <div className="home-shell__copy">
              <h1>{title}</h1>
              <p>{subtitle}</p>
            </div>
            <div className="home-shell__meta">
              {degraded ? <span className="header-chip header-chip--warning">Degraded mode</span> : null}
              {actions}
            </div>
          </header>
        ) : null}
        <main className="home-shell__content">{children}</main>
      </div>
    </div>
  );
}
