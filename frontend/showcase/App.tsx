import { lazy, Suspense, useEffect, useState } from "react";
import { Command, Github, Menu, RotateCcw, X } from "lucide-react";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
  useSearchParams,
} from "react-router-dom";
import { Brand, Empty, Loading, PageHeader, time } from "../src/components/ui";
import { QuickNavigation } from "../src/components/QuickNavigation";
import { SourceIcon, SourceStatus } from "../src/components/SourceHealth";
import { navigation } from "../src/utils/navigation";
import { useResource } from "../src/hooks/useResource";
import type { LogSource } from "../src/types";

const Dashboard = lazy(() =>
  import("../src/pages/Dashboard").then((module) => ({
    default: module.DashboardPage,
  })),
);
const Alerts = lazy(() =>
  import("../src/pages/Alerts").then((module) => ({
    default: module.AlertsPage,
  })),
);
const Events = lazy(() =>
  import("../src/pages/Events").then((module) => ({
    default: module.EventsPage,
  })),
);
const Incidents = lazy(() =>
  import("../src/pages/Incidents").then((module) => ({
    default: module.IncidentsPage,
  })),
);
const IncidentDetail = lazy(() =>
  import("../src/pages/Incidents").then((module) => ({
    default: module.IncidentDetailPage,
  })),
);
const Assistant = lazy(() =>
  import("../src/pages/Assistant").then((module) => ({
    default: module.AssistantPage,
  })),
);
const pages = navigation.filter((item) => !item.advanced);

function ShowcaseLayout() {
  const [menu, setMenu] = useState(false);
  const [quick, setQuick] = useState(false);
  const location = useLocation();
  const active = pages.find((item) => location.pathname.startsWith(item.path));

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (
        event.key.toLowerCase() !== "k" ||
        !(event.ctrlKey || event.metaKey) ||
        event.altKey
      )
        return;
      if (document.querySelector('[role="dialog"]') && !quick) return;
      event.preventDefault();
      setQuick((open) => !open);
    }
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, [quick]);

  return (
    <div className="app-shell calm-console showcase">
      {menu && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside className={`sidebar ${menu ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <Link to="/dashboard" aria-label="SentinelX overview">
            <Brand />
          </Link>
          <button
            className="icon-button mobile-only"
            aria-label="Close navigation"
            onClick={() => setMenu(false)}
          >
            <X size={20} />
          </button>
        </div>
        <nav aria-label="Main navigation">
          <div className="nav-group">
            {pages.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMenu(false)}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "active" : ""}`
                }
              >
                <item.icon size={19} strokeWidth={1.7} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
        <div className="sidebar-bottom">
          <a
            className="sidebar-help"
            href="https://github.com/aadvik1864/sentinelx"
            target="_blank"
            rel="noreferrer"
          >
            <Github size={17} />
            Source code
          </a>
          <a
            className="sidebar-help"
            href="./third-party-notices.txt"
            target="_blank"
            rel="noreferrer"
          >
            Licenses and credits
          </a>
          <p className="muted showcase-caption">
            A personal monitoring project. No real systems are connected to this
            demo.
          </p>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-only"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">{active?.label ?? "Demo"}</span>
            <span className="workspace-mode demo">Demo — synthetic data</span>
          </div>
          <div className="topbar-actions">
            <button
              className="quick-navigation-trigger"
              aria-label="Go to a page"
              aria-keyshortcuts="Control+k Meta+k"
              onClick={() => {
                setQuick(true);
                setMenu(false);
              }}
            >
              <Command size={17} />
              <span>Go to</span>
              <kbd>K</kbd>
            </button>
            <button
              className="button secondary"
              onClick={() => {
                window.location.hash = "/dashboard";
                window.location.reload();
              }}
            >
              <RotateCcw size={16} />
              Reset demo
            </button>
          </div>
        </header>
        <main className="main-content">
          <div className="practice-notice">
            All records are fictional. Notes and status changes stay in this tab
            and reset on reload. Don’t paste real logs or secrets.
          </div>
          <Outlet />
        </main>
        <footer className="console-footer">
          <span>
            Sample explanations only. No AI model or external provider is
            connected.
          </span>
          <span>Nothing here changes a real system.</span>
        </footer>
      </div>
      {quick && (
        <QuickNavigation items={pages} onClose={() => setQuick(false)} />
      )}
    </div>
  );
}

function ExampleSources() {
  const { data } = useResource<{ items: LogSource[] }>("/sources");
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const attention = params.get("filter") === "attention";
  const sources =
    data?.items.filter(
      (source) =>
        `${source.name} ${source.hostname}`
          .toLowerCase()
          .includes(query.toLowerCase()) &&
        (!attention ||
          ["offline", "error", "key_expired"].includes(source.status)),
    ) ?? [];

  return (
    <>
      <PageHeader
        title="Connected systems"
        description="Fictional source health. This demo does not run collectors or connect to a server."
      />
      <div className="filter-bar">
        <label className="system-search">
          Find a system
          <input
            value={query}
            onChange={(event) => {
              const next = new URLSearchParams(params);
              next.set("q", event.target.value);
              setParams(next);
            }}
          />
        </label>
        <button
          className="button secondary"
          onClick={() => {
            const next = new URLSearchParams(params);
            if (attention) next.delete("filter");
            else next.set("filter", "attention");
            setParams(next);
          }}
        >
          {attention ? "Show all systems" : "Show systems needing attention"}
        </button>
      </div>
      <div className="systems-list">
        {sources.map((source) => (
          <article className="system-row" key={source.id}>
            <div className="system-row-heading">
              <span className="source-kind-icon">
                <SourceIcon kind={source.kind} />
              </span>
              <div className="system-row-name">
                <h2>{source.name}</h2>
                <p>{source.hostname}</p>
              </div>
              <SourceStatus source={source} />
              <Link
                className="button secondary"
                to={`/events?source_id=${source.id}`}
              >
                View activity
              </Link>
            </div>
            <p className="system-status-help">
              {source.status === "offline"
                ? "An example of a collector gap that needs checking, not proof of an attack."
                : "Sample records are available. The displayed status is illustrative, not a live connection."}
            </p>
            <dl className="source-facts">
              <div>
                <dt>Example records</dt>
                <dd>{source.total_events}</dd>
              </div>
              <div>
                <dt>Last sample activity</dt>
                <dd>
                  {source.last_event_at
                    ? time(source.last_event_at, true)
                    : "No records"}
                </dd>
              </div>
            </dl>
          </article>
        ))}
        {data && !sources.length && (
          <Empty
            title="No example systems match"
            description="Try another name or show all systems."
          />
        )}
      </div>
    </>
  );
}

export default function ShowcaseApp() {
  return (
    <Suspense fallback={<Loading label="Opening the example workspace" />}>
      <Routes>
        <Route element={<ShowcaseLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="events" element={<Events allowImport={false} />} />
          <Route path="incidents" element={<Incidents />} />
          <Route path="incidents/:id" element={<IncidentDetail />} />
          <Route path="sources" element={<ExampleSources />} />
          <Route path="ai-assistant" element={<Assistant />} />
          <Route
            path="*"
            element={
              <Empty
                title="Not part of the public demo"
                description="Choose Overview or Investigations from the navigation. Account setup and real monitoring are not available here."
                action={
                  <Link className="button primary" to="/dashboard">
                    Open overview
                  </Link>
                }
              />
            }
          />
        </Route>
      </Routes>
    </Suspense>
  );
}
