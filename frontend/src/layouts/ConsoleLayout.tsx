import { useState } from "react";
import {
  Activity, Bell, Boxes, ChevronDown, CircleHelp, FileText, LayoutDashboard,
  LogOut, Menu, Radio, Search, Settings, Shield, SlidersHorizontal, Sparkles, X,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Brand, Modal, ErrorBox } from "../components/ui";
import { useAuth } from "../store/AuthContext";
import { useLive } from "../store/LiveContext";
import { useResource } from "../hooks/useResource";
import { errorMessage } from "../services/api";
import { roleLabels } from "../utils/labels";
import type { SystemInfo } from "../types";

const navigation = [
  { path: "/dashboard", label: "Overview", icon: LayoutDashboard, viewer: true },
  { path: "/alerts", label: "Alerts", icon: Bell, viewer: true },
  { path: "/incidents", label: "Investigations", icon: FileText, viewer: true },
  { path: "/events", label: "Activity", icon: Activity },
  { path: "/sources", label: "Connected systems", icon: Radio },
  { path: "/ai-assistant", label: "Assistant", icon: Sparkles },
  { path: "/assets", label: "Device list", icon: Boxes, advanced: true },
  { path: "/rules", label: "Alert rules", icon: SlidersHorizontal, advanced: true },
  { path: "/threat-intelligence", label: "Address checks", icon: Shield, advanced: true },
];

export function ConsoleLayout() {
  const { user, logout } = useAuth();
  const live = useLive();
  const navigate = useNavigate();
  const location = useLocation();
  const [menu, setMenu] = useState(false);
  const [help, setHelp] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: system } = useResource<SystemInfo>("/system");
  const active = navigation.find((item) => location.pathname.startsWith(item.path));
  const canInvestigate = user?.role !== "VIEWER";

  async function signOut() {
    try {
      await logout();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  function navItem(item: typeof navigation[number]) {
    return (
      <NavLink
        key={item.path} to={item.path} onClick={() => setMenu(false)}
        className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
      >
        <item.icon size={19} strokeWidth={1.7} /><span>{item.label}</span>
      </NavLink>
    );
  }

  return (
    <div className="app-shell calm-console">
      {menu && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMenu(false)} />}
      <aside className={`sidebar ${menu ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <Link to="/dashboard" aria-label="SentinelX overview"><Brand /></Link>
          <button className="icon-button mobile-only" aria-label="Close navigation" onClick={() => setMenu(false)}><X size={20} /></button>
        </div>
        <nav aria-label="Main navigation">
          <div className="nav-group">
            {navigation.filter((item) => !item.advanced && (canInvestigate || item.viewer)).map(navItem)}
          </div>
          {canInvestigate && (
            <details className="advanced-navigation" key={active?.advanced ? "advanced" : "main"} open={active?.advanced || undefined}>
              <summary>Advanced tools<ChevronDown size={15} /></summary>
              {navigation.filter((item) => item.advanced).map(navItem)}
            </details>
          )}
        </nav>
        <div className="sidebar-bottom">
          <Link className="sidebar-help" to="/settings" onClick={() => setMenu(false)}><Settings size={17} />Settings</Link>
          <button className="sidebar-help" onClick={() => { setHelp(true); setMenu(false); }}><CircleHelp size={17} />How to use SentinelX</button>
          <button className="user-profile" onClick={() => { navigate("/settings"); setMenu(false); }}>
            <span className="avatar">{user?.name.split(" ").map((part) => part[0]).slice(0, 2).join("")}</span>
            <span><strong>{user?.name}</strong><small>{roleLabels[user?.role ?? "VIEWER"]}</small></span>
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-only" aria-label="Open navigation" onClick={() => setMenu(true)}><Menu size={21} /></button>
            <span className="breadcrumb">{active?.label ?? "Settings"}</span>
            {system && (
              <span className={`workspace-mode ${system.demo_mode ? "demo" : ""}`}>
                {system.demo_mode ? "Practice data" : system.live_monitoring ? "Real activity" : "Your workspace"}
              </span>
            )}
          </div>
          <div className="topbar-actions">
            {canInvestigate && (
              <form className="global-search" onSubmit={(event) => {
                event.preventDefault();
                navigate(`/events?q=${encodeURIComponent(query)}`);
                setQuery("");
              }}>
                <Search size={17} />
                <input aria-label="Search activity" placeholder="Search activity…" value={query} onChange={(event) => setQuery(event.target.value)} />
              </form>
            )}
            <span
              className={`connection-chip ${live ? "connected" : ""}`}
              title="This is the dashboard connection, not the status of your monitored systems. If live updates disconnect, this page refreshes every 30 seconds. Check Connected systems for collection status."
            >
              <span className="status-light" />{live ? "Live updates" : "Auto refresh"}
            </span>
            <button className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut size={19} /></button>
          </div>
        </header>
        <main className="main-content">
          <ErrorBox message={error} />
          {system?.demo_mode && <div className="practice-notice">You’re viewing practice data, not activity from real systems.</div>}
          <Outlet />
        </main>
        <footer className="console-footer">
          <span>Advice only. SentinelX never changes your systems automatically.</span>
          <span>Times are shown in your local time.</span>
        </footer>
      </div>
      {help && (
        <Modal title="A simple guide to SentinelX" onClose={() => setHelp(false)}>
          <div className="guide">
            <p>SentinelX reads activity records from systems you connect and flags patterns that may need a closer look. An alert is a reason to investigate—not proof of an attack.</p>
            <ol>
              <li><strong>Connect a system.</strong> An administrator adds a computer, website, or app in Connected systems. The person who manages the server may need to finish setup.</li>
              <li><strong>Check the connection.</strong> Connected systems shows whether activity can reach SentinelX. Quiet systems may have nothing new to report.</li>
              <li><strong>Review alerts.</strong> Open an alert to see what happened and which system is involved.</li>
              <li><strong>Follow an investigation.</strong> Related alerts are grouped so you can read the story. Investigators can add notes and choose who reviews it.</li>
              <li><strong>Ask for an explanation.</strong> The assistant suggests what to check. Always verify its advice before taking action yourself.</li>
            </ol>
            <p>The advanced tools are for people who need raw records, custom alert rules, or address reputation checks. This is a local monitoring prototype, not a guarantee that a system is secure.</p>
          </div>
        </Modal>
      )}
    </div>
  );
}
