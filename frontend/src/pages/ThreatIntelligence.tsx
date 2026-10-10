import { useState } from "react";
import { Globe, Search, Shield, ShieldQuestion } from "lucide-react";
import { Badge, ErrorBox, Loading, PageHeader, time } from "../components/ui";
import { api, errorMessage } from "../services/api";
import { useResource } from "../hooks/useResource";
import type { IOC, SystemInfo } from "../types";

export function ThreatIntelligencePage() {
  const [kind, setKind] = useState("ip");
  const [value, setValue] = useState("");
  const [result, setResult] = useState<IOC | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { data: system } = useResource<SystemInfo>("/system");
  async function lookup(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const { data } = await api.get<IOC>(
        `/threat-intelligence/${kind}/${encodeURIComponent(value.trim())}`,
      );
      setResult(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Address checks"
        description="Look up information about an address. Unknown does not mean safe."
      />
      <section className="panel intel-search-panel">
        <div className="intel-search-title">
          <span className="intel-icon">
            <Globe size={25} />
          </span>
          <div>
            <h2>Check an address or file</h2>
            <p>Search a network address, website domain, or file fingerprint.</p>
          </div>
        </div>
        <form className="intel-search" onSubmit={lookup}>
          <select
            aria-label="Indicator type"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setResult(null);
            }}
          >
            <option value="ip">IP address</option>
            <option value="domain">Domain</option>
            <option value="hash">File fingerprint (hash)</option>
          </select>
          <input
            aria-label="Indicator value"
            placeholder={
              kind === "ip"
                ? "203.0.113.42"
                : kind === "domain"
                  ? "example.com"
                  : "MD5, SHA-1, or SHA-256"
            }
            value={value}
            onChange={(event) => setValue(event.target.value)}
            required
            maxLength={253}
          />
          <button className="button primary" disabled={busy}>
            <Search size={17} />
            {busy ? "Checking…" : "Check information"}
          </button>
        </form>
        <div className="provider-line">
          <span
            className={`status-light ${system?.threat_intel_provider !== "unconfigured" ? "online" : ""}`}
          />
          {system?.threat_intel_provider === "unconfigured"
            ? "No external service configured. Only local address information is available."
            : `Information service: ${system?.threat_intel_provider ?? "Loading…"}`}
        </div>
        <ErrorBox message={error} />
      </section>
      {busy && <Loading label="Checking address information…" />}
      {result ? (
        <section className="panel intel-result">
          <div className="panel-heading">
            <div>
              <h2 className="mono">{result.value}</h2>
              <p>
                {result.type.toUpperCase()} indicator · {result.source}
              </p>
            </div>
            <Badge value={result.reputation} />
          </div>
          <div className="intel-result-grid">
            <div>
              <span>Service’s reputation score</span>
              <strong>
                {result.confidence === null
                  ? "Not available"
                  : `${result.confidence} / 100`}
              </strong>
            </div>
            <div>
              <span>First saved</span>
              <strong>{time(result.first_seen, true)}</strong>
            </div>
            <div>
              <span>Last checked</span>
              <strong>{time(result.last_seen, true)}</strong>
            </div>
          </div>
          <div className="notice">
            <ShieldQuestion size={20} />
            <p>
              {String(
                result.metadata.notice ??
                  "A reputation score is not proof of an attack. Check it against the activity records.",
              )}
            </p>
          </div>
          <h3>Information from the service</h3>
          <dl className="intel-metadata">
            {Object.entries(result.metadata)
              .filter(([key]) => key !== "notice")
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{value === null ? "Not available" : String(value)}</dd>
                </div>
              ))}
          </dl>
        </section>
      ) : (
        !busy && (
          <div className="intel-principles">
            <Shield size={30} />
            <h2>A check is not a verdict</h2>
            <p>
              Addresses can belong to shared services or legitimate tools. Check what actually happened before deciding whether there is a problem. This tool never blocks, scans, or contacts the address you enter.
            </p>
            <div>
              <span>Information source shown</span>
              <span>Results saved for 6 hours</span>
              <span>No automatic actions</span>
            </div>
          </div>
        )
      )}
    </>
  );
}
