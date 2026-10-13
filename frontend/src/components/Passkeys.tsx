import { useState } from "react";
import { startRegistration } from "@simplewebauthn/browser";
import type { PublicKeyCredentialCreationOptionsJSON } from "@simplewebauthn/browser";
import { api, applySession, errorMessage } from "../services/api";
import { useResource } from "../hooks/useResource";
import { useAuth } from "../store/AuthContext";
import { ErrorBox, time } from "./ui";

interface RegistrationOptions {
  challenge_id: string;
  options: PublicKeyCredentialCreationOptionsJSON;
}

interface EnrolledPasskey {
  id: number;
  name: string;
  created_at: string;
}

export function AddPasskey() {
  const { completeEnrollment } = useAuth();
  const [password, setPassword] = useState("");
  const [name, setName] = useState("My passkey");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post<RegistrationOptions>(
        "/auth/passkeys/register/options",
        { password },
      );
      setPassword("");
      const credential = await startRegistration({ optionsJSON: data.options });
      const response = await api.post<{ recovery_codes: string[] }>(
        "/auth/passkeys/register/verify",
        { challenge_id: data.challenge_id, credential, name },
      );
      completeEnrollment("passkey", response.data.recovery_codes);
    } catch (err) {
      setPassword("");
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={add}>
      <h2>Add a passkey</h2>
      <p>
        Use a security key or your device’s verified passkey. You still enter your
        password at sign-in. The browser requires your device PIN or biometric
        verification.
      </p>
      <label>
        Passkey name
        <input
          value={name}
          required
          maxLength={100}
          disabled={busy}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        Current password for passkey
        <input
          type="password"
          autoComplete="current-password"
          value={password}
          required
          maxLength={128}
          disabled={busy}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <ErrorBox message={error} />
      <button className="button primary" disabled={busy}>
        {busy ? "Waiting for your device…" : "Add passkey"}
      </button>
    </form>
  );
}

export function PasskeySecurity() {
  const { data, error, reload } = useResource<{ items: EnrolledPasskey[] }>(
    "/auth/passkeys",
  );
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  async function remove(id: number) {
    setBusy(true);
    setRemoveError(null);
    try {
      await api.post(`/auth/passkeys/${id}/remove`, { password });
      applySession(null);
    } catch (err) {
      setRemoveError(errorMessage(err));
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <>
      <AddPasskey />
      <ErrorBox message={error} retry={reload} />
      {!!data?.items.length && (
        <details className="disclosure">
          <summary>Manage enrolled passkeys</summary>
          <p>
            Keep at least one sign-in factor. Removing a passkey signs you out
            everywhere.
          </p>
          <label>
            Removal password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              maxLength={128}
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {data.items.map((passkey) => (
            <p key={passkey.id}>
              {passkey.name} · {time(passkey.created_at)}{" "}
              <button
                className="text-button"
                disabled={busy || !password}
                onClick={() => remove(passkey.id)}
              >
                Remove {passkey.name}
              </button>
            </p>
          ))}
          <ErrorBox message={removeError} />
        </details>
      )}
    </>
  );
}
