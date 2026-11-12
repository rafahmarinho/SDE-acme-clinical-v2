// Profile: review/correct personal data, privacy notice acknowledgement, data export and account erasure
// (skills/privacy T177/T238/T239/T740/T741/T751/T179/T240).
// * The privacy notice must be acknowledged (checkbox unchecked by default) before the profile can be
//   edited; the API enforces the same rule (409) and re-prompts when PRIVACY_NOTICE_VERSION changes.
// * Export and erasure require the current password (verified server-side, the session is not replaced).
// * The e-mail address is the sign-in identifier: changes go through Supabase Auth's confirmation e-mail.
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { request } from "../services/api";
import type { Me } from "../services/types";
import { supabase } from "../lib/supabase";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { PasswordField } from "../components/PasswordField";
import { formatDateTime, humanize } from "../lib/format";

/** Must equal PRIVACY_NOTICE_VERSION in backend/app/services/privacy.py (checked by backend tests). */
export const PRIVACY_NOTICE_VERSION = "2026-11-01";

export const PRIVACY_NOTICE = {
  purposes: [
    "Patient monitoring, alarm handling and clinical record keeping (care relationship and legal obligation).",
    "Staff authentication, access control and a tamper-evident audit trail (security and legal obligation).",
    "Device maintenance tracking (patient safety).",
    "Aggregated, de-identified ward statistics (quality improvement); small groups are suppressed.",
  ],
  categories: [
    "Staff: name, work email, role, ward assignments, sign-in times and IP address, actions you perform.",
    "Patients: pseudonymous code, name, birth year, ward and bed, vital signs, ECG, observations, alarms, files.",
  ],
  recipients: [
    "Supabase (database, authentication, file storage, realtime) - processor.",
    "Vercel (hosting of the web application and API) - processor.",
    "No data is sold or shared with third parties; external integrations are simulated.",
  ],
  retention: [
    "Readings and resolved alarms: the configured retention period (default 365 days).",
    "Patient records: until the patient's retention date after discharge, unless on legal hold.",
    "Staff accounts: pseudonymised after deactivation plus the retention period, or on an approved erasure request.",
    "Audit trail: append-only; it contains identifiers, never names or clinical free text.",
    "Backups: Supabase backups and point-in-time recovery age out deleted data within the backup window.",
  ],
  rights: [
    "Review and correct your profile on this page.",
    "Download a machine-readable copy of your personal data.",
    "Request erasure of your account. Clinical records you authored are kept with a pseudonymous author, as required by health-record law.",
    "Raise a privacy concern with your administrator or the hospital data protection officer.",
  ],
  legalBasis:
    "Employment and legal obligations for staff data; provision of health care for patient data. Processing of patient data does not rely on consent.",
};

/** The full notice, also suitable for a public /privacy route. */
export function PrivacyNotice() {
  const sections: [string, string[]][] = [
    ["Purposes", PRIVACY_NOTICE.purposes],
    ["Categories of personal data", PRIVACY_NOTICE.categories],
    ["Recipients", PRIVACY_NOTICE.recipients],
    ["Retention", PRIVACY_NOTICE.retention],
    ["Your rights", PRIVACY_NOTICE.rights],
  ];
  return (
    <article aria-label="Privacy notice">
      <p className="muted small">
        Version {PRIVACY_NOTICE_VERSION} (effective {PRIVACY_NOTICE_VERSION})
      </p>
      {sections.map(([title, items]) => (
        <section key={title}>
          <h3>{title}</h3>
          <ul>
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ))}
      <h3>Legal basis</h3>
      <p>{PRIVACY_NOTICE.legalBasis}</p>
    </article>
  );
}

type ProfileMe = Me & {
  privacy_notice_version?: string | null;
  privacy_notice_required?: boolean;
  erasure_requested_at?: string | null;
};

export function noticeRequired(me: ProfileMe): boolean {
  if (typeof me.privacy_notice_required === "boolean") return me.privacy_notice_required;
  return me.privacy_notice_version !== PRIVACY_NOTICE_VERSION;
}

function download(data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `acme-clinical-my-data-${new Date().toISOString().slice(0, 10)}.json`;
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function NoticeCard({ me, onAccepted }: { me: ProfileMe; onAccepted: () => Promise<void> }) {
  const required = noticeRequired(me);
  const [read, setRead] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function accept(e: FormEvent) {
    e.preventDefault();
    if (!read) return;
    setBusy(true);
    setError(null);
    try {
      await request<void>("POST", "/v1/me/privacy-notice", { body: { notice_version: PRIVACY_NOTICE_VERSION } });
      await onAccepted();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" id="privacy-notice">
      <h2>Privacy notice</h2>
      {required && (
        <p className="notice" role="status">
          Please read the privacy notice and acknowledge it to continue using ACME Clinical.
        </p>
      )}
      <PrivacyNotice />
      <ErrorMessage error={error} />
      {required ? (
        <form onSubmit={accept}>
          <label className="checkbox">
            <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
            I have read and understood the privacy notice (version {PRIVACY_NOTICE_VERSION}).
          </label>
          <button type="submit" disabled={!read || busy}>
            {busy ? "Saving…" : "Acknowledge privacy notice"}
          </button>
        </form>
      ) : (
        <p className="muted">
          Version {me.privacy_notice_version ?? PRIVACY_NOTICE_VERSION} acknowledged on{" "}
          {formatDateTime(me.privacy_notice_accepted_at)}.
        </p>
      )}
    </div>
  );
}

function AccountCard({ me, locked, onSaved }: { me: ProfileMe; locked: boolean; onSaved: () => Promise<void> }) {
  const [fullName, setFullName] = useState(me.full_name);
  const [newEmail, setNewEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => setFullName(me.full_name), [me.full_name]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await request<Me>("PATCH", "/v1/me", { body: { full_name: fullName.trim() } });
      await onSaved();
      setStatus("Profile updated.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function changeEmail(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      // Supabase sends a confirmation link; the address changes only after it is confirmed.
      const { error: authError } = await supabase.auth.updateUser({ email: newEmail.trim().toLowerCase() });
      if (authError) throw new Error("The e-mail change could not be started. Please try again later.");
      setNewEmail("");
      setStatus("Check the new mailbox and confirm the change. Your sign-in e-mail stays the same until then.");
    } catch (err) {
      setError(err instanceof Error ? err.message : err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Account</h2>
      <ErrorMessage error={error} />
      <dl className="facts">
        <dt>Email</dt>
        <dd>{me.email}</dd>
        <dt>Role</dt>
        <dd>{humanize(me.role)} (managed by administrators)</dd>
        <dt>Assigned wards</dt>
        <dd>{me.ward_ids.length}</dd>
        <dt>Previous sign-in</dt>
        <dd>{formatDateTime(me.previous_login_at)}</dd>
      </dl>
      <form onSubmit={save}>
        <fieldset disabled={locked || busy}>
          <label>
            Full name
            <input value={fullName} maxLength={120} required onChange={(e) => setFullName(e.target.value)} />
          </label>
          <p className="muted small" role="note">
            Your name is shown to your team and recorded with your clinical actions.
          </p>
          <button type="submit" disabled={!fullName.trim() || fullName.trim() === me.full_name}>
            Save
          </button>
        </fieldset>
      </form>
      <form onSubmit={changeEmail}>
        <fieldset disabled={locked || busy}>
          <label>
            New work e-mail
            <input type="email" value={newEmail} maxLength={254} required onChange={(e) => setNewEmail(e.target.value)} />
          </label>
          <button type="submit" className="secondary" disabled={!newEmail.trim()}>
            Change e-mail
          </button>
        </fieldset>
      </form>
      {locked && <p className="muted small">Acknowledge the privacy notice to edit your profile.</p>}
      {status && <p role="status">{status}</p>}
    </div>
  );
}

function YourDataCard({ me, onRequested }: { me: ProfileMe; onRequested: () => Promise<void> }) {
  const [exportPassword, setExportPassword] = useState("");
  const [erasePassword, setErasePassword] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function exportData(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const data = await request<unknown>("POST", "/v1/me/export", { body: { reauthentication: exportPassword } });
      download(data);
      setStatus("Your data was downloaded.");
    } catch (err) {
      setError(err);
    } finally {
      setExportPassword("");
      setBusy(false);
    }
  }

  async function requestErasure(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await request("POST", "/v1/me/erasure-request", {
        body: { reauthentication: erasePassword, confirm_text: confirmText },
      });
      await onRequested();
      setStatus("Your erasure request was sent to an administrator.");
    } catch (err) {
      setError(err);
    } finally {
      setErasePassword("");
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Your data</h2>
      <ErrorMessage error={error} />
      <p>
        Download a machine-readable (JSON) copy of your profile, ward assignments, privacy acknowledgements, sessions,
        references to records you authored and your audit trail, with information about how it is processed.
      </p>
      <form onSubmit={exportData}>
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          value={exportPassword}
          onChange={setExportPassword}
        />
        <button type="submit" className="secondary" disabled={busy || !exportPassword}>
          Export my data
        </button>
      </form>

      <div className="danger-zone">
        <h3>Delete my account</h3>
        {me.erasure_requested_at ? (
          <p role="status">
            Erasure requested on {formatDateTime(me.erasure_requested_at)}. An administrator will complete it; you will
            then be signed out and unable to sign in again.
          </p>
        ) : (
          <form onSubmit={requestErasure}>
            <p>
              ACME Clinical cannot be used without an account. When an administrator completes your request, your name,
              e-mail and sign-in history are removed and your account is closed. Clinical records you authored stay in
              the patient record with a pseudonymous author, as health-record law requires.
            </p>
            <PasswordField
              label="Current password"
              autoComplete="current-password"
              value={erasePassword}
              onChange={setErasePassword}
            />
            <label>
              Type DELETE MY ACCOUNT to confirm
              <input value={confirmText} maxLength={40} onChange={(e) => setConfirmText(e.target.value)} />
            </label>
            <button type="submit" className="danger" disabled={busy || !erasePassword || confirmText !== "DELETE MY ACCOUNT"}>
              Request account deletion
            </button>
          </form>
        )}
      </div>
      {status && <p role="status">{status}</p>}
    </div>
  );
}

export default function Profile() {
  const { me, refreshMe } = useAuth();
  if (!me) return <LoadingState />;
  const profile = me as ProfileMe;
  const locked = noticeRequired(profile);

  return (
    <section>
      <h1>My profile</h1>
      <div className="grid two">
        <AccountCard me={profile} locked={locked} onSaved={refreshMe} />
        <NoticeCard me={profile} onAccepted={refreshMe} />
      </div>
      <YourDataCard me={profile} onRequested={refreshMe} />
    </section>
  );
}
