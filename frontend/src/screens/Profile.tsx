// Profile: review/correct personal data, privacy notice acknowledgement, data export and account erasure
// (skills/privacy T177/T238/T239/T740/T741/T751/T179/T240).
// * The privacy notice must be acknowledged (checkbox unchecked by default) before the profile can be
//   edited; the API enforces the same rule (409) and re-prompts when PRIVACY_NOTICE_VERSION changes.
// * Export and erasure require the current password (verified server-side, the session is not replaced).
// * The e-mail address is the sign-in identifier: changes go through Supabase Auth's confirmation e-mail.
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
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

/** Public /privacy route (reachable before sign-in, linked from every page footer and the login screen). */
export function PrivacyPage() {
  return (
    <main className="auth-page">
      <div className="card">
        <h1>Privacy notice</h1>
        <PrivacyNotice />
        <p>
          <Link to="/">Back to ACME Clinical</Link>
        </p>
      </div>
    </main>
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
      <p>
        <Link to="/reset-password">Change password</Link>
        <span className="muted small"> (you will be asked for your current password)</span>
      </p>
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

// ---------------------------------------------------------------------------------------------------------
// Optional uses of personal data (T178/T604): consent per purpose, off by default, withdrawable with one toggle.
// ---------------------------------------------------------------------------------------------------------
interface ConsentPurpose {
  purpose: string;
  title: string;
  description: string;
  data_categories: string[];
  retention: string;
  third_parties: string[];
  withdrawal: string;
  required: boolean;
  active: boolean;
  granted_at: string | null;
}

interface ConsentsResponse {
  notice_version: string;
  purposes: ConsentPurpose[];
}

const PHONE_PATTERN = /^\+[1-9][0-9]{7,14}$/;

function EscalationPhone() {
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const r = await request<{ escalation_phone: string | null }>("GET", "/v1/me/escalation-contact");
        if (active) setSaved(r?.escalation_phone ?? null);
      } catch {
        // the form still works; the current number is simply not shown
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await request<{ escalation_phone: string | null }>("PUT", "/v1/me/escalation-contact", {
        body: { escalation_phone: phone.trim() },
      });
      setSaved(r?.escalation_phone ?? phone.trim());
      setPhone("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save}>
      <ErrorMessage error={error} />
      {saved && <p className="muted small">Current number: {saved}</p>}
      <label>
        Mobile phone for escalation (optional)
        <input
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="+5511912345678"
          maxLength={16}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
      </label>
      <button type="submit" className="secondary" disabled={busy || !PHONE_PATTERN.test(phone.trim())}>
        Save number
      </button>
    </form>
  );
}

function ConsentCard({ locked }: { locked: boolean }) {
  const [data, setData] = useState<ConsentsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const r = await request<ConsentsResponse>("GET", "/v1/me/consents");
        if (active && r) setData(r);
      } catch (err) {
        if (active) setError(err);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function grant(p: ConsentPurpose) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const r = await request<ConsentsResponse>("POST", "/v1/me/consents", {
        body: { purpose: p.purpose, notice_version: PRIVACY_NOTICE_VERSION },
      });
      if (r) setData(r);
      setStatus(`Consent given for "${p.title}".`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function withdraw(p: ConsentPurpose) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const r = await request<ConsentsResponse>("DELETE", "/v1/me/consents", { query: { purpose: p.purpose } });
      if (r) setData(r);
      setStatus(`Consent for "${p.title}" withdrawn on ${formatDateTime(new Date().toISOString())}. The data was deleted.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function decline(p: ConsentPurpose) {
    setStatus(`"${p.title}" stays off. You can change this at any time.`);
  }

  const purposes = data?.purposes ?? [];
  return (
    <div className="card">
      <h2>Optional uses of your data</h2>
      <p className="muted small">
        Everything ACME Clinical needs to work is described in the privacy notice and does not depend on consent. The
        uses below are optional and stay off unless you switch them on. You can withdraw at any time.
      </p>
      <ErrorMessage error={error} />
      {purposes.map((p) => (
        <fieldset key={p.purpose} disabled={locked || busy}>
          <legend>
            {p.title} <span className="muted small">({p.required ? "required" : "optional"})</span>
          </legend>
          <p>{p.description}</p>
          <dl className="facts small">
            <dt>Data</dt>
            <dd>{p.data_categories.join(", ")}</dd>
            <dt>Kept</dt>
            <dd>{p.retention}</dd>
            <dt>Shared with</dt>
            <dd>{p.third_parties.join(" ") || "Nobody"}</dd>
            <dt>Withdrawal</dt>
            <dd>{p.withdrawal}</dd>
          </dl>
          <label className="checkbox">
            <input
              type="checkbox"
              role="switch"
              checked={p.active}
              aria-label={`Allow ${p.title}`}
              onChange={(e) => void (e.target.checked ? grant(p) : withdraw(p))}
            />
            {p.active ? `On since ${formatDateTime(p.granted_at)}` : "Off"}
          </label>
          {p.active ? (
            p.purpose === "escalation_contact" && <EscalationPhone />
          ) : (
            <div className="actions">
              <button type="button" onClick={() => void grant(p)}>
                Accept
              </button>
              <button type="button" className="secondary" onClick={() => decline(p)}>
                Decline
              </button>
            </div>
          )}
        </fieldset>
      ))}
      {locked && <p className="muted small">Acknowledge the privacy notice first.</p>}
      {status && <p role="status">{status}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Restriction of processing (T754): see restrictions on my data, ask the administrators for one.
// ---------------------------------------------------------------------------------------------------------
const RESTRICTABLE: [string, string][] = [
  ["staff_activity_report", "Staff activity reports"],
  ["statistics", "Statistics"],
  ["research_extract", "De-identified research extracts"],
];

interface OwnRestriction {
  activity: string;
  basis: string;
  created_at: string;
  lifted_at: string | null;
}

function RestrictionCard() {
  const [items, setItems] = useState<OwnRestriction[]>([]);
  const [activity, setActivity] = useState(RESTRICTABLE[0]![0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const r = await request<{ items: OwnRestriction[] }>("GET", "/v1/me/processing-restrictions");
        if (active) setItems(r?.items ?? []);
      } catch {
        // nothing to show
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function ask(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      await request("POST", "/v1/me/processing-restrictions/request", { body: { activity } });
      setStatus("Your request was sent to the administrators.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const label = (a: string) => RESTRICTABLE.find(([k]) => k === a)?.[1] ?? humanize(a);
  return (
    <div className="card">
      <h2>Restrict processing</h2>
      <p className="muted small">
        You can object to secondary uses of your data. Clinical care and the legally required audit trail cannot be
        restricted.
      </p>
      <ErrorMessage error={error} />
      {items.length > 0 && (
        <ul>
          {items.map((r) => (
            <li key={`${r.activity}-${r.created_at}`}>
              {label(r.activity)}: restricted since {formatDateTime(r.created_at)}
              {r.lifted_at ? ` (lifted ${formatDateTime(r.lifted_at)})` : ""}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={ask}>
        <label>
          Activity
          <select value={activity} onChange={(e) => setActivity(e.target.value)}>
            {RESTRICTABLE.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="secondary" disabled={busy}>
          Ask an administrator to restrict
        </button>
      </form>
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
      <div className="grid two">
        <ConsentCard locked={locked} />
        <RestrictionCard />
      </div>
    </section>
  );
}
