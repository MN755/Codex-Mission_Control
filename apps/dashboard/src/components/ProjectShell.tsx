import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import type { Project } from "../types";
import { MissionControlMark } from "./MissionControlMark";

function projectPath(project: Project): string {
  return project.slug ? `/projects/${project.id}/${project.slug}` : `/projects/${project.id}`;
}

export function ProjectShell({
  project,
  title,
  subtitle,
  rightRail,
  children,
}: {
  project: Project | null;
  title: string;
  subtitle: string;
  rightRail?: ReactNode;
  children: ReactNode;
}) {
  const workspacePath = project ? projectPath(project) : "/dashboard";
  const modelsPath = project?.slug
    ? `/projects/${project.id}/${project.slug}/models-runners`
    : project
      ? `/projects/${project.id}/models-runners`
      : "/models-runners";

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <div>
          <Link className="brand" to="/dashboard">
            <MissionControlMark className="brand__mark" />
            Codex Mission Control
          </Link>
          <div className="app-shell__title">
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        </div>
        {project ? (
          <nav className="project-nav">
            <NavLink to={workspacePath}>Workspace</NavLink>
            <NavLink to={`/projects/${project.id}/interview`}>Interview</NavLink>
            <NavLink to={`/projects/${project.id}/plan`}>Plan</NavLink>
            <NavLink to={modelsPath}>Models &amp; Runners</NavLink>
            <NavLink to={`/projects/${project.id}/handoff`}>Handoff</NavLink>
          </nav>
        ) : null}
        {rightRail ? <div className="app-shell__rail">{rightRail}</div> : null}
      </header>
      <main className="app-shell__content">{children}</main>
    </div>
  );
}
