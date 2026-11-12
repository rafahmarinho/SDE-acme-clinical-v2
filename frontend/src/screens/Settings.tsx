// Unified security settings (skills/secure-config-supply-chain T371/T2273, skills/privacy T607/T179).
// Administrator-only: the API refuses every /v1/settings route to other roles (403), and this screen does
// not call it for them. One place for the database-managed parameters (bounded by the API), the
// read-only environment configuration, component versions, the approved-configuration fingerprint with
// drift warning, data retention and staff erasure requests.
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api, request } from "../services/api";
import type { SecuritySettings, SecuritySettingsUpdate } from "../services/types";
import { useAsync } from "../hooks/useAsync";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { formatDateTime, humanize } from "../lib/format";

type NumericKey = Exclude<keyof SecuritySettings, "require_mfa_for_admin" | "updated_at">;

const FIELDS: { key: NumericKey; label: string; min: number; max: number }[] = [
  { key: "password_min_length", label: "Minimum password length", min: 12, max: 128 },
  { key: "session_idle_minutes", label: "Idle session timeout (minutes)", min: 5, max: 60 },
  { key: "session_absolute_hours", label: "Absolute session lifetime (hours)", min: 1, max: 24 },
  { key: "max_concurrent_sessions", label: "Max concurrent sessions", min: 1, max: 10 },
  { key: "lockout_threshold", label: "Failed sign-ins before lockout", min: 3, max: 10 },
  { key: "lockout_minutes", label: "Lockout duration (minutes)", min: 5, max: 120 },
  { key: "data_retention_days", label: "Readings/alarms retention (days)", min: 30, max: 3650 },
];

interface SecurityReport {
  settings: SecuritySettings;
  fingerprint: string;
  approved_fingerprint: string | null;
  approved_at: string | null;
  drift: boolean;
  environment: Record<string, unknown>;
  components: Record<string, string>;
  generated_at: string;
}

interface PurgeRun {
  run_at: string;
  run_source: "scheduled" | "manual";
  counts: Record<string, number | null>;
}

interface RetentionStatus {
  data_retention_days: number;
  schedule: string;
  files_pending_removal: number;
  items: PurgeRun[];
}

interface PrivacyRequest {
  id: string;
  user_id: string;
  full_name: string;
  email: string;
  status: string;
  requested_at: string;
}

function show(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value ?? "-");
}

function SettingsForm({ onSaved }: { onSaved: () => void }) {
  const { data, error, loading, reload, setData } = useAsync(() => api.securitySettings(), []);
  const [draft, setDraft] = useState<SecuritySettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => setDraft(data ?? null), [data]);

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorMessage error={error} onRetry={reload} />;
  if (!draft || !data) return null;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft || !data) return;
    const changes: SecuritySettingsUpdate = {};
    for (const f of FIELDS) if (draft[f.key] !== data[f.key]) changes[f.key] = draft[f.key];
    if (draft.require_mfa_for_admin !== data.require_mfa_for_admin) changes.require_mfa_for_admin = draft.require_mfa_for_admin;
    if (Object.keys(changes).length === 0) return;
    if (changes.require_mfa_for_admin === false && !window.confirm("Turn off mandatory MFA for administrators? This weakens account security.")) {
      return;
    }
    setBusy(true);
    setSaveError(null);
    setSaved(false);
    try {
      setData(await api.updateSecuritySettings(changes));
      setSaved(true);
      onSaved();
    } catch (err) {
      setSaveError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={save}>
      <h2>Security parameters</h2>
      <ErrorMessage error={saveError} />
      <fieldset disabled={busy}>
        <div className="grid two">
          {FIELDS.map((f) => (
            <label key={f.key}>
              {f.label}
              <input
                type="number"
                min={f.min}
                max={f.max}
                value={draft[f.key]}
                onChange={(e) => setDraft({ ...draft, [f.key]: Number(e.target.value) })}
              />
              <span className="muted small">
                Allowed {f.min}–{f.max}
              </span>
            </label>
          ))}
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.require_mfa_for_admin}
            onChange={(e) => setDraft({ ...draft, require_mfa_for_admin: e.target.checked })}
          />
          Require multi-factor authentication for administrators
        </label>
      </fieldset>
      <p className="muted small">Last updated {formatDateTime(data.updated_at)}</p>
      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : "Save settings"}
      </button>
      {saved && <p role="status">Settings saved. Approve the configuration below once the change is reviewed.</p>}
    </form>
  );
}

function ConfigurationReport({ version }: { version: number }) {
  const { data, error, loading, reload } = useAsync(
    () => request<SecurityReport>("GET", "/v1/settings/security/report"),
    [version],
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  async function approve() {
    setBusy(true);
    setActionError(null);
    try {
      await request("POST", "/v1/settings/security/approve");
      await reload();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  function downloadReport() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `acme-clinical-security-configuration-${data.generated_at.slice(0, 10)}.json`;
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorMessage error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="card">
      <h2>Configuration report</h2>
      <ErrorMessage error={actionError} />
      {data.drift ? (
        <p className="notice danger" role="alert">
          {data.approved_fingerprint
            ? "The security configuration differs from the last approved baseline. Review the change and approve it, or restore the approved values."
            : "No configuration has been approved yet."}
        </p>
      ) : (
        <p role="status">Configuration matches the approved baseline (approved {formatDateTime(data.approved_at)}).</p>
      )}
      <dl className="facts">
        <dt>Current fingerprint</dt>
        <dd className="small">{data.fingerprint}</dd>
        <dt>Approved fingerprint</dt>
        <dd className="small">{data.approved_fingerprint ?? "none"}</dd>
      </dl>
      <h3>Environment (read-only, set in Vercel and applied by redeploying)</h3>
      <table className="table">
        <tbody>
          {Object.entries(data.environment).map(([k, v]) => (
            <tr key={k}>
              <th scope="row">{humanize(k)}</th>
              <td>{show(v)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Components</h3>
      <table className="table">
        <tbody>
          {Object.entries(data.components).map(([k, v]) => (
            <tr key={k}>
              <th scope="row">{k}</th>
              <td>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row">
        <button type="button" onClick={approve} disabled={busy || !data.drift}>
          Approve current configuration
        </button>
        <button type="button" className="secondary" onClick={downloadReport}>
          Download report (JSON)
        </button>
      </div>
    </div>
  );
}

function RetentionCard() {
  const { data, error, loading, reload } = useAsync(() => request<RetentionStatus>("GET", "/v1/settings/retention"), []);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<unknown>(null);
  const [result, setResult] = useState<string | null>(null);

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setRunError(null);
    setResult(null);
    try {
      const out = await request<{ counts: Record<string, number | null>; files_removed: number; files_pending_removal: number }>(
        "POST",
        "/v1/settings/retention/run",
        { body: { confirm_text: confirmText } },
      );
      setResult(
        `Purged ${out.counts.patients ?? 0} patient record(s), ${out.counts.readings ?? 0} reading(s), ${out.counts.alarms ?? 0} alarm(s); pseudonymised ${out.counts.staff_pseudonymised ?? 0} staff account(s); removed ${out.files_removed} file(s).`,
      );
      setConfirmText("");
      await reload();
    } catch (err) {
      setRunError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorMessage error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="card">
      <h2>Data retention</h2>
      <p>
        Readings and resolved alarms older than <strong>{data.data_retention_days} days</strong>, patients past their
        retention date (unless on legal hold) and staff accounts deactivated for longer than that period are deleted or
        pseudonymised automatically. {data.schedule}.
      </p>
      {data.files_pending_removal > 0 && (
        <p className="notice">{data.files_pending_removal} file(s) are waiting to be removed from storage.</p>
      )}
      <table className="table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Source</th>
            <th>Deleted or pseudonymised</th>
          </tr>
        </thead>
        <tbody>
          {data.items.length === 0 && (
            <tr>
              <td colSpan={3}>No retention runs yet.</td>
            </tr>
          )}
          {data.items.map((r) => (
            <tr key={r.run_at}>
              <td>{formatDateTime(r.run_at)}</td>
              <td>{humanize(r.run_source)}</td>
              <td>
                {Object.entries(r.counts)
                  .filter(([k]) => k !== "retention_days")
                  .map(([k, v]) => `${humanize(k)}: ${v ?? 0}`)
                  .join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ErrorMessage error={runError} />
      <form onSubmit={run}>
        <p className="danger">Running the purge permanently deletes expired personal data. This cannot be undone.</p>
        <label>
          Type PURGE EXPIRED DATA to run now
          <input value={confirmText} maxLength={40} onChange={(e) => setConfirmText(e.target.value)} />
        </label>
        <button type="submit" className="danger" disabled={busy || confirmText !== "PURGE EXPIRED DATA"}>
          Run retention purge
        </button>
      </form>
      {result && <p role="status">{result}</p>}
    </div>
  );
}

function ErasureRequests() {
  const { data, error, loading, reload } = useAsync(
    () => request<{ items: PrivacyRequest[] }>("GET", "/v1/settings/privacy-requests"),
    [],
  );
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  async function decide(req: PrivacyRequest, action: "complete" | "reject") {
    if (action === "complete") {
      const typed = window.prompt(
        `Erase the account of ${req.full_name}? Their name, e-mail and sign-in history are removed and the account is closed. Clinical records stay with a pseudonymous author. Type ERASE to confirm.`,
      );
      if (typed !== "ERASE") return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await request("POST", `/v1/settings/privacy-requests/${encodeURIComponent(req.id)}/${action}`, {
        body: action === "complete" ? { confirm_text: "ERASE" } : undefined,
      });
      await reload();
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data) return <LoadingState />;
  if (error) return <ErrorMessage error={error} onRetry={reload} />;
  if (!data) return null;

  return (
    <div className="card">
      <h2>Account erasure requests</h2>
      <ErrorMessage error={actionError} />
      {data.items.length === 0 ? (
        <p className="muted">No pending requests.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Staff member</th>
              <th>Requested</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.full_name}
                  <div className="muted small">{r.email}</div>
                </td>
                <td>{formatDateTime(r.requested_at)}</td>
                <td className="row">
                  <button type="button" className="danger" disabled={busy} onClick={() => void decide(r, "complete")}>
                    Erase account
                  </button>
                  <button type="button" className="secondary" disabled={busy} onClick={() => void decide(r, "reject")}>
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Settings() {
  const { can } = useAuth();
  const [version, setVersion] = useState(0);

  if (!can("settings:manage")) {
    return (
      <section>
        <h1>Security settings</h1>
        <p className="notice" role="status">
          Security settings are managed by administrators. Your session timeout and password rules are applied
          automatically; see your <Link to="/profile">profile</Link> for your personal data and privacy options.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h1>Security settings</h1>
      <SettingsForm onSaved={() => setVersion((v) => v + 1)} />
      <ConfigurationReport version={version} />
      <RetentionCard />
      {can("staff:manage") && <ErasureRequests />}
    </section>
  );
}
