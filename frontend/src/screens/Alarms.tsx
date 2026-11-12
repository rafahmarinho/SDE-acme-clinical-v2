import { useCallback, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../services/api";
import type { Alarm, AlarmAckResult } from "../services/types";
import { useAuth } from "../auth/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { useRealtime, ConnectionLabel } from "../hooks/useRealtime";
import { AlarmBanner } from "../components/AlarmBanner";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { SearchFilterBar } from "../components/SearchFilterBar";

type StateFilter = "active" | "resolved" | "all";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function Alarms() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const wardParam = params.get("ward_id") ?? "";
  const wardId = UUID_RE.test(wardParam) ? wardParam : "";
  const [state, setState] = useState<StateFilter>("active");

  const wards = useAsync(() => api.wards(), []);
  const alarms = useAsync(() => api.alarms({ state, ward_id: wardId || undefined, limit: 100 }), [state, wardId]);
  const reload = alarms.reload;
  const connection = useRealtime({ tables: ["alarms"], onChange: useCallback(() => void reload(), [reload]), poll: reload });

  const [ackNotice, setAckNotice] = useState<string | null>(null);
  const replace = ({ notice, ...updated }: AlarmAckResult) => {
    setAckNotice(notice); // the server states the consequence: acknowledged, NOT resolved (T342)
    alarms.setData(alarms.data?.map((a) => (a.id === updated.id ? updated : a)));
  };
  const activeCount = alarms.data?.filter((a) => a.state === "active").length ?? 0;
  const unacked = alarms.data?.filter((a) => a.state === "active" && !a.acknowledged_at).length ?? 0;

  return (
    <section>
      <div className="page-head">
        <h1>Alarms</h1>
        <div className="connection">{ConnectionLabel(connection)}</div>
      </div>
      <p className="notice">
        Acknowledging an alarm records that you have seen it. It does <strong>not</strong> end the condition: the alarm stays
        active until the monitor reports that the condition has cleared.
      </p>
      <SearchFilterBar>
        <label className="inline">
          State
          <select value={state} onChange={(e) => setState(e.target.value as StateFilter)}>
            <option value="active">Active</option>
            <option value="resolved">Resolved</option>
            <option value="all">All</option>
          </select>
        </label>
        <label className="inline">
          Ward
          <select
            value={wardId}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set("ward_id", e.target.value);
              else next.delete("ward_id");
              setParams(next, { replace: true });
            }}
          >
            <option value="">All my wards</option>
            {wards.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
      </SearchFilterBar>
      {alarms.data && (
        <div className="stats">
          <div>
            <div className="big danger">{activeCount}</div>
            <div className="muted small">Active</div>
          </div>
          <div>
            <div className="big">{unacked}</div>
            <div className="muted small">Active, not acknowledged</div>
          </div>
        </div>
      )}
      {ackNotice && (
        <p className="notice" role="status">
          {ackNotice}
        </p>
      )}
      <ErrorMessage error={alarms.error} onRetry={alarms.reload} />
      {alarms.loading && !alarms.data && <LoadingState />}
      {alarms.data?.length === 0 && <p className="muted">No alarms for this filter.</p>}
      <div className="stack">
        {alarms.data?.map((a) => (
          <AlarmBanner key={a.id} alarm={a}>
            {a.state === "active" && !a.acknowledged_at && can("alarm:ack") && <AckForm alarm={a} onDone={replace} />}
          </AlarmBanner>
        ))}
      </div>
    </section>
  );
}

function AckForm({ alarm, onDone }: { alarm: Alarm; onDone: (a: AlarmAckResult) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api.acknowledgeAlarm(alarm.id, note.trim() || null));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="row ack" onSubmit={submit} autoComplete="off">
      <ErrorMessage error={error} />
      <input aria-label="Acknowledgement note (optional)" placeholder="Note (optional)" maxLength={500} autoComplete="off" spellCheck={false} value={note} onChange={(e) => setNote(e.target.value)} />
      <button type="submit" disabled={busy}>
        {busy ? "Acknowledging…" : "Acknowledge"}
      </button>
    </form>
  );
}
