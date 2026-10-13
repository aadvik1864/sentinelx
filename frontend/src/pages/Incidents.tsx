import { lazy, Suspense, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  CheckCheck,
  ChevronRight,
  FileText,
  GitBranch,
  Link2,
  LockKeyhole,
  MessageSquare,
  Plus,
  Search,
  Shield,
  Sparkles,
  UserRound,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
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
import { buildTimeline } from "../utils/timeline";
import { statusLabel } from "../utils/labels";
import type { Analysis, Incident, Page, Severity } from "../types";

const EvidenceGraph = lazy(() => import("../components/EvidenceGraph"));
const techniqueNames: Record<string, string> = {
  T1110: "Brute force",
  T1078: "Valid accounts",
  "T1548.003": "Sudo and sudo caching",
  T1046: "Network service discovery",
};
const statuses = ["open", "investigating", "contained", "resolved"];

function CreateIncident({ close }: { close: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<Severity>("medium");
  const [eventIds, setEventIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const notify = useToast();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ids = eventIds.trim()
        ? eventIds
            .split(",")
            .map((id) => Number(id.trim().replace(/^EVT-/, "")))
        : [];
      if (ids.some((id) => !Number.isInteger(id) || id < 1)) {
        setError("Enter record IDs separated by commas, such as EVT-00001, EVT-00002.");
        return;
      }
      await api.post("/incidents", {
        title,
        description,
        severity,
        event_ids: ids,
      });
      reconcile();
      notify("Investigation created.");
      close();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="stack-form" onSubmit={submit}>
      <label>
        Investigation title
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          required
          minLength={3}
          maxLength={200}
        />
      </label>
      <label>
        Description
        <textarea
          rows={4}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={8000}
        />
      </label>
      <label>
        Priority
        <SeveritySelect
          value={severity}
          onChange={(value) => setSeverity(value as Severity)}
        />
      </label>
      <label>
        Link activity record IDs (optional)
        <input
          placeholder="EVT-00001, EVT-00002"
          value={eventIds}
          onChange={(event) => setEventIds(event.target.value)}
        />
      </label>
      <ErrorBox message={error} />
      <div className="form-actions">
        <button type="button" className="button secondary" onClick={close}>
          Cancel
        </button>
        <button className="button primary" disabled={busy}>
          {busy ? "Creating…" : "Create investigation"}
        </button>
      </div>
    </form>
  );
}

export function IncidentsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const { user } = useAuth();
  const debounced = useDebounced(query);
  const filters = new URLSearchParams({
    q: debounced,
    limit: "25",
    offset: String(offset),
  });
  if (status) filters.set("status", status);
  if (severity) filters.set("severity", severity);
  const { data, error, loading, reload } = useResource<Page<Incident>>(
    `/incidents?${filters}`,
  );
  return (
    <>
      <PageHeader
        title="Investigations"
        description="Related alerts and activity brought together, so you can understand the whole story."
        actions={
          user?.role !== "VIEWER" && (
            <button
              className="button primary"
              onClick={() => setCreating(true)}
            >
              <Plus size={17} />
              Create investigation
            </button>
          )
        }
      />
      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search investigations"
              placeholder="Search investigations or systems…"
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
              setSeverity(value);
              setOffset(0);
            }}
          />
          <select
            aria-label="Investigation status"
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
                  <th>Investigation</th>
                  <th>Priority</th>
                  <th>Status</th>
                  <th>Client address</th>
                  <th>System</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((incident) => (
                  <tr key={incident.id}>
                    <td>
                      <Link
                        className="table-title"
                        to={`/incidents/${incident.id}`}
                      >
                        {incident.title}
                        <small>
                          {incident.reference}
                        </small>
                      </Link>
                    </td>
                    <td>
                      <Badge value={incident.severity} severity />
                    </td>
                    <td>
                      <Badge value={incident.status} />
                    </td>
                    <td>
                      <code>{incident.source_ip ?? "—"}</code>
                    </td>
                    <td>{incident.hostname || "Not linked"}</td>
                    <td className="muted">{relative(incident.updated_at)}</td>
                    <td>
                      <Link
                        className="icon-button"
                        to={`/incidents/${incident.id}`}
                        aria-label={`Open ${incident.reference}`}
                      >
                        <ChevronRight size={17} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No investigations found"
            description="Try fewer filters. Related alerts create investigations automatically, or an investigator can start one."
          />
        )}
        <Pagination
          total={data?.total ?? 0}
          offset={offset}
          setOffset={setOffset}
        />
      </div>
      {creating && (
        <Modal title="Create an investigation" onClose={() => setCreating(false)}>
          <CreateIncident close={() => setCreating(false)} />
        </Modal>
      )}
    </>
  );
}

export function IncidentDetailPage() {
  const { id } = useParams();
  const {
    data: incident,
    error,
    loading,
    reload,
  } = useResource<Incident>(`/incidents/${id}`);
  const { user } = useAuth();
  const canEdit = user?.role !== "VIEWER";
  const { data: assignees } = useResource<{
    items: { id: number; name: string }[];
  }>(canEdit ? "/users/assignees" : null);
  const [tab, setTab] = useState("timeline");
  const [note, setNote] = useState("");
  const [noteKind, setNoteKind] = useState("note");
  const [linkIds, setLinkIds] = useState("");
  const [linking, setLinking] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const notify = useToast();
  async function update(values: Record<string, string | number | null>) {
    setBusy(true);
    try {
      await api.patch(`/incidents/${id}`, values);
      reload();
      reconcile();
      setResolving(false);
      notify("Investigation updated.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function addNote(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api.post(`/incidents/${id}/notes`, {
        content: note,
        kind: noteKind,
      });
      setNote("");
      reload();
      notify(
        noteKind === "evidence"
          ? "Evidence added."
          : "Investigation note added.",
      );
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function linkEvents(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const ids = linkIds
        .split(",")
        .map((item) => Number(item.trim().replace(/^EVT-/, "")));
      if (ids.some((item) => !Number.isInteger(item) || item < 1)) {
        notify("Enter record IDs separated by commas, such as EVT-00001, EVT-00002.", true);
        return;
      }
      await api.post(`/incidents/${id}/events`, { event_ids: ids });
      setLinking(false);
      setLinkIds("");
      reload();
      notify("Activity records linked to this investigation.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function enrich() {
    setBusy(true);
    try {
      await api.post(`/incidents/${id}/enrich`);
      reload();
      notify(
        "Address information refreshed. Check who provided it and read the notice.",
      );
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function analyze() {
    setTab("analysis");
    setAnalyzing(true);
    try {
      const { data } = await api.post<Analysis>(
        "/ai/analyze-incident", { incident_id: Number(id) },
        { timeout: AI_REQUEST_TIMEOUT },
      );
      setAnalysis(data);
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setAnalyzing(false);
    }
  }
  const timeline = incident ? buildTimeline(incident) : [];
  return (
    <>
      <Link className="back-link" to="/incidents">
        <ArrowLeft size={16} />
        All investigations
      </Link>
      <ErrorBox message={error} retry={reload} />
      {loading && !incident ? (
        <Loading />
      ) : (
        incident && (
          <>
            <PageHeader
              title={incident.title}
              description={`${incident.reference} · Created ${time(incident.created_at, true)}`}
              actions={
                canEdit && (
                  <>
                    <button
                      className="button secondary"
                      onClick={analyze}
                      disabled={analyzing}
                    >
                      <Sparkles size={16} />
                      {analyzing ? "Reviewing…" : "Explain this investigation"}
                    </button>
                    {incident.status !== "resolved" && (
                      <button
                        className="button primary"
                        onClick={() => setResolving(true)}
                      >
                        <CheckCheck size={16} />
                        Close investigation
                      </button>
                    )}
                  </>
                )
              }
            />
            <div className="incident-summary-bar">
              <Badge value={incident.severity} severity />
              <Badge value={incident.status} />
              <span>
                <Shield size={16} />
                <code>{incident.source_ip ?? "Unknown source"}</code>
              </span>
              <span>
                <FileText size={16} />
                {incident.hostname || "No linked system"}
              </span>
              <span>
                <UserRound size={16} />
                {incident.assigned_name ?? "Unassigned"}
              </span>
            </div>
            <div className="investigation-layout">
              <section className="panel investigation-main">
                <div
                  className="tabs"
                  role="tablist"
                  aria-label="Investigation views"
                >
                  {[
                    { id: "timeline", label: "Timeline", icon: FileText },
                    { id: "graph", label: "Connections", icon: GitBranch },
                    ...(canEdit
                      ? [
                          {
                            id: "analysis",
                            label: "Explanation",
                            icon: Sparkles,
                          },
                        ]
                      : []),
                  ].map((item) => (
                    <button
                      role="tab"
                      aria-selected={tab === item.id}
                      className={tab === item.id ? "active" : ""}
                      key={item.id}
                      onClick={() => setTab(item.id)}
                    >
                      <item.icon size={16} />
                      {item.label}
                    </button>
                  ))}
                </div>
                {tab === "timeline" && (
                  <div className="timeline-view">
                    <div className="timeline-intro">
                      <div>
                        <h2>What happened, in order</h2>
                        <p>
                          {incident.event_total} linked activity records, in chronological
                          order.
                        </p>
                      </div>
                      {canEdit && (
                        <button
                          className="text-button"
                          onClick={() => setLinking(true)}
                        >
                          <Link2 size={15} />
                          Link records
                        </button>
                      )}
                    </div>
                    {incident.evidence_truncated && (
                      <div className="notice">
                        Showing the first 500 records. Use Activity to search all the records.
                      </div>
                    )}
                    <div className="timeline">
                      {timeline.map((entry) => (
                        <div className="timeline-entry" key={entry.key}>
                          <div className="timeline-time">
                            <strong>{time(entry.timestamp)}</strong>
                            <span>
                              {new Date(entry.timestamp).toLocaleDateString(
                                undefined,
                                { month: "short", day: "numeric" },
                              )}
                            </span>
                          </div>
                          <div
                            className={`timeline-point severity-${entry.severity}`}
                          >
                            {entry.type === "note" ? (
                              <MessageSquare size={12} />
                            ) : entry.type === "system" ? (
                              <CheckCheck size={12} />
                            ) : (
                              <span />
                            )}
                          </div>
                          <div className="timeline-content">
                            <h3>{entry.title}</h3>
                            <p>{entry.body}</p>
                            <div>
                              <code>{entry.reference}</code>
                              <span>{entry.label}</span>
                            </div>
                            {entry.events && entry.events.length > 1 && (
                              <details className="grouped-evidence">
                                <summary>
                                  View {entry.events.length} original records
                                </summary>
                                <ol>
                                  {entry.events.map((event) => (
                                    <li key={event.id}>
                                      <div>
                                        <code>{event.reference}</code>
                                        <time dateTime={event.timestamp}>
                                          {time(event.timestamp)}
                                        </time>
                                      </div>
                                      <p>{event.message}</p>
                                    </li>
                                  ))}
                                </ol>
                              </details>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    {canEdit && (
                      <form className="note-form" onSubmit={addNote}>
                        <label htmlFor="incident-note">
                          Add to the investigation
                        </label>
                        <textarea
                          id="incident-note"
                          rows={3}
                          placeholder="Record findings, decisions, or verified evidence…"
                          value={note}
                          onChange={(event) => setNote(event.target.value)}
                          required
                          maxLength={8000}
                        />
                        <div>
                          <select
                            aria-label="Contribution type"
                            value={noteKind}
                            onChange={(event) =>
                              setNoteKind(event.target.value)
                            }
                          >
                            <option value="note">Investigation note</option>
                            <option value="evidence">Evidence</option>
                          </select>
                          <button
                            className="button primary"
                            disabled={busy || !note.trim()}
                          >
                            <Plus size={15} />
                            Add {noteKind}
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                )}
                {tab === "graph" && (
                  <div className="graph-view">
                    <h2>Connected evidence</h2>
                    <p>
                      Related activity shown together. A connection does not prove that one event caused another.
                    </p>
                    <Suspense fallback={<Loading />}>
                      <EvidenceGraph incident={incident} />
                    </Suspense>
                  </div>
                )}
                {tab === "analysis" && (
                  <div className="assistant-view">
                    {analyzing ? (
                      <Loading label="Reviewing the activity records… Local AI may take a couple of minutes." />
                    ) : analysis ? (
                      <AnalysisPanel analysis={analysis} />
                    ) : (
                      <Empty
                        title="Need help understanding the activity?"
                        description="Get an explanation and suggestions for what to check. Verify the advice before taking action."
                        action={
                          <button className="button primary" onClick={analyze}>
                            <Sparkles size={16} />
                            Explain this investigation
                          </button>
                        }
                      />
                    )}
                  </div>
                )}
              </section>
              <aside className="incident-context">
                <section className="panel context-panel">
                  <h2>Investigation details</h2>
                  {canEdit ? (
                    <>
                      <label>
                        Person reviewing
                        <select
                          value={incident.assigned_to ?? ""}
                          disabled={busy}
                          onChange={(event) =>
                            update({
                              assigned_to: event.target.value
                                ? Number(event.target.value)
                                : null,
                            })
                          }
                        >
                          <option value="">Unassigned</option>
                          {assignees?.items.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Priority
                        <SeveritySelect
                          value={incident.severity}
                          onChange={(value) => update({ severity: value })}
                        />
                      </label>
                      <label>
                        Status
                        <select
                          aria-label="Investigation status"
                          value={incident.status}
                          disabled={busy}
                          onChange={(event) => {
                            if (event.target.value === "resolved")
                              setResolving(true);
                            else update({ status: event.target.value });
                          }}
                        >
                          {statuses.map((item) => (
                            <option key={item} value={item}>
                              {statusLabel(item)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </>
                  ) : (
                    <dl className="detail-grid">
                      <dt>Person reviewing</dt>
                      <dd>{incident.assigned_name ?? "Unassigned"}</dd>
                      <dt>Status</dt>
                      <dd>{statusLabel(incident.status)}</dd>
                    </dl>
                  )}
                </section>
                <details className="panel context-panel context-disclosure">
                  <summary>Attack pattern references</summary><p className="muted">MITRE ATT&CK describes known attack patterns. These matches are not proof of an attack.</p>
                  <div className="mitre-list">
                    {incident.mitre_techniques.length ? (
                      incident.mitre_techniques.map((item) => (
                        <a
                          key={item}
                          href={`https://attack.mitre.org/techniques/${item.replace(".", "/")}/`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <div>
                            <code>{item}</code>
                            <span>
                              {techniqueNames[item] ?? "Mapped technique"}
                            </span>
                          </div>
                          <ArrowUpRight size={16} />
                        </a>
                      ))
                    ) : (
                      <p className="muted">No techniques mapped.</p>
                    )}
                  </div>
                </details>
                <details className="panel context-panel context-disclosure">
                  <summary>Address reputation checks</summary>
                  <div className="context-heading">
                    <h2>Address information</h2>
                    {canEdit && (
                      <button
                        className="text-button"
                        onClick={enrich}
                        disabled={busy}
                      >
                        Check addresses
                      </button>
                    )}
                  </div>
                  {incident.iocs?.length ? (
                    incident.iocs.map((ioc) => (
                      <div className="ioc-mini" key={ioc.id}>
                        <code>{ioc.value}</code>
                        <Badge value={ioc.reputation} />
                        <p>{String(ioc.metadata.notice ?? "")}</p>
                        <span>
                          {ioc.source}
                          {ioc.confidence !== null
                            ? ` · Provider score ${ioc.confidence}/100`
                            : " · No reputation score"}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="muted">
                      {canEdit
                          ? "Check whether a connected service has information about these addresses. Without a service configured, reputation stays unknown."
                          : "No address information saved yet. An investigator can check these addresses."}
                    </p>
                  )}
                </details>
                <section className="panel context-panel">
                  <h2>
                    Related alerts{" "}
                    <span className="heading-count">
                      {incident.alerts?.length ?? 0}
                    </span>
                  </h2>
                  {incident.alerts?.map((alert) => (
                    <Link
                      className="related-alert"
                      key={alert.id}
                      to={`/alerts?selected=${alert.id}`}
                    >
                      <span
                        className={`alert-mark severity-${alert.severity}`}
                      />
                      <div>
                        <strong>{alert.title}</strong>
                        <small>{alert.reference}</small>
                      </div>
                      <ChevronRight size={14} />
                    </Link>
                  ))}
                </section>
                <div className="safety-reminder">
                  <LockKeyhole size={17} />
                  <p>
                    Recommendations only.
                    <br />
                    You remain in control.
                  </p>
                </div>
              </aside>
            </div>
            {resolving && (
              <Modal
                title="Close this investigation?"
                onClose={() => setResolving(false)}
              >
                <p className="muted">
                  This closes the investigation and its related alerts, except alerts already marked Not an issue. It does not fix the underlying issue, block addresses, or change your systems.
                </p>
                <div className="form-actions">
                  <button
                    className="button secondary"
                    onClick={() => setResolving(false)}
                  >
                    Keep investigating
                  </button>
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => update({ status: "resolved" })}
                  >
                    Confirm closure
                  </button>
                </div>
              </Modal>
            )}
            {linking && (
              <Modal
                title="Link activity records"
                onClose={() => setLinking(false)}
              >
                <form className="stack-form" onSubmit={linkEvents}>
                  <label>
                    Record IDs
                    <input
                      placeholder="EVT-00001, EVT-00002"
                      value={linkIds}
                      onChange={(event) => setLinkIds(event.target.value)}
                      required
                    />
                  </label>
                  <p className="muted">
                    Find record IDs in Activity. Records already linked will not be added twice.
                  </p>
                  <div className="form-actions">
                    <button
                      type="button"
                      className="button secondary"
                      onClick={() => setLinking(false)}
                    >
                      Cancel
                    </button>
                    <button className="button primary" disabled={busy}>
                      Link records
                    </button>
                  </div>
                </form>
              </Modal>
            )}
          </>
        )
      )}
    </>
  );
}
