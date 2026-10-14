import { useState } from "react";
import { ArrowUpRight, LockKeyhole, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { Empty, ErrorBox, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { AI_REQUEST_TIMEOUT, api, errorMessage } from "../services/api";
import type { Analysis, Incident, Page, SystemInfo } from "../types";
import { assistantModeLabel } from "../utils/ai";

export function AssistantPage() {
  const { data: incidents, error: incidentsError, reload } = useResource<Page<Incident>>(
    "/incidents?limit=100",
  );
  const { data: system } = useResource<SystemInfo>("/system");
  const [selected, setSelected] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function analyze(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setAnalysis(null);
    try {
      const { data } = await api.post<Analysis>(
        "/ai/analyze-incident", { incident_id: Number(selected) },
        { timeout: AI_REQUEST_TIMEOUT },
      );
      setAnalysis(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Assistant"
        description="Understand an investigation and get suggestions for what to check next."
        actions={
          <span className="assistant-mode">
            <Sparkles size={16} />
            {assistantModeLabel(system)}
          </span>
        }
      />
      <div className="assistant-layout">
        <section className="panel assistant-workspace">
          <div className="panel-heading">
            <div>
              <h2>Choose an investigation</h2>
              <p>
                The explanation uses records already saved in this workspace.
              </p>
            </div>
            <Sparkles size={21} />
          </div>
          <form className="assistant-selector" onSubmit={analyze}>
            <label htmlFor="assistant-incident">Investigation</label>
            <div>
              <select
                id="assistant-incident"
                value={selected}
                onChange={(event) => {
                  setSelected(event.target.value);
                  setAnalysis(null);
                }}
                disabled={busy}
                required
              >
                <option value="">Choose an investigation…</option>
                {incidents?.items.map((incident) => (
                  <option value={incident.id} key={incident.id}>
                    {incident.reference}: {incident.title}
                  </option>
                ))}
              </select>
              <button className="button primary" disabled={busy || !selected}>
                <Sparkles size={16} />
                Explain
              </button>
            </div>
            {selected && (
              <Link className="text-link" to={`/incidents/${selected}`}>
                Open investigation
                <ArrowUpRight size={14} />
              </Link>
            )}
          </form>
          <ErrorBox message={incidentsError} retry={reload} />
          <ErrorBox message={error} />
          {busy ? (
            <Loading label="Reviewing the activity records… Local AI may take a couple of minutes." />
          ) : analysis ? (
            <div className="assistant-output">
              <AnalysisPanel analysis={analysis} />
            </div>
          ) : (
            <Empty
              title={incidents?.total === 0 ? "No investigations to explain yet" : "Start with an investigation"}
              description="Choose one above to see what happened, possible explanations, and suggested checks. The assistant reviews a limited sample, not every record."
            />
          )}
        </section>
        <aside className="assistant-sidebar">
          <div className="assistant-safety">
            <LockKeyhole size={25} />
            <h2>You stay in control</h2>
            <p>
              The assistant gives advice only. It cannot block addresses, disable accounts, or change your systems.
            </p>
            <ul>
              <li>Check the original activity records</li>
              <li>Consider normal explanations too</li>
              <li>Ask an authorized person before making changes</li>
            </ul>
          </div>
          <div className="panel context-panel">
            <h2>About this mode</h2>
            <p className="muted">
              {!system ? "Reading the assistant setup…"
                : system.ai_provider === "ollama"
                  ? "A free local AI model writes the explanation on this server. It may get things wrong, so check its claims."
                  : system.ai_provider === "llm"
                    ? "An online AI service writes the explanation. It may get things wrong, so check its claims."
                    : "No generative AI is connected. The explanation is a rule-based summary of saved activity."}
            </p>
            {system?.ai_model && <p className="muted">Model: {system.ai_model}</p>}
            <p className="muted">
              {system?.ai_provider === "ollama"
                ? "The selected records stay on this installation; no cloud AI receives them. Explanations run only when requested and may take a couple of minutes."
                : "Enabling online AI sends some investigation details to that provider. The server administrator should review its privacy policy first."}
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
