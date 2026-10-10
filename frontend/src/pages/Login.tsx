import { useState } from "react";
import {
  ArrowRight,
  Fingerprint,
  LockKeyhole,
  Pause,
  Play,
  ScanLine,
  ShieldCheck,
} from "lucide-react";
import { Navigate } from "react-router-dom";
import { Brand, ErrorBox } from "../components/ui";
import { useAuth } from "../store/AuthContext";
import { errorMessage } from "../services/api";
import { ShapeGrid } from "../components/react-bits/ShapeGrid";
import { SignalFlow } from "../components/SignalFlow";
import { useReducedMotion } from "../hooks/useReducedMotion";

export function LoginPage() {
  const { user, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [backgroundPaused, setBackgroundPaused] = useState(false);
  const reducedMotion = useReducedMotion();
  if (user) return <Navigate to="/dashboard" replace />;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <section className="login-story">
        <ShapeGrid paused={backgroundPaused} />
        <div className="login-story-top">
          <Brand />
          <button
            type="button"
            className="login-motion-toggle"
            aria-label={
              reducedMotion
                ? "Background motion disabled by your preference"
                : backgroundPaused
                  ? "Resume background animation"
                  : "Pause background animation"
            }
            aria-pressed={backgroundPaused}
            disabled={reducedMotion}
            onClick={() => setBackgroundPaused((value) => !value)}
          >
            {backgroundPaused || reducedMotion ? (
              <Play size={13} />
            ) : (
              <Pause size={13} />
            )}
            <span>
              {reducedMotion
                ? "Reduced motion"
                : backgroundPaused
                  ? "Motion paused"
                  : "Pause motion"}
            </span>
          </button>
        </div>
        <div className="login-story-main">
          <h1>
            Know what happened.
            <br /> Know what to check.
          </h1>
          <p>
            Bring activity from your computers, websites, and apps into one place.
            See unusual patterns and understand what needs a closer look.
          </p>
          <SignalFlow />
          <div className="login-capabilities">
            <span>
              <ScanLine size={19} />
              Alerts with context
            </span>
            <span>
              <Fingerprint size={19} />
              Connected investigations
            </span>
            <span>
              <LockKeyhole size={19} />
              Advice, not automatic actions
            </span>
          </div>
        </div>
        <p className="login-story-footer">
          <span className="status-light online" />
          Built for learning. Designed for investigation.
        </p>
      </section>
      <section className="login-form-section">
        <div className="login-form-wrap">
          <div className="login-form-title">
            <span className="form-shield">
              <ShieldCheck size={27} />
            </span>
            <h2>Welcome to SentinelX</h2>
            <p>
              Sign in to see your systems’ activity and alerts.
            </p>
          </div>
          <ErrorBox message={error} />
          <form onSubmit={submit}>
            <label>
              Email address
              <input
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                placeholder="Enter your password"
                minLength={1}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <button className="button primary login-submit" disabled={busy}>
              {busy ? "Please wait…" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="login-switch">
            Need access? Ask your workspace administrator to create an account.
          </p>
          <div className="login-security">
            <LockKeyhole size={15} />
            <span>
              Your access is set by your administrator.
              <br />
              SentinelX never changes your systems automatically.
            </span>
          </div>
          <p className="dev-credential-hint">
            Local setup: use the administrator email and generated password from
            your <code>.env</code> file.
          </p>
        </div>
      </section>
    </div>
  );
}
