import { Navigate, Route, Routes, useParams } from "react-router-dom";

import { ArchivePage } from "./pages/ArchivePage";
import { AsciiMonitorPage } from "./pages/AsciiMonitorPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { HandoffPage } from "./pages/HandoffPage";
import { HandoffsPage } from "./pages/HandoffsPage";
import { ImportReviewPage } from "./pages/ImportReviewPage";
import { InterviewPage } from "./pages/InterviewPage";
import { ModelsRunnersLandingPage } from "./pages/ModelsRunnersLandingPage";
import { ModelsRunnersPage } from "./pages/ModelsRunnersPage";
import { PlanReviewPage } from "./pages/PlanReviewPage";
import { ProjectIntakePage } from "./pages/ProjectIntakePage";
import { ProjectWorkspacePage } from "./pages/ProjectWorkspacePage";
import { SetupPage } from "./pages/SetupPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SkillsToolsPage } from "./pages/SkillsToolsPage";
import { StartupErrorPage } from "./pages/StartupErrorPage";
import { StartupPage } from "./pages/StartupPage";

function LegacyBuildRedirect() {
  const { projectId } = useParams();
  return <Navigate to={projectId ? `/projects/${projectId}` : "/dashboard"} replace />;
}

function LegacyProjectSettingsRedirect() {
  const { projectId } = useParams();
  return <Navigate to={projectId ? `/projects/${projectId}/models-runners` : "/models-runners"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/startup" replace />} />
      <Route path="/startup" element={<StartupPage />} />
      <Route path="/setup" element={<SetupPage />} />
      <Route path="/startup-error" element={<StartupErrorPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/archive" element={<ArchivePage />} />
      <Route path="/handoffs" element={<HandoffsPage />} />
      <Route path="/diagnostics" element={<DiagnosticsPage />} />
      <Route path="/skills-tools" element={<SkillsToolsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/models-runners" element={<ModelsRunnersLandingPage />} />
      <Route path="/projects/new" element={<ProjectIntakePage />} />
      <Route path="/projects/:projectId" element={<ProjectWorkspacePage />} />
      <Route path="/projects/:projectId/:projectSlug" element={<ProjectWorkspacePage />} />
      <Route path="/projects/:projectId/ascii-monitor" element={<AsciiMonitorPage />} />
      <Route path="/projects/:projectId/:projectSlug/ascii-monitor" element={<AsciiMonitorPage />} />
      <Route path="/projects/:projectId/models-runners" element={<ModelsRunnersPage />} />
      <Route path="/projects/:projectId/:projectSlug/models-runners" element={<ModelsRunnersPage />} />
      <Route path="/projects/:projectId/interview" element={<InterviewPage />} />
      <Route path="/projects/:projectId/import/review" element={<ImportReviewPage />} />
      <Route path="/projects/:projectId/plan" element={<PlanReviewPage />} />
      <Route path="/projects/:projectId/settings" element={<LegacyProjectSettingsRedirect />} />
      <Route path="/projects/:projectId/build" element={<LegacyBuildRedirect />} />
      <Route path="/projects/:projectId/handoff" element={<HandoffPage />} />
      <Route path="*" element={<Navigate to="/startup" replace />} />
    </Routes>
  );
}
