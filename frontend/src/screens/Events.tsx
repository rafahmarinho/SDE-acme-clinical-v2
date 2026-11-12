import { useState } from "react";
import { api } from "../services/api";
import type { EventRecord, IntegrityResult } from "../services/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { SearchFilterBar } from "../components/SearchFilterBar";
import { formatDateTime } from "../lib/format";
import { useAsync } from "../hooks/useAsync";

const ACTION_RE = /^[a-z_]+(\.[a-z_]+)?$/;
const ENTITY_RE = /^[a-z_]+$/;
const PAGE = 50;

export default function Events() {
  const { can } = useAuth();
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [older, setOlder] = useState<EventRecord[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<unknown>(null);
  const [integrity, setIntegrity] = useState<IntegrityResult | null>(null);
  const [integrityError, setIntegrityError] = useState<unknown>(null);

  const validAction = !action || ACTION_RE.test(action);
  const validEntity = !entityType || ENTITY_RE.test(entityType);
  const filters = {
    action: validAction ? action || undefined : undefined,
    entity_type: validEntity ? entityType || undefined : undefined,
  };
  const events = useAsync(async () => {
    setOlder([]);
    return api.events({ ...filters, limit: PAGE });
  }, [filters.action, filters.entity_type]);

  const all = [...(events.data ?? []), ...older];
  const lastId = all[all.length - 1]?.id;
  const lastPageFull = (older.length ? older.length % PAGE === 0 : (events.data?.length ?? 0) === PAGE) && all.length > 0;

  async function loadMore() {
    if (!lastId) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const next = await api.events({ ...filters, before_id: lastId, limit: PAGE });
      setOlder((o) => [...o, ...next]);
    } catch (err) {
      setMoreError(err);
    } finally {
      setLoadingMore(false);
    }
  }

  async function checkIntegrity() {
    setIntegrityError(null);
    try {
      setIntegrity(await api.eventsIntegrity());
    } catch (err) {
      setIntegrityError(err);
    }
  }

  return (
    <section>
      <div className="page-head">
        <h1>Events</h1>
        {can("events:read_all") && (
          <button type="button" className="secondary" onClick={checkIntegrity}>
            Verify audit log integrity
          </button>
        )}
      </div>
      <p className="muted">{can("events:read_all") ? "All audit events." : "Your own audit events."}</p>
      <ErrorMessage error={integrityError} />
      {integrity && (
        <p role="status" className={integrity.intact ? "notice" : "error"}>
          {integrity.intact
            ? "Audit log integrity verified: the hash chain is intact."
            : `Audit log integrity check FAILED at event #${integrity.first_broken_id ?? "?"}.`}
        </p>
      )}
      <SearchFilterBar search={action} onSearch={setAction} placeholder="Action, e.g. alarm or alarm.acknowledged">
        <label className="inline">
          Entity type
          <input value={entityType} maxLength={40} placeholder="e.g. patient" autoComplete="off" spellCheck={false} onChange={(e) => setEntityType(e.target.value.trim())} />
        </label>
      </SearchFilterBar>
      {!validAction && <p className="error">Action filters use lowercase words, e.g. “alarm” or “alarm.acknowledged”.</p>}
      {!validEntity && <p className="error">Entity types use lowercase words, e.g. “patient”.</p>}
      <ErrorMessage error={events.error} onRetry={events.reload} />
      {events.loading && !events.data && <LoadingState />}
      {events.data && all.length === 0 && <p className="muted">No events match.</p>}
      {all.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>#</th>
              <th>When</th>
              <th>Role</th>
              <th>Action</th>
              <th>Entity</th>
              <th>Outcome</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {all.map((e) => (
              <tr key={e.id} className={e.outcome !== "success" ? "row-alarming" : ""}>
                <td>{e.id}</td>
                <td>{formatDateTime(e.occurred_at)}</td>
                <td>{e.actor_role ?? "system"}</td>
                <td className="strong">{e.action}</td>
                <td>
                  {e.entity_type}
                  {e.entity_id ? ` ${e.entity_id.slice(0, 8)}` : ""}
                </td>
                <td>{e.outcome}</td>
                <td>
                  <code className="small">{JSON.stringify(e.details)}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <ErrorMessage error={moreError} />
      {lastPageFull && (
        <button type="button" className="secondary" disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? "Loading…" : "Load older events"}
        </button>
      )}
    </section>
  );
}
