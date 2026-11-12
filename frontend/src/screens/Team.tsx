import { useState, type FormEvent } from "react";
import { api, request } from "../services/api";
import type { Role, Staff } from "../services/types";
import { useAuth } from "../auth/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { ErrorMessage } from "../components/ErrorMessage";
import { LoadingState } from "../components/LoadingState";
import { SearchFilterBar } from "../components/SearchFilterBar";
import { formatDateTime, humanize } from "../lib/format";
import { canonicalEmail } from "../lib/authPolicy";

// Team management (administrators with MFA). Invitations never set passwords: Supabase e-mails a single-use
// link and the person chooses their own. The invite result is the same message whether or not the address
// already has an account (no enumeration); refresh the list to see new members.
const INVITE_SENT =
  "Invitation processed. If the address can receive invitations, the person will get an email with a single-use link to set their password.";

const ROLES: Role[] = ["nurse", "physician", "biomed_tech", "admin"];
const ROLE_LABELS: Record<Role, string> = {
  nurse: "Nurse",
  physician: "Physician",
  biomed_tech: "Biomedical technician",
  admin: "Administrator",
};

export default function Team() {
  const { me } = useAuth();
  const staff = useAsync(() => api.staff(), []);
  const wards = useAsync(() => api.wards(), []);
  const roleRequests = useAsync(() => api.roleRequests(), []);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const wardName = (id: string) => wards.data?.find((w) => w.id === id)?.code ?? "?";
  const rows = (staff.data ?? []).filter(
    (s) =>
      (!roleFilter || s.role === roleFilter) &&
      (!search || s.full_name.toLowerCase().includes(search.toLowerCase()) || s.email.toLowerCase().includes(search.toLowerCase())),
  );

  async function unlock(s: Staff) {
    if (!window.confirm(`Unlock sign-in for ${s.full_name}? Use this only after confirming their identity.`)) return;
    setError(null);
    setNotice(null);
    try {
      await request<void>("POST", `/v1/staff/${encodeURIComponent(s.user_id)}/unlock`);
      setNotice(`Sign-in unlocked for ${s.full_name}.`);
    } catch (err) {
      setError(err);
    }
  }

  async function update(s: Staff, body: Parameters<typeof api.updateStaff>[1], confirmText?: string) {
    if (confirmText && !window.confirm(confirmText)) return;
    setError(null);
    setNotice(null);
    try {
      if (body.role === "admin" && s.role !== "admin") {
        // Two-person rule: promotion to administrator is a request a second administrator must approve.
        await api.requestRoleChange(s.user_id, "admin");
        setNotice(`Role request created for ${s.full_name}. Another administrator must approve it.`);
        await roleRequests.reload();
        return;
      }
      const updated = await api.updateStaff(s.user_id, body);
      staff.setData(staff.data?.map((x) => (x.user_id === updated.user_id ? updated : x)));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <h1>Team</h1>
      <Invite wards={wards.data ?? []} onInvited={() => void staff.reload()} />
      {/* client-side filter only: names/emails are never sent in a query string */}
      <SearchFilterBar search={search} onSearch={setSearch} placeholder="Filter by name or email">
        <label className="inline">
          Role
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
            <option value="">All roles</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
      </SearchFilterBar>
      <ErrorMessage error={error ?? staff.error} onRetry={staff.reload} />
      {notice && <p role="status">{notice}</p>}
      {(roleRequests.data ?? []).filter((r) => r.status === "pending").length > 0 && (
        <div className="card">
          <h2>Pending role requests</h2>
          <ul className="list">
            {(roleRequests.data ?? [])
              .filter((r) => r.status === "pending")
              .map((r) => {
                const target = staff.data?.find((x) => x.user_id === r.target_user_id);
                const mine = r.requested_by === me?.user_id;
                return (
                  <li key={r.id} className="row spread">
                    <span>
                      {target?.full_name ?? "Staff member"} → {ROLE_LABELS[r.new_role]} · requested {formatDateTime(r.requested_at)}
                    </span>
                    {mine ? (
                      <span className="muted small">Awaiting another administrator</span>
                    ) : (
                      <button
                        type="button"
                        className="secondary"
                        onClick={async () => {
                          if (!window.confirm(`Approve ${target?.full_name ?? "this"} as ${ROLE_LABELS[r.new_role]}?`)) return;
                          setError(null);
                          try {
                            const updated = await api.approveRoleRequest(r.id);
                            staff.setData(staff.data?.map((x) => (x.user_id === updated.user_id ? updated : x)));
                            await roleRequests.reload();
                          } catch (err) {
                            setError(err);
                          }
                        }}
                      >
                        Approve
                      </button>
                    )}
                  </li>
                );
              })}
          </ul>
        </div>
      )}
      {staff.loading && !staff.data && <LoadingState />}
      {staff.data && (
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Wards</th>
              <th>Last sign-in</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const self = s.user_id === me?.user_id;
              return (
                <tr key={s.user_id} className={s.is_active ? "" : "row-muted"}>
                  <td className="strong">{s.full_name}</td>
                  <td>{s.email}</td>
                  <td>
                    <select
                      aria-label={`Role for ${s.full_name}`}
                      value={s.role}
                      disabled={self}
                      onChange={(e) =>
                        update(s, { role: e.target.value as Role }, `Change ${s.full_name}'s role to ${ROLE_LABELS[e.target.value as Role]}?`)
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABELS[r]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <WardPicker
                      wards={wards.data ?? []}
                      value={s.ward_ids}
                      label={s.ward_ids.map(wardName).join(", ") || "None"}
                      onSave={(ids) => update(s, { ward_ids: ids })}
                    />
                  </td>
                  <td>{formatDateTime(s.last_login_at)}</td>
                  <td>
                    {s.is_active ? "Active" : "Deactivated"}{" "}
                    {!self && (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() =>
                          update(
                            s,
                            { is_active: !s.is_active },
                            s.is_active ? `Deactivate ${s.full_name}? Their account will be blocked in the identity service: they will be signed out and unable to sign in.` : `Reactivate ${s.full_name}?`,
                          )
                        }
                      >
                        {s.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    )}{" "}
                    {!self && s.is_active && (
                      <button type="button" className="secondary" onClick={() => void unlock(s)}>
                        Unlock sign-in
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function WardPicker({
  wards,
  value,
  label,
  onSave,
}: {
  wards: { id: string; name: string }[];
  value: string[];
  label: string;
  onSave: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(value);
  if (!open)
    return (
      <button
        type="button"
        className="link"
        onClick={() => {
          setSelected(value);
          setOpen(true);
        }}
      >
        {label}
      </button>
    );
  return (
    <div className="stack small-gap">
      {wards.map((w) => (
        <label key={w.id} className="checkbox">
          <input
            type="checkbox"
            checked={selected.includes(w.id)}
            onChange={(e) => setSelected(e.target.checked ? [...selected, w.id] : selected.filter((x) => x !== w.id))}
          />
          {w.name}
        </label>
      ))}
      <div className="row">
        <button
          type="button"
          onClick={() => {
            onSave(selected.slice(0, 10));
            setOpen(false);
          }}
        >
          Save
        </button>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Invite({ wards, onInvited }: { wards: { id: string; name: string }[]; onInvited: () => void }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("nurse");
  const [wardIds, setWardIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      // The API answers {detail} identically for new and existing addresses; the UI shows one fixed message.
      await api.inviteStaff({ email: canonicalEmail(email), full_name: fullName.trim(), role, ward_ids: wardIds });
      onInvited();
      setDone(INVITE_SENT);
      setEmail("");
      setFullName("");
      setWardIds([]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="card">
      <summary className="strong">Invite a team member</summary>
      <form onSubmit={submit}>
        <ErrorMessage error={error} />
        <div className="grid two">
          <label>
            Work email
            <input type="email" required maxLength={254} autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Full name
            <input required maxLength={120} autoComplete="off" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {humanize(ROLE_LABELS[r])}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Wards</legend>
            {wards.map((w) => (
              <label key={w.id} className="checkbox">
                <input
                  type="checkbox"
                  checked={wardIds.includes(w.id)}
                  onChange={(e) => setWardIds(e.target.checked ? [...wardIds, w.id] : wardIds.filter((x) => x !== w.id))}
                />
                {w.name}
              </label>
            ))}
          </fieldset>
        </div>
        <button type="submit" disabled={busy || !email || !fullName}>
          {busy ? "Sending…" : "Send invitation"}
        </button>
        {done && <p role="status">{done}</p>}
      </form>
    </details>
  );
}
