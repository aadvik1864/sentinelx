import { useState } from "react";
import {
  ArrowUpRight,
  Bell,
  ChevronRight,
  Search,
  Sparkles,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { AnalysisPanel } from "../components/AnalysisPanel";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  PageHeader,
  Pagination,
  SeveritySelect,
  relative,
  time,
  useToast,
} from "../components/ui";
import { useDebounced, useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { AI_REQUEST_TIMEOUT, api, errorMessage, reconcile } from "../services/api";
import { eventLabel, statusLabel } from "../utils/labels";
import type { Alert, Analysis, Page } from "../types";

const statuses = [
  "open",
  "acknowledged",
  "investigating",
  "resolved",
  "false_positive",
];
function AlertDetails({ id, close }: { id: number; close: () => void }) {
  const {
    data: alert,
    error,
    loading,
    reload,
  } = useResource<Alert>(`/alerts/${id}`);
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const notify = useToast();
  async function update(status: string) {
    setBusy(true);
    try {
      await api.patch(`/alerts/${id}`, { status });
      reconcile();
      reload();
      notify(`Alert updated: ${statusLabel(status).toLowerCase()}.`);
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function explain() {
    setAnalyzing(true);
    try {
      const { data } = await api.post<Analysis>(
        "/ai/explain-alert", { alert_id: id }, { timeout: AI_REQUEST_TIMEOUT },
      );
      setAnalysis(data);
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setAnalyzing(false);
    }
  }
  return (
    <Modal title={alert?.reference ?? "Alert details"} onClose={close} drawer>
      <ErrorBox message={error} retry={reload} />
      {loading && !alert ? (
        <Loading />
      ) : (
        alert && (
          <>
            <div className="detail-head">
              <Badge value={alert.severity} severity />
              <Badge value={alert.status} />
            </div>
            <h2 className="detail-title">{alert.title}</h2>
            <p className="muted">{alert.description}</p>
            <dl className="detail-grid">
              <dt>Client address</dt>
              <dd>
                <code>{alert.source_ip ?? "Unknown"}</code>
              </dd>
              <dt>System</dt>
              <dd>{alert.hostname}</dd>
              <dt>Detected</dt>
              <dd>{time(alert.detected_at, true)}</dd>
              <dt>Matching activity records</dt>
              <dd>{alert.event_count}</dd>
              <dt>Rule</dt>
              <dd>{alert.rule?.name ?? "Rule removed"}</dd>
            </dl>
            {user?.role !== "VIEWER" && (
              <label className="standalone-label">
                Alert status
                <select
                  value={alert.status}
                  disabled={busy}
                  onChange={(event) => update(event.target.value)}
                >
                  {statuses.map((item) => (
                    <option key={item} value={item}>
                      {statusLabel(item)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {alert.incident_id && (
              <Link
                className="incident-link"
                to={`/incidents/${alert.incident_id}`}
                onClick={close}
              >
                <FileIcon />
                <span>
                  Open related investigation
                  <strong>
                    INC-{String(alert.incident_id).padStart(5, "0")}
                  </strong>
                </span>
                <ArrowUpRight size={19} />
              </Link>
            )}
            <details className="disclosure"><summary>Attack pattern references (MITRE ATT&CK)</summary><p>These references describe patterns seen in the records. A match does not confirm an attack.</p>
            <div className="technique-tags">
              {alert.mitre_techniques.length ? (
                alert.mitre_techniques.map((item) => (
                  <a
                    href={`https://attack.mitre.org/techniques/${item.replace(".", "/")}/`}
                    target="_blank"
                    rel="noreferrer"
                    key={item}
                  >
                    {item}
                    <ArrowUpRight size={12} />
                  </a>
                ))
              ) : (
                <span className="muted">No technique mapped</span>
              )}
            </div>
            </details>
            <h3>Activity behind this alert</h3>
            {alert.event && (
              <>
                <div className="evidence-label">
                  <code>{alert.event.reference}</code>
                  <span>{eventLabel(alert.event.event_type)}</span>
                </div>
                <pre className="log-block">{alert.event.message}</pre>
              </>
            )}
            {user?.role !== "VIEWER" && (
              <button
                className="button secondary full-width"
                disabled={analyzing}
                onClick={explain}
              >
                <Sparkles size={16} />
                {analyzing ? "Reviewing records…" : "Explain this alert"}
              </button>
            )}
            {analysis && <AnalysisPanel analysis={analysis} />}
          </>
        )
      )}
    </Modal>
  );
}
function FileIcon() {
  return <Bell size={20} />;
}

export function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const severity = params.get("severity") ?? "";
  const selected = Number(params.get("selected")) || null;
  const debounced = useDebounced(query);
  const filters = new URLSearchParams({
    q: debounced,
    limit: "25",
    offset: String(offset),
  });
  if (severity) filters.set("severity", severity);
  if (status) filters.set("status", status);
  const { data, error, loading, reload } = useResource<Page<Alert>>(
    `/alerts?${filters}`,
  );
  function select(id: number | null) {
    const next = new URLSearchParams(params);
    if (id) next.set("selected", String(id));
    else next.delete("selected");
    setParams(next);
  }
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Patterns that need a closer look. An alert is not proof that an attack happened."
        actions={
          <span className="count-chip">
            <Bell size={16} />
            {data?.total ?? "…"} alerts
          </span>
        }
      />
      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search alerts"
              placeholder="Search alerts, systems, or addresses…"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
            />
          </div>
          <SeveritySelect
            value={severity}
            all
            onChange={(value) => {
              const next = new URLSearchParams(params);
              if (value) next.set("severity", value);
              else next.delete("severity");
              setParams(next);
              setOffset(0);
            }}
          />
          <select
            aria-label="Alert status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {statuses.map((item) => (
              <option key={item} value={item}>
                {statusLabel(item)}
              </option>
            ))}
          </select>
        </div>
        <ErrorBox message={error} retry={reload} />
        {loading && !data ? (
          <Loading />
        ) : data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>What needs checking</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Client address</th>
                  <th>System</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((alert) => (
                  <tr key={alert.id}>
                    <td>
                      <button
                        className="table-title"
                        onClick={() => select(alert.id)}
                      >
                        {alert.title}
                        <small>
                          {alert.reference} <span> / </span>
                          {alert.event_count} matching records
                        </small>
                      </button>
                    </td>
                    <td>
                      <Badge value={alert.severity} severity />
                    </td>
                    <td>
                      <Badge value={alert.status} />
                    </td>
                    <td>
                      <code>{alert.source_ip ?? "Unknown"}</code>
                    </td>
                    <td>{alert.hostname}</td>
                    <td className="muted">{relative(alert.created_at)}</td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`View ${alert.reference}`}
                        onClick={() => select(alert.id)}
                      >
                        <ChevronRight size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No matching alerts"
            description="Try fewer filters. New alerts appear when activity matches an enabled alert rule."
          />
        )}
        <Pagination
          total={data?.total ?? 0}
          offset={offset}
          setOffset={setOffset}
        />
      </div>
      {selected && (
        <AlertDetails key={selected} id={selected} close={() => select(null)} />
      )}
    </>
  );
}
