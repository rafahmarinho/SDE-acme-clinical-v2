import { useCallback, useState, type FormEvent } from "react";
import { api, MAX_PAIRING_CODE, MIN_PAIRING_CODE, PAIRING_CODE_PATTERN } from "../services/api";
import { MAINTENANCE_KINDS, type Bed, type MaintenanceKind, type Monitor, type Ward } from "../services/types";
import { useAuth } from "../auth/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { useRealtime, ConnectionLabel } from "../hooks/useRealtime";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { SearchFilterBar } from "../components/SearchFilterBar";
import { formatDateTime, humanize } from "../lib/format";

/** Beds (with occupancy) come from the API (GET /v1/wards/{id}/beds), never from direct table reads. */
export async function loadBeds(wards: Ward[]): Promise<Bed[]> {
  const perWard = await Promise.all(wards.map((w) => api.beds(w.id)));
  return perWard.flat();
}

export function pairingCodeValid(raw: string): boolean {
  return PAIRING_CODE_PATTERN.test(raw.trim());
}

export default function Devices() {
  const { can } = useAuth();
  const monitors = useAsync(() => api.monitors(), []);
  const wards = useAsync(() => api.wards(), []);
  const beds = useAsync(() => loadBeds(wards.data ?? []), [wards.data], can("device:write") && !!wards.data);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [bindFor, setBindFor] = useState<Monitor | null>(null);
  const [maintFor, setMaintFor] = useState<Monitor | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reload = monitors.reload;
  const connection = useRealtime({ tables: ["monitors"], onChange: useCallback(() => void reload(), [reload]), poll: reload });

  const wardName = (id: string | null) => wards.data?.find((w) => w.id === id)?.name ?? "—";
  const filtered = (monitors.data ?? []).filter(
    (m) =>
      (!status || m.status === status) &&
      (!search || m.serial.toLowerCase().includes(search.toLowerCase()) || m.model.toLowerCase().includes(search.toLowerCase())),
  );

  async function unbind(m: Monitor) {
    if (!window.confirm(`Unbind monitor ${m.serial} from bed ${m.bed_label ?? ""}? Readings will stop being linked to that bed.`)) return;
    setError(null);
    try {
      await api.unassignMonitor(m.id);
      await monitors.reload();
      await beds.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>Devices</h1>
        <div className="connection">{ConnectionLabel(connection)}</div>
      </div>
      <SearchFilterBar search={search} onSearch={setSearch} placeholder="Search serial or model">
        <label className="inline">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
            <option value="maintenance">Maintenance</option>
            <option value="retired">Retired</option>
          </select>
        </label>
      </SearchFilterBar>
      <ErrorMessage error={error ?? monitors.error} onRetry={monitors.reload} />
      {monitors.loading && !monitors.data && <LoadingState />}
      {monitors.data && (
        <table className="table">
          <thead>
            <tr>
              <th>Serial</th>
              <th>Model</th>
              <th>Firmware</th>
              <th>Status</th>
              <th>Battery</th>
              <th>Last heartbeat</th>
              <th>Ward / bed</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.map((m) => (
              <tr key={m.id} className={m.status !== "online" || m.battery_pct < 20 ? "row-alarming" : ""}>
                <td className="strong">{m.serial}</td>
                <td>{m.model}</td>
                <td>{m.firmware_version}</td>
                <td>{humanize(m.status)}</td>
                <td className={m.battery_pct < 20 ? "danger strong" : ""}>
                  {m.battery_pct}%{m.battery_pct < 20 ? " (low)" : ""}
                </td>
                <td>{formatDateTime(m.last_heartbeat_at)}</td>
                <td>{m.bed_id ? `${wardName(m.ward_id)} / ${m.bed_label ?? ""}` : "Unassigned"}</td>
                <td className="row">
                  {can("device:write") &&
                    (m.bed_id ? (
                      <button type="button" className="secondary" onClick={() => unbind(m)}>
                        Unbind
                      </button>
                    ) : (
                      <button type="button" className="secondary" onClick={() => setBindFor(m)}>
                        Bind to bed
                      </button>
                    ))}
                  {(can("maintenance:read") || can("maintenance:write")) && (
                    <button type="button" className="secondary" onClick={() => setMaintFor(m)}>
                      Maintenance
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {bindFor && (
        <BindForm
          monitor={bindFor}
          beds={(beds.data ?? []).filter((b) => !b.occupied && !(monitors.data ?? []).some((m) => m.bed_id === b.id))}
          bedsError={beds.error}
          wardName={wardName}
          onClose={() => setBindFor(null)}
          onDone={async () => {
            setBindFor(null);
            await monitors.reload();
            await beds.reload();
          }}
        />
      )}
      {maintFor && (
        <Maintenance
          monitor={maintFor}
          canWrite={can("maintenance:write")}
          onClose={() => setMaintFor(null)}
          onSaved={monitors.reload}
        />
      )}
    </section>
  );
}

export function BindForm(props: {
  monitor: Monitor;
  beds: Bed[];
  bedsError: unknown;
  wardName: (id: string) => string;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const { monitor, beds, wardName } = props;
  const [bedId, setBedId] = useState("");
  const [pairingCode, setPairingCode] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const bed = beds.find((b) => b.id === bedId);
  const codeValid = pairingCodeValid(pairingCode);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!bedId || !confirmed || !codeValid) return;
    setBusy(true);
    setError(null);
    try {
      await api.assignMonitor(monitor.id, bedId, pairingCode.trim());
      await props.onDone();
    } catch (err) {
      setError(err);
    } finally {
      setPairingCode(""); // never keep the device secret around after an attempt
      setBusy(false);
    }
  }

  return (
    <form className="card confirm-box" onSubmit={submit} autoComplete="off">
      <h2>Bind monitor {monitor.serial} to a bed</h2>
      <ErrorMessage error={error ?? props.bedsError} />
      <label>
        Bed
        <select value={bedId} onChange={(e) => setBedId(e.target.value)}>
          <option value="">Select a free bed…</option>
          {beds.map((b) => (
            <option key={b.id} value={b.id}>
              {wardName(b.ward_id)} — {b.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Pairing code (printed on the monitor label)
        <input
          value={pairingCode}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          maxLength={MAX_PAIRING_CODE}
          aria-describedby="pairing-help"
          onChange={(e) => setPairingCode(e.target.value)}
        />
      </label>
      <p id="pairing-help" className="muted small">
        The pairing code proves this is the physical monitor ({MIN_PAIRING_CODE} to {MAX_PAIRING_CODE} characters).
        {pairingCode && !codeValid ? " Check the code: letters, digits, - and _ only." : ""}
      </p>
      {bed && (
        <label className="checkbox">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I have checked at the
          bedside that monitor {monitor.serial} is physically connected to the patient in {wardName(bed.ward_id)} bed {bed.label}.
        </label>
      )}
      <div className="row">
        <button type="submit" disabled={busy || !bedId || !confirmed || !codeValid}>
          {busy ? "Binding…" : "Confirm binding"}
        </button>
        <button type="button" className="secondary" onClick={props.onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Maintenance({
  monitor,
  canWrite,
  onClose,
  onSaved,
}: {
  monitor: Monitor;
  canWrite: boolean;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const records = useAsync(() => api.maintenance(monitor.id), [monitor.id]);
  const [kind, setKind] = useState<MaintenanceKind>("inspection");
  const [notes, setNotes] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.addMaintenance(monitor.id, { kind, notes: notes.trim(), next_due: nextDue || null });
      setNotes("");
      setNextDue("");
      await records.reload();
      await onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="row spread">
        <h2>Maintenance — {monitor.serial}</h2>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      {canWrite && (
        <form onSubmit={submit} autoComplete="off">
          <ErrorMessage error={error} />
          <div className="row">
            <label>
              Type
              <select value={kind} onChange={(e) => setKind(e.target.value as MaintenanceKind)}>
                {MAINTENANCE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {humanize(k)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Next due
              <input type="date" value={nextDue} autoComplete="off" onChange={(e) => setNextDue(e.target.value)} />
            </label>
          </div>
          <label>
            Notes
            <textarea value={notes} maxLength={1000} rows={2} autoComplete="off" spellCheck={false} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Record maintenance"}
          </button>
        </form>
      )}
      <ErrorMessage error={records.error} onRetry={records.reload} />
      {records.loading && !records.data && <LoadingState />}
      {records.data?.length === 0 && <p className="muted">No maintenance recorded.</p>}
      <ul className="list">
        {records.data?.map((r) => (
          <li key={r.id}>
            <div className="strong">
              {humanize(r.kind)} · {formatDateTime(r.performed_at)} · {r.performed_by_name}
            </div>
            {r.notes && <div className="prewrap">{r.notes}</div>}
            {r.next_due && <div className="muted small">Next due {r.next_due}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
