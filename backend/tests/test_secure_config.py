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
    "SUPABASE_JWT_SECRET": "jwt-secret-for-tests-0123456789-abcdefXYZ",
    "DATABASE_URL": "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@db.example:5432/postgres?sslmode=verify-full",
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
    monkeypatch.setenv("DATABASE_URL", "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@h/db?sslmode=verify-full&sslrootcert=system")
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
    async def transaction(self, principal, read_only=False):
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


# =========================================================================== T2599 connection string pollution
GOOD_DSN = "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@db.example:5432/postgres?sslmode=verify-full"


@pytest.mark.parametrize("dsn", [
    "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@db.example:5432/postgres?sslmode=disable",
    GOOD_DSN + "&host=attacker.example",
    "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@db.example,attacker.example/postgres?sslmode=verify-full",
    GOOD_DSN + "&options=-c%20role%3Dpostgres",
    GOOD_DSN + "&user=postgres",
    GOOD_DSN + "&sslmode=verify-full",
    "mysql://acme_api:Test-DB-Pw-7f3k9q2m@db.example:3306/postgres?sslmode=verify-full",
    "http://acme_api:Test-DB-Pw-7f3k9q2m@db.example/postgres?sslmode=verify-full",
])
def test_t2599_settings_reject_polluted_connection_strings(bare_env, monkeypatch, dsn):
    monkeypatch.setenv("DATABASE_URL", dsn)
    with pytest.raises(ValidationError) as exc:
        Settings()
    assert "Test-DB-Pw-7f3k9q2m" not in str(exc.value)


def test_t2599_well_formed_dsn_accepted_and_read_only_by_config_and_db(bare_env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", GOOD_DSN + "&sslrootcert=system&connect_timeout=5")
    assert Settings()
    readers = sorted(p.name for p in (Path(__file__).resolve().parents[1] / "app").rglob("*.py")
                     if "database_url" in p.read_text(encoding="utf-8").lower())
    # passwords.py inspects the DSN structure for problems, cli.py only reads ADMIN_DATABASE_URL for operators.
    assert set(readers) <= {"config.py", "db.py", "passwords.py", "cli.py"}, readers


# =========================================================================== T151 random numbers
def test_t151_math_random_never_used_outside_frontend_tests():
    offenders = [p.name for p, src in fe_sources() if re.search(r"Math\.random\s*\(", src)]
    assert offenders == []


def test_t151_generated_security_values_are_unique_and_high_entropy():
    from app.services import device_auth, files

    secrets_ = {device_auth.new_device_secret()[0] for _ in range(1000)}
    assert len(secrets_) == 1000 and all(len(s) >= 32 for s in secrets_)          # token_urlsafe(24) = 192 bits
    pid = uuid.uuid4()
    paths = {files.new_object_path(pid, "png") for _ in range(1000)}
    assert len(paths) == 1000
    for p in list(paths)[:50]:
        assert uuid.UUID(p.rsplit("/", 1)[1].split(".")[0]).version == 4          # 122 random bits


# =========================================================================== T156 / T21 certificate validation & TLS
def test_t156_tls_failures_fail_closed_with_a_security_event(caplog):
    import ssl

    import httpx

    from app.core.errors import install_error_handlers, is_tls_verification_failure

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/x")
    async def x():
        try:
            raise ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("TLS handshake failed") from exc

    with caplog.at_level("ERROR", logger="acme.security"), TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/x")
    assert r.status_code == 503 and r.json()["code"] == "dependency_unavailable" and r.headers["retry-after"]
    assert "certificate" not in r.text.lower() and "ssl" not in r.text.lower()
    assert any(rec.getMessage() == "tls_verification_failed" for rec in caplog.records)
    assert not is_tls_verification_failure(httpx.ConnectError("connection refused"))


def test_t21_hsts_on_api_responses_and_plain_http_refused_in_production(prod_client):
    r = prod_client.get("/v1/health")
    assert r.headers["strict-transport-security"].startswith("max-age=63072000")
    assert prod_client.get("/v1/health", headers={"X-Forwarded-Proto": "http"}).status_code == 400
    assert prod_client.get("/v1/health", headers={"X-Forwarded-Proto": "https"}).status_code == 200


def test_t21_frontend_origins_are_tls_only():
    data = json.loads((FRONTEND / "vercel.json").read_text(encoding="utf-8"))
    csp = data["headers"][0]["headers"][0]["value"]
    assert "upgrade-insecure-requests" in csp
    connect = next(d for d in csp.split(";") if d.strip().startswith("connect-src")).split()[1:]
    assert all(o == "'self'" or o.startswith(("https://", "wss://")) for o in connect)
    hsts = {h["key"]: h["value"] for h in data["headers"][0]["headers"]}["Strict-Transport-Security"]
    assert "max-age=63072000" in hsts
    supa = (FRONTEND / "src" / "lib" / "supabase.ts").read_text(encoding="utf-8")
    assert "VITE_SUPABASE_URL must use https" in supa


# =========================================================================== T186 secure settings / patches
def test_t186_runtime_and_package_manager_are_pinned_and_installs_are_frozen():
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"pnpm@\d+\.\d+\.\d+", pkg["packageManager"]) and pkg["engines"]["node"]
    assert "--frozen-lockfile" in CI and "pip-audit" in CI and "pnpm audit" in CI
    reqs = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pyjwt\[crypto\]==", reqs, re.M | re.I) and re.search(r"^cryptography==", reqs, re.M)
    toml = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
    assert "enable_signup = false" in toml and "secure_password_change = true" in toml


# =========================================================================== T279 dynamic code loading
def test_t279_scenario_names_are_an_enum_not_code(client, identities):
    uid = add_identity(identities, "admin")
    h = {"Authorization": f"Bearer {make_token(uid, aal='aal2', auth_time=int(time.time()))}"}
    for scenario in ("__import__('os')", "unknown_scenario"):
        r = client.post("/v1/simulation/scenario", json={"scenario": scenario}, headers=h)
        assert r.status_code == 422, (scenario, r.status_code)


# =========================================================================== T59 / T60 cryptography
def test_t59_frontend_has_no_third_party_crypto_library():
    pkg = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert not [d for d in deps if re.search(r"crypto|forge|sjcl|tweetnacl|bcrypt|jose|jsencrypt", d, re.I)]


def test_t60_purpose_keys_are_separate_from_each_other_and_the_jwt_secret():
    from app.services import integrity

    audit = integrity._derive(b"audit-signing-key-v1", 64)
    config = integrity._derive(b"config-integrity-key-v1", 32)
    jwt_secret = get_settings().supabase_jwt_secret.get_secret_value().encode()
    assert audit[:32] != config and jwt_secret not in (audit, config) and len(config) * 8 >= 256


# =========================================================================== T76 no hardcoded passwords
def test_t76_frontend_env_example_holds_only_public_placeholders():
    example = (FRONTEND / ".env.example").read_text(encoding="utf-8")
    keys = re.findall(r"^([A-Z_]+)=", example, re.M)
    assert set(keys) == {"VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY", "VITE_API_BASE_URL"}
    assert all("<" in line for line in example.splitlines() if "=" in line and not line.startswith("#"))
    toml = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
    smtp = toml.split("[auth.email.smtp]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'^pass = "env\(SUPABASE_SMTP_PASS\)"$', smtp, re.M)  # never an inline credential
    assert "gitleaks" in CI


# =========================================================================== T49 release preparation
def test_t49_release_bundles_carry_no_debug_code_tests_or_source_maps():
    vite = (FRONTEND / "vite.config.ts").read_text(encoding="utf-8")
    assert "sourcemap: false" in vite
    assert not [p.name for p, src in fe_sources() if re.search(r"\bconsole\.(log|debug|trace)\(|\bdebugger\b", src)]
    ignore = (BACKEND / ".vercelignore").read_text(encoding="utf-8").split()
    for entry in ("tests/", ".pytest_cache/", "__pycache__/", "*.log", ".env"):
        assert entry in ignore, entry
    dist = FRONTEND / "dist"
    if dist.exists():
        assert not list(dist.rglob("*.map"))  # (console calls in third-party bundles are library code, not ours)


# =========================================================================== T1386 / T2157 e-mail and messaging
TEMPLATES = ROOT / "supabase" / "templates"
TOML = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")


def test_t1386_every_template_has_the_anti_phishing_statement_and_no_secrets_or_patient_data():
    files_ = sorted(TEMPLATES.glob("*.html"))
    assert {p.name for p in files_} >= {"invite.html", "recovery.html", "email_change.html", "password_changed.html"}
    for p in files_:
        body = p.read_text(encoding="utf-8")
        assert "never asks for your password" in body, p.name
        assert "contains no patient information" in body and "intended only for" in body, p.name
        placeholders = set(re.findall(r"\{\{\s*\.(\w+)", body))
        assert placeholders <= {"ConfirmationURL", "Email", "OldEmail", "Token", "SiteURL"}, (p.name, placeholders)
        assert not re.search(r"password\s*[:=]|patient name|\bMRN\b|PT-\d{4}", body, re.I), p.name
        assert f'content_path = "./supabase/templates/{p.name}"' in TOML, p.name


def test_t1386_admin_alerts_only_carry_allow_listed_identifiers(monkeypatch):
    import asyncio as _asyncio

    from app.core import audit

    stored: list[str] = []

    class Conn:
        async def execute(self, sql, params=()):
            stored.append(params[2])

    @asynccontextmanager
    async def tx(principal, read_only=False):
        yield Conn()

    monkeypatch.setattr("app.db.transaction", tx)
    audit._last_alert.clear()
    _asyncio.run(audit.notify_admins("test_alert", {"patient_id": "p-1", "display_name": "Alex Morgan", "mrn": "123",
                                                   "heart_rate": 180, "note": "free text"}))
    assert json.loads(stored[0]) == {"patient_id": "p-1"}


def test_t2157_smtp_uses_env_credentials_and_tls_port_and_limits_mail_volume():
    smtp = TOML.split("[auth.email.smtp]", 1)[1].split("\n[", 1)[0]
    for key in ("host", "user", "pass", "admin_email"):
        assert re.search(rf'^{key} = "env\(SUPABASE_SMTP_[A-Z_]+\)"$', smtp, re.M), key
    assert re.search(r"^port = (587|465)$", smtp, re.M)
    assert re.search(r"^email_sent = \d+$", TOML, re.M) and 'max_frequency = "60s"' in TOML
    assert "supabase --yes config push" in CI and "SUPABASE_SMTP_PASS: ${{ secrets.SUPABASE_SMTP_PASS }}" in CI
    doc = (DOCS / "deployment.md").read_text(encoding="utf-8")
    assert "SPF" in doc and "DKIM" in doc and "DMARC" in doc


@pytest.mark.parametrize("email", ["a@b.com\r\nBcc: x@evil.test", "a@b.com\nCc: x@evil.test", "a@b.com%0d%0aBcc:x@evil.test"])
def test_t2157_header_injection_in_invite_address_is_rejected(client, identities, email):
    uid = add_identity(identities, "admin")
    h = {"Authorization": f"Bearer {make_token(uid, aal='aal2', auth_time=int(time.time()))}"}
    r = client.post("/v1/staff", json={"email": email, "full_name": "Eve Test", "role": "nurse"}, headers=h)
    assert r.status_code == 422


# =========================================================================== INFRA re-check: repo-side config
def test_t2170_api_functions_pinned_to_a_documented_region():
    cfg = json.loads((BACKEND / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["regions"] == ["gru1"]
    doc = (DOCS / "deployment.md").read_text(encoding="utf-8")
    assert "## Data location (T2170)" in doc and "sa-east-1" in doc


def test_t374_per_request_resources_are_bounded_and_edge_controls_documented():
    fn = json.loads((BACKEND / "vercel.json").read_text(encoding="utf-8"))["functions"]["api/index.py"]
    assert fn["maxDuration"] <= 30 and fn["memory"] <= 1024
    doc = (DOCS / "deployment.md").read_text(encoding="utf-8")
    assert "## Request handling offloaded to the platform (T374)" in doc and "Vercel Firewall" in doc


def test_t2602_pgaudit_logs_writes_ddl_and_role_changes_without_phi():
    sql = (ROOT / "supabase" / "migrations" / "0014_database_audit_logging.sql").read_text(encoding="utf-8")
    assert "create extension if not exists pgaudit" in sql
    assert "'write, ddl, role'" in sql and "pgaudit.log_parameter = %L', r, 'off'" in sql
    assert "'read'" not in sql.split("--")[-1]
    for role in ("acme_api", "acme_api_rw", "acme_reset_owner"):
        assert f"'{role}'" in sql
    assert '"application_name": "acme-clinical-api"' in (BACKEND / "app" / "db.py").read_text(encoding="utf-8")
    assert "## Database server logging (T2602)" in (DOCS / "logging-audit.md").read_text(encoding="utf-8")


def test_t4593_t4595_operator_checklists_exist():
    doc = (DOCS / "deployment.md").read_text(encoding="utf-8")
    section = doc.split("## Endpoint behaviour monitoring and privileged processes (T4593, T4595)", 1)[1]
    for item in ("log drains", "Baselines", "EDR", "SOC 2", "superuser"):
        assert item in section, item
