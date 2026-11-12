// Sign-in: Supabase Auth email/password, then TOTP MFA when the account has a verified factor or the
// API requires it (administrators: the API rejects tokens below aal2). Every sign-in failure shows the
// same generic message; nothing about the account (exists, locked, unconfirmed) is revealed.
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { homePathFor } from "../components/RoleGuard";
import { ErrorMessage } from "../components/ErrorMessage";
import { PasswordField } from "../components/PasswordField";
import { supabase } from "../lib/supabase";
import { api, ApiError } from "../services/api";
import { registerSession } from "../auth/session";
import { canonicalEmail, GENERIC_LOGIN_ERROR, GENERIC_MFA_ERROR } from "../lib/authPolicy";

type Step = { kind: "password" } | { kind: "verify"; factorId: string } | { kind: "enroll"; factorId: string; qr: string; secret: string };

const MFA_CODE = /^\d{6}$/;

export default function Login() {
  const { signIn, signOut, refreshMe, status, me, error: profileError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<Step>({ kind: "password" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Not while a sign-in is in progress: the MFA decision must be made before leaving this screen.
  if (status === "signed_in" && me && step.kind === "password" && !busy) return <Navigate to={homePathFor(me.permissions)} replace />;

  async function mfaRequiredByApi(): Promise<boolean> {
    try {
      await api.me();
      return false;
    } catch (err) {
      return err instanceof ApiError && err.status === 403;
    }
  }

  async function nextStepAfterPassword(): Promise<Step | null> {
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (!aal || aal.currentLevel === "aal2") return null;
    const { data: factors } = await supabase.auth.mfa.listFactors();
    const verified = factors?.totp?.find((f) => f.status === "verified");
    if (verified) return { kind: "verify", factorId: verified.id };
    if (!(await mfaRequiredByApi())) return null;
    // Remove abandoned, never-verified enrolments before starting a new one.
    for (const f of factors?.all ?? []) {
      if (f.status !== "verified") await supabase.auth.mfa.unenroll({ factorId: f.id });
    }
    const { data: enrolled, error: enrollError } = await supabase.auth.mfa.enroll({ factorType: "totp", friendlyName: "ACME Clinical" });
    if (enrollError || !enrolled) throw new Error("enroll_failed");
    return { kind: "enroll", factorId: enrolled.id, qr: enrolled.totp.qr_code, secret: enrolled.totp.secret };
  }

  async function onSubmitPassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let signedIn = false;
    try {
      await signIn(canonicalEmail(email), password);
      signedIn = true;
      const next = await nextStepAfterPassword();
      if (next) setStep(next);
    } catch {
      if (signedIn) {
        await signOut(); // never leave a single-factor session behind when MFA could not start
        setError("Two-step verification could not be started. Please try again.");
      } else {
        setError(GENERIC_LOGIN_ERROR);
      }
    } finally {
      setPassword("");
      setBusy(false);
    }
  }

  async function onSubmitCode(e: FormEvent) {
    e.preventDefault();
    if (step.kind === "password") return;
    if (!MFA_CODE.test(code)) return setError(GENERIC_MFA_ERROR);
    setBusy(true);
    setError(null);
    const { error: verifyError } = await supabase.auth.mfa.challengeAndVerify({ factorId: step.factorId, code });
    setCode("");
    if (verifyError) {
      setBusy(false);
      setError(GENERIC_MFA_ERROR);
      return;
    }
    try {
      await registerSession(); // registers the (now two-factor) session with the API
    } catch {
      // bookkeeping only
    }
    await refreshMe();
    setBusy(false);
    setStep({ kind: "password" });
  }

  async function cancelMfa() {
    setCode("");
    setError(null);
    setStep({ kind: "password" });
    await signOut();
  }

  if (step.kind !== "password") {
    return (
      <main className="auth-page">
        <form className="card auth-card" onSubmit={onSubmitCode} noValidate>
          <h1>Two-step verification</h1>
          {step.kind === "enroll" ? (
            <>
              <p className="muted">
                Your role requires an authenticator app. Scan this code with your authenticator app, then enter the 6-digit code it shows.
              </p>
              <img src={step.qr} alt="QR code for your authenticator app" width={180} height={180} />
              <details>
                <summary>Can't scan the code?</summary>
                <p className="small">
                  Enter this key in your app: <code>{step.secret}</code>
                </p>
              </details>
            </>
          ) : (
            <p className="muted">Enter the 6-digit code from your authenticator app.</p>
          )}
          <ErrorMessage error={error} />
          <label>
            Authentication code
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              required
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
          </label>
          <button type="submit" disabled={busy || code.length !== 6}>
            {busy ? "Verifying…" : "Verify"}
          </button>
          <button type="button" className="secondary" onClick={() => void cancelMfa()}>
            Cancel and sign out
          </button>
        </form>
      </main>
    );
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={onSubmitPassword} noValidate>
        <h1>ACME Clinical</h1>
        <p className="muted">Sign in with your personal hospital account.</p>
        <ErrorMessage error={error ?? (status === "signed_out" ? profileError : null)} />
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            autoCapitalize="off"
            spellCheck={false}
            required
            maxLength={254}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <PasswordField label="Password" autoComplete="current-password" value={password} onChange={setPassword} />
        <button type="submit" disabled={busy || !email || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <Link to="/forgot-password">Forgot your password?</Link>
        <p className="muted small">Accounts are personal. Never share your password or sign in for someone else.</p>
      </form>
    </main>
  );
}
