import { useState } from "react";
import { AuthenticatorSetup } from "../components/AccountSecurity";
import { KeyRound, LockKeyhole, Settings, UserPlus, Users } from "lucide-react";
import {
  Badge,
  ErrorBox,
  Modal,
  PageHeader,
  humanize,
  time,
  useToast,
} from "../components/ui";
import { useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { api, applySession, errorMessage, reconcile } from "../services/api";
import { roleLabels } from "../utils/labels";
import { assistantModeLabel } from "../utils/ai";
import type { Page, SystemInfo, User } from "../types";

interface AuditEntry {
  id: number;
  user_id: number | null;
  action: string;
  resource: string;
  resource_id: string;
  timestamp: string;
  ip_address: string | null;
}

function AddPerson({ close, added }: { close: () => void; added: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [trusted, setTrusted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!trusted || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/users", { name: name.trim(), email, password });
      setPassword("");
      added();
    } catch (err) {
      setError(errorMessage(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Add a person"
      onClose={() => { if (!busy) close(); }}
    >
      <form className="stack-form" onSubmit={submit}>
        <p className="muted">
          Only add someone you trust. Read-only access includes this workspace’s
          alerts, investigation evidence, and notes—not a private personal workspace.
        </p>
        <label>
          Full name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            minLength={2}
            maxLength={100}
            required
            disabled={busy}
          />
        </label>
        <label>
          Email address
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="off"
            required
            disabled={busy}
          />
        </label>
        <label>
          Starter password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
            minLength={12}
            maxLength={128}
            required
            disabled={busy}
          />
        </label>
        <p className="muted">
          Verify the recipient and share the starter password privately, not in investigation notes.
          They must replace it before viewing the workspace. No email or invitation is sent.
        </p>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={trusted}
            onChange={(event) => setTrusted(event.target.checked)}
            required
            disabled={busy}
          />
          I trust this person to read this workspace’s security information.
        </label>
        <ErrorBox message={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button className="button primary" disabled={busy || !trusted}>
            {busy ? "Creating account…" : "Create read-only account"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  const admin = user?.role === "ADMIN";
  const { data: system } = useResource<SystemInfo>("/system");
  const {
    data: users,
    reload: reloadUsers,
    error: usersError,
  } = useResource<{ items: User[] }>(admin ? "/users" : null);
  const { data: audit, error: auditError } = useResource<Page<AuditEntry>>(
    admin ? "/audit-logs?limit=25" : null,
  );
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const notify = useToast();
  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      applySession(null);
      notify("Password changed. You’ve been signed out on all devices. Sign in again.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function setRole(row: User, role: string) {
    setBusy(true);
    try {
      await api.patch(`/users/${row.id}`, { role });
      reloadUsers();
      reconcile();
      notify("Access updated. The user’s previous sign-in permissions no longer apply.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  async function setAccess(row: User) {
    setBusy(true);
    try {
      await api.patch(`/users/${row.id}/access`, { disabled: !row.disabled });
      reloadUsers();
      reconcile();
      notify(row.disabled ? "Account enabled. Previous sessions remain revoked." : "Account disabled. All sessions have been revoked.");
    } catch (err) {
      notify(errorMessage(err), true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Settings"
        description="Manage your account and who can use this workspace."
      />
      <div className="settings-grid">
        <section className="panel settings-panel">
          <h2>
            <Users size={18} />
            Your profile
          </h2>
          <dl className="detail-grid">
            <dt>Name</dt>
            <dd>{user?.name}</dd>
            <dt>Email</dt>
            <dd>{user?.email}</dd>
            <dt>Role</dt>
            <dd>
              <Badge value={user?.role ?? "VIEWER"} />
            </dd>
          </dl>
          <p className="muted">
            {user?.role === "VIEWER"
              ? "You can view the overview, alerts, and investigations without changing them."
              : user?.role === "ADMIN" ? "You can investigate alerts, manage connections, and choose who has access." : "You can investigate alerts. Only an administrator can change connections, rules, and user access."}
          </p>
        </section>
        <section className="panel settings-panel">
          <h2>
            <Settings size={18} />
            Workspace setup
          </h2>
          <dl className="detail-grid">
            <dt>Version</dt>
            <dd>{system?.version}</dd>
            <dt>Environment</dt>
            <dd>{system?.environment}</dd>
            <dt>Assistant</dt>
            <dd>
              {assistantModeLabel(system)}
              {system?.ai_model && <small className="table-description">{system.ai_model}</small>}
            </dd>
             <dt>Address checks</dt>
             <dd>{system?.threat_intel_provider === "abuseipdb" ? "AbuseIPDB configured" : "No external service configured"}</dd>
          </dl>
          <p className="muted">
            The server administrator configures local AI, online services, and security settings on the server. Private keys are not shown here.
          </p>
        </section>
        <section className="panel settings-panel password-panel">
          <h2>
            <KeyRound size={18} />
            Change password
          </h2>
          <form className="stack-form" onSubmit={changePassword}>
            <div className="form-row">
              <label>
                Current password
                <input
                  type="password"
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  maxLength={128}
                  required
                />
              </label>
              <label>
                New password
                <input
                  type="password"
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  minLength={12}
                  maxLength={128}
                  required
                />
              </label>
            </div>
            <ErrorBox message={error} />
            <div className="password-action">
              <span>
                <LockKeyhole size={15} />
                At least 12 characters. Changing it signs you out on every device.
              </span>
              <button className="button primary" disabled={busy}>
                Change password
              </button>
            </div>
          </form>
        </section>
        <section className="panel settings-panel">
          {user?.mfa_enabled ? <><h2>Two-step sign-in</h2><p>Your authenticator is enabled. Keep your single-use recovery codes in your password manager.</p></> : <AuthenticatorSetup />}
        </section>
      </div>
      {admin && (
        <>
          <section className="panel settings-users">
            <div className="panel-heading">
              <div>
                <h2>User access</h2>
                <p>
                  Only administrators can add people. New accounts start with read-only access to this shared workspace.
                </p>
              </div>
              <button className="button secondary" onClick={() => setAdding(true)}>
                <UserPlus size={16} /> Add a person
              </button>
            </div>
            <ErrorBox message={usersError} retry={reloadUsers} />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Registered</th>
                    <th>Access</th>
                  </tr>
                </thead>
                <tbody>
                  {users?.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <strong>{row.name}</strong>
                        {row.id === user?.id && (
                          <small className="table-description">You</small>
                        )}
                      </td>
                      <td>{row.email}</td>
                      <td>
                        <select
                          aria-label={`Role for ${row.name}`}
                          value={row.role}
                          disabled={busy || row.id === user?.id}
                          onChange={(event) => setRole(row, event.target.value)}
                        >
                          {["ADMIN", "ANALYST", "VIEWER"].map((role) => (
                            <option key={role} value={role}>
                               {roleLabels[role]}
                            </option>
                          ))}
                        </select>
                      </td>
                       <td className="muted">{time(row.created_at, true)}</td>
                       <td><button className="button secondary" disabled={busy || row.id === user?.id} onClick={() => setAccess(row)}>{row.disabled ? "Enable account" : "Disable account"}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {adding && (
            <AddPerson
              close={() => setAdding(false)}
              added={() => {
                setAdding(false);
                reloadUsers();
                reconcile();
                notify("Read-only account created. Share its starter password privately.");
              }}
            />
          )}
          <section className="panel settings-audit">
            <div className="panel-heading">
              <div>
                 <h2>Recent account and settings changes</h2>
                <p>
                  Most recent 25 sensitive actions. Log content is not included.
                </p>
              </div>
              <LockKeyhole size={19} />
            </div>
            <ErrorBox message={auditError} />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>What changed</th>
                    <th>Who</th>
                    <th>Client address</th>
                  </tr>
                </thead>
                <tbody>
                  {audit?.items.map((entry) => (
                    <tr key={entry.id}>
                      <td className="mono">{time(entry.timestamp, true)}</td>
                      <td>{humanize(entry.action.toLowerCase())}</td>
                      <td>
                        <code>
                          {entry.resource}:{entry.resource_id}
                        </code>
                      </td>
                      <td>
                        {entry.user_id
                          ? `User #${entry.user_id}`
                          : "Unauthenticated"}
                      </td>
                      <td>
                        <code>{entry.ip_address ?? "—"}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  );
}
