import { lazy, Suspense } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Empty, Loading } from "./components/ui";
import { AccountSecuritySetup, SecurityEnrollmentComplete } from "./components/AccountSecurity";
import { ConsoleLayout } from "./layouts/ConsoleLayout";
import { LoginPage } from "./pages/Login";
import { useAuth } from "./store/AuthContext";
import { LiveProvider } from "./store/LiveContext";

const AlertsPage = lazy(() => import("./pages/Alerts").then((module) => ({ default: module.AlertsPage })));
const AssetsPage = lazy(() => import("./pages/Assets").then((module) => ({ default: module.AssetsPage })));
const AssistantPage = lazy(() => import("./pages/Assistant").then((module) => ({ default: module.AssistantPage })));
const DashboardPage = lazy(() => import("./pages/Dashboard").then((module) => ({ default: module.DashboardPage })));
const EventsPage = lazy(() => import("./pages/Events").then((module) => ({ default: module.EventsPage })));
const IncidentsPage = lazy(() => import("./pages/Incidents").then((module) => ({ default: module.IncidentsPage })));
const IncidentDetailPage = lazy(() => import("./pages/Incidents").then((module) => ({ default: module.IncidentDetailPage })));
const RulesPage = lazy(() => import("./pages/Rules").then((module) => ({ default: module.RulesPage })));
const SettingsPage = lazy(() => import("./pages/Settings").then((module) => ({ default: module.SettingsPage })));
const SourcesPage = lazy(() => import("./pages/Sources").then((module) => ({ default: module.SourcesPage })));
const ThreatIntelligencePage = lazy(() => import("./pages/ThreatIntelligence").then((module) => ({ default: module.ThreatIntelligencePage })));

function Protected() {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="startup">
        <Loading label="Restoring your secure session" />
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password || (user.mfa_required && !user.mfa_enabled))
    return <AccountSecuritySetup />;
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
  const { securityCompletion } = useAuth();
  if (securityCompletion) return <SecurityEnrollmentComplete />;
  return (
    <Suspense fallback={<Loading label="Loading workspace page" />}>
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
    </Suspense>
  );
}
