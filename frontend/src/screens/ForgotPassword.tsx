import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { canonicalEmail, GENERIC_RESET_MESSAGE as NEUTRAL_MESSAGE } from "../lib/authPolicy";

// Account recovery: a single-use, one-hour Supabase recovery link (no temporary passwords, no security
// questions). The message, UI state and browser storage are identical for every address;
// Supabase Auth rate limits ([auth.rate_limit] email_sent) cap the volume.

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      // The outcome is intentionally ignored: the same message is shown whether or not the account exists.
      await supabase.auth.resetPasswordForEmail(canonicalEmail(email), {
        redirectTo: `${window.location.origin}/reset-password`,
      });
    } catch {
      // swallow: never reveal account existence or rate-limit details
    } finally {
      setBusy(false);
      setSent(true);
      setEmail("");
    }
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={onSubmit}>
        <h1>Reset your password</h1>
        {sent ? (
          <p role="status">{NEUTRAL_MESSAGE}</p>
        ) : (
          <>
            <p className="muted">Enter your work email address and we will send you a reset link.</p>
            <label>
              Email
              <input type="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <button type="submit" disabled={busy || !email}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
          </>
        )}
        <Link to="/login">Back to sign in</Link>
      </form>
    </main>
  );
}
