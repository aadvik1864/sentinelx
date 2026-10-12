import { useState } from "react";
import { api, applySession, errorMessage } from "../services/api";
import { useAuth } from "../store/AuthContext";
import { Brand, ErrorBox } from "./ui";
import { AddPasskey } from "./Passkeys";

export function AuthenticatorSetup() {
  const [password, setPassword] = useState("");
  const [secret, setSecret] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (!secret) {
        const { data } = await api.post<{ secret: string }>("/auth/mfa/setup", { password });
        setSecret(data.secret);
        setPassword("");
      } else {
        const { data } = await api.post<{ recovery_codes: string[] }>("/auth/mfa/enable", { code });
        setCodes(data.recovery_codes);
        setSecret("");
        setCode("");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  if (codes.length) return (
    <div className="stack-form">
      <h2>Save your recovery codes</h2>
      <p>Keep these in your password manager. Each code works once if you lose your authenticator. They will not be shown again.</p>
      <pre className="recovery-codes" aria-label="Recovery codes">{codes.join("\n")}</pre>
      <label className="checkbox-label"><input type="checkbox" checked={saved} onChange={(event) => setSaved(event.target.checked)} />I saved my recovery codes privately.</label>
      <button className="button primary" disabled={!saved} onClick={() => applySession(null)}>Continue to sign in</button>
      <p className="muted">All previous sessions have been revoked. Wait for a fresh authenticator code, then sign in again.</p>
    </div>
  );
  return (
    <form className="stack-form" onSubmit={submit}>
      <h2>Add an authenticator</h2>
      <p>Use a TOTP authenticator app for two-step sign-in. Setup expires after 10 minutes.</p>
      {!secret ? <label>Current password<input type="password" autoComplete="current-password" value={password} maxLength={128} required disabled={busy} onChange={(event) => setPassword(event.target.value)} /></label> : <>
        <p>In your app, add a time-based account named SentinelX and enter this key:</p>
        <code className="enrollment-secret">{secret}</code>
        <p className="muted">Do not share this key or put it in investigation notes.</p>
        <label>Six-digit code<input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" minLength={6} maxLength={6} value={code} required disabled={busy} onChange={(event) => setCode(event.target.value)} /></label>
      </>}
      <ErrorBox message={error} />
      <button className="button primary" disabled={busy}>{busy ? "Please wait…" : secret ? "Enable two-step sign-in" : "Start authenticator setup"}</button>
      {secret && <button type="button" className="button secondary" disabled={busy} onClick={() => { setSecret(""); setCode(""); setError(null); }}>Start setup again</button>}
    </form>
  );
}

export function AccountSecuritySetup() {
  const { user, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [method, setMethod] = useState("totp");
  async function change(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/change-password", { current_password: currentPassword, new_password: newPassword });
      applySession(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return <main className="account-security-screen">
    <Brand />
    <section className="panel account-security-panel">
      <h1>Secure your account</h1>
      <p className="muted">Workspace activity stays locked until you complete account setup.</p>
      {user?.must_change_password ? <form className="stack-form" onSubmit={change}>
        <h2>Replace your starter password</h2>
        <p>Choose your own password with at least 12 characters. You will sign in again afterward.</p>
        <label>Starter password<input type="password" autoComplete="current-password" value={currentPassword} maxLength={128} required disabled={busy} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
        <label>New password<input type="password" autoComplete="new-password" value={newPassword} minLength={12} maxLength={128} required disabled={busy} onChange={(event) => setNewPassword(event.target.value)} /></label>
        <ErrorBox message={error} />
        <button className="button primary" disabled={busy}>{busy ? "Changing password…" : "Change password and sign out"}</button>
      </form> : <>
        <label>Sign-in protection<select value={method} onChange={(event) => setMethod(event.target.value)}><option value="totp">Authenticator app</option><option value="passkey">Passkey or security key</option></select></label>
        {method === "totp" ? <AuthenticatorSetup /> : <AddPasskey />}
      </>}
    </section>
    <button className="button secondary" onClick={() => { logout().catch((err) => setError(errorMessage(err))); }}>Sign out</button>
    <ErrorBox message={!user?.must_change_password ? error : null} />
  </main>;
}
