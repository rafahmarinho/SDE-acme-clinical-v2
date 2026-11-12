import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api";
import type { Alarm, Patient, Reading } from "../services/types";
import { useRealtime, ConnectionLabel, type RealtimeChange } from "../hooks/useRealtime";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { EcgTrace } from "../components/EcgTrace";
import { formatTime } from "../lib/format";

function toReading(r: Record<string, unknown>): Reading | null {
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  if (typeof r.recorded_at !== "string") return null;
  return {
    recorded_at: r.recorded_at,
    heart_rate: num(r.heart_rate),
    spo2: num(r.spo2),
    resp_rate: num(r.resp_rate),
    bp_systolic: num(r.bp_systolic),
    bp_diastolic: num(r.bp_diastolic),
    ecg: Array.isArray(r.ecg) ? r.ecg.filter((x): x is number => typeof x === "number") : null,
    quality: typeof r.quality === "string" ? r.quality : "good",
  };
}

export default function LiveMonitoring() {
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [latest, setLatest] = useState<Record<string, Reading | undefined>>({});
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const patientsRef = useRef<Patient[]>([]);

  const loadAlarms = useCallback(async () => {
    setAlarms(await api.alarms({ state: "active", limit: 100 }));
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const page = await api.patients({ limit: 100 });
      patientsRef.current = page.items;
      setPatients(page.items);
      const entries = await Promise.all(
        page.items.map(async (p) => [p.id, (await api.readings(p.id, 1))[0]] as const),
      );
      setLatest(Object.fromEntries(entries));
      await loadAlarms();
      setError(null);
      setUpdatedAt(new Date().toISOString());
    } catch (err) {
      setError(err);
    }
  }, [loadAlarms]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const onChange = useCallback(
    (c: RealtimeChange) => {
      if (c.table === "readings" && c.eventType === "INSERT") {
        const pid = c.record.patient_id;
        const reading = toReading(c.record);
        if (typeof pid === "string" && reading && patientsRef.current.some((p) => p.id === pid)) {
          setLatest((prev) => ({ ...prev, [pid]: reading }));
          setUpdatedAt(new Date().toISOString());
        }
      } else if (c.table === "alarms") {
        void loadAlarms().catch(setError);
      }
    },
    [loadAlarms],
  );

  const connection = useRealtime({ tables: ["readings", "alarms"], onChange, poll: loadAll, pollMs: 5000 });

  const alarmsByPatient = new Map<string, Alarm[]>();
  for (const a of alarms) {
    if (!a.patient_id) continue;
    alarmsByPatient.set(a.patient_id, [...(alarmsByPatient.get(a.patient_id) ?? []), a]);
  }

  return (
    <section>
      <div className="page-head">
        <h1>Live monitoring</h1>
        <div className={`connection connection-${connection}`} role="status">
          {ConnectionLabel(connection)}
          {updatedAt && <span className="muted small"> · updated {formatTime(updatedAt)}</span>}
        </div>
      </div>
      <ErrorMessage error={error} onRetry={loadAll} />
      {!patients && !error && <LoadingState label="Connecting to monitors…" />}
      {patients?.length === 0 && <p className="muted">No monitored patients in your wards.</p>}
      <div className="grid monitors">
        {patients?.map((p) => {
          const r = latest[p.id];
          const pa = alarmsByPatient.get(p.id) ?? [];
          const high = pa.some((a) => a.priority === "high");
          return (
            <article key={p.id} className={`card live ${pa.length ? (high ? "live-high" : "live-alarm") : ""}`}>
              <div className="row spread">
                <Link to={`/patients/${encodeURIComponent(p.id)}`} className="strong">
                  {p.bed_label ?? "—"} · {p.display_name}
                </Link>
                <span className="muted small">{r ? formatTime(r.recorded_at) : "no data"}</span>
              </div>
              <div className="live-vitals">
                <div>
                  <span className="label">HR</span>
                  <span className="big">{r?.heart_rate ?? "--"}</span>
                </div>
                <div>
                  <span className="label">SpO₂</span>
                  <span className="big">{r?.spo2 ?? "--"}</span>
                </div>
                <div>
                  <span className="label">RR</span>
                  <span className="big">{r?.resp_rate ?? "--"}</span>
                </div>
                <div>
                  <span className="label">BP</span>
                  <span className="big">{r?.bp_systolic != null ? `${r.bp_systolic}/${r.bp_diastolic ?? "--"}` : "--"}</span>
                </div>
              </div>
              <EcgTrace samples={r?.ecg} height={60} label={`ECG ${p.pseudonym}`} />
              {r && r.quality !== "good" && <div className="vital-flag">Signal quality: {r.quality}</div>}
              {pa.map((a) => (
                <div key={a.id} className={`alarm-chip alarm-${a.priority}`}>
                  {a.acknowledged_at ? "STILL ACTIVE (acknowledged): " : "ACTIVE: "}
                  {a.message}
                </div>
              ))}
            </article>
          );
        })}
      </div>
    </section>
  );
}
