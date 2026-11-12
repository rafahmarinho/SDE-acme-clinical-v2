// Set a new password, in one of two modes:
// * recovery / invitation: the user arrived from a single-use Supabase e-mail link (short-lived session);
// * change: a signed-in user changes their password and MUST re-enter the current one first (T3). The
//   current password is verified without replacing the session, then updateUser also sends it
//   (current_password) and Supabase "secure password change" adds reauthentication for old sessions.
// The new password must satisfy the policy (min length from Settings, never below the platform floor).
// After any change every session is signed out.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { api } from "../services/api";
import { ErrorMessage } from "../components/ErrorMessage";
import { PasswordField } from "../components/PasswordField";
import { contextWords, MAX_PASSWORD_LENGTH, passwordProblems, passwordRules, PLATFORM_MIN_LENGTH } from "../lib/authPolicy";
import { verifyCurrentPassword } from "../lib/reauth";
import { performLogout } from "../auth/session";

type Mode = "checking" | "recovery" | "change" | "invalid";

function arrivedFromEmailLink(): boolean {
  const { search, hash } = window.location;
  return /[?&]code=/.test(search) || /type=(recovery|invite)/.test(hash) || /access_token=/.test(hash);
}

export default function ResetPassword() {
  const navigate = useNavigate();
  const fromLink = useRef(arrivedFromEmailLink());
  const [mode, setMode] = useState<Mode>("checking");
  const [email, setEmail] = useState<string | null>(null);
  const [minLength, setMinLength] = useState(PLATFORM_MIN_LENGTH);
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    let active = true;
    // detectSessionInUrl exchanges the PKCE code from the recovery link for a short-lived session.
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (!active) return;
      if (event === "PASSWORD_RECOVERY" || (session && event === "SIGNED_IN" && fromLink.current)) {
        setEmail(session?.user.email ?? null);
        setMode("recovery");
      }
    });
    void supabase.auth.getSession().then(({ data }) => {
      if (!active || !data.session) return;
      setEmail(data.session.user.email ?? null);
      setMode((m) => (m !== "checking" ? m : fromLink.current ? "recovery" : "change"));
    });
    const t = window.setTimeout(() => setMode((m) => (m === "checking" ? "invalid" : m)), 4000);
    return () => {
      active = false;
      window.clearTimeout(t);
      sub.subscription.unsubscribe();
    };
  }, []);

  // The administrator-configured minimum (Settings > Security). Supabase enforces the platform floor.
  useEffect(() => {
    if (mode !== "recovery" && mode !== "change") return;
    let active = true;
    api
      .securitySettings()
      .then((s) => active && setMinLength(Math.max(PLATFORM_MIN_LENGTH, s.password_min_length)))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [mode]);

  function clearFields() {
    setCurrent("");
    setPassword("");
    setConfirm("");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const problems = passwordProblems(password, minLength, contextWords(email));
    if (problems.length) return setError(problems.join(" "));
    if (password !== confirm) return setError("The passwords do not match.");
    if (mode === "change" && (!current || current === password)) {
      return setError(current ? "Choose a password different from the current one." : "Enter your current password.");
    }
    setBusy(true);
    try {
      if (mode === "change") {
        if (!email || !(await verifyCurrentPassword(email, current))) {
          setError("The current password is incorrect.");
          return;
        }
      }
      const { error: updateError } = await supabase.auth.updateUser(
        mode === "change" ? { password, current_password: current } : { password },
      );
      if (updateError) {
        setError(
          mode === "change"
            ? "The password could not be changed. It may not meet the policy, or you need to sign in again."
            : "The password could not be changed. The link may have expired or the password does not meet the policy.",
        );
        return;
      }
      setDone(true);
      // End every session after a password change.
      if (mode === "change") {
        // Registered API session: revoke all sessions server-side and wipe this browser.
        await performLogout({ reason: "user", scope: "global", navigate: () => window.setTimeout(() => navigate("/login", { replace: true }), 2500) });
      } else {
        await supabase.auth.signOut({ scope: "global" });
        window.setTimeout(() => navigate("/login", { replace: true }), 2500);
      }
    } finally {
      clearFields();
      setBusy(false);
    }
  }

  const title = mode === "change" ? "Change your password" : "Choose a new password";
  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={onSubmit} noValidate>
        <h1>{title}</h1>
        {done ? (
          <p role="status">Your password has been changed. Please sign in with your new password.</p>
        ) : mode === "invalid" ? (
          <p role="alert">This reset link is invalid or has expired. Request a new one.</p>
        ) : mode === "checking" ? (
          <p role="status">Verifying your reset link…</p>
        ) : (
          <>
            <ErrorMessage error={error} />
            {mode === "change" && (
              <PasswordField label="Current password" autoComplete="current-password" maxLength={MAX_PASSWORD_LENGTH} value={current} onChange={setCurrent} />
            )}
            <PasswordField
              label="New password"
              autoComplete="new-password"
              minLength={minLength}
              maxLength={MAX_PASSWORD_LENGTH}
              describedBy="password-rules"
              value={password}
              onChange={setPassword}
            />
            <PasswordField
              label="Confirm new password"
              autoComplete="new-password"
              minLength={minLength}
              maxLength={MAX_PASSWORD_LENGTH}
              value={confirm}
              onChange={setConfirm}
            />
            <div id="password-rules" className="muted small">
              Use:
              <ul>
                {passwordRules(minLength).map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              Longer passphrases are encouraged.
            </div>
            <button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Change password"}
            </button>
          </>
        )}
        {mode === "change" ? (
          <Link to="/profile">Cancel</Link>
        ) : (
          <Link to={mode === "invalid" ? "/forgot-password" : "/login"}>{mode === "invalid" ? "Request a new link" : "Back to sign in"}</Link>
        )}
      </form>
    </main>
  );
}
