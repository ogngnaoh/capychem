import { BrowserRouter, Routes, Route } from "react-router";
import { StudioProvider } from "./StudioContext";
import { ProductShell } from "./ProductShell";
import { OverviewPage } from "./OverviewPage";
import { ExperimentIndexPage } from "./ExperimentIndexPage";
import { SetupPage } from "./SetupPage";
import { ExperimentLayout } from "./ExperimentLayout";
import { WorkspacePage } from "./WorkspacePage";
import { ActivityPage, ComparePage } from "./ReviewPages";
import { ReferencePage, EnginePage, HelpPage } from "./SupportPages";
import { NotFoundPage } from "./ProductUI";
import { StudyIndexPage, StudyPage } from "./StudyPages";
import { StudySetupPage } from "./StudySetupPage";
export default function App() {
  return (
    <BrowserRouter>
      <StudioProvider>
        <Routes>
          <Route element={<ProductShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="experiments" element={<ExperimentIndexPage />} />
            <Route path="experiments/new" element={<SetupPage />} />
            <Route path="studies" element={<StudyIndexPage />} />
            <Route path="studies/new" element={<StudySetupPage />} />
            <Route path="studies/:studyId" element={<StudyPage />} />
            <Route
              path="experiments/:experimentId"
              element={<ExperimentLayout />}
            >
              <Route index element={<WorkspacePage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="compare" element={<ComparePage />} />
            </Route>
            <Route path="references/cdk2" element={<ReferencePage />} />
            <Route path="engine" element={<EnginePage />} />
            <Route path="help" element={<HelpPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </StudioProvider>
    </BrowserRouter>
  );
}
