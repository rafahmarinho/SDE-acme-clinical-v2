import { useCallback, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../services/api";
import { SUPABASE_URL } from "../lib/supabase";
import { useAuth } from "../auth/AuthContext";
import { useAsync, type AsyncState } from "../hooks/useAsync";
import { useRealtime, ConnectionLabel } from "../hooks/useRealtime";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { VitalSignTile } from "../components/VitalSignTile";
import { EcgTrace } from "../components/EcgTrace";
import { RoleGuard } from "../components/RoleGuard";
import { openSafely } from "../components/ExternalLink";
import { ThresholdEditor } from "../components/ThresholdEditor";
import { formatBytes, formatDateTime, formatTime } from "../lib/format";
import { VITAL_LABELS, type Attachment, type Observation, type Threshold, type ThresholdUpdate, type VitalParameter } from "../services/types";

const ALLOWED_TYPES = ["application/pdf", "image/png", "image/jpeg"];
const MAX_UPLOAD = 5 * 1024 * 1024;

function limits(thresholds: Threshold[], param: VitalParameter): { low?: number; high?: number } {
  const t = thresholds.find((x) => x.parameter === param);
  return t ? { low: t.low_limit, high: t.high_limit } : {};
}

export default function PatientDetail() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const patient = useAsync(() => api.patient(id), [id]);
  const readings = useAsync(() => api.readings(id, 30), [id], !!patient.data);
  const observations = useAsync(() => api.observations(id), [id], !!patient.data);
  const files = useAsync(() => api.files(id), [id], !!patient.data);
  const patientThresholds = useAsync(() => api.thresholds({ patient_id: id }), [id], !!patient.data);
  const wardId = patient.data?.ward_id;
  const wardThresholds = useAsync(() => api.thresholds({ ward_id: wardId }), [wardId], !!wardId);

  const reloadReadings = readings.reload;
  const connection = useRealtime({
    tables: ["readings"],
    enabled: !!patient.data,
    onChange: useCallback(
      (c) => {
        if (c.record.patient_id === id) void reloadReadings();
      },
      [id, reloadReadings],
    ),
    poll: reloadReadings,
  });

  if (patient.loading && !patient.data) return <LoadingState label="Loading patient…" />;
  if (patient.error) {
    const denied = patient.error instanceof ApiError && (patient.error.status === 403 || patient.error.status === 404);
    return (
      <section>
        <ErrorMessage error={patient.error} onRetry={patient.reload} />
        {denied && can("break_glass:request") && <BreakGlass patientId={id} onGranted={patient.reload} />}
        <Link to="/patients">Back to patients</Link>
      </section>
    );
  }
  const p = patient.data;
  if (!p) return null;

  const latest = readings.data?.[0];
  const effective = [
    ...(patientThresholds.data ?? []),
    ...(wardThresholds.data ?? []).filter((w) => !(patientThresholds.data ?? []).some((t) => t.parameter === w.parameter)),
  ];
  const degraded = latest ? latest.quality !== "good" : false;

  return (
    <section>
      <Link to="/patients">← Patients</Link>
      <div className="page-head">
        <div>
          <h1>{p.display_name}</h1>
          <div className="muted">
            {p.pseudonym} · Bed {p.bed_label ?? "—"} · Monitor {p.monitor_serial ?? "none"} · Born {p.birth_year ?? "—"} ·
            Admitted {formatDateTime(p.admitted_at)}
          </div>
        </div>
        <div className="connection">{ConnectionLabel(connection)}</div>
      </div>
      {p.active_alarms > 0 && (
        <div className="alarm alarm-high alarm-active" role="alert">
          <strong>{p.active_alarms} active alarm(s).</strong> <Link to="/alarms">Open alarms</Link>
        </div>
      )}

      <h2>Latest vitals {latest && <span className="muted small">at {formatTime(latest.recorded_at)}</span>}</h2>
      <ErrorMessage error={readings.error} onRetry={readings.reload} />
      {readings.loading && !readings.data && <LoadingState />}
      <div className="vitals">
        <VitalSignTile label={VITAL_LABELS.heart_rate.label} unit="bpm" value={latest?.heart_rate} degraded={degraded} {...limits(effective, "heart_rate")} />
        <VitalSignTile label={VITAL_LABELS.spo2.label} unit="%" value={latest?.spo2} degraded={degraded} {...limits(effective, "spo2")} />
        <VitalSignTile label={VITAL_LABELS.resp_rate.label} unit="/min" value={latest?.resp_rate} degraded={degraded} {...limits(effective, "resp_rate")} />
        <VitalSignTile
          label="Blood pressure"
          unit="mmHg"
          value={latest && latest.bp_systolic != null ? `${latest.bp_systolic}/${latest.bp_diastolic ?? "--"}` : null}
          degraded={degraded}
        />
      </div>
      <EcgTrace samples={latest?.ecg} />

      <div className="grid two">
        <Observations patientId={id} state={observations} canWrite={can("observation:write")} />
        <Files patientId={id} state={files} canWrite={can("file:write")} />
      </div>

      <div className="card">
        <h2>Alarm limits for this patient</h2>
        <ErrorMessage error={patientThresholds.error ?? wardThresholds.error} />
        <ThresholdEditor
          thresholds={patientThresholds.data ?? []}
          inherited={wardThresholds.data ?? []}
          editable={can("threshold:write")}
          scopeLabel="Patient override"
          onSave={async (body: ThresholdUpdate) => {
            await api.setPatientThreshold(id, body);
            await patientThresholds.reload();
          }}
        />
      </div>
    </section>
  );
}

function Observations({
  patientId,
  state,
  canWrite,
}: {
  patientId: string;
  state: AsyncState<Observation[]>;
  canWrite: boolean;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.addObservation(patientId, text.trim());
      setText("");
      await state.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Observations</h2>
      <RoleGuard requires={["observation:write"]}>
        {canWrite && (
          <form onSubmit={submit} autoComplete="off">
            <ErrorMessage error={error} />
            <label>
              New observation
              <textarea value={text} maxLength={2000} rows={3} autoComplete="off" spellCheck={false} onChange={(e) => setText(e.target.value)} />
            </label>
            <div className="muted small">{text.length}/2000</div>
            <button type="submit" disabled={busy || !text.trim()}>
              {busy ? "Saving…" : "Add observation"}
            </button>
          </form>
        )}
      </RoleGuard>
      <ErrorMessage error={state.error} onRetry={state.reload} />
      {state.loading && !state.data && <LoadingState />}
      {state.data?.length === 0 && <p className="muted">No observations yet.</p>}
      <ul className="list">
        {state.data?.map((o) => (
          <li key={o.id}>
            <div className="muted small">
              {formatDateTime(o.created_at)} · {o.author_name}
            </div>
            <div className="prewrap">{o.body}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Files({
  patientId,
  state,
  canWrite,
}: {
  patientId: string;
  state: AsyncState<Attachment[]>;
  canWrite: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    if (!ALLOWED_TYPES.includes(file.type)) return setError("Only PDF, PNG or JPEG files can be uploaded.");
    if (file.size === 0 || file.size > MAX_UPLOAD) return setError("Files must be between 1 byte and 5 MB.");
    setBusy(true);
    try {
      await api.uploadFile(patientId, file);
      await state.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function open(attachmentId: string) {
    setError(null);
    try {
      const { url } = await api.fileUrl(attachmentId);
      const parsed = new URL(url);
      // Only open short-lived signed URLs on our own Supabase storage origin.
      if (parsed.origin !== new URL(SUPABASE_URL).origin || !parsed.pathname.startsWith("/storage/v1/")) {
        throw new Error("unexpected file location");
      }
      openSafely(parsed.toString(), SUPABASE_URL);
    } catch (err) {
      setError(err instanceof ApiError ? err : "The file could not be opened.");
    }
  }

  return (
    <div className="card">
      <h2>Files</h2>
      <ErrorMessage error={error} />
      {canWrite && (
        <div>
          <input ref={input} type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" hidden onChange={onFile} />
          <button type="button" disabled={busy} onClick={() => input.current?.click()}>
            {busy ? "Uploading…" : "Upload file"}
          </button>
          <span className="muted small"> PDF, PNG or JPEG, up to 5 MB</span>
        </div>
      )}
      <ErrorMessage error={state.error} onRetry={state.reload} />
      {state.loading && !state.data && <LoadingState />}
      {state.data?.length === 0 && <p className="muted">No files.</p>}
      <ul className="list">
        {state.data?.map((f) => (
          <li key={f.id} className="row spread">
            <span>
              {f.original_name}
              <span className="muted small">
                {" "}
                · {formatBytes(f.size_bytes)} · {formatDateTime(f.created_at)}
              </span>
            </span>
            <button type="button" className="secondary" onClick={() => open(f.id)}>
              Open
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function BreakGlass({ patientId, onGranted }: { patientId: string; onGranted: () => void }) {
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!acknowledged) return;
    setBusy(true);
    setError(null);
    try {
      await api.requestBreakGlass(patientId, reason.trim());
      onGranted();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card confirm-box" onSubmit={submit} autoComplete="off">
      <h2>Emergency access</h2>
      <p>
        This patient is outside your assigned wards. In an emergency you can request temporary access. The request and your
        reason are recorded and reviewed by an administrator.
      </p>
      <ErrorMessage error={error} />
      <label>
        Clinical reason (at least 10 characters)
        <textarea value={reason} minLength={10} maxLength={500} rows={3} autoComplete="off" spellCheck={false} onChange={(e) => setReason(e.target.value)} />
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />I understand that
        emergency access is for direct patient care only, lasts 30 minutes, and that every action is audited and reviewed.
      </label>
      <p className="muted small">You may be asked to confirm your password before access is granted.</p>
      <button type="submit" disabled={busy || reason.trim().length < 10 || !acknowledged}>
        Request emergency access
      </button>
    </form>
  );
}
