import { useState } from "react";
import {
  ArrowDownToLine, ArrowUpRight, Bell, CheckCheck, ChevronRight,
  FileText, Play, Radio, RefreshCw, ShieldAlert,
} from "lucide-react";
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Link, useNavigate } from "react-router-dom";
import {
  Badge, ErrorBox, Loading, PageHeader, relative, severities, useToast,
} from "../components/ui";
import { useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { CountUp } from "../components/react-bits/CountUp";
import { SpotlightCard } from "../components/react-bits/SpotlightCard";
import { SourceHealth } from "../components/SourceHealth";
import { api, errorMessage, reconcile } from "../services/api";
import { priorityLabels } from "../utils/labels";
import type {
  Alert, DashboardMetrics, Incident, Page, SystemInfo, LogSource,
} from "../types";

export function DashboardPage() {
  const { data, error, loading, reload } = useResource<DashboardMetrics>("/dashboard");
  const { data: alerts, error: alertsError } = useResource<Page<Alert>>("/alerts?limit=4&status=open");
  const { data: incidents, error: incidentsError } = useResource<Page<Incident>>("/incidents?limit=3&status=open");
  const { data: system } = useResource<SystemInfo>("/system");
  const { user } = useAuth();
  const { data: sources, error: sourcesError } = useResource<{ items: LogSource[] }>(
    user?.role === "VIEWER" ? null : "/sources",
  );
  const [simulating, setSimulating] = useState(false);
  const notify = useToast();
  const navigate = useNavigate();
  const canInvestigate = user?.role !== "VIEWER";
  const connectionIssues = sources?.items.filter((source) =>
    ["offline", "error", "not_connected"].includes(source.status),
  ) ?? [];

  async function simulate() {
    setSimulating(true);
    try {
      const { data: result } = await api.post<{ incident_id: number }>("/demo/simulate");
      reconcile();
      notify("Practice activity added. Your example investigation is ready.");
      navigate(`/incidents/${result.incident_id}`);
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setSimulating(false);
    }
  }

  function exportSnapshot() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "sentinelx-overview.json";
    link.click();
    URL.revokeObjectURL(url);
    notify("Overview downloaded.");
  }

  return (
    <>
      <PageHeader
        title="Your security overview"
        description="See what needs a closer look and whether your systems are connected."
        actions={
          <button className="button secondary" onClick={reconcile} aria-label="Refresh overview">
            <RefreshCw size={16} />Refresh
          </button>
        }
      />
      <ErrorBox message={error} retry={reload} />
      {loading && !data ? <Loading /> : data && (
        <>
          <SpotlightCard
            className={`overview-review ${data.active_alerts ? "has-alerts" : ""}`}
            spotlightColor="rgba(128, 170, 255, 0.10)"
          >
            <span className="review-symbol">
              {data.active_alerts ? <ShieldAlert size={27} /> : <CheckCheck size={27} />}
            </span>
            <div>
              <h2>
                {data.active_alerts
                  ? `${data.active_alerts.toLocaleString()} ${data.active_alerts === 1 ? "alert needs" : "alerts need"} a review`
                  : "No alerts waiting for review"}
              </h2>
              <p>
                {data.active_alerts
                  ? `${data.critical_alerts ? `${data.critical_alerts} urgent. ` : ""}An alert means a pattern needs checking, not that an attack is confirmed.`
                  : "Nothing has been flagged right now. This is not a guarantee that your systems are secure."}
              </p>
            </div>
            <Link className="button secondary" to="/alerts">
              {data.active_alerts ? "Review alerts" : "View alerts"}<ChevronRight size={16} />
            </Link>
          </SpotlightCard>

          {canInvestigate && (sourcesError ? (
            <ErrorBox message="We couldn’t check your system connections. Open Connected systems to try again." />
          ) : connectionIssues.length > 0 && (
            <Link className="connection-attention" to="/sources">
              <Radio size={18} />
              <span>
                {connectionIssues.length} {connectionIssues.length === 1 ? "system needs" : "systems need"} connection help.
                Activity from {connectionIssues.length === 1 ? "it" : "them"} may be missing.
              </span>
              <ChevronRight size={16} />
            </Link>
          ))}

          <div className="overview-stats" aria-label="Overview totals">
            {[
              { label: "Activity recorded", value: data.total_events, note: "In the last 24 hours" },
              { label: "Alerts to review", value: data.active_alerts, note: "All current alerts" },
              { label: "Open investigations", value: data.open_incidents, note: "Related activity being checked" },
            ].map((metric) => (
              <div className="metric" key={metric.label}>
                <span className="metric-label">{metric.label}</span>
                <strong><CountUp to={metric.value} /></strong>
                <span className="metric-note">{metric.note}</span>
              </div>
            ))}
          </div>

          <div className="overview-main-grid">
            <section className="panel overview-alerts">
              <div className="panel-heading">
                <div><h2>Latest alerts</h2><p>Open an alert to understand what happened.</p></div>
                <Link className="text-link" to="/alerts">View all<ArrowUpRight size={15} /></Link>
              </div>
              <ErrorBox message={alertsError} />
              {!alerts && !alertsError ? <Loading label="Checking alerts…" /> : alerts?.items.length ? (
                <div className="review-list">
                  {alerts.items.map((alert) => (
                    <Link className="review-list-row" key={alert.id} to={`/alerts?selected=${alert.id}`}>
                      <div><strong>{alert.title}</strong><span>{alert.hostname} · {relative(alert.detected_at)}</span></div>
                      <Badge value={alert.severity} severity /><ChevronRight size={16} />
                    </Link>
                  ))}
                </div>
              ) : !alertsError && (
                <div className="quiet-state">
                  <Bell size={22} /><h3>No open alerts</h3>
                  <p>New alerts appear here when recorded activity matches one of your rules.</p>
                </div>
              )}
            </section>
            {canInvestigate ? (
              <section className="panel overview-systems">
                <SourceHealth sources={sources?.items ?? []} loading={!sources && !sourcesError} error={sourcesError} />
              </section>
            ) : (
              <section className="panel">
                <div className="panel-heading">
                  <div><h2>Investigations</h2><p>Related alerts brought together for review.</p></div>
                  <FileText size={19} />
                </div>
                <InvestigationList incidents={incidents} error={incidentsError} />
              </section>
            )}
          </div>

          <section className="panel activity-panel simplified-chart">
            <div className="panel-heading">
              <div><h2>Activity over time</h2><p>Records received from your systems, grouped by when the activity happened.</p></div>
              <span className="chart-legend">Last 24 hours</span>
            </div>
            <div className="activity-chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data.activity} margin={{ top: 10, right: 12, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="event-fill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#80aaff" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="#80aaff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#27364c" vertical={false} strokeDasharray="3 5" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={(value) => new Date(value).toLocaleTimeString(undefined, {
                      hour: "2-digit", minute: "2-digit", hour12: false,
                    })}
                    axisLine={false} tickLine={false} minTickGap={40}
                    tick={{ fill: "#a7b8cc", fontSize: 12 }}
                  />
                  <YAxis axisLine={false} tickLine={false} allowDecimals={false} tick={{ fill: "#a7b8cc", fontSize: 12 }} />
                  <Tooltip
                    contentStyle={{ background: "#192940", border: "1px solid #344763", borderRadius: 8, color: "#e5edf8" }}
                    labelFormatter={(value) => new Date(value).toLocaleString()}
                  />
                  <Area type="monotone" dataKey="events" name="Activity records" stroke="#80aaff" strokeWidth={2} fill="url(#event-fill)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-footer">
              <span>More activity does not necessarily mean more risk.</span>
              {canInvestigate && <Link className="text-link" to="/events">View activity<ChevronRight size={15} /></Link>}
            </div>
          </section>

          <details className="disclosure overview-details">
            <summary>More detail</summary>
            <div className="overview-detail-grid">
              <section>
                <h2>Alert priorities</h2>
                <div className="priority-list">
                  {severities.map((severity) => (
                    <Link to={`/alerts?severity=${severity}`} key={severity}>
                      <span>{priorityLabels[severity]}</span><strong>{data.severity_counts[severity]}</strong>
                    </Link>
                  ))}
                </div>
                <p className="muted">Priority helps you decide what to check first.</p>
                <dl className="collection-totals">
                  <div><dt>Devices saved</dt><dd>{data.monitored_assets}</dd></div>
                  <div><dt>Distinct client addresses (24 hours)</dt><dd>{data.unique_source_ips}</dd></div>
                  <div><dt>Records received per second (last minute)</dt><dd>{data.events_per_second}</dd></div>
                </dl>
                <p className="muted">Saved devices are not proof of a working connection.</p>
              </section>
              <section>
                <h2>Open investigations</h2>
                <InvestigationList incidents={incidents} error={incidentsError} />
              </section>
              <section>
                <h2>Most active addresses</h2>
                <p className="muted">An IP address identifies a network connection. Activity volume alone does not mean an address is harmful.</p>
                {data.top_ips.length ? (
                  <div className="priority-list">
                    {data.top_ips.map((item) => (
                      <Link key={item.ip} to={canInvestigate ? `/events?q=source_ip:${item.ip}` : "/alerts"}>
                        <code>{item.ip}</code><span>{item.count} records</span>
                      </Link>
                    ))}
                  </div>
                ) : <p className="muted">No addresses were recorded in this time period.</p>}
                <button className="text-button download-summary" onClick={exportSnapshot}>
                  <ArrowDownToLine size={15} />Download overview data
                </button>
              </section>
            </div>
          </details>

          {system?.demo_mode && user?.role === "ADMIN" && (
            <section className="practice-action">
              <div><h3>Want to see how an investigation works?</h3><p>This adds a clearly marked practice example, not a real attack.</p></div>
              <button className="button secondary" onClick={simulate} disabled={simulating}>
                <Play size={15} />{simulating ? "Preparing example…" : "Try a practice example"}
              </button>
            </section>
          )}
        </>
      )}
    </>
  );
}

function InvestigationList({ incidents, error }: { incidents: Page<Incident> | null; error: string | null }) {
  if (error) return <ErrorBox message={error} />;
  if (!incidents) return <Loading label="Checking investigations…" />;
  return incidents.items.length ? (
    <div className="review-list">
      {incidents.items.map((incident) => (
        <Link className="review-list-row" key={incident.id} to={`/incidents/${incident.id}`}>
          <div><strong>{incident.title}</strong><span>{incident.hostname} · {relative(incident.updated_at)}</span></div>
          <ChevronRight size={16} />
        </Link>
      ))}
    </div>
  ) : <p className="compact-empty">No open investigations. Related alerts will appear here together.</p>;
}
