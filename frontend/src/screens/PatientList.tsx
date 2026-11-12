import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { SearchFilterBar } from "../components/SearchFilterBar";
import { formatDateTime } from "../lib/format";

const PAGE_SIZE = 25;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default function PatientList() {
  const [params, setParams] = useSearchParams();
  const wardParam = params.get("ward_id") ?? "";
  const wardId = UUID_RE.test(wardParam) ? wardParam : "";
  const alarming = params.get("alarming") === "true";
  const [q, setQ] = useState(""); // kept in memory only, not in the browser URL
  const [offset, setOffset] = useState(0);

  const wards = useAsync(() => api.wards(), []);
  const list = useAsync(
    () =>
      api.patients({
        q: q || undefined,
        ward_id: wardId || undefined,
        alarming: alarming || undefined,
        limit: PAGE_SIZE,
        offset,
      }),
    [q, wardId, alarming, offset],
  );

  const onSearch = useCallback((value: string) => {
    setQ(value);
    setOffset(0);
  }, []);

  function setFilter(key: "ward_id" | "alarming", value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
    setOffset(0);
  }

  return (
    <section>
      <h1>Patients</h1>
      <SearchFilterBar search={q} onSearch={onSearch} placeholder="Search by name or pseudonym">
        <label className="inline">
          Ward
          <select value={wardId} onChange={(e) => setFilter("ward_id", e.target.value)}>
            <option value="">All my wards</option>
            {wards.data?.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline checkbox">
          <input type="checkbox" checked={alarming} onChange={(e) => setFilter("alarming", e.target.checked ? "true" : "")} />
          Only patients with active alarms
        </label>
      </SearchFilterBar>
      <ErrorMessage error={list.error} onRetry={list.reload} />
      {list.loading && !list.data && <LoadingState />}
      {list.data && list.data.items.length === 0 && <p className="muted">No patients match these filters.</p>}
      {list.data && list.data.items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Patient</th>
              <th>Pseudonym</th>
              <th>Bed</th>
              <th>Monitor</th>
              <th>Active alarms</th>
              <th>Admitted</th>
            </tr>
          </thead>
          <tbody>
            {list.data.items.map((p) => (
              <tr key={p.id} className={p.active_alarms > 0 ? "row-alarming" : ""}>
                <td>
                  <Link to={`/patients/${encodeURIComponent(p.id)}`}>{p.display_name}</Link>
                </td>
                <td>{p.pseudonym}</td>
                <td>{p.bed_label ?? "—"}</td>
                <td>{p.monitor_serial ?? "—"}</td>
                <td className={p.active_alarms > 0 ? "danger strong" : ""}>{p.active_alarms}</td>
                <td>{formatDateTime(p.admitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="pager">
        <button type="button" className="secondary" disabled={offset === 0 || list.loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </button>
        <span className="muted">
          Showing {list.data ? offset + 1 : 0}–{offset + (list.data?.items.length ?? 0)}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={list.loading || list.data?.next_offset == null}
          onClick={() => list.data?.next_offset != null && setOffset(list.data.next_offset)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
