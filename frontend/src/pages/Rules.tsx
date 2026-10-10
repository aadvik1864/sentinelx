import { useState } from "react";
import { Pencil, Plus, Search, SlidersHorizontal, Trash2 } from "lucide-react";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  PageHeader,
  SeveritySelect,
  humanize,
  useToast,
} from "../components/ui";
import { useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { api, errorMessage, reconcile } from "../services/api";
import type { Rule, Severity } from "../types";

const kinds = [
  "threshold",
  "successful_after_failures",
  "privilege_escalation",
  "port_scan",
  "http_errors",
  "suspicious_authentication",
];
function RuleEditor({ rule, close }: { rule: Rule | null; close: () => void }) {
  const [name, setName] = useState(rule?.name ?? "");
  const [description, setDescription] = useState(rule?.description ?? "");
  const [kind, setKind] = useState(rule?.kind ?? "threshold");
  const [eventType, setEventType] = useState(
    rule?.event_type ?? "authentication_failure",
  );
  const [threshold, setThreshold] = useState(rule?.threshold ?? 10);
  const [windowSeconds, setWindowSeconds] = useState(
    rule?.window_seconds ?? 300,
  );
  const [severity, setSeverity] = useState<Severity>(rule?.severity ?? "high");
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [mitre, setMitre] = useState(rule?.mitre_techniques.join(", ") ?? "");
  const [errorRatio, setErrorRatio] = useState(
    Number(rule?.config.error_ratio ?? 0.3),
  );
  const [sourceScope, setSourceScope] = useState(
    Array.isArray(rule?.config.sources) ? rule.config.sources.join(", ") : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const notify = useToast();
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      name,
      description,
      kind,
      event_type: eventType,
      threshold,
      window_seconds: windowSeconds,
      severity,
      enabled,
      mitre_techniques: mitre
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      config: {
        ...(kind === "http_errors" ? { error_ratio: errorRatio } : {}),
        ...(sourceScope.trim()
          ? {
              sources: sourceScope
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            }
          : {}),
      },
    };
    try {
      if (rule) await api.patch(`/rules/${rule.id}`, payload);
      else await api.post("/rules", payload);
      reconcile();
      notify(rule ? "Detection rule updated." : "Detection rule created.");
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
        Rule name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          minLength={3}
          maxLength={150}
        />
      </label>
      <label>
        Description
        <textarea
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={2000}
        />
      </label>
      <div className="form-row">
        <label>
          Detection pattern
          <select
            value={kind}
            onChange={(event) => {
              const value = event.target.value;
              setKind(value);
              setEventType(
                value === "port_scan"
                  ? "network_connection"
                  : value === "http_errors"
                    ? "http_request"
                    : value === "privilege_escalation"
                      ? "privilege_escalation"
                      : value.includes("authentication") ||
                          value === "successful_after_failures"
                        ? "authentication_success"
                        : "authentication_failure",
              );
            }}
          >
            {kinds.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Event type
          <input
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
            pattern="[a-z][a-z0-9_]*"
            maxLength={100}
            required
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          {kind === "port_scan" ? "Distinct ports" : "Event threshold"}
          <input
            type="number"
            min={1}
            max={100000}
            value={threshold}
            onChange={(event) => setThreshold(Number(event.target.value))}
            required
          />
        </label>
        <label>
          Window (seconds)
          <input
            type="number"
            min={1}
            max={86400}
            value={windowSeconds}
            onChange={(event) => setWindowSeconds(Number(event.target.value))}
            required
          />
        </label>
        <label>
          Severity
          <SeveritySelect
            value={severity}
            onChange={(value) => setSeverity(value as Severity)}
          />
        </label>
      </div>
      {kind === "http_errors" && (
        <label>
          Minimum error ratio (0–1)
          <input
            type="number"
            min={0.01}
            max={1}
            step={0.01}
            value={errorRatio}
            onChange={(event) => setErrorRatio(Number(event.target.value))}
            required
          />
        </label>
      )}
      <label>
        MITRE ATT&CK IDs
        <input
          value={mitre}
          onChange={(event) => setMitre(event.target.value)}
          placeholder="T1110, T1078"
        />
      </label>
      <label>
        Log formats (blank means all)
        <input
          value={sourceScope}
          onChange={(event) => setSourceScope(event.target.value)}
          placeholder="linux, application, nginx, apache, network"
        />
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        Enable this detection
      </label>
      <div className="notice">
        <SlidersHorizontal size={16} />
        <p>
          Thresholds are inclusive. Rules group by source IP and target
          hostname. Login-success patterns also require the same username.
        </p>
      </div>
      <ErrorBox message={error} />
      <div className="form-actions">
        <button type="button" className="button secondary" onClick={close}>
          Cancel
        </button>
        <button className="button primary" disabled={busy}>
          {busy ? "Saving…" : "Save rule"}
        </button>
      </div>
    </form>
  );
}

export function RulesPage() {
  const { data, error, loading, reload } = useResource<{ items: Rule[] }>(
    "/rules",
  );
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Rule | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<Rule | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const notify = useToast();
  async function toggle(rule: Rule) {
    setBusy(rule.id);
    try {
      await api.patch(`/rules/${rule.id}`, { enabled: !rule.enabled });
      reload();
      notify(`Rule ${rule.enabled ? "disabled" : "enabled"}.`);
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(null);
    }
  }
  async function remove() {
    if (!deleting) return;
    setBusy(deleting.id);
    try {
      await api.delete(`/rules/${deleting.id}`);
      reload();
      setDeleting(null);
      notify("Rule deleted. Existing alerts retain their evidence.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(null);
    }
  }
  const rules =
    data?.items.filter((rule) =>
      `${rule.name} ${rule.event_type}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) ?? [];
  return (
    <>
      <PageHeader
        title="Alert rules"
        description="Choose which activity patterns should raise an alert. These settings are for experienced users."
        actions={
          isAdmin && (
            <button className="button primary" onClick={() => setEditing(null)}>
              <Plus size={17} />
              Create rule
            </button>
          )
        }
      />
      <div className="rule-stats">
        <span>
          <span className="status-light online" />
          {data?.items.filter((rule) => rule.enabled).length ?? 0} enabled
        </span>
        <span>{data?.items.length ?? 0} configured rules</span>
        <span>Changes are audit logged</span>
      </div>
      <div className="panel">
        <div className="filter-bar">
          <div className="search-field">
            <Search size={17} />
            <input
              aria-label="Search rules"
              placeholder="Find a detection rule…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <span className="muted">
            {isAdmin
              ? "Administrator controls"
              : "Read-only detection configuration"}
          </span>
        </div>
        <ErrorBox message={error} retry={reload} />
        {loading && !data ? (
          <Loading />
        ) : rules.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Pattern</th>
                  <th>Threshold</th>
                  <th>Window</th>
                  <th>Priority</th>
                  <th>Enabled</th>
                  {isAdmin && <th />}
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.id}>
                    <td>
                      <strong className="rule-name">{rule.name}</strong>
                      <small className="table-description">
                        {rule.description}
                      </small>
                      <div className="rule-mitre">
                        {rule.mitre_techniques.map((id) => (
                          <code key={id}>{id}</code>
                        ))}
                      </div>
                    </td>
                    <td>
                      <span className="pattern-label">
                        {humanize(rule.kind)}
                      </span>
                      <small className="table-description mono">
                        {rule.event_type}
                      </small>
                    </td>
                    <td className="mono">≥ {rule.threshold}</td>
                    <td className="mono">{rule.window_seconds}s</td>
                    <td>
                      <Badge value={rule.severity} severity />
                    </td>
                    <td>
                      <button
                        className={`toggle ${rule.enabled ? "on" : ""}`}
                        role="switch"
                        aria-label={`Enable ${rule.name}`}
                        aria-checked={rule.enabled}
                        disabled={!isAdmin || busy === rule.id}
                        onClick={() => toggle(rule)}
                      >
                        <span />
                      </button>
                    </td>
                    {isAdmin && (
                      <td>
                        <div className="row-actions">
                          <button
                            className="icon-button"
                            aria-label={`Edit ${rule.name}`}
                            onClick={() => setEditing(rule)}
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            className="icon-button"
                            aria-label={`Delete ${rule.name}`}
                            onClick={() => setDeleting(rule)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="No matching rules"
            description="Change the search or create a new detection rule."
          />
        )}
      </div>
      {editing !== undefined && (
        <Modal
          title={editing ? "Edit detection rule" : "Create detection rule"}
          onClose={() => setEditing(undefined)}
          wide
        >
          <RuleEditor rule={editing} close={() => setEditing(undefined)} />
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete detection rule?" onClose={() => setDeleting(null)}>
          <p className="muted">
            Delete “{deleting.name}”? Existing alerts and incident evidence will
            be preserved. You can disable the rule instead.
          </p>
          <div className="form-actions">
            <button
              className="button secondary"
              onClick={() => setDeleting(null)}
            >
              Cancel
            </button>
            <button
              className="button danger"
              disabled={busy !== null}
              onClick={remove}
            >
              Delete rule
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
