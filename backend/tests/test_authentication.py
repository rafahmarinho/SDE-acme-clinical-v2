"""Authentication controls (skills/authentication): password policy, Supabase Auth configuration as code,
no stored/default passwords, MFA for administrators, lockout hook, generic errors, uniform staff
invitations, account lifecycle, username consistency, server-to-server authentication and monitor
(device) authenticity. No database or Supabase is needed: SQL/TOML artefacts are checked statically and
router DB/HTTP helpers are monkeypatched.
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
import time
import tomllib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import cli
from app.core.config import Settings, get_settings
from app.core.security import PUBLIC_ROUTES
from app.main import create_app
from app.routers import staff
from app.services import device_auth, identity, passwords
from app.services.passwords import PasswordPolicy, policy_from_settings, violations
from tests.conftest import SECRET, add_identity, make_token

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
SUPABASE = ROOT / "supabase"
MIGRATIONS = sorted((SUPABASE / "migrations").glob("*.sql"))
ALL_SQL = "\n".join(p.read_text(encoding="utf-8") for p in MIGRATIONS)
AUTH_SQL = (SUPABASE / "migrations" / "0006_auth.sql").read_text(encoding="utf-8")
CONFIG = tomllib.loads((SUPABASE / "config.toml").read_text(encoding="utf-8"))
AUTH_CFG = CONFIG["auth"]


def _admin_headers(identities, role: str = "admin", aal: str | None = None) -> tuple[str, dict]:
    uid = add_identity(identities, role)
    token = make_token(uid, aal=aal or ("aal2" if role == "admin" else "aal1"), auth_time=int(time.time()))
    return uid, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T4 / T5 / T80 / T2270 - password policy
# ---------------------------------------------------------------------------
POLICY = PasswordPolicy()


@pytest.mark.parametrize("pw", [
    "Short1a",                 # too short
    "alllowercase1234x",       # no upper-case
    "ALLUPPERCASE1234X",       # no lower-case
    "NoDigitsHereAtAll",       # no digit
    "AcmeClinical2026x",       # service name
    "Nora.Lindqvist99",        # context word (name / e-mail local part)
    "Password123456!",         # common password + suffix
    "Aaaaaaaaaaaa1",           # repetitive
    "Abcdefgh12345",           # sequential
    "x" * 129 + "A1",          # too long
])
def test_policy_rejects_weak_passwords(pw):
    assert violations(pw, POLICY, passwords.context_words("nora.lindqvist@acme-clinical.org", "Nora Lindqvist"))


def test_policy_accepts_strong_passphrase():
    assert violations("Violet-Harbor-Lantern-82", POLICY, ["nora", "lindqvist"]) == []


def test_configured_minimum_is_enforced_and_bounded():
    assert violations("Violet-Harb82", policy_from_settings({"password_min_length": 12})) == []
    stricter = policy_from_settings({"password_min_length": 16})
    assert stricter.min_length == 16
    assert violations("Violet-Harbor-82", stricter) == []           # 16 characters
    assert violations("Violet-Harb-82", stricter)                    # 14 characters now fails
    assert policy_from_settings({"password_min_length": 4}).min_length == 12   # never below the floor
    assert policy_from_settings(None).min_length == 12
    with pytest.raises(ValueError):
        PasswordPolicy(min_length=8)


def test_policy_rules_are_human_readable_and_never_echo_the_password():
    assert any("12 to 128" in r for r in POLICY.rules())
    secret = "Tr0ub4dor-acme"
    with pytest.raises(passwords.PasswordPolicyError) as exc:
        passwords.assert_acceptable(secret, POLICY)
    assert secret not in str(exc.value)


def test_generated_passwords_are_unique_and_meet_policy():
    pws = {passwords.generate_password(POLICY) for _ in range(20)}
    assert len(pws) == 20 and all(not violations(p, POLICY) for p in pws)


def test_platform_floor_matches_supabase_and_frontend():
    assert AUTH_CFG["minimum_password_length"] == passwords.PLATFORM_MIN_LENGTH >= 12
    assert AUTH_CFG["password_requirements"] == "lower_upper_letters_digits"
    ts = (FRONTEND / "src" / "lib" / "authPolicy.ts").read_text(encoding="utf-8")
    assert f"PLATFORM_MIN_LENGTH = {passwords.PLATFORM_MIN_LENGTH}" in ts
    assert f"MAX_PASSWORD_LENGTH = {passwords.MAX_LENGTH}" in ts


def test_security_settings_min_length_floor_in_schema():
    assert re.search(r"password_min_length smallint not null default 12 check \(password_min_length between 12 and 128\)", ALL_SQL)


# ---------------------------------------------------------------------------
# Supabase Auth settings as code (T1, T3, T5, T6, T78, T340, T517, T518)
# ---------------------------------------------------------------------------
def test_supabase_auth_configuration_hardened():
    assert AUTH_CFG["enable_signup"] is False and AUTH_CFG["email"]["enable_signup"] is False
    assert AUTH_CFG["enable_anonymous_sign_ins"] is False
    assert AUTH_CFG["email"]["enable_confirmations"] is True
    assert AUTH_CFG["email"]["secure_password_change"] is True
    assert AUTH_CFG["email"]["double_confirm_changes"] is True
    assert AUTH_CFG["email"]["otp_expiry"] <= 3600
    assert AUTH_CFG["jwt_expiry"] <= 3600
    assert AUTH_CFG["enable_refresh_token_rotation"] is True
    assert AUTH_CFG["mfa"]["totp"] == {"enroll_enabled": True, "verify_enabled": True}
    rl = AUTH_CFG["rate_limit"]
    assert rl["sign_in_sign_ups"] <= 30 and rl["token_verifications"] <= 30 and rl["email_sent"] <= 10
    assert rl["anonymous_users"] == 0


def test_redirect_allow_list_is_exact():
    urls = [AUTH_CFG["site_url"], *AUTH_CFG["additional_redirect_urls"]]
    for u in urls:
        assert "*" not in u
        assert u.startswith("https://") or u.startswith("http://localhost:"), u


def test_lockout_hook_registered_and_defined():
    hook = AUTH_CFG["hook"]["password_verification_attempt"]
    assert hook["enabled"] is True
    assert hook["uri"] == "pg-functions://postgres/public/hook_password_verification_attempt"
    assert "create or replace function public.hook_password_verification_attempt(event jsonb)" in AUTH_SQL
    body = AUTH_SQL.split("public.hook_password_verification_attempt(event jsonb) returns jsonb", 1)[1].split("end $$;", 1)[0]
    assert "lockout_threshold" in body and "lockout_minutes" in body          # administrator-configurable
    assert "'reject', 'message', 'Invalid login credentials'" in body          # generic, same as a wrong password
    assert "security definer set search_path = ''" in AUTH_SQL
    assert "grant execute on function public.hook_password_verification_attempt(jsonb) to supabase_auth_admin" in AUTH_SQL


def test_private_schema_not_exposed():
    assert "private" not in CONFIG["api"]["schemas"]
    assert "revoke all on schema private from public" in AUTH_SQL
    assert not re.search(r"grant [^;]* on (schema )?private[^;]* to (anon|authenticated)", AUTH_SQL)


# ---------------------------------------------------------------------------
# T7 / T220 - the app never stores passwords; T61 / T323 - no default accounts
# ---------------------------------------------------------------------------
def test_no_password_columns_in_any_migration():
    cols = re.findall(r"^\s*(\w*pass\w*)\s+(?:text|varchar|character|char|bytea|citext)\b", ALL_SQL, re.I | re.M)
    assert cols == []
    assert not re.search(r"add column (if not exists )?\w*pass", ALL_SQL, re.I)


@pytest.mark.parametrize("path", [*MIGRATIONS, SUPABASE / "seed.sql"], ids=lambda p: p.name)
def test_no_hand_rolled_password_hashing_or_auth_rows(path):
    sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))  # code only, not explanatory comments
    assert not re.search(r"\bcrypt\s*\(|gen_salt\s*\(|encrypted_password|\bmd5\s*\(", sql, re.I)
    assert not re.search(r"insert\s+into\s+auth\.", sql, re.I)


DEFAULT_CRED_PATTERNS = [r"(?i)password\s*[:=]\s*['\"]?[A-Za-z0-9!@#$%^&*]{4,}", r"(?i)\b(admin|demo|test)123\b",
                         r"(?i)changeme", r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJpc3MiOiJzdXBhYmFzZS1kZW1v"]


@pytest.mark.parametrize("path", [SUPABASE / "seed.sql", ROOT / "README.md", BACKEND / ".env.example",
                                  FRONTEND / ".env.example", SUPABASE / "config.toml"], ids=lambda p: p.name)
def test_no_default_credentials_in_repo_artefacts(path):
    if not path.exists():
        pytest.skip("not present")
    text = path.read_text(encoding="utf-8")
    hits = [p for p in DEFAULT_CRED_PATTERNS if re.search(p, text)]
    assert hits == []


def test_seed_creates_no_staff_and_no_shared_accounts():
    seed = (SUPABASE / "seed.sql").read_text(encoding="utf-8")
    assert "staff_profiles" not in seed.split("--")[0] and not re.search(r"insert\s+into\s+public\.staff_profiles", seed)
    assert not re.search(r"(admin|nurse|physician|doctor|ward|shared|team)[0-9-]*@", seed, re.I)


def test_cli_demo_accounts_are_personal_random_and_refused_in_production(monkeypatch, capsys):
    emails = {cli.demo_email(name, "example.test") for name, _ in cli.DEMO}
    assert len(emails) == len(cli.DEMO)
    assert not any(re.match(r"^(admin|nurse|physician|biomed|tech|ward|shared)\b", e) for e in emails)
    pws = {cli._password(name, f"{name}@x.test") for name, _ in cli.DEMO}
    assert len(pws) == len(cli.DEMO) and all(not violations(p, PasswordPolicy(min_length=16)) for p in pws)
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(is_production=True))
    called = []
    monkeypatch.setattr(cli, "create_demo_staff", lambda domain: called.append(domain))
    assert cli.main(["cli", "create-demo-staff", "example.test"]) == 2 and called == []
    assert "Refusing" in capsys.readouterr().out


def test_cli_operator_dsn_requires_tls(monkeypatch):
    monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql://postgres:pw@db.example.supabase.co:5432/postgres")
    with pytest.raises(SystemExit):
        cli.operator_dsn()
    monkeypatch.setenv("ADMIN_DATABASE_URL", "postgresql://postgres:pw@db.example.supabase.co:5432/postgres?sslmode=verify-full")
    assert cli.operator_dsn().endswith("verify-full")


def test_simulation_reset_never_touches_accounts():
    reset_sql = ALL_SQL.split("function public.reset_simulation_data", 1)
    if len(reset_sql) == 2:
        body = reset_sql[1].split("$$;", 1)[0]
        assert "staff_profiles" not in body and "auth." not in body


# ---------------------------------------------------------------------------
# T135 / T233 / T286 / T287 - unique user IDs and one username rule
# ---------------------------------------------------------------------------
def test_unique_user_ids_enforced_in_schema():
    assert re.search(r"create table public\.staff_profiles \(\s*user_id uuid primary key references auth\.users\(id\)", ALL_SQL)
    assert re.search(r"email citext not null unique", ALL_SQL)
    assert "staff_profiles_email_canonical" in AUTH_SQL and "lower(btrim(email::text))" in AUTH_SQL


@pytest.mark.parametrize("raw", ["Joe@acme-clinical.org", "joe@ACME-CLINICAL.ORG", "JOE@Acme-Clinical.org"])
def test_case_variants_canonicalise_to_one_username(raw):
    assert identity.canonical_email(raw) == "joe@acme-clinical.org"


@pytest.mark.parametrize("raw", [" joe@acme-clinical.org", "joe@acme-clinical.org ", "joe​@acme-clinical.org",
                                 "jоe@acme-clinical.org", "joe@acme-clinical.org\n", "ｊoe@acme-clinical.org", "not-an-email"])
def test_whitespace_invisible_and_lookalike_variants_rejected(raw):
    with pytest.raises(ValueError):
        identity.canonical_email(raw)


def test_frontend_uses_same_username_rule():
    ts = (FRONTEND / "src" / "lib" / "authPolicy.ts").read_text(encoding="utf-8")
    assert "export function canonicalEmail" in ts and ".trim().toLowerCase()" in ts


# ---------------------------------------------------------------------------
# Staff invitation / lifecycle (T517, T518, T340, T2277, T73, T82)
# ---------------------------------------------------------------------------
class _Conn:
    def __init__(self, log):
        self.log = log

    async def execute(self, sql, params=()):
        self.log.append((sql, params))


@pytest.fixture
def staff_env(monkeypatch):
    env = SimpleNamespace(existing={}, sql=[], events=[], supabase=[], supabase_status=200)

    @asynccontextmanager
    async def fake_tx(principal, read_only=False):
        yield _Conn(env.sql)

    async def fake_one(conn, sql, params=()):
        env.sql.append((sql, params))
        if "where email = %s" in sql:
            return env.existing.get(params[0])
        if "for update" in sql:
            return {"role": "nurse", "is_active": env.existing.get("__active__", True)}
        if "unlock_staff_account" in sql:
            return {"unlocked": True}
        return {"user_id": params[0], "email": "x@acme-clinical.org", "full_name": "X Y", "role": "nurse",
                "is_active": True, "ward_ids": [], "last_login_at": None}

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        env.events.append((action, entity_id, kw.get("outcome", "success")))

    def handler(request: httpx.Request) -> httpx.Response:
        env.supabase.append(request)
        if env.supabase_status >= 400:
            return httpx.Response(env.supabase_status, json={"error_code": "email_exists"})
        return httpx.Response(200, json={"id": str(uuid.uuid4())})

    def fake_client(settings):
        assert str(settings.supabase_url).startswith("https://")
        key = settings.supabase_service_role_key.get_secret_value()
        return httpx.AsyncClient(base_url=str(settings.supabase_url).rstrip("/"), transport=httpx.MockTransport(handler),
                                 headers={"apikey": key, "Authorization": f"Bearer {key}"})

    monkeypatch.setattr(staff, "transaction", fake_tx)
    monkeypatch.setattr(staff, "fetch_one", fake_one)
    monkeypatch.setattr(staff, "fetch_all", lambda conn, sql, params=(): asyncio.sleep(0, result=[]))
    monkeypatch.setattr(staff, "record_event", fake_record)
    monkeypatch.setattr(staff, "supabase_admin_client", fake_client)
    monkeypatch.setattr(staff, "uniform_auth_timing", lambda: identity.uniform_auth_timing(0.01, 5))
    return env


INVITE = {"email": "joe@acme-clinical.org", "full_name": "Joe Test", "role": "nurse"}


def test_invite_response_identical_for_existing_and_new_email(client, identities, staff_env):
    _, h = _admin_headers(identities)
    new = client.post("/v1/staff", json=INVITE, headers=h)
    staff_env.existing["joe@acme-clinical.org"] = {"user_id": uuid.uuid4()}
    dup = client.post("/v1/staff", json={**INVITE, "email": "Joe@Acme-Clinical.org", "role": "admin"}, headers=h)
    assert (new.status_code, new.json()) == (dup.status_code, dup.json()) == (202, {"detail": staff.INVITE_ACCEPTED})
    assert len(staff_env.supabase) == 1                                       # no second account created
    assert [e[0] for e in staff_env.events] == ["staff.invited", "staff.invite_duplicate"]
    assert not any("update public.staff_profiles set role" in s for s, _ in staff_env.sql)


def test_invite_refused_by_identity_service_looks_the_same(client, identities, staff_env):
    _, h = _admin_headers(identities)
    staff_env.supabase_status = 422
    r = client.post("/v1/staff", json=INVITE, headers=h)
    assert (r.status_code, r.json()) == (202, {"detail": staff.INVITE_ACCEPTED})
    assert staff_env.events[-1][0] == "staff.invite_failed"
    assert not any("insert into public.staff_profiles" in s for s, _ in staff_env.sql)


def test_invite_never_sends_a_password_and_uses_server_key(client, identities, staff_env):
    _, h = _admin_headers(identities)
    client.post("/v1/staff", json=INVITE, headers=h)
    req = staff_env.supabase[0]
    assert req.url.path == "/auth/v1/invite" and req.url.scheme == "https"
    assert "password" not in json.loads(req.content)
    assert req.headers["apikey"] == "service-test-key"


@pytest.mark.parametrize("email", ["joe​@acme-clinical.org", "jоe@acme-clinical.org"])
def test_invite_rejects_ambiguous_usernames(client, identities, staff_env, email):
    _, h = _admin_headers(identities)
    assert client.post("/v1/staff", json={**INVITE, "email": email}, headers=h).status_code == 422
    assert staff_env.supabase == []


@pytest.mark.parametrize("email", [" joe@acme-clinical.org", "JOE@acme-clinical.org", "joe@ACME-clinical.org ", "joe@acme-clinical.org "])
def test_invite_variants_resolve_to_the_existing_account(client, identities, staff_env, email):
    _, h = _admin_headers(identities)
    staff_env.existing["joe@acme-clinical.org"] = {"user_id": uuid.uuid4()}
    r = client.post("/v1/staff", json={**INVITE, "email": email, "role": "admin"}, headers=h)
    assert r.status_code in (202, 422)
    assert staff_env.supabase == []                                           # never a second account
    assert not any("insert into public.staff_profiles" in s for s, _ in staff_env.sql)


def test_deactivation_bans_and_reactivation_unbans_in_supabase(client, identities, staff_env):
    _, h = _admin_headers(identities)
    target = uuid.uuid4()
    assert client.patch(f"/v1/staff/{target}", json={"is_active": False}, headers=h).status_code == 200
    staff_env.existing["__active__"] = False
    assert client.patch(f"/v1/staff/{target}", json={"is_active": True}, headers=h).status_code == 200
    bans = [(r.method, r.url.path, r.content) for r in staff_env.supabase]
    assert bans[0][:2] == ("PUT", f"/auth/v1/admin/users/{target}") and b"876000h" in bans[0][2]
    assert b'"none"' in bans[1][2]


def test_deactivation_rolled_back_when_ban_fails(client, identities, staff_env):
    _, h = _admin_headers(identities)
    staff_env.supabase_status = 500
    r = client.patch(f"/v1/staff/{uuid.uuid4()}", json={"is_active": False}, headers=h)
    assert r.status_code == 502


def test_admin_unlock_is_audited_and_admin_only(client, identities, staff_env):
    _, h = _admin_headers(identities)
    target = uuid.uuid4()
    assert client.post(f"/v1/staff/{target}/unlock", headers=h).status_code == 204
    assert ("staff.unlocked", str(target), "success") in staff_env.events
    _, nurse = _admin_headers(identities, "nurse")
    assert client.post(f"/v1/staff/{target}/unlock", headers=nurse).status_code == 403
    assert "public.unlock_staff_account" in AUTH_SQL and "current_staff_role() is distinct from 'admin'" in AUTH_SQL


def test_uniform_auth_timing_has_floor_and_random_jitter():
    async def run() -> float:
        start = time.monotonic()
        with pytest.raises(RuntimeError):
            async with identity.uniform_auth_timing(0.05, 40):
                raise RuntimeError("fail fast")
        return time.monotonic() - start

    samples = [asyncio.run(run()) for _ in range(6)]
    assert min(samples) >= 0.05
    assert len({round(s, 3) for s in samples}) > 1


def test_invite_is_wrapped_in_uniform_timing():
    src = (BACKEND / "app" / "routers" / "staff.py").read_text(encoding="utf-8")
    assert "async with uniform_auth_timing():" in src


# ---------------------------------------------------------------------------
# T1 / T77 - single-factor administrator sessions are refused by the API
# ---------------------------------------------------------------------------
ADMIN_ENDPOINTS = [("GET", "/v1/staff"), ("POST", "/v1/staff"), ("PATCH", f"/v1/staff/{uuid.uuid4()}"),
                   ("POST", f"/v1/staff/{uuid.uuid4()}/unlock"), ("PATCH", "/v1/settings/security"), ("GET", "/v1/me")]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_password_only_session_rejected(client, identities, method, path):
    _, h = _admin_headers(identities, "admin", aal="aal1")
    r = client.request(method, path, headers=h, json={})
    assert r.status_code == 403 and "Multi-factor" in r.text


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS[:4])
def test_admin_two_factor_session_passes_authentication(client, identities, staff_env, method, path):
    _, h = _admin_headers(identities, "admin", aal="aal2")
    r = client.request(method, path, headers=h, json=INVITE if method == "POST" and path == "/v1/staff" else {})
    assert r.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# T8 / T82 - uniform authentication failures from the API
# ---------------------------------------------------------------------------
def test_api_authentication_failures_are_indistinguishable(client, identities):
    unknown_user = make_token(str(uuid.uuid4()))
    expired = make_token(add_identity(identities, "nurse"), iat=int(time.time()) - 7200, exp_in=60)
    forged = make_token(add_identity(identities, "nurse"), secret="not-the-secret-not-the-secret-123456")
    bodies = {(r.status_code, r.text) for r in (
        client.get("/v1/me", headers={"Authorization": f"Bearer {t}"}) for t in (unknown_user, expired, forged, "garbage"))}
    assert len({b[0] for b in bodies}) == 1 and next(iter(bodies))[0] == 401
    assert len({re.sub(r'"request_id":"[^"]*"', "", b[1]) for b in bodies}) == 1


# ---------------------------------------------------------------------------
# T10 / T222 / T589 / T230 / T114 - server-to-server and component authentication
# ---------------------------------------------------------------------------
def _routes():
    return [r for r in create_app().routes if isinstance(r, APIRoute)]


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_every_non_public_route_requires_credentials():
    checks = [(m, r.path) for r in _routes() for m in sorted(r.methods - {"HEAD", "OPTIONS"}) if (m, r.path) not in PUBLIC_ROUTES]
    for i in range(0, len(checks), 20):  # fresh app per batch: stay under the unauthenticated per-IP rate limit
        with TestClient(create_app()) as c:
            for method, path in checks[i:i + 20]:
                r = c.request(method, _fill(path), json={})
                assert r.status_code == 401, (method, path, r.status_code)


@pytest.mark.parametrize("token_kind", ["alg_none", "wrong_audience", "wrong_issuer", "no_exp"])
def test_invalid_tokens_rejected(client, identities, token_kind):
    uid = add_identity(identities, "nurse")
    now = int(time.time())
    claims = {"sub": uid, "aud": "authenticated", "iss": "https://test-project.supabase.co/auth/v1", "iat": now, "exp": now + 600}
    if token_kind == "alg_none":
        token = jwt.encode(claims, key=None, algorithm="none")
    elif token_kind == "wrong_audience":
        token = jwt.encode({**claims, "aud": "service_role"}, SECRET, algorithm="HS256")
    elif token_kind == "wrong_issuer":
        token = jwt.encode({**claims, "iss": "https://evil.example/auth/v1"}, SECRET, algorithm="HS256")
    else:
        claims.pop("exp")
        token = jwt.encode(claims, SECRET, algorithm="HS256")
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_origin_ip_and_role_headers_are_not_authentication(client, identities):
    spoof = {"Origin": "https://acme-clinical.vercel.app", "X-Forwarded-For": "127.0.0.1", "X-Role": "admin",
             "X-User-Id": str(uuid.uuid4()), "Referer": "https://acme-clinical.vercel.app/team"}
    assert client.get("/v1/staff", headers=spoof).status_code == 401
    _, nurse = _admin_headers(identities, "nurse")
    assert client.get("/v1/staff", headers={**nurse, **spoof}).status_code == 403


def test_outbound_http_clients_verify_tls():
    for path in (BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("AsyncClient", "Client"):
                kw = {k.arg: k.value for k in node.keywords}
                assert "verify" in kw and isinstance(kw["verify"], ast.Constant) and kw["verify"].value is True, \
                    f"{path.name}:{node.lineno} must pass verify=True"
        assert "verify=False" not in path.read_text(encoding="utf-8")


def test_supabase_admin_client_uses_https_tls_and_server_key():
    async def build():
        async with staff.supabase_admin_client(get_settings()) as c:
            return c.base_url.scheme, c.headers.get("apikey"), c.follow_redirects

    assert asyncio.run(build()) == ("https", "service-test-key", False)


def test_service_role_key_never_reaches_the_browser():
    env_example = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    keys = re.findall(r"^([A-Z0-9_]+)=", env_example, re.M)
    assert set(keys) <= {"VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY", "VITE_API_BASE_URL"}
    for path in (FRONTEND / "src").rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"SERVICE_ROLE|service_role_key|JWT_SECRET|DATABASE_URL", text), path.name
    dist = FRONTEND / "dist"
    if dist.exists():
        for path in dist.rglob("*.js"):
            assert "service-role" not in path.read_text(encoding="utf-8", errors="ignore").lower()


def test_database_connection_requires_tls_and_dedicated_role():
    base = dict(supabase_url="https://x.supabase.co", supabase_anon_key="a", supabase_service_role_key="s",
                supabase_jwt_secret="j" * 40)
    with pytest.raises(ValueError):
        Settings(**base, database_url="postgresql://acme_api:pw@db:5432/postgres")
    assert passwords.database_url_problems("postgresql://postgres:short@db/postgres")
    assert passwords.database_url_problems(
        "postgresql://acme_api:Zq8-vR2kLp0wXs9Tb7Yn@db:5432/postgres?sslmode=verify-full") == []


@pytest.mark.parametrize("value", ["changeme", "short", "a" * 40, "<service-role-key>"])
def test_weak_system_secrets_rejected(value):
    assert passwords.system_secret_problems("SECRET", value)


def test_env_examples_do_not_pass_secret_validation():
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    dsn = re.search(r"^DATABASE_URL=(.+)$", example, re.M).group(1)
    assert passwords.database_url_problems(dsn)
    service = re.search(r"^SUPABASE_SERVICE_ROLE_KEY=(.+)$", example, re.M).group(1)
    assert passwords.system_secret_problems("SUPABASE_SERVICE_ROLE_KEY", service)


def test_no_shared_secret_internal_routes_exist():
    """All machine-to-API calls use per-user JWTs; there is no static-secret /internal endpoint to brute force."""
    assert not [r.path for r in _routes() if r.path.startswith(("/internal", "/v1/internal", "/cron"))]


# ---------------------------------------------------------------------------
# T425 / T426 / T114 - monitor authenticity
# ---------------------------------------------------------------------------
def test_device_secret_verification():
    secret, digest = device_auth.new_device_secret()
    assert len(digest) == 32 and device_auth.verify_device_secret(secret, digest)
    assert not device_auth.verify_device_secret(secret + "x", digest)                    # wrong secret
    assert not device_auth.verify_device_secret(secret, device_auth.hash_device_secret("other-secret-value-123"))
    assert not device_auth.verify_device_secret(secret, digest, status="retired")         # retired device
    assert not device_auth.verify_device_secret("", digest) and not device_auth.verify_device_secret("short", digest)
    assert not device_auth.verify_device_secret(secret, None)                             # unknown device
    assert device_auth.new_device_secret()[0] != secret


def test_device_verification_in_db_fails_closed():
    class Conn:
        def __init__(self, ok):
            self.ok = ok

        def cursor(self):
            ok = self.ok

            class Cur:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *a):
                    return False

                async def execute(self, sql, params):
                    assert "public.verify_monitor_secret(%s, %s)" in sql

                async def fetchone(self):
                    return {"ok": ok}

            return Cur()

    mid = uuid.uuid4()
    asyncio.run(device_auth.verify_in_db(Conn(True), mid, "a-valid-length-secret"))
    for conn, secret in ((Conn(False), "a-valid-length-secret"), (Conn(True), None), (Conn(True), "short")):
        with pytest.raises(device_auth.DeviceAuthError):
            asyncio.run(device_auth.verify_in_db(conn, mid, secret))


def test_device_verification_sql_is_hashed_and_throttled():
    body = AUTH_SQL.split("create or replace function public.verify_monitor_secret", 1)[1].split("end $$;", 1)[0]
    assert "digest(convert_to(p_secret, 'UTF8'), 'sha256') = v_hash" in body
    assert "v_status <> 'retired'" in body
    assert "f.failures + 1 >= 5" in body and "locked_until > now()" in body
    assert "grant execute on function public.verify_monitor_secret(uuid, text) to acme_api_rw" in AUTH_SQL
    seed = (SUPABASE / "seed.sql").read_text(encoding="utf-8")
    assert "digest(gen_random_bytes(32), 'sha256')" in seed


# ---------------------------------------------------------------------------
# T427 / T428 - previous-login notice data
# ---------------------------------------------------------------------------
def test_login_history_counts_failures_since_previous_success():
    assert "insert into private.login_attempts (user_id, success)" in AUTH_SQL
    body = AUTH_SQL.split("function public.login_activity_summary(p_user uuid)", 1)[1].split("$$;", 1)[0]
    assert "offset 1 limit 1" in body                                    # previous success, not the current one
    assert "p_user = public.current_staff_id() or public.current_staff_role() = 'admin'" in body  # own history only
    assert "interval '90 days'" in AUTH_SQL                              # retention


# ---------------------------------------------------------------------------
# T2 - secure password reset mechanism (config as code + templates; UI behaviour in frontend auth.test.tsx)
# ---------------------------------------------------------------------------
def test_t2_recovery_links_are_short_lived_rate_limited_and_notified():
    email = AUTH_CFG["email"]
    assert email["otp_expiry"] <= 1800                       # 15-30 minutes, single use (GoTrue one-time tokens)
    assert email["max_frequency"] == "60s"                  # one recovery e-mail per address per minute
    assert 0 < AUTH_CFG["rate_limit"]["email_sent"] <= 10 and 0 < AUTH_CFG["rate_limit"]["token_verifications"] <= 30
    notice = email["notification"]["password_changed"]
    assert notice["enabled"] is True                        # confirmation e-mail after every password change
    body = (ROOT / notice["content_path"].removeprefix("./")).read_text(encoding="utf-8")
    assert "{{ .Password" not in body and "password was changed" in body.lower()
    assert (ROOT / email["template"]["recovery"]["content_path"].removeprefix("./")).exists()
    assert all("*" not in u for u in AUTH_CFG["additional_redirect_urls"])  # exact redirect allow-list


def test_t2_captcha_decision_is_documented_with_compensating_controls():
    """CAPTCHA would need a third-party script/iframe, which the CSP forbids (T279); the decision and the
    compensating controls are recorded so the gap stays visible."""
    doc = (ROOT / "docs" / "security" / "authentication.md").read_text(encoding="utf-8")
    assert AUTH_CFG["captcha"]["enabled"] is False
    section = doc.split("### Anti-automation on recovery (T2)", 1)[1].split("\n## ", 1)[0]
    for control in ("token_verifications", "max_frequency", "email_sent", "lockout", "Vercel Firewall"):
        assert control in section, control


# ---------------------------------------------------------------------------
# T69 - strong credentials for server-to-server system accounts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["0123456789abcdefghijklmnopqrstuv", "abcdefghijklmnopqrstuvwxyz012345",
                                   "password1234567890", "zzzzzzzzzzzzzzzzzzzz", "<jwt-secret>", "Ab1!Ab1!"])
def test_t69_sequential_common_short_and_placeholder_system_secrets_rejected(value):
    assert passwords.system_secret_problems("SECRET", value, min_length=32)


def test_t69_system_secret_floor_never_below_end_user_policy():
    assert passwords.system_secret_problems("X", "Zq8-vR2kLp0", min_length=4)  # 11 chars < platform floor 12
    assert passwords.PLATFORM_MIN_LENGTH == AUTH_CFG["minimum_password_length"]


STRONG_JWT = "7hT2-xK9qLm4Vb8Np1Zr6Wc3Ys5Ud0Fg2Jk7Ha4Ee9Ti1Ro6"
STRONG_DSN = "postgresql://acme_api:Zq8-vR2kLp0wXs9Tb7Yn@db:5432/postgres?sslmode=verify-full"


def _prod(**overrides):
    base = dict(app_env="production", supabase_url="https://x.supabase.co", supabase_anon_key="anon-key-value",
                supabase_service_role_key="Sv9-kQ2wLx7pZr4Tn8Yb3Mc6", supabase_jwt_secret=STRONG_JWT,
                database_url=STRONG_DSN)
    base.update(overrides)
    return Settings(**base)


def test_t69_production_rejects_a_20_character_jwt_secret_and_accepts_48_random():
    import secrets as _secrets

    with pytest.raises(ValueError):
        _prod(supabase_jwt_secret="Kx7-Pq2mZt9Lw4Rb8Nc1")      # 20 characters
    assert _prod(supabase_jwt_secret=_secrets.token_urlsafe(36)).is_production  # 48 characters


def test_t69_t60_production_requires_an_ec_p521_audit_signing_key_when_set():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa

    def pem(key) -> str:
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption()).decode()

    assert _prod(audit_signing_key=pem(ec.generate_private_key(ec.SECP521R1()))).is_production
    for bad in (pem(ec.generate_private_key(ec.SECP256R1())), pem(rsa.generate_private_key(65537, 2048)), "not-a-pem"):
        with pytest.raises(ValueError):
            _prod(audit_signing_key=bad)


def test_t69_database_dsn_must_verify_the_server_certificate():
    assert passwords.database_url_problems(STRONG_DSN.replace("verify-full", "require"))
    assert passwords.database_url_problems(STRONG_DSN) == []


def test_t69_cli_device_secrets_are_unique_and_at_least_32_characters():
    issued = {device_auth.new_device_secret()[0] for _ in range(1000)}
    assert len(issued) == 1000 and min(len(s) for s in issued) >= 32


# ---------------------------------------------------------------------------
# T70 - lockout / throttling of system accounts (monitors presenting device secrets)
# ---------------------------------------------------------------------------
LOCKOUT_SQL = (SUPABASE / "migrations" / "0012_device_auth_lockout.sql").read_text(encoding="utf-8")


def test_t70_device_lockout_backs_off_exponentially_with_a_24_hour_cap():
    body = LOCKOUT_SQL.split("create or replace function public.verify_monitor_secret", 1)[1].split("end $$;", 1)[0]
    assert "f.failures + 1 >= 5" in body and "locked_until > now()" in body
    assert "interval '15 minutes' * power(2, least(f.lockouts, 7))" in body       # 15, 30, 60 ... minutes
    assert "least(interval '24 hours'" in body                                     # capped at 24 hours
    assert "delete from private.device_auth_failures where monitor_id = p_monitor" in body  # reset on success
    assert "digest(convert_to(p_secret, 'UTF8'), 'sha256') = v_hash" in body
    # state lives in the database, shared by every API instance; nothing is counted in process memory
    assert "device_auth_failures" not in (BACKEND / "app" / "services" / "device_auth.py").read_text(encoding="utf-8")


def test_t70_admin_unlock_is_database_enforced():
    fn = LOCKOUT_SQL.split("create or replace function public.unlock_monitor_auth", 1)[1].split("end $$;", 1)[0]
    assert "public.has_permission('settings:manage')" in fn and "security definer set search_path" in fn
    assert "'public.unlock_monitor_auth(uuid) to acme_api_rw'" in LOCKOUT_SQL


@pytest.fixture
def monitor_env(monkeypatch):
    from app.routers import monitors

    env = SimpleNamespace(sql=[], events=[], alerts=[], verify_ok=False, locked=False)

    @asynccontextmanager
    async def fake_tx(principal, read_only=False):
        yield _Conn(env.sql)

    async def fake_one(conn, sql, params=()):
        env.sql.append((sql, params))
        if "verify_monitor_secret" in sql:
            return {"ok": env.verify_ok}
        if "monitor_auth_locked" in sql:
            return {"locked": env.locked}
        if "unlock_monitor_auth" in sql:
            return {"unlocked": True}
        return None

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        env.events.append((action, kw.get("outcome", "success"), kw.get("details")))

    async def fake_notify(kind, details=None):
        env.alerts.append((kind, details))

    monkeypatch.setattr(monitors, "transaction", fake_tx)
    monkeypatch.setattr(monitors, "fetch_one", fake_one)
    monkeypatch.setattr("app.db.fetch_one", fake_one)  # device_auth.verify_in_db uses app.db.fetch_one
    monkeypatch.setattr(monitors, "record_event", fake_record)
    monkeypatch.setattr(monitors, "notify_admins", fake_notify)
    return env


def _bind_body() -> dict:
    return {"bed_id": str(uuid.uuid4()), "confirm": True, "pairing_code": "Device-Pairing-Code-Valid-1"}


def test_t70_locked_monitor_gets_the_wrong_secret_response_plus_audit_and_admin_alert(client, identities, monitor_env):
    mid = str(uuid.uuid4())
    _, h = _admin_headers(identities, "biomed_tech")
    wrong = client.post(f"/v1/monitors/{mid}/assignment", headers=h, json=_bind_body())
    monitor_env.locked = True
    locked = client.post(f"/v1/monitors/{mid}/assignment", headers=h, json=_bind_body())
    assert wrong.status_code == locked.status_code == 403

    def strip(r):
        return {k: v for k, v in r.json().items() if k != "request_id"}

    assert strip(wrong) == strip(locked)                                      # no oracle for "locked"
    actions = [a for a, _, _ in monitor_env.events]
    assert actions.count("monitor.auth_failed") == 2 and actions.count("monitor.auth_locked") == 1
    assert monitor_env.alerts == [("device_auth_lockout", {"monitor_id": mid})]
    # refused before any database write that binds the monitor (T558)
    assert not any("monitor_assignments" in sql for sql, _ in monitor_env.sql)


def test_t70_admin_unlock_is_audited_and_admin_only(client, identities, monitor_env):
    mid = str(uuid.uuid4())
    for role in ("biomed_tech", "nurse", "physician"):
        _, h = _admin_headers(identities, role)
        assert client.delete(f"/v1/monitors/{mid}/auth-lockout", headers=h).status_code == 403
    _, h = _admin_headers(identities, "admin")
    assert client.delete(f"/v1/monitors/{mid}/auth-lockout", headers=h).status_code == 204
    assert ("monitor.auth_unlocked", "success", {"was_locked": True}) in monitor_env.events


def test_t70_device_authentication_is_rate_limited_per_client_and_per_ip():
    from app.core.middleware import DEVICE_AUTH_PER_IP, ROUTE_LIMITS, RateLimitMiddleware

    rule = next(r for r in ROUTE_LIMITS if r.name == "device-auth")
    path = f"/v1/monitors/{uuid.uuid4()}/assignment"
    assert rule.pattern.match(path) and rule.per_minute <= 10 and DEVICE_AUTH_PER_IP <= 30
    mw = RateLimitMiddleware(app=None, per_minute=120, auth_per_minute=10)
    request = SimpleNamespace(url=SimpleNamespace(path=path), method="POST",
                              headers={"x-vercel-forwarded-for": "203.0.113.9", "authorization": "Bearer t"},
                              client=None)
    keys = [k for k, _ in mw._budgets(request)]
    assert "device-auth|ip:203.0.113.9" in keys                       # per source address
    assert any(k.startswith("device-auth|u:") for k in keys)          # per client


# ---------------------------------------------------------------------------
# T558 - every component authenticates its peer before exchanging data
# ---------------------------------------------------------------------------
def test_t558_every_hop_authenticates_its_peer():
    with pytest.raises(ValueError):
        _prod(database_url=STRONG_DSN.replace("verify-full", "require"))   # API -> Postgres: verified TLS only
    with pytest.raises(ValueError):
        _prod(supabase_url="http://x.supabase.co")                          # API -> Supabase: https only
    csp = json.loads((FRONTEND / "vercel.json").read_text(encoding="utf-8"))["headers"][0]["headers"][0]["value"]
    connect = next(d for d in csp.split(";") if d.strip().startswith("connect-src")).split()[1:]
    assert all(o == "'self'" or o.startswith(("https://", "wss://")) for o in connect)  # browser -> pinned origins
    assert "must use https" in (FRONTEND / "src" / "services" / "api.ts").read_text(encoding="utf-8")
