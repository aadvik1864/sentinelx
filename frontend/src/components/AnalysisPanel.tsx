import {
  BookOpen,
  CircleHelp,
  LockKeyhole,
  ScanLine,
  Sparkles,
} from "lucide-react";
import type { Analysis } from "../types";
import { humanize } from "./ui";

export function AnalysisPanel({ analysis }: { analysis: Analysis }) {
  return (
    <div className="analysis-result">
      <div className="analysis-mode">
        <Sparkles size={17} />
        <span>
          {analysis.mode === "llm"
            ? `${analysis.provider === "ollama" ? "Local AI" : "AI"} analysis · ${analysis.model}`
            : "Offline review · no online AI"}
        </span>
        <span className="confidence">
          {humanize(analysis.confidence)} confidence
        </span>
      </div>
      <div className="analysis-summary">
        <h3>What happened</h3>
        <p>{analysis.summary}</p>
        <h3>What it could mean</h3>
        <p>{analysis.likely_attack}</p>
      </div>
      <section>
        <h3>
          <ScanLine size={17} />
          Records behind this explanation
        </h3>
        <ul>
          {analysis.evidence.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </section>
      <div className="analysis-columns">
        <section>
          <h3>
            <BookOpen size={17} />
            What to check next
          </h3>
          <ol>
            {analysis.recommended_investigation.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ol>
        </section>
        <section>
          <h3>
            <LockKeyhole size={17} />
            Protective steps to consider
          </h3>
          <ol>
            {analysis.recommended_containment.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ol>
        </section>
      </div>
      <section>
        <h3>
          <CircleHelp size={17} />
          Could this be normal activity?
        </h3>
        <ul>
          {analysis.false_positive_indicators.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      </section>
      <div className="analysis-meta">
        <span>
          Systems mentioned:{" "}
          {analysis.affected_assets.join(", ") || "Not established"}
        </span>
        <span>
          Attack pattern references: {analysis.mitre_techniques.join(", ") || "None recorded"}
        </span>
      </div>
      <div className="notice">
        <LockKeyhole size={16} />
        <p>
          {analysis.notice} Verify the advice first. Any protective action must be taken by an authorized person; SentinelX does not take action for you.
        </p>
      </div>
    </div>
  );
}
