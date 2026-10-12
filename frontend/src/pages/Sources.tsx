import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine, Braces, Check, Copy, Globe, Plus, RefreshCw, Search, ShieldCheck, Terminal,
} from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  ErrorBox, Loading, Modal, PageHeader, relative, time, useToast,
} from "../components/ui";
import { SourceIcon, SourceStatus } from "../components/SourceHealth";
import { SegmentedControl } from "../components/SegmentedControl";
import { Step, Stepper } from "../components/react-bits/Stepper";
import { useResource } from "../hooks/useResource";
import { api, errorMessage, reconcile } from "../services/api";
import { useAuth } from "../store/AuthContext";
import type { LogSource } from "../types";

type Setup = { source: LogSource; collector_key?: string };
const defaults = {
  linux: "/var/log/auth.log",
  nginx: "/var/log/nginx/access.log",
  apache: "/var/log/apache2/access.log",
  application: "/var/log/myapp/security.jsonl",
};
const choices = [
  { type: "linux", title: "Linux computer", detail: "Sign-ins and administrator activity", icon: Terminal },
  { type: "nginx", title: "Website", detail: "Page requests and website errors", icon: Globe },
  { type: "application", title: "Web app", detail: "Sign-ins and activity recorded by your app", icon: Braces },
] as const;

function systemType(kind: LogSource["kind"]) {
  return kind === "linux" ? "Linux computer" : kind === "application" ? "Web app" : "Website";
}

function statusHelp(source: LogSource) {
  if (source.status === "key_expired") return "The connection key expired. Ask an administrator to replace it and update the helper’s private settings, keeping its existing checkpoint file.";
  if (source.status === "error") {
    if (source.last_error.includes("read its configured log file"))
      return "The helper cannot read the activity file. Ask the server administrator to check its location and read permissions.";
    if (source.last_error.includes("container"))
      return "The app or website container is unavailable. Ask its administrator to check that it is running and its activity can be read.";
    if (source.last_error.includes("rejected"))
      return "Some activity records could not be read. The helper saved a private error report for the server administrator to review.";
    if (source.last_error.includes("rotated") || source.last_error.includes("disappeared"))
      return "Some activity may be missing because an old file was removed before it could be read. Ask the server administrator to review the gap.";
    return "The connection needs help. Ask the server administrator to check the helper and review the technical message in connection details.";
  }
  const descriptions: Record<string, string> = {
    not_connected: "Finish setup on the server to start receiving activity.",
    waiting: "The connection is responding. There may simply be nothing new to report.",
    receiving: "Recent activity has reached SentinelX.",
    offline: "Activity may be missing. Check that the helper is running and can reach SentinelX.",
    paused: "New records are not being accepted. Records already received are kept.",
  };
  return descriptions[source.status];
}

function saveFile(content: Blob, name: string) {
  const url = URL.createObjectURL(content);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

export function SourcesPage() {
  const { user } = useAuth();
  const admin = user?.role === "ADMIN";
  const { data, error, loading, reload } = useResource<{ items: LogSource[] }>("/sources");
  const [create, setCreate] = useState(false);
  const [step, setStep] = useState(1);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [rotate, setRotate] = useState<LogSource | null>(null);
  const [overlap, setOverlap] = useState(false);
  const [kind, setKind] = useState<LogSource["kind"]>("linux");
  const [name, setName] = useState("");
  const [hostname, setHostname] = useState("");
  const [path, setPath] = useState(defaults.linux);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const filter = ["attention", "receiving", "paused"].includes(params.get("filter") ?? "") ? params.get("filter")! : "all";
  const [query, setQuery] = useState(params.get("q") ?? "");
  useEffect(() => {
    // External navigation updates the search; our own delayed URL commits must
    // not overwrite newer keystrokes in this synchronously controlled input.
    if (!location.state?.sourceFilterChange) setQuery(params.get("q") ?? "");
  }, [params, location.state]);
  const items = data?.items ?? [];
  const attention = (source: LogSource) => ["offline", "error", "not_connected", "key_expired"].includes(source.status);
  const filtered = items.filter((source) => {
    const matchesStatus = filter === "all" || filter === "attention" && attention(source) || source.status === filter;
    return matchesStatus && `${source.name} ${source.hostname} ${systemType(source.kind)}`.toLowerCase().includes(query.toLowerCase().trim());
  });
  const notify = useToast();

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (query) next.set("q", query);
    else next.delete("q");
    if (!value || key === "filter" && value === "all") next.delete(key);
    else next.set(key, value);
    if (key === "q") setQuery(value);
    setParams(next, { replace: true, state: { ...location.state, sourceFilterChange: true } });
  }

  function chooseKind(value: LogSource["kind"]) {
    setKind(value);
    setPath(defaults[value]);
  }
  function startConnection() {
    setStep(1);
    setCreate(true);
    setName("");
    setHostname("");
    chooseKind("linux");
    setFormError(null);
  }
  async function nextStep() {
    setFormError(null);
    if (step === 1) {
      if (name.trim().length < 2) {
        setFormError("Give this system a name with at least two characters.");
        return;
      }
      setStep(2);
      return;
    }
    if (step === 2) {
      if (!hostname.trim()) {
        setFormError("Enter the computer name. The person who manages the server can help you find it.");
        return;
      }
      if (!path.trim()) {
        setFormError("Enter the activity file location on that computer.");
        return;
      }
      setStep(3);
      return;
    }
    setBusy(true);
    try {
      const result = await api.post<Setup>("/sources", {
        name: name.trim(), kind, hostname: hostname.trim(), log_path: path.trim(),
      });
      setCreate(false);
      setSetup(result.data);
      reconcile();
      notify("Connection saved. Finish setup on the server to receive activity.");
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function pause(source: LogSource) {
    setBusy(true);
    try {
      await api.patch(`/sources/${source.id}`, { enabled: !source.enabled });
      reconcile();
      notify(source.enabled ? "Activity collection paused for this system." : "Collection resumed. The helper can reconnect.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function replaceKey() {
    if (!rotate) return;
    setBusy(true);
    try {
      const result = await api.post<Setup>(`/sources/${rotate.id}/rotate-key`, { overlap_seconds: overlap ? 300 : 0 });
      setRotate(null);
      setSetup(result.data);
      reconcile();
      notify(overlap ? "New key created. Update the helper within five minutes, keeping its checkpoint file." : "Old connection key disabled. Download the new settings and update the helper.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Connected systems"
        description="See where your activity comes from and add a computer, website, or app."
        actions={admin && (
          <button className="button primary" onClick={startConnection}>
            <Plus size={17} />Connect a system
          </button>
        )}
      />
      <details className="disclosure connection-explainer">
        <summary>How does connecting a system work?</summary>
        <p>SentinelX reads activity files, often called logs, from systems you have permission to monitor. A small helper runs on the computer holding those files and sends new records here.</p>
        <p>A website address alone is not enough. For one website, use its own activity file rather than a file shared by every website on the server. You may need the person who manages your hosting or server to finish setup.</p>
      </details>
      <ErrorBox message={error} retry={reload} />
      {items.length > 0 && (
        <div className="system-filter-bar">
          <SegmentedControl
            label="Filter systems"
            value={filter}
            options={[
              { value: "all", label: "All systems", count: items.length },
              { value: "attention", label: "Needs attention", count: items.filter(attention).length },
              { value: "receiving", label: "Receiving", count: items.filter((source) => source.status === "receiving").length },
              { value: "paused", label: "Paused", count: items.filter((source) => source.status === "paused").length },
            ]}
            onChange={(value) => updateFilter("filter", value)}
          />
          <label className="system-search">
            <Search size={17} /><span className="sr-only">Find a system</span>
            <input value={query} onChange={(event) => updateFilter("q", event.target.value)} placeholder="Name or computer name" maxLength={100} />
          </label>
          <p className="system-filter-count" role="status">Showing {filtered.length} of {items.length} systems</p>
        </div>
      )}
      {loading && !data ? <Loading label="Checking your system connections…" /> : data?.items.length ? (
        <div className="systems-list">
          {!filtered.length && (
            <div className="system-filter-empty">
              <h2>No systems match these filters</h2>
              <p>Try another name or show all of your connections.</p>
              <button className="button secondary" onClick={() => {
                const next = new URLSearchParams(params);
                next.delete("q"); next.delete("filter");
                setQuery("");
                setParams(next, { replace: true, state: { ...location.state, sourceFilterChange: true } });
              }}>Clear filters</button>
            </div>
          )}
          {filtered.map((source) => (
            <article className="system-row" key={source.id}>
              <div className="system-row-heading">
                <span className="source-kind-icon"><SourceIcon kind={source.kind} /></span>
                <div className="system-row-name"><h2>{source.name}</h2><p>{systemType(source.kind)} · {source.hostname}</p></div>
                <SourceStatus source={source} />
                <Link className="button secondary" to={`/events?source_id=${source.id}`}>View activity</Link>
              </div>
              <p className={`system-status-help ${["offline", "error", "not_connected"].includes(source.status) ? "needs-help" : ""}`}>
                {statusHelp(source)}
              </p>
              <details className="system-options">
                <summary>Connection details and settings</summary>
                <dl className="source-facts">
                  <div><dt>Activity records received</dt><dd>{source.total_events.toLocaleString()}</dd></div>
                  <div><dt>Connection last responded</dt><dd>{source.last_heartbeat_at ? time(source.last_heartbeat_at, true) : "Not yet connected"}</dd></div>
                  <div><dt>Last activity received</dt><dd>{source.last_event_at ? time(source.last_event_at, true) : "No records yet"}</dd></div>
                   <div><dt>Activity file location</dt><dd><code>{source.log_path || "Not specified"}</code></dd></div>
                   <div><dt>Connection key expires</dt><dd>{source.token_expires_at ? time(source.token_expires_at, true) : "Legacy key: administrator review required"}</dd></div>
                </dl>
                {source.last_error && (
                  <details className="technical-message">
                    <summary>Technical message for the server administrator</summary><p>{source.last_error}</p>
                  </details>
                )}
                <div className="source-detail-actions">
                  <button className="button secondary" onClick={() => setSetup({ source })}>Setup instructions</button>
                  {admin && (
                    <>
                      <button className="text-button" disabled={busy} onClick={() => pause(source)}>
                        {source.enabled ? "Pause collection" : "Resume collection"}
                      </button>
                      <button className="text-button" disabled={busy} onClick={() => { setOverlap(false); setRotate(source); }}>Replace connection key</button>
                    </>
                  )}
                </div>
              </details>
            </article>
          ))}
        </div>
      ) : !error && (
        <section className="panel getting-started-empty">
          <ShieldCheck size={32} /><h2>Connect your first system</h2>
          <p>Choose a computer, website, or app to start receiving its activity. Nothing is monitored until you finish setup on that system.</p>
          {admin ? <button className="button primary" onClick={startConnection}>Connect a system</button> : <p>Ask an administrator to add a system for you.</p>}
        </section>
      )}

      {create && (
        <Modal title="Connect a system" onClose={() => !busy && setCreate(false)} wide>
          <ErrorBox message={formError} />
          <Stepper
            labels={["Choose", "Details", "Review"]} step={step}
            onStepChange={(value) => { setFormError(null); setStep(value); }}
            onNext={nextStep} nextLabel={step === 3 ? "Save connection" : "Continue"} busy={busy}
          >
            <Step title="What would you like to watch?" description="Choose a system you own or have permission to monitor.">
              <fieldset className="system-type-choices">
                <legend className="sr-only">System type</legend>
                {choices.map((choice) => {
                  const selected = kind === choice.type || choice.type === "nginx" && kind === "apache";
                  return (
                    <label className={`system-type-choice ${selected ? "selected" : ""}`} key={choice.type}>
                      <input type="radio" name="system-type" checked={selected} onChange={() => chooseKind(choice.type)} />
                      <choice.icon size={22} /><strong>{choice.title}</strong><span>{choice.detail}</span>
                    </label>
                  );
                })}
              </fieldset>
              <label className="standalone-label">
                Name for this system
                <input value={name} onChange={(event) => setName(event.target.value)} placeholder="For example, My shop website" minLength={2} maxLength={100} required />
              </label>
            </Step>
            <Step title="Where is its activity saved?" description="These details come from the computer running the system. If you’re unsure, ask the person who manages the server.">
              <div className="stack-form">
                {(kind === "nginx" || kind === "apache") && (
                  <label>
                    Website server software
                    <select aria-label="Website server software" aria-describedby="website-software-help" value={kind} onChange={(event) => chooseKind(event.target.value as LogSource["kind"])}>
                      <option value="nginx">Nginx</option><option value="apache">Apache</option>
                    </select>
                    <span id="website-software-help" className="field-help">Your hosting provider can tell you which one is used.</span>
                  </label>
                )}
                <label>
                  Computer name
                  <input aria-label="Computer name" aria-describedby="computer-name-help" value={hostname} onChange={(event) => setHostname(event.target.value)} placeholder="For example, shop-server" required maxLength={253} />
                  <span id="computer-name-help" className="field-help">The name of the computer running your website, app, or Linux system.</span>
                </label>
                <label>
                  Activity file location
                  <input aria-label="Activity file location" aria-describedby="activity-file-help" value={path} onChange={(event) => setPath(event.target.value)} required maxLength={512} />
                  <span id="activity-file-help" className="field-help">
                    {kind === "linux" ? "A common Linux location is filled in. Your server may use /var/log/secure instead."
                      : kind === "application" ? "Your app must already write a security activity file in JSON-lines format. A developer may need to add this."
                        : "Use the access log for this particular website. A shared file includes activity from all sites using it."}
                  </span>
                </label>
              </div>
            </Step>
            <Step title="Check your connection details" description="Saving creates a connection, but does not install anything on the server.">
              <dl className="setup-review">
                <div><dt>System</dt><dd>{name}</dd></div>
                <div><dt>Type</dt><dd>{systemType(kind)}</dd></div>
                <div><dt>Computer</dt><dd>{hostname}</dd></div>
                <div><dt>Activity file</dt><dd><code>{path}</code></dd></div>
              </dl>
              <div className="notice"><ShieldCheck size={18} /><p>Next you’ll download a helper and private connection settings. Run them on the server, or send the instructions securely to the person who manages it.</p></div>
            </Step>
          </Stepper>
        </Modal>
      )}
      {setup && (
        <ConnectionSetup setup={setup} currentSource={data?.items.find((source) => source.id === setup.source.id) ?? setup.source} onClose={() => setSetup(null)} />
      )}
      {rotate && (
        <Modal title="Replace this system’s connection key?" onClose={() => !busy && setRotate(null)}>
          <p className="muted">A connection key is the helper’s private pass to send activity. Replace it only if the settings were lost or shared with someone who should not have them.</p>
          <label className="checkbox-label"><input type="checkbox" checked={overlap} onChange={(event) => setOverlap(event.target.checked)} />Keep the old key valid for up to five minutes during a planned rotation. Do not enable this for a suspected leaked key.</label>
          <div className="notice"><ShieldCheck size={18} /><p>The old key for {rotate.name} {overlap ? "expires within five minutes" : "stops working immediately"}. New keys expire after 90 days. Update the helper’s private key without replacing its existing checkpoint file. Replacing a key does not restart the helper for you.</p></div>
          <div className="source-detail-actions">
            <button className="button secondary" disabled={busy} onClick={() => setRotate(null)}>Cancel</button>
            <button className="button danger" disabled={busy} onClick={replaceKey}>
              <Check size={16} />{busy ? "Replacing…" : "Replace connection key"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

function ConnectionSetup({ setup, currentSource, onClose }: {
  setup: Setup; currentSource: LogSource; onClose: () => void;
}) {
  const [step, setStep] = useState(1);
  const [saved, setSaved] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const warningRef = useRef<HTMLDivElement>(null);
  const notify = useToast();
  useEffect(() => {
    if (confirmClose) warningRef.current?.focus();
  }, [confirmClose]);
  const config = setup.collector_key ? JSON.stringify({
    url: window.location.protocol === "https:" ? window.location.origin : "http://localhost:8080",
    state_file: "./sentinelx-checkpoints.sqlite3",
    sources: [{
      id: setup.source.id,
      key: setup.collector_key,
      kind: setup.source.kind,
      ...(setup.source.log_path.startsWith("docker:") ? {
        mode: "docker",
        project: setup.source.log_path.slice(7).split("/")[0],
        service: setup.source.log_path.slice(7).split("/")[1],
        self_monitoring: setup.source.log_path.startsWith("docker:sentinelx/"),
      } : { mode: "file", path: setup.source.log_path }),
      timezone: "local",
      start: "tail",
    }],
  }, null, 2) : "";

  async function downloadHelper() {
    setDownloading(true);
    try {
      const response = await api.get("/sources/agent", { responseType: "blob" });
      saveFile(response.data, "sentinelx-agent.py");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setDownloading(false);
    }
  }
  async function copySettings() {
    try {
      await navigator.clipboard.writeText(config);
      setSaved(true);
      notify("Private connection settings copied. Save them in a protected file.");
    } catch {
      notify("Copy is unavailable. Use Download connection settings instead.", true);
    }
  }
  function close() {
    if (config && !saved) setConfirmClose(true);
    else onClose();
  }

  return (
    <Modal title={`Finish connecting ${setup.source.name}`} onClose={close} wide>
      {confirmClose ? (
        <div className="stack-form source-close-warning" ref={warningRef} tabIndex={-1}>
          <h3>Have you saved the private settings?</h3>
          <p className="muted">They are shown only once. If you leave without saving them, an administrator will need to replace the connection key.</p>
          <div className="source-detail-actions">
            <button className="button primary" onClick={() => setConfirmClose(false)}>Go back and save settings</button>
            <button className="text-button" onClick={onClose}>Close without saving</button>
          </div>
        </div>
      ) : (
        <Stepper
          labels={["Download", "Run on server", "Check"]} step={step} onStepChange={setStep}
          onNext={() => step < 3 ? setStep(step + 1) : close()}
          nextLabel={step === 3 ? "Return to systems" : "Continue"}
          nextDisabled={step === 1 && !!config && !saved}
        >
          <Step title="Save the helper and connection settings" description="The helper reads new activity from your system and sends it here. Download the files, then move them securely to the computer with the activity file.">
            <div className="setup-downloads">
              <button className="button secondary" onClick={downloadHelper} disabled={downloading}>
                <ArrowDownToLine size={17} />{downloading ? "Downloading…" : "Download helper"}
              </button>
              {config && (
                <button className="button primary" onClick={() => {
                  saveFile(new Blob([config], { type: "application/json" }), "sentinelx-source.json");
                  setSaved(true);
                }}>
                  <ArrowDownToLine size={17} />Download connection settings
                </button>
              )}
            </div>
            {config ? (
              <div className="notice"><ShieldCheck size={18} /><p>Save the connection settings before continuing. They contain a private key for this system only. Keep the file private; it cannot be downloaded again later.</p></div>
            ) : <p className="muted">Use the settings file you saved when this connection was created. Keys cannot be shown again. If that file is lost, ask an administrator to replace the connection key in Connection details and settings.</p>}
            {config && (
              <details className="disclosure small-disclosure">
                <summary>Copy settings instead</summary>
                <button className="text-button" onClick={copySettings}><Copy size={15} />Copy private settings</button>
              </details>
            )}
          </Step>
          <Step title="Start the helper on the server" description="This step needs access to the computer running your system. If someone else manages it, ask them to run the commands below. No command is run by clicking Continue.">
            <p className="setup-step-description">Install Python 3.12 or newer. Put the downloaded files in one folder, open a terminal there, and run:</p>
            <pre className="source-code">{`python3 -m venv .venv
.venv/bin/pip install httpx==0.28.1
chmod 600 sentinelx-source.json
.venv/bin/python sentinelx-agent.py --config sentinelx-source.json`}</pre>
            <p className="muted">Keep the helper running. It reads only new activity on first start, rather than treating old records as new. It needs permission to read the chosen file.</p>
            <details className="disclosure">
              <summary>The monitored system is on another computer</summary>
              <p>The default local setup cannot be reached directly from another computer. Keep this authorized SSH connection running on the monitored computer, replacing the example with the SSH address of your SentinelX server:</p>
              <pre className="source-code">ssh -N -L 8080:127.0.0.1:8080 your-user@sentinelx-host</pre>
              <p>An administrator can instead configure secure HTTPS hosting and update the settings file’s <code>url</code>. Never send private settings to a remote server using plain HTTP.</p>
            </details>
            {setup.source.kind === "application" && (
              <details className="disclosure">
                <summary>Developer instructions for app activity</summary>
                <p>The app must write one JSON object per line, using the actual time and client address. For example, a rejected sign-in can use this shape:</p>
                <pre className="source-code">{'{"timestamp":"2026-10-09T10:00:00Z","event_type":"authentication_failure","message":"Sign-in rejected","ip":"203.0.113.10","username":"alice","level":"WARNING"}'}</pre>
                <p>Replace the example values with the real activity. Never write passwords, tokens, cookies, or complete request bodies.</p>
              </details>
            )}
            {setup.source.log_path.startsWith("docker:") && (
              <p className="field-help">This connection reads container activity. Its administrator must provide Docker log access. Docker access is powerful; do not grant it unnecessarily.</p>
            )}
          </Step>
          <Step title="Check that the connection responds" description="A quiet system can be connected without sending new records. Check the connection separately from the activity count.">
            <div className="setup-connection-result">
              <SourceStatus source={currentSource} /><p>{statusHelp(currentSource)}</p>
              {currentSource.last_heartbeat_at && <small>Last response {relative(currentSource.last_heartbeat_at).toLowerCase()}</small>}
            </div>
            <button className="button secondary" onClick={reconcile}><RefreshCw size={16} />Check connection</button>
            <p className="setup-step-description">Connection status refreshes about every 30 seconds. When records arrive, choose View activity on this system’s row. The dashboard’s Live updates label only describes the dashboard connection.</p>
          </Step>
        </Stepper>
      )}
    </Modal>
  );
}
