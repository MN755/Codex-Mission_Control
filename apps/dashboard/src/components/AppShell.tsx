import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

export function AppShell({
  projectId,
  title,
  subtitle,
  rightRail,
  children,
}: {
  projectId?: number;
  title: string;
  subtitle: string;
  rightRail?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <div>
          <Link className="brand" to="/">
            Codex Mission Control
          </Link>
          <div className="app-shell__title">
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        </div>
        {projectId ? (
          <nav className="project-nav">
            <NavLink to={`/projects/${projectId}/interview`}>Interview</NavLink>
            <NavLink to={`/projects/${projectId}/plan`}>Plan</NavLink>
            <NavLink to={`/projects/${projectId}/settings`}>Settings</NavLink>
            <NavLink to={`/projects/${projectId}/build`}>Build</NavLink>
            <NavLink to={`/projects/${projectId}/handoff`}>Handoff</NavLink>
          </nav>
        ) : null}
        {rightRail ? <div className="app-shell__rail">{rightRail}</div> : null}
      </header>
      <main className="app-shell__content">{children}</main>
    </div>
  );
}
