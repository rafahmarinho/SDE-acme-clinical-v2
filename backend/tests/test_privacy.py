"""Privacy tests (skills/privacy): review/update (T177/T238/T743), notice before use (T239/T751/T752),
access/export (T740/T741), erasure (T179/T240), retention (T607/T735), de-identification and
pseudonymisation (T545/T745), data classification (T313/T314).

No database is available: the routers' `transaction` / `fetch_*` helpers are replaced by a recording fake,
Supabase HTTP calls by httpx.MockTransport, and database behaviour is verified statically against the
migrations (the SQL is the control; supabase/migrations/0007_privacy.sql).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from app.routers import profile as profile_router
from app.routers import settings as settings_router
from app.services import privacy
from tests.conftest import add_identity, make_token

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
ALL_SQL = "\n".join(re.sub(r"--[^\n]*", "", p.read_text(encoding="utf-8")) for p in MIGRATIONS)
PRIVACY_SQL = re.sub(r"--[^\n]*", "", (ROOT / "supabase" / "migrations" / "0007_privacy.sql").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "security" / "data-classification.md").read_text(encoding="utf-8")
PRIVACY_DOC = (ROOT / "docs" / "security" / "privacy.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- fakes
class Conn:
    def __init__(self, db: "DB"):
        self.db = db

    async def execute(self, sql, params=()):
        self.db.calls.append(("execute", sql, params))


class DB:
    """Records statements; `handlers` maps an SQL substring to the rows (list) or row (dict/None) returned."""

    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.handlers: dict[str, object] = {}

    def _match(self, sql: str):
        for key, value in self.handlers.items():
            if key in sql:
                return value(sql) if callable(value) else value
        return None

    @asynccontextmanager
    async def transaction(self, principal, read_only=False):
        yield Conn(self)

    async def fetch_all(self, conn, sql, params=()):
        self.calls.append(("all", sql, params))
        return list(self._match(sql) or [])

    async def fetch_one(self, conn, sql, params=()):
        self.calls.append(("one", sql, params))
        return self._match(sql)

    def statements(self, kind: str | None = None) -> list[str]:
        return [s for k, s, _ in self.calls if kind is None or k == kind]


@pytest.fixture
def db(monkeypatch):
    fake = DB()
    for module in (profile_router, settings_router):
        for attr in ("transaction", "fetch_all", "fetch_one"):
            monkeypatch.setattr(module, attr, getattr(fake, attr))
    monkeypatch.setattr("app.db.transaction", fake.transaction)
    return fake


@pytest.fixture
def audited(monkeypatch):
    events: list[tuple[str, str, dict]] = []

    async def record(principal, action, entity_type, entity_id=None, **kw):
        events.append((action, kw.get("outcome", "success"), kw.get("details") or {}))

    for module in (profile_router, settings_router):
        monkeypatch.setattr(module, "record_event", record)
    return events


def headers_for(identities, role: str, *, fresh: bool = True) -> tuple[str, dict[str, str]]:
    uid = add_identity(identities, role)
    ts = int(time.time()) - (0 if fresh else 3600)
    token = make_token(uid, aal="aal2" if role == "admin" else "aal1", amr=[{"method": "password", "timestamp": ts}])
    return uid, {"Authorization": f"Bearer {token}"}


def me_row(uid: str, **overrides) -> dict:
    row = {"user_id": uid, "email": "nurse@example.test", "full_name": "Nurse Example", "role": "nurse",
           "previous_login_at": None, "privacy_notice_accepted_at": None, "privacy_notice_version": None,
           "session_idle_minutes": 15, "ward_ids": [], "erasure_requested_at": None}
    row.update(overrides)
    return row


def mock_supabase(monkeypatch, handler):
    def client():
        return httpx.AsyncClient(base_url="https://test-project.supabase.co", transport=httpx.MockTransport(handler))

    monkeypatch.setattr(privacy, "_supabase_client", client)


# =========================================================================== T177 / T238 / T743 review & update
def test_t238_profile_shows_every_staff_personal_field(client, identities, db):
    uid, h = headers_for(identities, "nurse")
    db.handlers["from public.staff_profiles sp"] = me_row(uid, privacy_notice_version=privacy.PRIVACY_NOTICE_VERSION)
    body = client.get("/v1/me", headers=h).json()
    assert {"user_id", "email", "full_name", "role", "ward_ids", "previous_login_at", "privacy_notice_accepted_at",
            "privacy_notice_version", "privacy_notice_required", "erasure_requested_at"} <= body.keys()
    assert body["privacy_notice_required"] is False


def test_t238_profile_requires_authentication(client):
    assert client.get("/v1/me").status_code == 401
    assert client.patch("/v1/me", json={"full_name": "X"}).status_code == 401


def test_t177_update_name_is_persisted_and_audited(client, identities, db, audited):
    uid, h = headers_for(identities, "nurse")
    db.handlers["from public.staff_profiles sp"] = me_row(uid, privacy_notice_version=privacy.PRIVACY_NOTICE_VERSION)
    r = client.patch("/v1/me", json={"full_name": "Alex Grey"}, headers=h)
    assert r.status_code == 200
    update = [c for c in db.calls if c[0] == "execute" and "update public.staff_profiles set full_name" in c[1]]
    assert update and update[0][2] == ("Alex Grey", uid)  # own row only, id from the token
    assert ("profile.updated", "success", {"fields": ["full_name"]}) in audited


@pytest.mark.parametrize("payload", [{"full_name": ""}, {"full_name": "A" * 500}, {"full_name": "<script>x</script>"},
                                     {"full_name": "Sam", "role": "admin"}, {"full_name": "Sam", "email": "x@y.z"},
                                     {"full_name": "Sam", "user_id": str(uuid.uuid4())}])
def test_t743_invalid_or_tampered_profile_values_are_rejected(client, identities, db, payload):
    _, h = headers_for(identities, "nurse")
    assert client.patch("/v1/me", json=payload, headers=h).status_code == 422
    assert not db.statements("execute")


def test_t743_database_enforces_accuracy_and_consistency():
    assert "monitor_assignments_active_monitor" in ALL_SQL and "where unassigned_at is null" in ALL_SQL
    assert re.search(r"author_id uuid not null references public\.staff_profiles\(user_id\) on delete restrict", ALL_SQL)
    assert "created_at timestamptz not null default now()" in ALL_SQL  # server-assigned timestamps
    assert "staff_profiles_email_canonical" in ALL_SQL
    assert "check (char_length(full_name) between 1 and 120)" in ALL_SQL


def test_t177_email_change_goes_through_confirmed_supabase_flow():
    assert "create trigger acme_sync_staff_email after update of email on auth.users" in PRIVACY_SQL
    profile_tsx = (ROOT / "frontend" / "src" / "screens" / "Profile.tsx").read_text(encoding="utf-8")
    assert "supabase.auth.updateUser({ email" in profile_tsx


# =========================================================================== T239 / T751 / T752 notice before use
def test_t239_profile_changes_blocked_until_current_notice_acknowledged(client, identities, db):
    uid, h = headers_for(identities, "nurse")
    db.handlers["from public.staff_profiles sp"] = me_row(uid, privacy_notice_version=None)
    r = client.patch("/v1/me", json={"full_name": "Alex Grey"}, headers=h)
    assert r.status_code == 409
    assert not [c for c in db.calls if c[0] == "execute" and "set full_name" in c[1]]


def test_t752_new_notice_version_re_prompts_users(client, identities, db):
    uid, h = headers_for(identities, "nurse")
    db.handlers["from public.staff_profiles sp"] = me_row(uid, privacy_notice_version="2020-01-01",
                                                          privacy_notice_accepted_at="2020-01-01T00:00:00Z")
    body = client.get("/v1/me", headers=h).json()
    assert body["privacy_notice_required"] is True
    assert body["privacy_notice_current_version"] == privacy.PRIVACY_NOTICE_VERSION


def test_t239_acknowledgement_records_version_and_evidence(client, identities, db, audited):
    uid, h = headers_for(identities, "nurse")
    r = client.post("/v1/me/privacy-notice", json={"notice_version": privacy.PRIVACY_NOTICE_VERSION}, headers=h)
    assert r.status_code == 204
    sqls = db.statements("execute")
    assert any("privacy_notice_version = %s" in s for s in sqls)
    assert any("insert into public.privacy_consents" in s for s in sqls)
    assert ("privacy.notice_accepted", "success", {"notice_version": privacy.PRIVACY_NOTICE_VERSION}) in audited


def test_t239_acknowledging_an_outdated_notice_is_refused(client, identities, db):
    _, h = headers_for(identities, "nurse")
    r = client.post("/v1/me/privacy-notice", json={"notice_version": "2020-01-01"}, headers=h)
    assert r.status_code == 409
    assert not db.statements("execute")


def test_t751_notice_content_covers_required_elements_and_matches_frontend():
    for key in ("purposes", "categories", "recipients", "retention", "rights", "legal_basis"):
        assert privacy.PRIVACY_NOTICE[key], key
    profile_tsx = (ROOT / "frontend" / "src" / "screens" / "Profile.tsx").read_text(encoding="utf-8")
    version = re.search(r'export const PRIVACY_NOTICE_VERSION = "([0-9-]+)"', profile_tsx).group(1)
    assert version == privacy.PRIVACY_NOTICE_VERSION
    for item in privacy.PRIVACY_NOTICE["recipients"]:
        assert item in profile_tsx


def test_t752_consent_evidence_table_exists_with_rls():
    assert "create table if not exists public.privacy_consents" in PRIVACY_SQL
    assert "alter table public.privacy_consents force row level security" in PRIVACY_SQL
    assert "unique (user_id, notice_version)" in PRIVACY_SQL


# =========================================================================== T740 / T741 access & portability
REQUIRED_PROCESSING = {"purposes", "recipients", "retention", "source", "automated_decisions", "withheld"}


def _export_handlers(db: DB, uid: str) -> None:
    db.handlers.update({
        "from public.staff_profiles where user_id": {"user_id": uid, "email": "nurse@example.test", "full_name": "Nurse",
                                                     "role": "nurse", "is_active": True},
        "from public.staff_ward_assignments a": [{"ward_id": str(uuid.uuid4()), "code": "ICU-A", "name": "Intensive Care A"}],
        "from public.privacy_consents": [{"notice_version": privacy.PRIVACY_NOTICE_VERSION, "accepted_at": "2026-11-01T00:00:00Z"}],
        "my_authored_record_refs": [{"kind": "observation", "record_id": str(uuid.uuid4()), "recorded_at": "2026-11-02T00:00:00Z"},
                                    {"kind": "alarm_acknowledgement", "record_id": str(uuid.uuid4()), "recorded_at": None}],
        "data_retention_days": {"data_retention_days": 365},
    })


def test_t741_export_requires_reauthentication(client, identities, db, monkeypatch):
    _, h = headers_for(identities, "nurse")
    assert client.post("/v1/me/export", json={}, headers=h).status_code == 422

    async def wrong(email, password):
        return False

    monkeypatch.setattr(privacy, "verify_password", wrong)
    r = client.post("/v1/me/export", json={"reauthentication": "not-my-password"}, headers=h)
    assert r.status_code == 400
    assert not [c for c in db.calls if "staff_profiles" in c[1]]


def test_t741_export_is_complete_machine_readable_and_scoped(client, identities, db, audited, monkeypatch):
    uid, h = headers_for(identities, "nurse")
    _export_handlers(db, uid)
    seen = {}

    async def ok(email, password):
        seen["email"] = email
        return True

    monkeypatch.setattr(privacy, "verify_password", ok)
    r = client.post("/v1/me/export", json={"reauthentication": "correct horse"}, headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["cache-control"] == "no-store"
    assert "attachment" in r.headers["content-disposition"]
    body = json.loads(r.content)
    assert body["format"] == "acme-clinical-personal-data/v1"
    assert body["profile"]["email"] == "nurse@example.test"
    assert REQUIRED_PROCESSING <= body["processing"].keys()
    assert len(body["observations_authored"]) == 1 and len(body["alarm_acknowledgements"]) == 1
    assert "body" not in json.dumps(body["observations_authored"])  # clinical text withheld, reference only
    # every classified staff data category is represented
    for section in ("profile", "ward_assignments", "privacy_notice_acknowledgements", "privacy_requests", "sessions",
                    "observations_authored", "alarm_acknowledgements", "maintenance_performed", "files_uploaded",
                    "emergency_access_grants", "audit_events"):
        assert section in body
    # scoped: every parameterised query is bound to the caller's own id
    for kind, sql, params in db.calls:
        if params:
            assert params == (uid,), (sql, params)
    assert seen["email"] == "nurse@example.test"
    assert ("privacy.data_exported", "success", {"method": "password"}) in audited


def test_t740_get_export_needs_a_recent_sign_in(client, identities, db):
    _, stale = headers_for(identities, "nurse", fresh=False)
    assert client.get("/v1/me/export", headers=stale).status_code == 401


@pytest.mark.asyncio
async def test_t740_password_check_does_not_keep_a_session(monkeypatch):
    calls: list[tuple[str, str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path + ("?" + req.url.query.decode() if req.url.query else "")))
        if req.url.path == "/auth/v1/token":
            return httpx.Response(200, json={"access_token": "verification-session"})
        return httpx.Response(204)

    mock_supabase(monkeypatch, handler)
    assert await privacy.verify_password("nurse@example.test", "pw") is True
    assert calls[0] == ("POST", "/auth/v1/token?grant_type=password")
    assert calls[1] == ("POST", "/auth/v1/logout?scope=local")  # verification session revoked at once
    assert await privacy.verify_password("nurse@example.test", "") is False


# =========================================================================== T179 / T240 erasure
def test_t240_erasure_request_requires_password_and_typed_confirmation(client, identities, db, audited, monkeypatch):
    _, h = headers_for(identities, "nurse")
    assert client.post("/v1/me/erasure-request", json={"confirm_text": "DELETE MY ACCOUNT"}, headers=h).status_code == 422
    assert client.post("/v1/me/erasure-request", json={"reauthentication": "pw", "confirm_text": "yes"},
                       headers=h).status_code == 422

    async def wrong(email, password):
        return False

    monkeypatch.setattr(privacy, "verify_password", wrong)
    assert client.post("/v1/me/erasure-request", json={"reauthentication": "pw", "confirm_text": "DELETE MY ACCOUNT"},
                       headers=h).status_code == 400
    assert not db.calls
    assert ("privacy.reauth_failed", "denied", {"purpose": "erasure"}) in audited


def test_t179_erasure_request_is_created_and_audited(client, identities, db, audited, monkeypatch):
    uid, h = headers_for(identities, "physician")
    rid = str(uuid.uuid4())
    db.handlers["insert into public.privacy_requests"] = {"id": rid, "status": "pending", "requested_at": "2026-11-12T00:00:00Z"}

    async def ok(email, password):
        return True

    monkeypatch.setattr(privacy, "verify_password", ok)
    r = client.post("/v1/me/erasure-request", json={"reauthentication": "pw", "confirm_text": "DELETE MY ACCOUNT"}, headers=h)
    assert r.status_code == 202 and r.json()["id"] == rid
    insert = next(c for c in db.calls if "insert into public.privacy_requests" in c[1])
    assert insert[2] == (uid,)
    assert ("privacy.erasure_requested", "success", {}) in audited


@pytest.mark.parametrize("role", ["nurse", "physician", "biomed_tech"])
def test_t179_only_administrators_process_erasure(client, identities, db, role):
    _, h = headers_for(identities, role)
    rid = uuid.uuid4()
    assert client.get("/v1/settings/privacy-requests", headers=h).status_code == 403
    assert client.post(f"/v1/settings/privacy-requests/{rid}/complete", json={"confirm_text": "ERASE"},
                       headers=h).status_code == 403
    assert client.post(f"/v1/settings/privacy-requests/{rid}/reject", headers=h).status_code == 403


def test_t179_admin_cannot_complete_own_request(client, identities, db):
    uid, h = headers_for(identities, "admin")
    db.handlers["from public.privacy_requests r"] = {"user_id": uuid.UUID(uid)}
    r = client.post(f"/v1/settings/privacy-requests/{uuid.uuid4()}/complete", json={"confirm_text": "ERASE"}, headers=h)
    assert r.status_code == 403
    assert not [c for c in db.calls if "complete_erasure_request" in c[1]]


def test_t240_completion_pseudonymises_profile_and_scrubs_identity(client, identities, db, audited, monkeypatch):
    _, h = headers_for(identities, "admin")
    subject = uuid.uuid4()
    db.handlers["from public.privacy_requests r"] = {"user_id": subject}
    db.handlers["complete_erasure_request"] = {"user_id": subject}
    scrubbed: list[uuid.UUID] = []

    async def scrub(user_id):
        scrubbed.append(user_id)
        return True

    monkeypatch.setattr(privacy, "scrub_auth_identity", scrub)
    rid = uuid.uuid4()
    assert client.post(f"/v1/settings/privacy-requests/{rid}/complete", json={"confirm_text": "nope"},
                       headers=h).status_code == 422
    r = client.post(f"/v1/settings/privacy-requests/{rid}/complete", json={"confirm_text": "ERASE"}, headers=h)
    assert r.status_code == 200 and r.json()["identity_provider_scrubbed"] is True
    assert scrubbed == [subject]
    assert ("privacy.erasure_completed", "success", {}) in audited


@pytest.mark.asyncio
async def test_t240_identity_scrub_removes_email_and_bans_the_auth_user(monkeypatch):
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"], seen["path"], seen["body"] = req.method, req.url.path, json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={})

    mock_supabase(monkeypatch, handler)
    uid = uuid.uuid4()
    assert await privacy.scrub_auth_identity(uid) is True
    assert seen["method"] == "PUT" and seen["path"] == f"/auth/v1/admin/users/{uid}"
    assert seen["body"]["email"] == f"erased-{uid.hex}@erased.invalid"
    assert seen["body"]["ban_duration"] and seen["body"]["user_metadata"] == {}
    assert seen["auth"] == "Bearer service-test-key"  # server-only key, never sent by the browser


def test_t179_database_erasure_keeps_clinical_records_pseudonymised():
    fn = re.search(r"function public\.pseudonymise_staff\(p_user uuid\)(.*?)end \$\$", PRIVACY_SQL, re.S).group(1)
    assert "set full_name = 'Erased user'" in fn and "@erased.invalid" in fn
    for column in ("previous_login_ip = null", "last_login_ip = null", "is_active = false", "erased_at = now()"):
        assert column in fn
    assert "delete from public.staff_ward_assignments" in fn
    complete = re.search(r"function public\.complete_erasure_request\(p_request uuid\)(.*?)end \$\$", PRIVACY_SQL, re.S).group(1)
    assert "has_permission('staff:manage')" in complete and "subject = public.current_staff_id()" in complete
    assert "check (decided_by is null or decided_by <> user_id)" in PRIVACY_SQL
    # clinical records reference the random profile UUID and are never cascaded away
    assert re.search(r"author_id uuid not null references public\.staff_profiles\(user_id\) on delete restrict", ALL_SQL)
    assert "erasure" in PRIVACY_DOC.lower() and "health-record" in PRIVACY_DOC.lower()


# =========================================================================== T607 / T735 retention
def _purge_fn() -> str:
    return re.search(r"function public\.run_retention_purge\(p_source text default 'manual'\)(.*?)end \$\$",
                     PRIVACY_SQL, re.S).group(1)


def test_t607_purge_function_is_privileged_bounded_and_skips_legal_hold():
    fn = _purge_fn()
    assert "security definer set search_path = public, pg_temp" in fn
    assert "has_permission('settings:manage')" in fn
    assert "data_retention_days" in fn
    assert "p.retention_until < current_date and not p.legal_hold" in fn
    assert "delete from public.readings" in fn and "rd.recorded_at < cutoff" in fn
    assert "a.state = 'resolved' and a.resolved_at < cutoff" in fn
    assert "pseudonymise_staff" in fn and "sp.deactivated_at < cutoff" in fn
    assert "insert into public.storage_purge_queue" in fn  # files are removed too
    assert "revoke execute on function public.run_retention_purge(text) from public, anon, authenticated" in PRIVACY_SQL


def test_t735_purge_log_holds_counts_only_and_job_is_scheduled():
    table = re.search(r"create table if not exists public\.purge_log \((.*?)\n\);", PRIVACY_SQL, re.S).group(1)
    columns = {line.split()[0] for line in table.strip().splitlines()}
    assert columns == {"id", "run_at", "run_source", "counts"}
    assert "jsonb_build_object('patients', n_patients" in _purge_fn()
    assert "cron.schedule('acme-retention-purge'" in PRIVACY_SQL


@pytest.mark.parametrize("role", ["nurse", "physician", "biomed_tech"])
def test_t607_retention_controls_are_admin_only(client, identities, db, role):
    _, h = headers_for(identities, role)
    assert client.get("/v1/settings/retention", headers=h).status_code == 403
    assert client.post("/v1/settings/retention/run", json={"confirm_text": "PURGE EXPIRED DATA"}, headers=h).status_code == 403


def test_t735_manual_purge_runs_function_removes_files_and_audits_counts(client, identities, db, audited, monkeypatch):
    _, h = headers_for(identities, "admin")
    counts = {"patients": 1, "files_queued": 2, "readings": 30, "alarms": 4, "staff_pseudonymised": 1, "retention_days": 365}
    db.handlers["run_retention_purge('manual')"] = {"counts": counts}
    db.handlers["count(*)::int as n from public.storage_purge_queue"] = {"n": 0}

    async def drain(conn, limit=100):
        return 2

    monkeypatch.setattr(privacy, "drain_storage_queue", drain)
    assert client.post("/v1/settings/retention/run", json={"confirm_text": "purge"}, headers=h).status_code == 422
    r = client.post("/v1/settings/retention/run", json={"confirm_text": "PURGE EXPIRED DATA"}, headers=h)
    assert r.status_code == 200
    assert r.json() == {"counts": counts, "files_removed": 2, "files_pending_removal": 0}
    action, outcome, details = next(e for e in audited if e[0] == "privacy.retention_purged")
    assert all(isinstance(v, int) for v in details.values())  # counts only, no personal data


@pytest.mark.asyncio
async def test_t735_storage_objects_of_purged_patients_are_deleted(monkeypatch):
    path = f"patients/{uuid.uuid4()}/{uuid.uuid4()}.pdf"
    deleted: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        deleted.append(req.url.path)
        return httpx.Response(200, json={})

    mock_supabase(monkeypatch, handler)

    async def claim(conn, sql, params=()):
        assert "claim_storage_purge_batch" in sql
        return [{"object_path": path}]

    monkeypatch.setattr(privacy, "fetch_all", claim)
    assert await privacy.drain_storage_queue(object()) == 1
    assert deleted == [f"/storage/v1/object/clinical-files/{path}"]

    mock_supabase(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(privacy.StoragePurgeIncomplete):  # rolls the claim back: retried next run
        await privacy.drain_storage_queue(object())


def test_t735_retention_schedule_and_backup_window_documented():
    lowered = DOC.lower()
    for phrase in ("retention", "backup", "point-in-time", "legal hold", "purge_log", "third part"):
        assert phrase in lowered, phrase
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/security/data-classification.md" in readme


# =========================================================================== T545 / T745 de-identification
REPORTING_VIEWS = re.findall(r"create or replace view reporting\.(\w+) as(.*?);", PRIVACY_SQL, re.S)
IDENTIFIERS = ("patient_id", "pseudonym", "display_name", "birth_year", "bed_id", "full_name", "email")


def test_t545_reporting_views_are_aggregated_and_suppress_small_cells():
    assert {name for name, _ in REPORTING_VIEWS} == {"ward_alarm_daily", "ward_vitals_daily"}
    for name, body in REPORTING_VIEWS:
        select_list = body.split(" from ")[0]
        for ident in IDENTIFIERS:
            assert ident not in select_list, (name, ident)
        assert "group by" in body and re.search(r"having count\((\*|distinct r\.patient_id)\) >= 5", body), name
        assert "date_trunc('day'" in body  # timestamps generalised to the day


def test_t745_reporting_role_cannot_read_patient_linked_rows():
    assert "revoke select on public.alarms, public.readings from acme_reporting" in PRIVACY_SQL
    grants = [re.sub(r"\s+", " ", s) for s in ALL_SQL.lower().split(";") if s.strip().startswith("grant ")]
    for g in grants:
        target = g.rsplit(" to ", 1)[-1]
        if " on public.patients" in g or "public.patients," in g:
            assert "authenticated" not in target and "acme_reporting" not in target, g


def test_t745_browser_and_device_roles_cannot_re_identify(client, identities):
    for role in ("biomed_tech",):
        _, h = headers_for(identities, role)
        assert client.get("/v1/patients", headers=h).status_code == 403
    # Realtime feeds (readings/alarms) carry the patient UUID and vitals only, never names
    readings_grant = re.search(r"grant select \(([^)]*)\)\s+on public\.readings to authenticated", ALL_SQL).group(1)
    assert "name" not in readings_grant and "pseudonym" not in readings_grant


def test_t545_statistics_helpers_and_ward_report_hold_no_identifiers():
    assert privacy.suppress_small_counts({"low_spo2": 3, "low_battery": 7}) == {"low_spo2": None, "low_battery": 7}
    src = (ROOT / "backend" / "app" / "services" / "reports.py").read_text(encoding="utf-8")
    returned = re.search(r"return \{(.*?)\n    \}", src, re.S).group(1)
    for ident in ("display_name", "pseudonym", "full_name", "email", "body"):
        assert ident not in returned


# =========================================================================== T313 / T314 classification
def _personal_tables() -> dict[str, set[str]]:
    tables = ("staff_profiles", "patients", "observations", "readings", "alarms", "attachments", "break_glass_grants",
              "privacy_consents", "privacy_requests")
    out: dict[str, set[str]] = {}
    for t in tables:
        m = re.search(rf"create table (?:if not exists )?public\.{t} \((.*?)\n\);", ALL_SQL, re.S)
        assert m, t
        cols = set()
        for line in m.group(1).splitlines():
            word = line.strip().split(" ")[0].strip(",")
            if word and word.lower() not in ("check", "unique", "primary", "constraint", "foreign", "") and line.startswith("  "):
                if re.fullmatch(r"[a-z_]+", word):
                    cols.add(word)
        cols |= set(re.findall(rf"alter table public\.{t} add column if not exists (\w+)", ALL_SQL))
        out[t] = cols
    return out


LABELS = dict(((t, c), cls) for t, c, cls in
              re.findall(r"comment on column public\.(\w+)\.(\w+) is 'class=([A-Za-z]+)", ALL_SQL))


def test_t314_every_column_of_personal_data_tables_is_classified():
    missing = [f"{t}.{c}" for t, cols in _personal_tables().items() for c in sorted(cols) if (t, c) not in LABELS]
    assert missing == [], "add `comment on column ... is 'class=...'` and document it: " + ", ".join(missing)
    assert set(LABELS.values()) <= {"PII", "PHI", "Internal", "Public", "Confidential", "Secret"}


def test_t314_document_and_schema_labels_are_consistent():
    for (table, column), cls in LABELS.items():
        if cls in ("PII", "PHI"):
            assert f"`{table}.{column}`" in DOC, f"{table}.{column} ({cls}) missing from data-classification.md"
    documented = set(re.findall(r"`(\w+)\.(\w+)`", DOC))
    for table, column in documented:
        if table in _personal_tables():
            assert (table, column) in LABELS, f"{table}.{column} documented but not labelled in a migration"
    for item in ("clinical-files", "supabase_realtime", "readings", "alarms", "monitors", "logs"):
        assert item in DOC, item


def test_t314_phi_and_pii_tables_have_rls():
    for table in _personal_tables():
        assert (f"'{table}'" in ALL_SQL and "force row level security" in ALL_SQL) or \
            f"alter table public.{table} force row level security" in ALL_SQL, table


# =========================================================================== T178 / T604 consent and withdrawal
CONSENT_SQL = re.sub(r"--[^\n]*", "", (ROOT / "supabase" / "migrations" / "0013_consent_and_restriction.sql")
                     .read_text(encoding="utf-8"))


class ConsentDB(DB):
    """DB fake with a tiny in-memory consent_grants table (the SQL itself is checked statically below)."""

    def __init__(self):
        super().__init__()
        self.grants: list[dict] = []

    def _active(self, purpose: str) -> dict | None:
        return next((g for g in self.grants if g["purpose"] == purpose and g["withdrawn_at"] is None), None)

    async def fetch_one(self, conn, sql, params=()):
        self.calls.append(("one", sql, params))
        if "has_active_consent" in sql:
            return {"ok": self._active(params[1]) is not None}
        if "from public.consent_grants where user_id = %s and purpose = %s and withdrawn_at is null" in sql:
            return self._active(params[1])
        if "insert into public.consent_grants" in sql:
            row = {"id": uuid.uuid4(), "purpose": params[1], "notice_version": params[2], "language": params[3],
                   "request_id": params[4], "granted_at": "2026-11-12T10:00:00Z", "withdrawn_at": None}
            self.grants.append(row)
            return row
        if "update public.consent_grants set withdrawn_at" in sql:
            row = self._active(params[2])
            if row:
                row["withdrawn_at"] = "2026-11-12T11:00:00Z"
                return {"id": row["id"]}
            return None
        return self._match(sql)

    async def fetch_all(self, conn, sql, params=()):
        self.calls.append(("all", sql, params))
        if "from public.consent_grants where user_id" in sql:
            return [dict(g) for g in self.grants]
        return list(self._match(sql) or [])


@pytest.fixture
def cdb(monkeypatch):
    from app.services import consent

    fake = ConsentDB()
    for module in (profile_router, consent):
        for attr in ("transaction", "fetch_all", "fetch_one"):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, getattr(fake, attr))
    monkeypatch.setattr("app.db.transaction", fake.transaction)
    alerts: list[tuple] = []

    async def notify(kind, details=None):
        alerts.append((kind, details))

    monkeypatch.setattr(profile_router, "notify_admins", notify)
    fake.alerts = alerts  # type: ignore[attr-defined]
    return fake


PHONE = {"escalation_phone": "+5511912345678"}
GRANT = {"purpose": "escalation_contact", "notice_version": privacy.PRIVACY_NOTICE_VERSION}


def test_t178_optional_field_refused_without_grant_then_accepted(client, identities, cdb, audited):
    _, h = headers_for(identities, "nurse")
    r = client.put("/v1/me/escalation-contact", json=PHONE, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "consent_required"
    assert not [s for s in cdb.statements("execute") if "staff_optional_contacts" in s]   # nothing collected
    assert client.post("/v1/me/consents", json=GRANT, headers=h).status_code == 201
    r = client.put("/v1/me/escalation-contact", json=PHONE, headers=h)
    assert r.status_code == 200 and r.json() == PHONE
    assert [s for s in cdb.statements("execute") if "insert into public.staff_optional_contacts" in s]
    assert client.put("/v1/me/escalation-contact", json={"escalation_phone": "call me"}, headers=h).status_code == 422


def test_t178_grant_stores_purpose_version_language_time_and_request_id_and_is_audited(client, identities, cdb, audited):
    _, h = headers_for(identities, "nurse")
    r = client.post("/v1/me/consents", json=GRANT, headers={**h, "X-Request-Id": "req-consent-0001"})
    assert r.status_code == 201
    grant = cdb.grants[0]
    assert (grant["purpose"], grant["notice_version"], grant["language"], grant["request_id"]) == \
        ("escalation_contact", privacy.PRIVACY_NOTICE_VERSION, "en", "req-consent-0001")
    assert grant["granted_at"]
    assert ("consent.granted", "success", {"purpose": "escalation_contact",
                                           "notice_version": privacy.PRIVACY_NOTICE_VERSION, "language": "en"}) in audited
    purpose = r.json()["purposes"][0]
    assert purpose["active"] is True and purpose["required"] is False
    for field in ("data_categories", "retention", "third_parties", "withdrawal", "description"):
        assert purpose[field], field


def test_t178_consent_needs_the_current_notice_and_a_known_purpose(client, identities, cdb):
    _, h = headers_for(identities, "nurse")
    assert client.post("/v1/me/consents", json={**GRANT, "notice_version": "2020-01-01"}, headers=h).status_code == 409
    assert client.post("/v1/me/consents", json={**GRANT, "purpose": "marketing"}, headers=h).status_code == 422
    listed = client.get("/v1/me/consents", headers=h).json()
    assert all(p["active"] is False for p in listed["purposes"])   # off by default


def test_t178_rls_keeps_consent_grants_private_and_gates_optional_data():
    flat = re.sub(r"\s+", " ", CONSENT_SQL)
    assert "create policy consent_grants_read on public.consent_grants for select to acme_api_rw " \
           "using (user_id = public.current_staff_id())" in flat
    assert "with check (user_id = public.current_staff_id() and withdrawn_at is null)" in flat
    assert "alter table public.consent_grants force row level security" in flat
    insert = flat.split("create policy optional_contacts_insert", 1)[1].split(";", 1)[0]
    assert "public.has_active_consent(user_id, 'escalation_contact')" in insert
    assert "grant select, insert on public.consent_grants to acme_api_rw" in flat
    assert not re.search(r"grant [^;]*(delete)[^;]* on public\.consent_grants", flat)   # evidence is never deleted


def test_t604_withdrawal_keeps_evidence_stops_processing_and_is_audited(client, identities, cdb, audited):
    from app.services import consent

    _, h = headers_for(identities, "nurse")
    client.post("/v1/me/consents", json=GRANT, headers=h)
    client.put("/v1/me/escalation-contact", json=PHONE, headers=h)
    r = client.delete("/v1/me/consents", params={"purpose": "escalation_contact"}, headers=h)
    assert r.status_code == 200 and r.json()["purposes"][0]["active"] is False
    assert len(cdb.grants) == 1 and cdb.grants[0]["withdrawn_at"]               # row kept, withdrawn_at set
    executed = cdb.statements("execute")
    assert "delete from public.staff_optional_contacts where user_id = %s" in executed  # dependent data deleted
    assert ("consent.withdrawn", "success", {"purpose": "escalation_contact"}) in audited
    # time-of-use check: the dependent feature is skipped once consent is gone
    before = len(cdb.calls)
    assert client.get("/v1/me/escalation-contact", headers=h).json() == {"escalation_phone": None}
    assert not [c for c in cdb.calls[before:] if "from public.staff_optional_contacts" in c[1]]
    assert client.put("/v1/me/escalation-contact", json=PHONE, headers=h).status_code == 409
    assert consent.STOP_PROCESSING["escalation_contact"]


def test_t604_withdrawal_scoped_to_the_caller_and_validated(client, identities, cdb):
    _, h = headers_for(identities, "nurse")
    assert client.delete("/v1/me/consents", params={"purpose": "escalation_contact"}, headers=h).status_code == 404
    assert client.delete("/v1/me/consents", params={"purpose": "other"}, headers=h).status_code == 422
    flat = re.sub(r"\s+", " ", CONSENT_SQL)
    withdraw = flat.split("create policy consent_grants_withdraw", 1)[1].split(";", 1)[0]
    assert "using (user_id = public.current_staff_id() and withdrawn_at is null)" in withdraw  # never another user's
    uid = str(next(iter(k for k in identities if k != "__events__")))
    for _, sql, params in cdb.calls:  # every consent statement is bound to the caller's own id
        if "consent_grants" in sql and params:
            assert uid in [str(p) for p in params], sql


def test_t604_export_includes_consent_history_and_erasure_closes_grants():
    fields = profile_router.PersonalDataExport.model_fields
    assert {"consents", "optional_data", "processing_restrictions"} <= fields.keys()
    src = (ROOT / "backend" / "app" / "routers" / "profile.py").read_text(encoding="utf-8")
    build = src.split("async def _build_export", 1)[1].split("\nasync def ", 1)[0]
    assert "from public.consent_grants" in build and "from public.staff_optional_contacts" in build
    trigger = re.sub(r"\s+", " ", CONSENT_SQL).split("create or replace function public.privacy_on_staff_erased()", 1)[1]
    assert "delete from public.staff_optional_contacts where user_id = new.user_id" in trigger
    assert "update public.consent_grants set withdrawn_at = now()" in trigger
    assert "after update of erased_at on public.staff_profiles" in re.sub(r"\s+", " ", CONSENT_SQL)


# =========================================================================== T754 restriction of processing
@pytest.fixture
def staff_db(monkeypatch):
    from app.routers import staff as staff_router

    fake = DB()
    for attr in ("transaction", "fetch_all", "fetch_one"):
        monkeypatch.setattr(staff_router, attr, getattr(fake, attr))
    events: list[tuple] = []

    async def record(principal, action, entity_type, entity_id=None, **kw):
        events.append((action, entity_id, kw.get("details") or {}))

    monkeypatch.setattr(staff_router, "record_event", record)
    fake.events = events  # type: ignore[attr-defined]
    return fake


RESTRICTION_ROW = {"id": uuid.uuid4(), "activity": "staff_activity_report", "basis": "objection",
                   "created_by": uuid.uuid4(), "created_at": "2026-11-12T10:00:00Z", "lifted_by": None, "lifted_at": None}


@pytest.mark.parametrize("role", ["nurse", "physician", "biomed_tech"])
def test_t754_only_administrators_create_or_lift_restrictions(client, identities, staff_db, role):
    target = str(uuid.uuid4())
    _, h = headers_for(identities, role)
    body = {"activity": "staff_activity_report", "basis": "objection"}
    assert client.post(f"/v1/staff/{target}/processing-restrictions", json=body, headers=h).status_code == 403
    assert client.delete(f"/v1/staff/{target}/processing-restrictions", params={"activity": "statistics"},
                         headers=h).status_code == 403
    assert client.get(f"/v1/staff/{target}/processing-restrictions", headers=h).status_code == 403
    assert staff_db.calls == []


def test_t754_restriction_and_lift_are_audited(client, identities, staff_db):
    target = str(uuid.uuid4())
    _, h = headers_for(identities, "admin")
    staff_db.handlers = {"select 1 from public.staff_profiles": {"?column?": 1},
                         "insert into public.processing_restrictions": RESTRICTION_ROW,
                         "update public.processing_restrictions": {"id": RESTRICTION_ROW["id"]}}
    r = client.post(f"/v1/staff/{target}/processing-restrictions",
                    json={"activity": "staff_activity_report", "basis": "objection"}, headers=h)
    assert r.status_code == 201, r.text
    r = client.delete(f"/v1/staff/{target}/processing-restrictions", params={"activity": "staff_activity_report"},
                      headers=h)
    assert r.status_code == 204
    assert ("privacy.processing_restricted", target, {"activity": "staff_activity_report", "basis": "objection"}) \
        in staff_db.events
    assert ("privacy.restriction_lifted", target, {"activity": "staff_activity_report"}) in staff_db.events
    assert client.post(f"/v1/staff/{target}/processing-restrictions", json={"activity": "patient_care",
                                                                          "basis": "objection"}, headers=h).status_code == 422


def test_t754_reports_and_views_skip_restricted_subjects_but_clinical_paths_do_not():
    from app.services import reports

    src = (ROOT / "backend" / "app" / "services" / "reports.py").read_text(encoding="utf-8")
    audit_rows = src.split("async def audit_rows", 1)[1].split("\nasync def ", 1)[0]
    assert "public.processing_allowed('staff', actor_id, 'staff_activity_report')" in audit_rows  # report + CSV
    ward = src.split("async def ward_activity", 1)[1].split("\nasync def ", 1)[0]
    assert "public.processing_allowed('patient', p.id, 'statistics')" in ward
    extract = src.split("async def research_extract", 1)[1]
    assert "public.processing_allowed('patient', p.id, 'research_extract')" in extract
    flat = re.sub(r"\s+", " ", CONSENT_SQL)
    for view in ("reporting.ward_alarm_daily", "reporting.ward_vitals_daily"):
        body = flat.split(f"create or replace view {view} as", 1)[1].split(";", 1)[0]
        assert "r.activity = 'statistics'" in body or "pr.activity = 'statistics'" in body, view
    assert "lifted_at is null" in flat.split("create or replace function public.processing_allowed", 1)[1]
    # clinical care and the audit trail itself are never restricted
    for name in ("patients.py", "alarms.py", "observations.py", "events.py", "break_glass.py"):
        assert "processing_allowed" not in (ROOT / "backend" / "app" / "routers" / name).read_text(encoding="utf-8")
    assert "processing_allowed" not in src.split("def summarize_audit", 1)[1].split("\nasync def audit_summary", 1)[0]
    assert reports.AUDIT_COLUMNS  # the export uses audit_rows, so the same filter applies


def test_t754_audit_report_says_how_many_subjects_were_excluded(client, identities, monkeypatch):
    from app.routers import reports as rep_router
    from app.services import reports

    async def fake_all(conn, sql, params=()):
        return []

    async def fake_one(conn, sql, params=()):
        if "processing_restrictions" in sql:
            return {"n": 2}
        if "verify_event_chain" in sql:
            return {"broken_at": None}
        return {"retry_after": 0}

    async def record(*a, **k):
        return None

    @asynccontextmanager
    async def tx(principal, read_only=False):
        yield Conn(DB())

    monkeypatch.setattr(reports, "fetch_all", fake_all)
    monkeypatch.setattr(reports, "fetch_one", fake_one)
    monkeypatch.setattr(rep_router, "fetch_one", fake_one)
    monkeypatch.setattr(rep_router, "transaction", tx)
    monkeypatch.setattr(rep_router, "record_event", record)
    _, h = headers_for(identities, "admin")
    r = client.get("/v1/reports/audit", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["restricted_subjects_excluded"] == 2


def test_t754_staff_can_see_and_request_restrictions(client, identities, cdb, audited):
    _, h = headers_for(identities, "nurse")
    assert client.get("/v1/me/processing-restrictions", headers=h).json() == {"items": [], "next_offset": None}
    r = client.post("/v1/me/processing-restrictions/request", json={"activity": "statistics"}, headers=h)
    assert r.status_code == 202
    assert ("privacy.restriction_requested", "success", {"activity": "statistics"}) in audited
    assert cdb.alerts and cdb.alerts[0][0] == "processing_restriction_requested"


# =========================================================================== T742 accuracy (duplicates)
def test_t742_duplicate_active_patients_and_occupied_beds_are_refused():
    flat = re.sub(r"\s+", " ", CONSENT_SQL)
    assert "create unique index if not exists patients_one_active_identity on public.patients " \
           "(lower(display_name), birth_year, ward_id) where discharged_at is null" in flat
    assert re.search(r"bed_id uuid unique references public\.beds", ALL_SQL)       # one patient per bed
    assert "monitor_assignments_active_bed" in ALL_SQL                             # one monitor per bed


def test_t742_unique_violation_is_a_generic_409(identities):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from psycopg import errors as pg_errors

    from app.core.errors import install_error_handlers

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/dup")
    async def dup():
        raise pg_errors.UniqueViolation('duplicate key value violates unique constraint "patients_one_active_identity"')

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/dup")
    assert r.status_code == 409 and r.json()["code"] == "conflict"
    assert "patients_one_active_identity" not in r.text and "duplicate key" not in r.text


# =========================================================================== T744 pseudonymised data
def test_t744_pseudonyms_are_not_derived_from_identity_and_mapping_stays_protected():
    seed = (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8")
    codes = re.findall(r"\('(PT-\d{4})', '([^']+)'", seed)
    assert len(codes) == 12 and [c for c, _ in codes] == [f"PT-{i:04d}" for i in range(1, 13)]  # assigned, not hashed
    assert "pseudonym ~ '^PT-[0-9]{4}$'" in ALL_SQL
    grants = [re.sub(r"\s+", " ", s) for s in ALL_SQL.lower().split(";") if s.strip().startswith("grant ")]
    for g in grants:
        if " on public.patients" in g or "public.patients," in g:
            assert not re.search(r"\bto (.*\b)?(anon|authenticated|acme_reporting)\b", g.split(" to ", 1)[1]), g
    assert "alter table public.patients force row level security" in ALL_SQL.lower() or "'patients'" in ALL_SQL


def test_t744_secondary_outputs_carry_no_names_or_pseudonyms():
    from app.services import reports

    assert not {"display_name", "pseudonym", "full_name", "email"} & set(reports.AUDIT_COLUMNS)
    assert not {"display_name", "pseudonym", "birth_year", "bed_label"} & set(reports.EXTRACT_COLUMNS)
    from app.core.audit import ALERT_DETAIL_KEYS

    assert not {"display_name", "pseudonym", "full_name", "email", "mrn", "name"} & ALERT_DETAIL_KEYS


# =========================================================================== T544 / T377 secondary use
def test_t544_csv_export_suppresses_small_counts(client, identities, monkeypatch, tmp_path):
    from app.routers import reports as rep_router
    from app.services import reports

    captured: dict = {}
    real_build = reports.build_csv_export

    def build(columns, rows, writer=None):
        captured["columns"], captured["rows"] = list(columns), list(rows)
        return real_build(columns, captured["rows"])

    async def fake_activity(conn, ward_id, start, end):
        return {"ward_id": None, "period_start": start, "period_end": end, "alarm_counts": {"low_spo2": 3, "tachycardia": 7},
                "mean_time_to_ack_seconds": None, "unacknowledged_high_priority": 0, "readings_count": 0,
                "generated_at": end}

    async def one(conn, sql, params=()):
        return {"retry_after": 0}

    async def record(*a, **k):
        return None

    @asynccontextmanager
    async def tx(principal, read_only=False):
        yield Conn(DB())

    monkeypatch.setattr(reports, "TMP_ROOT", tmp_path / "acme-reports")
    monkeypatch.setattr(rep_router.reports, "build_csv_export", build)
    monkeypatch.setattr(rep_router.reports, "ward_activity", fake_activity)
    monkeypatch.setattr(rep_router, "fetch_one", one)
    monkeypatch.setattr(rep_router, "transaction", tx)
    monkeypatch.setattr(rep_router, "record_event", record)
    _, h = headers_for(identities, "physician")
    r = client.get("/v1/reports/export.csv", params={"kind": "ward_activity"}, headers=h)
    assert r.status_code == 200, r.text
    lines = r.text.strip().splitlines()
    assert "low_spo2," in lines and "tachycardia,7" in lines and "low_spo2,3" not in lines  # 3 is never reported
    for col in captured["columns"]:
        assert not re.search(r"name|pseudonym|birth|bed|email", col), col


def _reading(pid, ward, minute, hr=80):
    from datetime import UTC, datetime, timedelta

    return {"patient_id": pid, "ward_code": ward, "recorded_at": datetime(2026, 11, 12, 8, tzinfo=UTC) + timedelta(minutes=minute),
            "heart_rate": hr, "spo2": 97, "resp_rate": 16, "bp_systolic": 120, "bp_diastolic": 80, "quality": "good",
            "display_name": "Alex Morgan (fictitious)", "pseudonym": "PT-0001", "birth_year": 1956, "ecg": [0.1, 0.2],
            "bed_label": "A01", "object_path": "patients/x/y.pdf", "body": "free text"}


def test_t377_deidentified_extract_drops_phi_and_uses_per_extract_codes():
    from datetime import datetime

    from app.services import reports

    big = [str(uuid.uuid4()) for _ in range(5)]
    small = [str(uuid.uuid4()) for _ in range(2)]
    rows = [_reading(p, "A", m) for p in big for m in (0, 5)] + [_reading(p, "B", 0) for p in small]
    one = reports.deidentify_readings(rows, key=b"k1" * 16, min_subjects=5)
    two = reports.deidentify_readings(rows, key=b"k2" * 16, min_subjects=5)
    assert len(one) == 10                                               # ward B (2 patients) suppressed
    for row in one:
        assert set(row) == set(reports.EXTRACT_COLUMNS)
        assert not set(row) & reports.PHI_DROP
        assert not any(isinstance(v, datetime) for v in row.values())  # offsets, no timestamps
        blob = json.dumps(row)
        assert "PT-0001" not in blob and "Alex" not in blob and "patients/" not in blob and "free text" not in blob
    assert {r["offset_seconds"] for r in one} == {0, 300}
    assert {r["subject"] for r in one}.isdisjoint({r["subject"] for r in two})  # different codes per extract
    assert not {r["subject"] for r in one} & set(big)


def test_t377_extract_endpoint_is_admin_only_and_audited_with_counts(client, identities, monkeypatch):
    from app.routers import reports as rep_router

    audited: list[tuple] = []

    async def fake_extract(conn, start, end, *, min_subjects):
        return [{"subject": "S-1", "ward_code": "A", "offset_seconds": 0, "heart_rate": 80, "spo2": 97, "resp_rate": 16,
                 "bp_systolic": 120, "bp_diastolic": 80, "quality": "good"}]

    async def one(conn, sql, params=()):
        return {"retry_after": 0}

    async def record(principal, action, entity_type, entity_id=None, **kw):
        audited.append((action, kw.get("details")))

    @asynccontextmanager
    async def tx(principal, read_only=False):
        yield Conn(DB())

    monkeypatch.setattr(rep_router.reports, "research_extract", fake_extract)
    monkeypatch.setattr(rep_router, "fetch_one", one)
    monkeypatch.setattr(rep_router, "transaction", tx)
    monkeypatch.setattr(rep_router, "record_event", record)
    for role in ("nurse", "physician", "biomed_tech"):
        _, h = headers_for(identities, role)
        assert client.get("/v1/reports/research-extract", headers=h).status_code == 403
    _, h = headers_for(identities, "admin")
    r = client.get("/v1/reports/research-extract", params={"days": 7}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["method"] == "safe-harbor" and r.json()["min_subjects_per_ward"] == privacy.MIN_CELL_SIZE
    assert audited == [("report.research_extract", {"days": 7, "rows": 1, "subjects": 1})]  # counts only


def test_t377_extract_query_never_selects_text_files_or_ecg():
    src = (ROOT / "backend" / "app" / "services" / "reports.py").read_text(encoding="utf-8")
    query = src.split("async def research_extract", 1)[1]
    select = query.split("rows = await fetch_all(conn, \"\"\"", 1)[1].split("from public.readings", 1)[0]
    for forbidden in ("display_name", "pseudonym", "birth_year", "ecg", "body", "object_path", "attachments",
                      "observations", "bed"):
        assert forbidden not in select, forbidden


def test_t178_consent_purpose_type_matches_the_catalogue():
    from typing import get_args

    from app.services import consent

    assert set(get_args(profile_router.ConsentPurpose)) == set(consent.CONSENT_PURPOSES)
