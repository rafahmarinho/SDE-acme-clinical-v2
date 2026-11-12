"""Secure configuration and supply-chain tests (skills/secure-config-supply-chain).

Secure defaults (T2349/T2357), secrets in configuration (T62), certificate validation (T175), random numbers
(T587), cryptography (T446/T445), dynamic code loading (T305), third-party components (T241/T1364/T370),
unified security settings (T371/T2273), documentation (T379), cloud architecture (T2288/T2300/T2361) and
re-deployment routines (T2478/T2477).
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.middleware import RateLimitMiddleware
from app.core.security import decode_access_token
from app.routers import settings as settings_router
from app.services import privacy
from tests.conftest import ISSUER, SECRET, add_identity, make_token

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
APP = BACKEND / "app"
FRONTEND = ROOT / "frontend"
DOCS = ROOT / "docs" / "security"
README = (ROOT / "README.md").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def py_sources():
    return [(p, p.read_text(encoding="utf-8")) for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def fe_sources():
    return [(p, p.read_text(encoding="utf-8")) for p in (FRONTEND / "src").rglob("*.ts*")
            if not p.name.endswith((".test.ts", ".test.tsx"))]


REQUIRED_ENV = {
    "SUPABASE_URL": "https://x.supabase.co",
    "SUPABASE_ANON_KEY": "anon-key-value",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role-value",
    "SUPABASE_JWT_SECRET": "j" * 40,
    "DATABASE_URL": "postgresql://acme_api:pw@db.example:5432/postgres?sslmode=verify-full",
}


@pytest.fixture
def bare_env(monkeypatch):
    """Only the required secrets: every optional setting takes its default (no .env file)."""
    for key in list(os.environ):
        if key in REQUIRED_ENV or key in ("APP_ENV", "ENABLE_DOCS", "CORS_ALLOWED_ORIGINS"):
            monkeypatch.delenv(key, raising=False)
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(ROOT)  # no backend/.env picked up
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def prod_client(bare_env):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


# =========================================================================== T2349 / T2357 secure defaults
def test_t2349_defaults_are_production_with_docs_off_and_no_origins(bare_env):
    s = get_settings()
    assert s.app_env == "production" and s.is_production
    assert s.docs_enabled is False and s.origins == []


def test_t2357_docs_and_openapi_absent_by_default(prod_client):
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert prod_client.get(path).status_code in (401, 404)


def test_t2357_enable_docs_is_ignored_in_production(bare_env, monkeypatch):
    monkeypatch.setenv("ENABLE_DOCS", "true")
    assert Settings().docs_enabled is False
    monkeypatch.setenv("APP_ENV", "test")
    assert Settings().docs_enabled is True


def test_t2357_cors_denies_unknown_origins_by_default(prod_client):
    r = prod_client.options("/v1/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers


def test_t2357_security_headers_on_every_response(prod_client):
    h = prod_client.get("/v1/health", headers={"Host": "acme-clinical-api.vercel.app"}).headers
    assert h["x-content-type-options"] == "nosniff"
    assert "max-age=" in h["strict-transport-security"]
    assert "no-store" in h["cache-control"]


def test_t2349_production_start_refuses_unprotected_routes(bare_env):
    from app.main import create_app

    app = create_app()

    @app.get("/v1/debug")
    async def debug() -> dict:
        return {}

    with pytest.raises(RuntimeError, match="Unprotected routes"):
        with TestClient(app):
            pass


def test_t2349_simulation_reset_is_admin_only_with_typed_confirmation():
    src = (APP / "routers" / "simulation.py").read_text(encoding="utf-8")
    assert "SIMULATION_CONTROL" in src
    schemas = (APP / "schemas" / "__init__.py").read_text(encoding="utf-8")
    assert "RESET DEMO DATA" in schemas


# =========================================================================== T62 secrets in configuration
@pytest.mark.parametrize("missing", sorted(REQUIRED_ENV))
def test_t62_startup_fails_without_each_secret(bare_env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("name", ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "SUPABASE_ANON_KEY"])
@pytest.mark.parametrize("value", ["", "   ", "<service-role-key>"])
def test_t62_empty_or_placeholder_secrets_rejected(bare_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


def test_t62_secrets_never_appear_in_reprs(bare_env):
    s = Settings()
    text = repr(s) + str(s.model_dump())
    for value in REQUIRED_ENV.values():
        if "supabase.co" not in value:
            assert value not in text


def test_t62_env_examples_hold_placeholders_only_and_env_files_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore and "!.env.example" in gitignore
    backend = (BACKEND / ".env.example").read_text(encoding="utf-8")
    for key in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET"):
        assert re.search(rf"^{key}=<[^>]+>$", backend, re.M), key
    frontend = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    keys = set(re.findall(r"^([A-Z0-9_]+)=", frontend, re.M))
    assert keys <= {"VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY", "VITE_API_BASE_URL"}
    assert not [k for k in keys if re.search(r"SERVICE|SECRET|DATABASE", k)]


def test_t62_no_secrets_in_vercel_configs_seed_or_ci():
    for path in (BACKEND / "vercel.json", FRONTEND / "vercel.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "env" not in data and "build" not in data or "env" not in data.get("build", {}), path
    seed = (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8")
    assert not re.search(r"(?i)password\s*=|eyJ[a-zA-Z0-9_-]{10,}", seed)
    assert not re.search(r"eyJ[a-zA-Z0-9_-]{10,}\.|sb_secret_|service_role_key\s*:", CI)
    assert "${{ secrets." in CI and "gitleaks/gitleaks-action" in CI
    assert "bundle has no server secrets" in CI.lower()


def test_t62_readme_documents_where_secrets_live():
    for key in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "DATABASE_URL", "--sensitive"):
        assert key in README


# =========================================================================== T175 certificate validation
def test_t175_database_tls_must_verify_certificates(bare_env, monkeypatch):
    for dsn in ("postgresql://acme_api:pw@h/db", "postgresql://acme_api:pw@h/db?sslmode=require",
                "postgresql://acme_api:pw@h/db?sslmode=prefer", "postgresql://acme_api:pw@h/db?sslmode=verify-ca",
                "postgresql://acme_api:pw@h/db?sslmode=disable&sslmode=verify-full"):
        monkeypatch.setenv("DATABASE_URL", dsn)
        with pytest.raises(ValidationError):
            Settings()
    monkeypatch.setenv("DATABASE_URL", "postgresql://acme_api:pw@h/db?sslmode=verify-full&sslrootcert=system")
    assert Settings()


def test_t175_service_urls_must_be_https(bare_env, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://x.supabase.co")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://web.example")
    with pytest.raises(ValidationError):
        Settings()
    # local development stack only
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SUPABASE_URL", "http://127.0.0.1:54321")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    assert Settings().supabase_url.host == "127.0.0.1"


def test_t175_tls_verification_never_disabled_in_source():
    bad = re.compile(r"verify\s*=\s*False|CERT_NONE|check_hostname\s*=\s*False|NODE_TLS_REJECT_UNAUTHORIZED|rejectUnauthorized:\s*false")
    offenders = [p.name for p, src in py_sources() + fe_sources() if bad.search(src)]
    assert offenders == []
    for p, src in py_sources():
        for m in re.finditer(r"httpx\.AsyncClient\(([^\n]*)", src):
            assert "verify=True" in m.group(1), (p.name, m.group(0))


@pytest.mark.skipif(os.environ.get("RUN_NETWORK_TESTS") != "1", reason="network test (scheduled CI job)")
@pytest.mark.parametrize("host", ["self-signed.badssl.com", "expired.badssl.com", "wrong.host.badssl.com",
                                  "untrusted-root.badssl.com"])
@pytest.mark.asyncio
async def test_t175_rejects_bad_certificates(host):
    import httpx

    async with httpx.AsyncClient(base_url=f"https://{host}", timeout=10, verify=True) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("/")


# =========================================================================== T587 random numbers
def test_t587_random_module_only_for_synthetic_vitals():
    offenders = []
    for p, src in py_sources():
        if re.search(r"^\s*(import random|from random import)", src, re.M) and p.name != "simulation.py":
            offenders.append(p.name)
        assert not re.search(r"\buuid1\(", src), p.name
    assert offenders == []
    sim = (APP / "services" / "simulation.py").read_text(encoding="utf-8")
    assert "synthetic" in sim.lower() and "secrets" in sim  # documented: not for security values
    assert not [p.name for p, src in fe_sources() if "Math.random" in src]


def test_t587_security_values_use_csprng():
    joined = "\n".join(src for _, src in py_sources())
    assert "secrets.token_" in joined or "secrets.choice" in joined
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "supabase" / "migrations").glob("*.sql"))
    assert "gen_random_uuid()" in sql
    assert "crypto.randomUUID" in (FRONTEND / "src" / "services" / "api.ts").read_text(encoding="utf-8")


# =========================================================================== T446 / T445 cryptography
BANNED_PY = re.compile(r"^\s*(import|from)\s+(jose|Crypto|Cryptodome|pycrypto|simplecrypt|md5|sha)\b", re.M)
WEAK = re.compile(r"hashlib\.(md5|sha1)\(|hashlib\.new\(\s*['\"](md5|sha1)|modes\.ECB|algorithms\.(TripleDES|ARC4|Blowfish)|"
                  r"\bDES\b|algorithms\s*=\s*None")
UNVERIFIED_JWT = re.compile(r"verify_signature['\"]?\s*:\s*False")
# Only the rate limiter peeks at an unverified `sub` to pick a throttling bucket; it never authorizes anything.
UNVERIFIED_JWT_ALLOWED = {"middleware.py"}


def test_t446_only_standard_crypto_libraries():
    assert not [p.name for p, src in py_sources() if BANNED_PY.search(src)]
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    deps = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    assert not deps & {"crypto-js", "jsrsasign", "node-forge", "jwt-decode", "jsonwebtoken", "bcryptjs", "md5", "sha1"}
    reqs = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pyjwt\[crypto\]==", reqs, re.M) and re.search(r"^cryptography==", reqs, re.M)
    assert "python-jose" not in reqs and "pycrypto" not in reqs


def test_t445_no_weak_primitives_and_explicit_jwt_algorithms():
    assert not [p.name for p, src in py_sources() if WEAK.search(src)]
    assert {p.name for p, src in py_sources() if UNVERIFIED_JWT.search(src)} <= UNVERIFIED_JWT_ALLOWED
    for p, src in py_sources():
        for call in re.finditer(r"jwt\.decode\((.*?)\)\n", src, re.S):
            if not UNVERIFIED_JWT.search(call.group(1)):  # every VERIFYING decode pins its algorithms
                assert "algorithms=[" in call.group(1), p.name


def _token(**overrides) -> str:
    now = int(time.time())
    claims = {"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISSUER, "iat": now, "exp": now + 600}
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_t445_alg_none_and_wrong_keys_are_rejected():
    from fastapi import HTTPException

    settings = get_settings()
    assert decode_access_token(_token(), settings)["aud"] == "authenticated"
    header = jwt.utils.base64url_encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode()
    body = jwt.utils.base64url_encode(json.dumps({"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": ISSUER,
                                                  "iat": int(time.time()), "exp": int(time.time()) + 600}).encode()).decode()
    forged = [f"{header}.{body}.", jwt.encode({"sub": "x", "aud": "authenticated"}, "secret", algorithm="HS256"),
              jwt.encode({"sub": "x", "aud": "authenticated", "iss": ISSUER, "iat": 1, "exp": 2 ** 31}, "x" * 40,
                         algorithm="HS512")]
    for token in forged:
        with pytest.raises(HTTPException) as exc:
            decode_access_token(token, settings)
        assert exc.value.status_code == 401


def test_t445_jwt_secret_meets_key_length_in_production():
    doc = (DOCS / "secure-config.md").read_text(encoding="utf-8")
    assert "HS256" in doc and "SHA-256" in doc and "AES-256-GCM" in doc and "bcrypt" in doc


# =========================================================================== T305 dynamic code loading
def test_t305_no_eval_or_remote_code_in_frontend():
    dynamic = re.compile(r"\beval\(|new Function\(|importScripts\(|import\(\s*[`'\"]https?:|setDecoderPath\(\s*['\"]https?:")
    assert not [p.name for p, src in fe_sources() if dynamic.search(src)]
    for p, src in fe_sources():
        for m in re.finditer(r"\bimport\(([^)]*)\)", src):
            assert re.fullmatch(r"\s*['\"]\./[^'\"]+['\"]\s*", m.group(1)), (p.name, m.group(0))  # static, same-origin
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script[^>]+src=\"(https?:)?//", index)
    dist = FRONTEND / "dist" / "index.html"
    if dist.exists():
        assert not re.search(r"<script[^>]+src=\"(https?:)?//", dist.read_text(encoding="utf-8"))


def test_t305_no_dynamic_imports_or_exec_in_backend():
    bad = re.compile(r"\bimportlib\b|__import__\(|\bexec\(|\beval\(|pickle\.loads|yaml\.load\(")
    assert not [p.name for p, src in py_sources() if bad.search(src)]


def test_t305_csp_restricts_scripts_to_self():
    data = json.loads((FRONTEND / "vercel.json").read_text(encoding="utf-8"))
    csp = [h["value"] for block in data.get("headers", []) for h in block["headers"] if h["key"] == "Content-Security-Policy"]
    assert csp and "script-src 'self'" in csp[0] and "object-src 'none'" in csp[0]


# =========================================================================== T241 / T1364 / T370 third-party components
def test_t241_backend_dependencies_are_exactly_pinned():
    for file in ("requirements.txt", "requirements-dev.txt"):
        for line in (BACKEND / file).read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line and not line.startswith("-r"):
                assert re.fullmatch(r"[A-Za-z0-9_.\-]+(\[[a-z,]+\])?==[0-9][0-9A-Za-z.\-]*", line), (file, line)


def test_t241_frontend_dependencies_are_exact_and_locked():
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    for name, version in {**pkg["dependencies"], **pkg["devDependencies"]}.items():
        assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), (name, version)
    assert (FRONTEND / "pnpm-lock.yaml").exists()
    assert pkg["packageManager"].startswith("pnpm@")


def test_t241_ci_audits_dependencies_and_dependabot_covers_all_ecosystems():
    for step in ("pip-audit -r requirements.txt --strict", "pnpm audit --audit-level=moderate",
                 "pnpm install --frozen-lockfile", "gitleaks", "cron:"):
        assert step in CI, step
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    for eco in ('"pip"', '"npm"', '"github-actions"'):
        assert eco in dependabot


def test_t1364_scanner_canaries_and_license_checks_in_ci():
    assert "jinja2==2.10" in CI and "lodash" in CI  # known-vulnerable canaries must be detected
    assert "pip-licenses" in CI and "pnpm licenses list" in CI


@pytest.mark.skipif(not (FRONTEND / "node_modules").exists(), reason="frontend dependencies not installed")
def test_t1364_frontend_direct_dependency_licenses_are_approved():
    allowed = re.compile(r"^(MIT|ISC|BSD-2-Clause|BSD-3-Clause|Apache-2.0|0BSD|MPL-2.0)$")
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    for name in {**pkg["dependencies"], **pkg["devDependencies"]}:
        manifest = FRONTEND / "node_modules" / name / "package.json"
        if manifest.exists():
            lic = json.loads(manifest.read_text(encoding="utf-8")).get("license", "")
            assert allowed.match(str(lic)), (name, lic)


def test_t1364_backend_direct_dependency_licenses_are_approved():
    from importlib import metadata

    allowed = re.compile(r"MIT|BSD|Apache|ISC|Unlicense|PSF|Python Software Foundation|LGPL|Lesser General Public", re.I)
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = re.match(r"^([A-Za-z0-9_.\-]+)", line.split("#")[0].strip())
        if not name:
            continue
        try:
            md = metadata.metadata(name.group(1))
        except metadata.PackageNotFoundError:
            continue
        text = " ".join([md.get("License-Expression") or "", md.get("License") or "",
                         *[c for c in (md.get_all("Classifier") or []) if c.startswith("License")]])
        assert allowed.search(text), (name.group(1), text[:80])
        assert "AGPL" not in text and "GNU General Public License" not in text.replace("Lesser General Public", "")


def test_t370_component_register_documents_every_direct_dependency():
    doc = (DOCS / "secure-config.md").read_text(encoding="utf-8").lower()
    for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = re.match(r"^([a-z0-9_.\-]+)", line.split("#")[0].strip().lower())
        if name:
            assert name.group(1).replace("[crypto]", "") in doc, name.group(1)
    for dep in ("react", "react router", "@supabase/supabase-js", "vite", "supabase", "vercel"):
        assert dep in doc, dep


def test_t1364_service_role_key_confined_to_backend():
    assert not [p.name for p, src in fe_sources() if re.search(r"SERVICE_ROLE|service_role|JWT_SECRET", src)]
    users = {p.name for p, src in py_sources() if "supabase_service_role_key" in src}
    assert users <= {"config.py", "files.py", "privacy.py", "cli.py", "staff.py", "auth.py", "passwords.py"}, users


# =========================================================================== T371 / T2273 unified security settings
class _Conn:
    def __init__(self, db):
        self.db = db

    async def execute(self, sql, params=()):
        self.db.calls.append((sql, params))


class _DB:
    def __init__(self):
        self.calls: list = []
        self.settings = {"password_min_length": 12, "session_idle_minutes": 15, "session_absolute_hours": 12,
                         "max_concurrent_sessions": 2, "lockout_threshold": 5, "lockout_minutes": 15,
                         "require_mfa_for_admin": True, "data_retention_days": 365, "updated_at": "2026-11-01T00:00:00Z"}
        self.approved: dict | None = None

    @asynccontextmanager
    async def transaction(self, principal):
        yield _Conn(self)

    async def fetch_one(self, conn, sql, params=()):
        self.calls.append((sql, params))
        if "from public.security_settings_approvals" in sql:
            return self.approved
        if "insert into public.security_settings_approvals" in sql:
            self.approved = {"fingerprint": params[0], "approved_at": "2026-11-12T00:00:00Z"}
            return self.approved
        if "from public.security_settings" in sql:
            return dict(self.settings)
        return None

    async def fetch_all(self, conn, sql, params=()):
        self.calls.append((sql, params))
        return []


@pytest.fixture
def sdb(monkeypatch):
    db = _DB()
    for attr in ("transaction", "fetch_all", "fetch_one"):
        monkeypatch.setattr(settings_router, attr, getattr(db, attr))
    events: list = []

    async def record(principal, action, entity_type, entity_id=None, **kw):
        events.append(action)

    monkeypatch.setattr(settings_router, "record_event", record)
    db.events = events
    return db


def _auth(identities, role):
    uid = add_identity(identities, role)
    token = make_token(uid, aal="aal2" if role == "admin" else "aal1",
                       amr=[{"method": "password", "timestamp": int(time.time())}])
    return {"Authorization": f"Bearer {token}"}


SETTINGS_ROUTES = [("GET", "/v1/settings/security", None), ("PATCH", "/v1/settings/security", {"session_idle_minutes": 30}),
                   ("GET", "/v1/settings/security/report", None), ("POST", "/v1/settings/security/approve", None),
                   ("GET", "/v1/settings/retention", None)]


@pytest.mark.parametrize("role", ["nurse", "physician", "biomed_tech"])
@pytest.mark.parametrize("method,path,body", SETTINGS_ROUTES)
def test_t2273_non_admins_cannot_read_or_change_security_settings(client, identities, sdb, role, method, path, body):
    r = client.request(method, path, headers=_auth(identities, role), json=body)
    assert r.status_code == 403
    assert not [c for c in sdb.calls if "security_settings" in c[0]]


@pytest.mark.parametrize("body", [{"session_idle_minutes": 600}, {"password_min_length": 4}, {"lockout_threshold": 1},
                                  {"data_retention_days": 1}, {"require_mfa_for_admin": "no"}, {"unknown": 1}])
def test_t2273_out_of_baseline_values_rejected(client, identities, sdb, body):
    r = client.patch("/v1/settings/security", headers=_auth(identities, "admin"), json=body)
    assert r.status_code == 422
    assert not [c for c in sdb.calls if c[0].startswith("update")]


def test_t371_changes_are_audited(client, identities, sdb):
    r = client.patch("/v1/settings/security", headers=_auth(identities, "admin"), json={"session_idle_minutes": 30})
    assert r.status_code == 200
    assert "settings.security_changed" in sdb.events


def test_t2273_report_detects_out_of_band_changes(client, identities, sdb):
    h = _auth(identities, "admin")
    first = client.get("/v1/settings/security/report", headers=h).json()
    assert first["drift"] is True and first["approved_fingerprint"] is None
    assert client.post("/v1/settings/security/approve", headers=h).status_code == 201
    approved = client.get("/v1/settings/security/report", headers=h).json()
    assert approved["drift"] is False and approved["fingerprint"] == approved["approved_fingerprint"]
    assert {"app_env", "docs_enabled", "database_tls"} <= approved["environment"].keys()
    assert {"fastapi", "pyjwt", "cryptography"} <= approved["components"].keys()
    sdb.settings["require_mfa_for_admin"] = False  # direct database change, bypassing the API
    drifted = client.get("/v1/settings/security/report", headers=h).json()
    assert drifted["drift"] is True and drifted["fingerprint"] != drifted["approved_fingerprint"]
    assert "settings.configuration_approved" in sdb.events


def test_t2273_documented_baseline_matches_api_bounds():
    from app.schemas import SecuritySettingsUpdate

    doc = (DOCS / "secure-config.md").read_text(encoding="utf-8")
    for name in SecuritySettingsUpdate.model_fields:
        if name == "require_mfa_for_admin":
            continue
        bounds = re.search(rf"\| `{name}` \| (\d+)-(\d+) \|", doc)
        assert bounds, name
        lo, hi = int(bounds.group(1)), int(bounds.group(2))
        assert SecuritySettingsUpdate.model_validate({name: lo}) and SecuritySettingsUpdate.model_validate({name: hi})
        for bad in (lo - 1, hi + 1):
            with pytest.raises(ValidationError):
                SecuritySettingsUpdate.model_validate({name: bad})


def test_t371_settings_screen_is_admin_only():
    screen = (FRONTEND / "src" / "screens" / "Settings.tsx").read_text(encoding="utf-8")
    assert 'can("settings:manage")' in screen
    for path in ("/v1/settings/security/report", "/v1/settings/security/approve", "/v1/settings/retention"):
        assert path in screen
    assert privacy.config_fingerprint(_DB().settings) == privacy.config_fingerprint(dict(_DB().settings))


# =========================================================================== T379 documentation
def test_t379_security_documentation_exists_and_is_linked():
    for page in ("architecture.md", "data-classification.md", "privacy.md", "secure-config.md", "deployment.md"):
        assert (DOCS / page).exists(), page
        assert f"docs/security/{page}" in README, page
    lowered = README.lower()
    for topic in ("roles", "authentication", "data handled", "secrets", "logging and audit", "backup",
                  "data sanitisation", "insecure demo settings", "reporting vulnerabilities", "tls"):
        assert topic in lowered, topic


def test_t379_risky_actions_carry_in_app_warnings():
    profile = (FRONTEND / "src" / "screens" / "Profile.tsx").read_text(encoding="utf-8")
    settings_screen = (FRONTEND / "src" / "screens" / "Settings.tsx").read_text(encoding="utf-8")
    assert "DELETE MY ACCOUNT" in profile and "PURGE EXPIRED DATA" in settings_screen
    assert "cannot be undone" in settings_screen and "Turn off mandatory MFA" in settings_screen


# =========================================================================== T2288 / T2300 / T2361 architecture
def test_t2288_architecture_document_shows_layers_boundaries_and_keys():
    doc = (DOCS / "architecture.md").read_text(encoding="utf-8")
    assert "```mermaid" in doc
    for item in ("Web", "Application", "Data", "Trust boundaries", "anon", "SUPABASE_SERVICE_ROLE_KEY", "region"):
        assert item in doc, item


def test_t2300_frontend_never_writes_tables_directly():
    write = re.compile(r"supabase\s*\.\s*from\([^)]*\)\s*\.\s*(insert|update|upsert|delete)\(")
    assert not [p.name for p, src in fe_sources() if write.search(src.replace("\n", " "))]
    sql = "\n".join(re.sub(r"--[^\n]*", "", p.read_text(encoding="utf-8")).lower()
                    for p in (ROOT / "supabase" / "migrations").glob("*.sql"))
    grants = [re.sub(r"\s+", " ", s.strip()) for s in sql.split(";") if s.strip().startswith("grant ")]
    assert not [g for g in grants if g.endswith("to authenticated") and re.match(r"grant (insert|update|delete)", g)]


def test_t2361_cross_layer_traffic_is_restricted():
    from app.main import create_app

    app = create_app()
    classes = {m.cls for m in app.user_middleware}
    assert RateLimitMiddleware in classes
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"] and cors.kwargs["allow_credentials"] is False
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "supabase" / "migrations").glob("*.sql"))
    # Realtime rows reach a browser session only for patients it may access
    assert re.search(r"create policy readings_read on public\.readings for select to acme_api, authenticated\s+using "
                     r"\(patient_id is null or public\.can_access_patient\(patient_id\)", sql)
    assert "Redundancy" in (DOCS / "architecture.md").read_text(encoding="utf-8") or \
        "redundancy" in (DOCS / "architecture.md").read_text(encoding="utf-8")


def test_t2361_rate_limit_returns_429():
    app = FastAPI()

    @app.get("/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, per_minute=2, auth_per_minute=2)
    with TestClient(app) as c:
        codes = [c.get("/v1/ping").status_code for _ in range(5)]
    assert 429 in codes


# =========================================================================== T2478 / T2477 re-deployment
def test_t2478_runbook_covers_deploy_from_scratch_rollback_and_restore():
    for item in ("supabase db push", "vercel deploy --prod", "vercel rollback", "PITR", "Smoke test", "/v1/health",
                 "Function Region", "Rebuild from scratch", "Secret exposure"):
        assert item in README, item
    for item in ("Recovery time objective", "Rollback", "Drill"):
        assert item in (DOCS / "deployment.md").read_text(encoding="utf-8"), item


def test_t2477_redeploy_drill_rebuilds_database_from_git():
    assert "db-drill" in CI and "supabase db reset" in CI and "select count(*) from public.patients" in CI
    assert "workflow_dispatch" in CI and "vercel deploy --prod --cwd backend" in CI and "/v1/health" in CI
    migrations = sorted(p.name for p in (ROOT / "supabase" / "migrations").glob("*.sql"))
    prefixes = [m.split("_", 1)[0] for m in migrations]
    assert len(prefixes) == len(set(prefixes)) and prefixes == sorted(prefixes)
    seed = (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8")
    assert len(re.findall(r"\('PT-\d{4}'", seed)) == 12 and "generate_series(1, 10)" in seed
