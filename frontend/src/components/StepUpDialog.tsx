// Step-up re-authentication (T9/T83): highly sensitive API calls (staff changes, role requests, simulation
// reset, alarm-limit changes, break-glass activation) answer 401 "step_up_required" when the last
// authentication is too old. api.ts calls the handler registered here, this dialog asks the user to prove
// their identity again, and the request is retried once.
// * Accounts with a verified TOTP factor re-verify with a fresh code (keeps the session at aal2; an
//   administrator's password-only sign-in would drop to aal1 and be refused by the API).
// * Otherwise the password is re-entered (Supabase signInWithPassword refreshes the authentication time);
//   the new session is registered with the API before the retry.
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { supabase } from "../lib/supabase";
import { api, setStepUpHandler } from "../services/api";
import { useAuth } from "../auth/AuthContext";
import { GENERIC_LOGIN_ERROR, GENERIC_MFA_ERROR } from "../lib/authPolicy";
import { PasswordField } from "./PasswordField";

type Mode = { kind: "password" } | { kind: "totp"; factorId: string };

export function StepUpDialog() {
  const { me, completeMfa } = useAuth();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>({ kind: "password" });
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<{ promise: Promise<boolean>; resolve: (ok: boolean) => void } | null>(null);
  const email = me?.email ?? null;

  const finish = useCallback((ok: boolean) => {
    pending.current?.resolve(ok);
    pending.current = null;
    setOpen(false);
    setSecret("");
    setError(null);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (!email) return undefined;
    setStepUpHandler(async () => {
      if (pending.current) return pending.current.promise; // concurrent challenges share one prompt
      let resolve: (ok: boolean) => void = () => undefined;
      const promise = new Promise<boolean>((r) => {
        resolve = r;
      });
      pending.current = { promise, resolve };
      let next: Mode = { kind: "password" };
      try {
        const { data } = await supabase.auth.mfa.listFactors();
        const verified = data?.totp?.find((f) => f.status === "verified");
        if (verified) next = { kind: "totp", factorId: verified.id };
      } catch {
        /* fall back to the password */
      }
      setMode(next);
      setOpen(true);
      return promise;
    });
    return () => setStepUpHandler(null);
  }, [email]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!email || !secret) return;
    setBusy(true);
    setError(null);
    try {
      if (mode.kind === "totp") {
        if (!/^\d{6}$/.test(secret)) throw new Error(GENERIC_MFA_ERROR);
        const { error: verifyError } = await supabase.auth.mfa.challengeAndVerify({ factorId: mode.factorId, code: secret });
        if (verifyError) throw new Error(GENERIC_MFA_ERROR);
        if (completeMfa) await completeMfa();
        else await api.startSession();
      } else {
        const { error: authError } = await supabase.auth.signInWithPassword({ email, password: secret });
        if (authError) throw new Error(GENERIC_LOGIN_ERROR);
        await api.startSession(); // register the new session before the retried request
      }
      finish(true);
    } catch (err) {
      setSecret("");
      setBusy(false);
      setError(err instanceof Error && err.message ? err.message : GENERIC_LOGIN_ERROR);
    }
  }

  if (!open) return null;
  return (
    <div className="modal-backdrop">
      <form className="card confirm-box" role="dialog" aria-modal="true" aria-labelledby="step-up-title" onSubmit={submit} autoComplete="off">
        <h2 id="step-up-title">Confirm it's you</h2>
        <p>This action needs a recent sign-in. {mode.kind === "totp" ? "Enter the code from your authenticator app." : "Enter your password."}</p>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {mode.kind === "totp" ? (
          <label>
            Authentication code
            <input
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              value={secret}
              onChange={(e) => setSecret(e.target.value.replace(/\D/g, ""))}
            />
          </label>
        ) : (
          <PasswordField label="Password" autoComplete="current-password" value={secret} onChange={setSecret} />
        )}
        <div className="row">
          <button type="submit" disabled={busy || !secret}>
            {busy ? "Checking…" : "Confirm"}
          </button>
          <button type="button" className="secondary" onClick={() => finish(false)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
