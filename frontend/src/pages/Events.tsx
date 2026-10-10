import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ChevronRight,
  Code2,
  Plus,
  Search,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  PageHeader,
  Pagination,
  SeveritySelect,
  time,
  useToast,
} from "../components/ui";
import { useDebounced, useResource } from "../hooks/useResource";
import { api, errorMessage, reconcile } from "../services/api";
import { eventLabel, formatLabel } from "../utils/labels";
import type { Page, SecurityEvent } from "../types";

function IngestForm({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState("normalized");
  const [source, setSource] = useState("linux");
  const [hostname, setHostname] = useState("linux-lab-01");
  const [text, setText] = useState(
    JSON.stringify(
      {
        timestamp: new Date().toISOString(),
        source: "linux",
        event_type: "authentication_failure",
        severity: "medium",
        source_ip: "203.0.113.42",
        username: "admin",
        hostname: "linux-lab-01",
        message: "Failed SSH authentication",
        metadata: {},
      },
      null,
      2,
    ),
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const notify = useToast();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload =
        mode === "normalized"
          ? JSON.parse(text)
          : {
              source,
              hostname,
              line: text,
              timestamp: new Date().toISOString(),
            };
      await api.post(
        mode === "normalized" ? "/events" : "/events/raw",
        payload,
      );
      reconcile();
      notify("Activity record imported and checked against your alert rules.");
      onClose();
    } catch (err) {
      setError(
        err instanceof SyntaxError ? "Enter valid JSON." : errorMessage(err),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="stack-form" onSubmit={submit}>
      <div className="notice">
        <Code2 size={17} />
        <p>
          Import a record into this workspace and check it against your alert rules.
          This does not connect a system or run commands. Replace the example with a real record; imported records affect your totals.
        </p>
      </div>
      <label>
        Input format
        <select
          value={mode}
          onChange={(event) => {
            setMode(event.target.value);
            setText(
              event.target.value === "raw"
                ? "sshd[1432]: Failed password for admin from 203.0.113.42 port 52412 ssh2"
                : JSON.stringify(
                    {
                      timestamp: new Date().toISOString(),
                      source: "linux",
                      event_type: "authentication_failure",
                      severity: "medium",
                      source_ip: "203.0.113.42",
                      hostname: "linux-lab-01",
                      message: "Failed SSH authentication",
                      metadata: {},
                    },
                    null,
                    2,
                  ),
            );
          }}
        >
          <option value="normalized">Structured record (JSON)</option>
          <option value="raw">Original activity file line</option>
        </select>
      </label>
      {mode === "raw" && (
        <div className="form-row">
          <label>
            File format
            <select
              value={source}
              onChange={(event) => setSource(event.target.value)}
            >
              <option value="linux">Linux authentication</option>
              <option value="nginx">Nginx access log</option>
              <option value="apache">Apache access log</option>
              <option value="application">Application JSON</option>
            </select>
          </label>
          <label>
            Computer name
            <input
              value={hostname}
              onChange={(event) => setHostname(event.target.value)}
              required
            />
          </label>
        </div>
      )}
      <label>
        {mode === "raw" ? "Original activity line" : "Activity record (JSON)"}
        <textarea
          className="code-input"
          rows={13}
          value={text}
          onChange={(event) => setText(event.target.value)}
          required
          maxLength={24000}
        />
      </label>
      <ErrorBox message={error} />
      <div className="form-actions">
        <button type="button" className="button secondary" onClick={onClose}>
          Cancel
        </button>
        <button className="button primary" disabled={busy}>
          {busy ? "Importing…" : "Import record"}
        </button>
      </div>
    </form>
  );
}

export function EventsPage() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [severity, setSeverity] = useState("");
  const [source, setSource] = useState("");
  const [range, setRange] = useState("24");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<SecurityEvent | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const debounced = useDebounced(query);
  const [startTime, setStartTime] = useState(() =>
    new Date(Date.now() - 24 * 3600000).toISOString(),
  );
  useEffect(() => {
    setQuery(params.get("q") ?? "");
    setOffset(0);
  }, [params]);
  const filters = new URLSearchParams({
    q: debounced,
    limit: "25",
    offset: String(offset),
  });
  if (severity) filters.set("severity", severity);
  if (source) filters.set("source", source);
  if (params.get("source_id"))
    filters.set("source_id", params.get("source_id")!);
  if (range !== "all") filters.set("start_time", startTime);
  const { data, error, loading, reload } = useResource<Page<SecurityEvent>>(
    `/events?${filters}`,
  );
  function exportEvents() {
    if (!data) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data.items, null, 2)], {
        type: "application/json",
      }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "sentinelx-events-page.json";
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHeader
        title="Activity"
        description="Read what your connected systems recorded. Activity by itself is not an alert."
        actions={
          <>
            <button
              className="button secondary"
              onClick={exportEvents}
              disabled={!data}
            >
              <ArrowDownToLine size={16} />
              Download these records
            </button>
          </>
        }
      />
      <div className="panel">
        <div className="filter-bar">
          {params.get("source_id") && (
            <p className="source-event-filter">
              Activity from system connection #{params.get("source_id")}.{" "}
              <Link className="text-link" to="/events">
                Show all systems
              </Link>
            </p>
          )}
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search activity"
              placeholder="Search a name, address, or message…"
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
            aria-label="System type"
            value={source}
            onChange={(event) => {
              setSource(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All system types</option>
            {["linux", "nginx", "apache", "application", "network"].map(
              (item) => (
                <option key={item} value={item}>
                  {formatLabel(item)}
                </option>
              ),
            )}
          </select>
          <select
            aria-label="Time range"
            value={range}
            onChange={(event) => {
              setRange(event.target.value);
              setStartTime(
                new Date(
                  Date.now() - (Number(event.target.value) || 24) * 3600000,
                ).toISOString(),
              );
              setOffset(0);
            }}
          >
            <option value="1">Last hour</option>
            <option value="24">Last 24 hours</option>
            <option value="168">Last 7 days</option>
            <option value="all">All time</option>
          </select>
        </div>
        <details className="search-help"><summary>Advanced search tips</summary><p>Search a particular field with <code>source_ip:203.0.113.42</code> or <code>hostname:your-server</code>. Priority uses the stored values <code>critical</code>, <code>high</code>, <code>medium</code>, and <code>low</code>; for example, <code>severity:high</code>.</p></details>
        <ErrorBox message={error} retry={reload} />
        {loading && !data ? (
          <Loading />
        ) : data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>What happened</th>
                  <th>Priority</th>
                  <th>Client address</th>
                  <th>System</th>
                  <th>Type</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((event) => (
                  <tr key={event.id}>
                    <td className="mono timestamp-cell">
                      {time(event.timestamp)}
                      <small>
                        {new Date(event.timestamp).toLocaleDateString()}
                      </small>
                    </td>
                    <td>
                      <button
                        className="table-title"
                        onClick={() => setSelected(event)}
                      >
                        {eventLabel(event.event_type)}
                        <small className="truncate">{event.message}</small>
                      </button>
                    </td>
                    <td>
                      <Badge value={event.severity} severity />
                    </td>
                    <td>
                      <code>{event.source_ip ?? "—"}</code>
                    </td>
                    <td>{event.hostname}</td>
                    <td>
                      <span className="source-tag">
                        {formatLabel(event.source)}
                      </span>
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`View ${event.reference}`}
                        onClick={() => setSelected(event)}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No activity found"
            description="Try a wider time range or fewer filters. If you expected new activity, check Connected systems."
            action={<Link className="button secondary" to="/sources">Check connections</Link>}
          />
        )}
        <Pagination
          total={data?.total ?? 0}
          offset={offset}
          setOffset={setOffset}
        />
      </div>
      {selected && (
        <Modal
          title={selected.reference}
          onClose={() => setSelected(null)}
          drawer
        >
          <div className="detail-head">
            <Badge value={selected.severity} severity />
            <span className="source-tag">{formatLabel(selected.source)}</span>
          </div>
          <h3>{eventLabel(selected.event_type)}</h3>
          <dl className="detail-grid">
            <dt>When</dt>
            <dd>{time(selected.timestamp, true)}</dd>
            <dt>Client address</dt>
            <dd>
              <code>{selected.source_ip ?? "Unknown"}</code>
            </dd>
            <dt>Destination address</dt>
            <dd>{selected.destination_ip ?? "Not recorded"}</dd>
            <dt>Computer name</dt>
            <dd>{selected.hostname}</dd>
            <dt>User</dt>
            <dd>{selected.username ?? "Not recorded"}</dd>
          </dl>
          <h3>Recorded message</h3>
          <pre className="log-block">{selected.message}</pre>
          <details className="disclosure"><summary>Technical record (JSON)</summary><pre className="json-block">{JSON.stringify(selected, null, 2)}</pre></details>
        </Modal>
      )}
      <details className="disclosure"><summary>Advanced: import a record manually</summary><p>For people who already have a record to import. This is not a way to connect a system for ongoing monitoring.</p><button className="button secondary" onClick={() => setIngesting(true)}><Plus size={16} />Import record</button></details>
      {ingesting && (
        <Modal
          title="Import an activity record"
          onClose={() => setIngesting(false)}
          wide
        >
          <IngestForm onClose={() => setIngesting(false)} />
        </Modal>
      )}
    </>
  );
}
