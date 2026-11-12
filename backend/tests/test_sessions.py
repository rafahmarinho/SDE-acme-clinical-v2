"""Session-management tests (skills/session-management): concurrent-session limit, logout, idle and
absolute timeouts, session id rotation, tokens in URLs, cookies (none set; helper flags), no remember-me.

The database is not available in unit tests: the SQL functions of supabase/migrations/0005_sessions.sql
are replaced by a fake that records calls, and time is simulated by patching ``app.routers.auth._now``.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from app.main import create_app
from app.routers import auth as auth_router
from tests.conftest import SECRET, add_identity, make_token
from tests.test_input_validation import fake_db  # noqa: F401 - fixture re-export

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "supabase" / "migrations" / "0005_sessions.sql").read_text(encoding="utf-8")
APP_DIR = ROOT / "backend" / "app"
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
IDLE, ABSOLUTE = 15, 12


def state(*, created=T0, last=T0, revoked=None, auth_exists=True, idle=IDLE, absolute=ABSOLUTE) -> dict:
    return {"created_at": created, "last_activity_at": last, "revoked_at": revoked, "revoked_reason": None,
            "auth_session_exists": auth_exists, "idle_minutes": idle, "absolute_hours": absolute}


class FakeConn:
    def __init__(self, db: SessionDB):
        self.db = db

    async def execute(self, sql, params=()):
        self.db.calls.append((sql, params))
        self.db.apply(sql, params)


class SessionDB:
    """In-memory stand-in for public.register_session / session_state / touch_session / revoke_session."""

    def __init__(self, limit: int = 2):
        self.calls: list[tuple[str, tuple]] = []
        self.sessions: dict[str, dict] = {}
        self.limit = limit
        self.now = T0

    @asynccontextmanager
    async def transaction(self, principal):
        yield FakeConn(self)

    async def fetch_one(self, conn, sql, params=()):
        self.calls.append((sql, params))
        if "register_session" in sql:
            sid = params[0]
            if sid in self.sessions:
                s = self.sessions[sid]
                return {"status": "revoked" if s["revoked_at"] else "active", "created": False,
                        "revoked_count": 0, "previous_unclosed": False}
            self.sessions[sid] = state(created=self.now, last=self.now)
            live = [k for k, v in sorted(self.sessions.items(), key=lambda kv: kv[1]["created_at"], reverse=True)
                    if v["revoked_at"] is None]
            stale = live[self.limit:]
            for k in stale:
                self.sessions[k]["revoked_at"] = self.now
            return {"status": "active", "created": True, "revoked_count": len(stale), "previous_unclosed": False}
        if "session_state" in sql:
            return self.sessions.get(params[0])
        if "staff_profiles" in sql:
            return {"last_login_at": T0 - timedelta(days=1), "ip": "203.0.113.7"}
        return None

    def apply(self, sql, params):
        if "touch_session" in sql and params[0] in self.sessions and not self.sessions[params[0]]["revoked_at"]:
            self.sessions[params[0]]["last_activity_at"] = self.now
        elif "revoke_session" in sql and params[0] in self.sessions:
            self.sessions[params[0]]["revoked_at"] = self.now
        elif "revoke_user_sessions" in sql:
            for s in self.sessions.values():
                s["revoked_at"] = s["revoked_at"] or self.now

    def tick(self, **delta):
        self.now += timedelta(**delta)

    def sql(self, needle: str) -> list[tuple]:
        return [p for s, p in self.calls if needle in s]


@pytest.fixture
def sdb(monkeypatch):
    db = SessionDB()
    monkeypatch.setattr(auth_router, "transaction", db.transaction)
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "_now", lambda: db.now)
    return db


def login(identities, role="nurse", uid=None, **claims):
    """A fresh Supabase sign-in: new random session_id every time (as Supabase Auth issues)."""
    uid = uid or add_identity(identities, role)
    token = make_token(uid, aal="aal2" if role == "admin" else "aal1", **claims)
    sid = jwt.decode(token, options={"verify_signature": False})["session_id"]
    return uid, sid, {"Authorization": f"Bearer {token}"}


def fake_request(method="GET", path="/v1/patients") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""})


def run(coro):
    return asyncio.run(coro)


def principal_for(uid, sid):
    from app.core.security import PERMISSIONS, Principal, Role
    return Principal(user_id=uuid.UUID(uid), email="n@example.test", role=Role.NURSE, session_id=sid, aal="aal1",
                     issued_at=0, auth_time=0, permissions=PERMISSIONS[Role.NURSE])


# --------------------------------------------------------------------------- pure session policy
def test_evaluate_session_policy():
    now = T0 + timedelta(minutes=5)
    assert auth_router.evaluate_session(None, now).error == "session_unknown"
    assert auth_router.evaluate_session(state(revoked=T0), now).error == "session_revoked"
    v = auth_router.evaluate_session(state(auth_exists=False), now)
    assert (v.error, v.revoke_reason) == ("session_revoked", "signed_out")
    ok = auth_router.evaluate_session(state(), now)
    assert ok.active and ok.expires_at == T0 + timedelta(hours=ABSOLUTE)


# --------------------------------------------------------------------------- T24 / T90 idle timeout
def test_t90_idle_session_rejected_and_revoked(sdb, identities):
    uid, sid, _ = login(identities)
    sdb.sessions[sid] = state()
    p = principal_for(uid, sid)
    sdb.tick(minutes=IDLE - 1)
    run(auth_router.enforce_session(fake_request(), p))  # still inside the window
    sdb.tick(minutes=2)
    with pytest.raises(Exception) as exc:
        run(auth_router.enforce_session(fake_request(), p))
    assert exc.value.status_code == 401 and "session_idle" in exc.value.headers["WWW-Authenticate"]
    assert sdb.sql("revoke_session") == [(sid, "idle_timeout")]
    assert sdb.sessions[sid]["revoked_at"] is not None


def test_t90_data_requests_do_not_count_as_activity(sdb, identities):
    uid, sid, _ = login(identities)
    sdb.sessions[sid] = state()
    p = principal_for(uid, sid)
    for _ in range(3):  # background polling every 5 minutes
        sdb.tick(minutes=5)
        try:
            run(auth_router.enforce_session(fake_request("GET", "/v1/alarms"), p))
        except Exception:
            break
    assert sdb.sql("touch_session") == []
    assert sdb.sessions[sid]["revoked_at"] is not None  # 15 min without user input => idle


def test_t90_heartbeat_keeps_session_alive_but_cannot_resurrect(client, sdb, identities):
    uid, sid, h = login(identities)
    assert client.post("/v1/auth/session", headers=h).status_code == 200
    for _ in range(4):
        sdb.tick(minutes=IDLE - 1)
        assert client.post("/v1/auth/session", headers=h).status_code == 200  # user input heartbeat
    sdb.tick(minutes=IDLE + 1)
    r = client.post("/v1/auth/session", headers=h)
    assert r.status_code == 401 and "session_idle" in r.headers["www-authenticate"]
    r = client.post("/v1/auth/session", headers=h)
    assert r.status_code == 401 and "session_revoked" in r.headers["www-authenticate"]


# --------------------------------------------------------------------------- T25 / T92 absolute timeout
def test_t92_continuous_activity_cannot_extend_absolute_lifetime(sdb, identities):
    uid, sid, _ = login(identities)
    sdb.sessions[sid] = state()
    p = principal_for(uid, sid)
    elapsed = timedelta()
    while elapsed < timedelta(hours=ABSOLUTE) - timedelta(minutes=5):
        sdb.tick(minutes=5)
        elapsed += timedelta(minutes=5)
        sdb.apply("select public.touch_session(%s)", (sid,))  # heartbeat on user input
        run(auth_router.enforce_session(fake_request(), p))
    sdb.tick(minutes=10)
    with pytest.raises(Exception) as exc:
        run(auth_router.enforce_session(fake_request(), p))
    assert "session_expired" in exc.value.headers["WWW-Authenticate"]
    assert sdb.sql("revoke_session") == [(sid, "absolute_timeout")]


def test_t92_refreshed_token_keeps_session_id_and_is_still_expired(sdb, identities):
    uid, sid, _ = login(identities)
    sdb.sessions[sid] = state()
    sdb.tick(hours=ABSOLUTE + 1)
    refreshed = make_token(uid, session_id=sid)  # Supabase refresh: new JWT, same session_id, new iat
    claims = jwt.decode(refreshed, options={"verify_signature": False})
    with pytest.raises(Exception) as exc:
        run(auth_router.enforce_session(fake_request(), principal_for(uid, claims["session_id"])))
    assert "session_expired" in exc.value.headers["WWW-Authenticate"]


def test_t25_get_principal_still_enforces_absolute_timeout_from_auth_time(client, identities, fake_db):
    uid = add_identity(identities, "nurse", absolute_hours=1)
    old = int(datetime.now(UTC).timestamp()) - 2 * 3600  # signed in 2 h ago, limit 1 h
    token = make_token(uid, iat=int(datetime.now(UTC).timestamp()), auth_time=old)
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


# --------------------------------------------------------------------------- T429 / T430 concurrent sessions
def test_t430_oldest_session_revoked_when_limit_exceeded(client, sdb, identities):
    uid = add_identity(identities, "nurse")
    sids, headers = [], []
    for _ in range(sdb.limit + 1):
        _, sid, h = login(identities, uid=uid)
        sdb.tick(seconds=1)
        r = client.post("/v1/auth/session", headers=h)
        assert r.status_code == 200
        sids.append(sid)
        headers.append(h)
    assert r.json()["revoked_sessions"] == 1
    assert sdb.sessions[sids[0]]["revoked_at"] is not None              # oldest revoked
    assert all(sdb.sessions[s]["revoked_at"] is None for s in sids[1:])  # newest kept
    r = client.post("/v1/auth/session", headers=headers[0])
    assert r.status_code == 401 and "session_revoked" in r.headers["www-authenticate"]


def test_t429_sql_enforces_limit_oldest_first_serialised_and_kills_refresh_tokens():
    sql = re.sub(r"\s+", " ", MIGRATION.lower())
    assert "pg_advisory_xact_lock" in sql
    assert "order by s.created_at desc" in sql and "offset v_limit - 1" in sql
    assert "least(s.max_concurrent_sessions, 1)" in sql                      # administrators: one session
    assert "delete from auth.sessions s where s.id = any(v_stale)" in sql    # refresh tokens die
    assert "security definer" in sql and "to acme_api_rw" in sql
    assert re.search(r"revoke execute on function public\.register_session.*from public, anon, authenticated", sql)


# --------------------------------------------------------------------------- T86 session id rotation
def test_t86_each_login_registers_a_new_unique_random_session(client, sdb, identities):
    uid = add_identity(identities, "physician")
    sdb.limit = 50
    seen = set()
    for _ in range(10):
        _, sid, h = login(identities, "physician", uid=uid)
        body = client.post("/v1/auth/session", headers=h).json()
        assert body["session_id"] == sid and body["new_session"] is True
        seen.add(sid)
    assert len(seen) == 10 and all(uuid.UUID(s).version == 4 for s in seen)
    assert "session_id uuid primary key" in MIGRATION  # keyed on session, never on user


def test_t86_client_supplied_session_id_is_ignored(client, sdb, identities):
    _, sid, h = login(identities)
    r = client.post("/v1/auth/session", headers=h, json={"session_id": str(uuid.uuid4())})
    assert r.status_code == 200 and r.json()["session_id"] == sid
    assert {p[0] for p in sdb.sql("register_session")} == {sid}


def test_token_without_session_id_is_refused(client, sdb, identities):
    uid = add_identity(identities, "nurse")
    token = jwt.encode({"sub": uid, "aud": "authenticated", "iss": "https://test-project.supabase.co/auth/v1",
                        "iat": int(datetime.now(UTC).timestamp()), "exp": int(datetime.now(UTC).timestamp()) + 600},
                       SECRET, algorithm="HS256")
    r = client.post("/v1/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and "session_unknown" in r.headers["www-authenticate"]


def test_login_records_previous_and_last_ip_correctly(client, sdb, identities):
    _, _, h = login(identities)
    body = client.post("/v1/auth/session", headers={**h, "x-vercel-forwarded-for": "198.51.100.4"}).json()
    assert body["previous_login_ip"] == "203.0.113.7"  # the PREVIOUS login's ip, read from last_login_ip
    (update,) = [(s, p) for s, p in sdb.calls if s.lstrip().startswith("update public.staff_profiles")]
    assert "previous_login_ip = last_login_ip" in update[0] and "last_login_ip = %s::inet" in update[0]
    assert update[1][0] == "198.51.100.4"


# --------------------------------------------------------------------------- T26 / T93 / T1540 logout
def test_t93_logout_revokes_server_side_and_clears_site_data(client, sdb, identities):
    _, sid, h = login(identities)
    client.post("/v1/auth/session", headers=h)
    r = client.post("/v1/auth/logout", headers=h)
    assert r.status_code == 204
    assert r.headers["clear-site-data"] == '"cache", "cookies", "storage"'
    assert r.headers["cache-control"] == "no-store"
    assert "set-cookie" not in r.headers
    assert sdb.sql("revoke_session") == [(sid, "logout")]
    r = client.post("/v1/auth/session", headers=h)  # replay of the captured access token
    assert r.status_code == 401 and "session_revoked" in r.headers["www-authenticate"]


def test_t26_sign_out_everywhere(client, sdb, identities):
    _, _, h = login(identities)
    r = client.post("/v1/auth/logout", headers=h, json={"scope": "global"})
    assert r.status_code == 204 and sdb.sql("revoke_user_sessions") == [("logout_all",)]


def test_t93_logout_is_not_a_get(client, identities):
    _, _, h = login(identities)
    assert client.get("/v1/auth/logout", headers=h).status_code == 405


# --------------------------------------------------------------------------- T27 / T94 tokens in URLs
@pytest.mark.parametrize("param", ["access_token", "token", "jwt", "refresh_token"])
def test_t94_query_string_token_is_not_accepted(client, identities, fake_db, param):
    _, _, h = login(identities)
    token = h["Authorization"].split()[1]
    r = client.get(f"/v1/me?{param}={token}")
    assert r.status_code == 401 and "@example.test" not in r.text


def test_t94_matrix_parameter_session_not_accepted(client, identities):
    _, sid, _ = login(identities)
    assert client.get(f"/v1/me;session={sid}").status_code in (401, 404)


# --------------------------------------------------------------------------- cookies (T22 T23 T88 T91 T557 T404 T405 T1092 T1093)
def _all_routes():
    return [r for r in create_app().routes if isinstance(r, APIRoute)]


def test_t88_t91_no_route_sets_a_cookie(client, sdb, identities):
    for route in _all_routes():
        path = re.sub(r"{\w+}", str(uuid.uuid4()), route.path)
        for method in route.methods:
            assert "set-cookie" not in client.request(method, path).headers, (method, path)
    _, _, h = login(identities)
    for method, path in (auth_router.SESSION_ROUTE, auth_router.LOGOUT_ROUTE):
        assert "set-cookie" not in client.request(method, path, headers=h).headers


def test_t405_no_ad_hoc_cookie_code_in_backend():
    offenders = []
    for py in APP_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if re.search(r"(set|delete)_cookie\([^)]*\bdomain\s*=", text, re.S) or (
                "set_cookie(" in text and py.name != "auth.py"):
            offenders.append(str(py))
    assert offenders == []


def test_t22_t23_t557_t404_cookie_helper_flags():
    resp = Response()
    auth_router.set_secure_cookie(resp, "__Secure-acme_pref", "opaque123")
    (cookie,) = resp.headers.getlist("set-cookie")
    attrs = [a.strip().lower() for a in cookie.split(";")]
    assert "httponly" in attrs and "secure" in attrs and "samesite=strict" in attrs and "path=/v1/auth" in attrs
    assert not any(a.startswith(("domain=", "max-age=", "expires=")) for a in attrs)  # host-only, non-persistent
    resp = Response()
    auth_router.set_secure_cookie(resp, "__Host-acme_rt", "opaque456", path="/")
    assert "path=/" in resp.headers["set-cookie"].lower()


@pytest.mark.parametrize("name,path,value", [
    ("role", "/v1/auth", "x"),                               # no prefix
    ("__Host-acme_rt", "/v1/auth", "x"),                     # __Host- requires Path=/
    ("__Secure-acme_rt", "/", "x"),                          # broad path
    ("__Secure-acme_rt", "/v1/auth", make_token()),          # JWT in a cookie (T1092)
])
def test_t1092_t404_cookie_helper_rejects_unsafe_cookies(name, path, value):
    with pytest.raises(ValueError):
        auth_router.set_secure_cookie(Response(), name, value, path=path)


def test_t1093_tampered_cookie_does_not_grant_role(client, identities, fake_db):
    _, _, h = login(identities, "nurse")
    client.cookies.set("role", "admin")
    try:
        assert client.get("/v1/staff", headers=h).status_code == 403
    finally:
        client.cookies.clear()


def test_cors_never_allows_credentials(client):
    r = client.options("/v1/me", headers={"Origin": "https://acme-clinical.vercel.app",
                                          "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-credentials" not in r.headers


# --------------------------------------------------------------------------- T28 / T95 remember-me
def test_t95_no_remember_me_and_session_storage_only():
    web = ROOT / "frontend" / "src"
    login_screen = (web / "screens" / "Login.tsx").read_text(encoding="utf-8")
    assert not re.search(r"remember|keep me signed in", login_screen, re.I)
    client_cfg = (web / "lib" / "supabase.ts").read_text(encoding="utf-8")
    assert "sessionStorage" in client_cfg and 'flowType: "pkce"' in client_cfg

