import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Empty, Loading } from "./components/ui";
import { ConsoleLayout } from "./layouts/ConsoleLayout";
import { AlertsPage } from "./pages/Alerts";
import { AssetsPage } from "./pages/Assets";
import { AssistantPage } from "./pages/Assistant";
import { DashboardPage } from "./pages/Dashboard";
import { EventsPage } from "./pages/Events";
import { IncidentDetailPage, IncidentsPage } from "./pages/Incidents";
import { LoginPage } from "./pages/Login";
import { RulesPage } from "./pages/Rules";
import { SettingsPage } from "./pages/Settings";
import { SourcesPage } from "./pages/Sources";
import { ThreatIntelligencePage } from "./pages/ThreatIntelligence";
import { useAuth } from "./store/AuthContext";
import { LiveProvider } from "./store/LiveContext";

function Protected() {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="startup">
        <Loading label="Restoring your secure session" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return (
    <LiveProvider>
      <Outlet />
    </LiveProvider>
  );
}
function InvestigatorOnly() {
  const { user } = useAuth();
  return user?.role === "VIEWER" ? (
    <Navigate to="/dashboard" replace />
  ) : (
    <Outlet />
  );
}
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route element={<ConsoleLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/:id" element={<IncidentDetailPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route element={<InvestigatorOnly />}>
            <Route path="events" element={<EventsPage />} />
            <Route path="rules" element={<RulesPage />} />
            <Route path="assets" element={<AssetsPage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route
              path="threat-intelligence"
              element={<ThreatIntelligencePage />}
            />
            <Route path="ai-assistant" element={<AssistantPage />} />
          </Route>
          <Route
            path="*"
            element={
              <Empty
                title="Page not found"
                description="Choose a page from the navigation to return to your workspace."
              />
            }
          />
        </Route>
      </Route>
    </Routes>
  );
}
