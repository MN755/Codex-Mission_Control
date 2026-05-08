import { Navigate, Route, Routes } from "react-router-dom";

import { BuildMonitorPage } from "./pages/BuildMonitorPage";
import { HandoffPage } from "./pages/HandoffPage";
import { InterviewPage } from "./pages/InterviewPage";
import { PlanReviewPage } from "./pages/PlanReviewPage";
import { ProjectIntakePage } from "./pages/ProjectIntakePage";
import { SettingsPage } from "./pages/SettingsPage";
import { StartupPage } from "./pages/StartupPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<StartupPage />} />
      <Route path="/projects/new" element={<ProjectIntakePage />} />
      <Route path="/projects/:projectId/interview" element={<InterviewPage />} />
      <Route path="/projects/:projectId/plan" element={<PlanReviewPage />} />
      <Route path="/projects/:projectId/settings" element={<SettingsPage />} />
      <Route path="/projects/:projectId/build" element={<BuildMonitorPage />} />
      <Route path="/projects/:projectId/handoff" element={<HandoffPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
