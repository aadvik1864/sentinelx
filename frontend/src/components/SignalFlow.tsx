import { useId } from "react";

export function SignalFlow() {
  const glow = useId();
  return (
    <div className="signal-flow">
      <div className="signal-flow-heading">
        <span>Your systems. One clear story.</span>
        <span>Illustrative flow</span>
      </div>
      <svg
        viewBox="0 0 520 180"
        role="img"
        aria-label="Computer, website, and app activity comes together as alerts and investigations."
      >
        <defs>
          <filter id={glow} x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="5" />
          </filter>
        </defs>
        <g className="signal-paths" fill="none">
          <path d="M60 36 H158 C206 36 206 90 254 90 H289" />
          <path d="M60 90 H289" />
          <path d="M60 144 H158 C206 144 206 90 254 90 H289" />
          <path d="M341 90 H452" />
        </g>
        <g className="signal-traces" fill="none">
          <path d="M60 36 H158 C206 36 206 90 254 90 H289" />
          <path d="M60 90 H289" />
          <path d="M60 144 H158 C206 144 206 90 254 90 H289" />
          <path d="M341 90 H452" />
        </g>
        <g className="signal-source-nodes">
          {[36, 90, 144].map((y) => (
            <g key={y}>
              <circle cx="60" cy={y} r="11" />
              <circle cx="60" cy={y} r="3" />
            </g>
          ))}
        </g>
        <circle className="signal-core-glow" cx="315" cy="90" r="30" filter={`url(#${glow})`} />
        <rect className="signal-core" x="289" y="64" width="52" height="52" rx="15" />
        <path className="signal-shield" d="M315 75 L328 80 V91 C328 99 315 105 315 105 S302 99 302 91 V80 Z M309 90 L313 94 L322 85" />
        <rect className="signal-case" x="452" y="73" width="36" height="34" rx="8" />
        <path className="signal-case-detail" d="M463 83 H478 M463 90 H478 M463 97 H473" />
        <g className="signal-labels">
          <text x="85" y="27">Computer sign-ins</text>
          <text x="85" y="81">Website visits</text>
          <text x="85" y="135">App activity</text>
          <text x="315" y="144" textAnchor="middle">Spot patterns</text>
          <text x="470" y="144" textAnchor="middle">Investigate</text>
        </g>
      </svg>
    </div>
  );
}
