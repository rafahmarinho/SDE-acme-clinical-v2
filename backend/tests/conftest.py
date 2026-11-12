"""Shared fixtures: a fully configured app with no real Supabase/DB, plus token minting helpers."""

from __future__ import annotations

import os
import time
import uuid

import jwt
import pytest

os.environ.update({
    "APP_ENV": "test",
    "SUPABASE_URL": "https://test-project.supabase.co",
    "SUPABASE_ANON_KEY": "anon-test-key",
    "SUPABASE_SERVICE_ROLE_KEY": "service-test-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret-that-is-long-enough-123456",
    "DATABASE_URL": "postgresql://acme_api:Test-DB-Pw-7f3k9q2m@localhost:5432/postgres?sslmode=verify-full",
    "CORS_ALLOWED_ORIGINS": "https://acme-clinical.vercel.app",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.core import audit  # noqa: E402
from app.main import create_app  # noqa: E402

ISSUER = "https://test-project.supabase.co/auth/v1"
SECRET = os.environ["SUPABASE_JWT_SECRET"]


def make_token(sub: str | None = None, *, aal: str = "aal1", iat: int | None = None, exp_in: int = 3600,
               secret: str = SECRET, aud: str = "authenticated", iss: str = ISSUER, **extra) -> str:
    now = int(time.time()) if iat is None else iat
    claims = {"sub": sub or str(uuid.uuid4()), "aud": aud, "iss": iss, "iat": now, "exp": now + exp_in,
              "aal": aal, "session_id": str(uuid.uuid4()), **extra}
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def identities(monkeypatch):
    """Map user_id -> identity dict returned by the (mocked) staff_identity lookup."""
    store: dict[str, dict] = {}

    async def fake_identity(user_id):
        return store.get(str(user_id))

    monkeypatch.setattr("app.db.fetch_staff_identity", fake_identity)

    async def no_session_check(request, principal):  # no app_sessions table without a database
        return None

    # get_principal runs app.routers.auth.enforce_session on every request; tests that exercise the real
    # session check call it directly or restore it (see tests/test_sessions.py).
    monkeypatch.setattr("app.core.security._enforce_session", no_session_check)
    events: list[tuple] = []

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        events.append((action, entity_type, entity_id, kw.get("outcome", "success")))

    monkeypatch.setattr(audit, "record_event", fake_record)
    store["__events__"] = events  # type: ignore[assignment]
    return store


def add_identity(store: dict, role: str, *, active: bool = True, mfa_admin: bool = True, absolute_hours: int = 12) -> str:
    uid = str(uuid.uuid4())
    store[uid] = {"email": f"{role}@example.test", "role": role, "is_active": active,
                  "security": {"session_idle_minutes": 15, "session_absolute_hours": absolute_hours,
                               "max_concurrent_sessions": 2, "require_mfa_for_admin": mfa_admin}}
    return uid


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c
