import { Braces, Globe, Terminal } from "lucide-react";
import { Link } from "react-router-dom";
import type { LogSource } from "../types";
import { relative } from "./ui";

export const sourceLabels = {
  not_connected: "Setup needed",
  receiving: "Receiving activity",
  waiting: "Connected",
  offline: "Disconnected",
  error: "Needs attention",
  paused: "Paused",
};

export function SourceIcon({ kind }: { kind: LogSource["kind"] }) {
  const Icon =
    kind === "linux" ? Terminal : kind === "application" ? Braces : Globe;
  return <Icon size={20} />;
}

export function SourceStatus({ source }: { source: LogSource }) {
  return (
    <span className={`source-status source-status-${source.status}`}>
      <span className="status-light" />
      {sourceLabels[source.status]}
    </span>
  );
}

export function SourceHealth({ sources, loading = false, error = null }: { sources: LogSource[]; loading?: boolean; error?: string | null }) {
  return (
    <div className="source-health-panel">
      <div className="panel-heading">
        <div>
          <h2>Connected systems</h2>
          <p>
            A connected system may have no new activity.
          </p>
        </div>
        <Link className="text-link" to="/sources">
          Manage
        </Link>
      </div>
      {loading ? <p className="compact-empty">Checking connections…</p> : error ? <p className="compact-empty">Connection information is unavailable. <Link className="text-link" to="/sources">Try Connected systems</Link></p> : sources.length ? (
        <div className="source-health-grid">
          {sources.map((source) => (
            <Link to={`/sources?q=${encodeURIComponent(source.name)}`} className="source-health-item" key={source.id}>
              <span className="source-kind-icon">
                <SourceIcon kind={source.kind} />
              </span>
              <div>
                <strong>{source.name}</strong>
                <SourceStatus source={source} />
                <small>
                  {source.last_event_at ? `Last activity received ${relative(source.last_event_at).toLowerCase()}` : "No activity received yet"}
                </small>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="source-health-empty">
          No systems added yet.{" "}
          <Link className="text-link" to="/sources">
            Connect your first system
          </Link>
        </p>
      )}
    </div>
  );
}
