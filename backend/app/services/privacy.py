"""Privacy services: privacy notice, personal-data export metadata, erasure, retention and the
security-configuration fingerprint.

* PRIVACY_NOTICE / PRIVACY_NOTICE_VERSION are the single source of the notice shown in the SPA
  (GET /v1/me/privacy-notice) and the version users acknowledge (T751/T752/T239). Bump the version
  whenever the content changes: every user is asked again at their next sign-in.
* PROCESSING_INFO is attached to every personal-data export (T740/T741).
* Erasure keeps clinical records (observations, alarm acknowledgements, maintenance) because health-record
  law requires them, but the author's profile is pseudonymised in the database
  (public.complete_erasure_request) and the Supabase Auth identity is scrubbed and banned here (T179).
* Retention runs in the database (public.run_retention_purge, daily via pg_cron); files of deleted
  patients are queued and removed from the private Storage bucket by `drain_storage_queue` (T607).
* `config_fingerprint` gives administrators tamper evidence for the unified security settings (T371).

Outbound calls go only to the configured Supabase project, over verified TLS, with the server-only
service role key (never exposed to the browser). Nothing here logs personal data.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

import cryptography
import fastapi
import httpx
import jwt
import psycopg
import pydantic
import starlette
from psycopg import AsyncConnection

from app.core.config import Settings, get_settings
from app.core.outbound import supabase_client
from app.db import fetch_all

log = logging.getLogger("acme.privacy")

PRIVACY_NOTICE_VERSION = "2026-11-01"
STORAGE_BUCKET = "clinical-files"
# Groups smaller than this are suppressed in secondary-use (statistics) outputs.
MIN_CELL_SIZE = 5

PRIVACY_NOTICE: dict[str, Any] = {
    "version": PRIVACY_NOTICE_VERSION,
    "effective_date": PRIVACY_NOTICE_VERSION,
    "controller": "The hospital operating ACME Clinical (demo deployment: fictitious data only).",
    "purposes": [
        "Patient monitoring, alarm handling and clinical record keeping (care relationship and legal obligation).",
        "Staff authentication, access control and a tamper-evident audit trail (security and legal obligation).",
        "Device maintenance tracking (patient safety).",
        "Aggregated, de-identified ward statistics (quality improvement); small groups are suppressed.",
    ],
    "categories": [
        "Staff: name, work email, role, ward assignments, sign-in times and IP address, actions you perform.",
        "Patients: pseudonymous code, name, birth year, ward and bed, vital signs, ECG, observations, alarms, files.",
    ],
    "recipients": [
        "Supabase (database, authentication, file storage, realtime) - processor.",
        "Vercel (hosting of the web application and API) - processor.",
        "No data is sold or shared with third parties; external integrations are simulated.",
    ],
    "retention": [
        "Readings and resolved alarms: the configured retention period (default 365 days).",
        "Patient records: until the patient's retention date after discharge, unless on legal hold.",
        "Staff accounts: pseudonymised after deactivation plus the retention period, or on an approved erasure request.",
        "Audit trail: append-only; it contains identifiers, never names or clinical free text.",
        "Backups: Supabase backups/point-in-time recovery age out deleted data within the backup window.",
    ],
    "rights": [
        "Review and correct your profile (Profile page).",
        "Download a machine-readable copy of your personal data (Profile > Your data).",
        "Request erasure of your account (Profile > Delete my account); clinical records you authored are kept "
        "with a pseudonymous author as required by health-record law.",
        "Raise a privacy concern with your administrator or the hospital data protection officer.",
    ],
    "legal_basis": "Employment and legal obligations for staff data; provision of health care for patient data. "
                   "Processing of patient data does not rely on consent.",
}

PROCESSING_INFO: dict[str, Any] = {
    "purposes": PRIVACY_NOTICE["purposes"],
    "recipients": PRIVACY_NOTICE["recipients"],
    "retention": PRIVACY_NOTICE["retention"],
    "source": "Provided by you or by the administrator who created your account; activity is recorded by the system.",
    "automated_decisions": "None. Alarms are threshold rules on patient vital signs, not decisions about you.",
    "international_transfer": "According to the region configured for the Supabase project and Vercel functions.",
    "withheld": "Clinical content you authored (observation text, notes) belongs to the patient record and is "
                "listed by reference only.",
    "notice_version": PRIVACY_NOTICE_VERSION,
}


def notice_required(accepted_version: str | None) -> bool:
    """True when the user has not acknowledged the current privacy notice version."""
    return accepted_version != PRIVACY_NOTICE_VERSION


def erased_email(user_id: UUID) -> str:
    """Deterministic, non-routable replacement address (RFC 2606 `.invalid`), unique per account."""
    return f"erased-{user_id.hex}@erased.invalid"


def suppress_small_counts(counts: Mapping[str, int], k: int = MIN_CELL_SIZE) -> dict[str, int | None]:
    """Small-cell suppression for statistics: values below k become None (not 0, which would be misleading)."""
    return {key: (value if value >= k else None) for key, value in counts.items()}


# ---------------------------------------------------------------------------
# Unified security configuration: fingerprint, environment flags, component inventory
# ---------------------------------------------------------------------------
FINGERPRINT_FIELDS = ("password_min_length", "session_idle_minutes", "session_absolute_hours", "max_concurrent_sessions",
                      "lockout_threshold", "lockout_minutes", "require_mfa_for_admin", "data_retention_days")


def config_fingerprint(values: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the security settings (tamper evidence, not a secret)."""
    canonical = json.dumps({k: values[k] for k in FINGERPRINT_FIELDS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def environment_flags(settings: Settings) -> dict[str, Any]:
    """Environment-controlled security settings (read-only in the UI; changed through Vercel env + redeploy)."""
    return {
        "app_env": settings.app_env,
        "docs_enabled": settings.docs_enabled,
        "cors_allowed_origins": settings.origins,
        "database_tls": "verify-full",
        "supabase_https": str(settings.supabase_url).startswith("https://"),
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "auth_rate_limit_per_minute": settings.auth_rate_limit_per_minute,
        "max_request_bytes": settings.max_request_bytes,
        "max_upload_bytes": settings.max_upload_bytes,
    }


def component_versions() -> dict[str, str]:
    """Security-relevant runtime components (cross-check with backend/requirements.txt and pip-audit)."""
    return {
        "fastapi": fastapi.__version__,
        "starlette": starlette.__version__,
        "pydantic": pydantic.VERSION,
        "pyjwt": jwt.__version__,
        "cryptography": cryptography.__version__,
        "psycopg": psycopg.__version__,
        "httpx": httpx.__version__,
    }


# ---------------------------------------------------------------------------
# Supabase Admin / Storage calls (server-only service role key, verified TLS, fixed base URL)
# ---------------------------------------------------------------------------
def _admin_headers() -> dict[str, str]:
    key = get_settings().supabase_service_role_key.get_secret_value()
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _supabase_client() -> httpx.AsyncClient:
    return supabase_client(10)


async def verify_password(email: str, password: str) -> bool:
    """Re-authentication for high-risk privacy actions (export, erasure) without touching the caller's session.

    Signs in once against Supabase Auth (failures count towards its rate limits and the lockout hook) and
    immediately revokes the verification session. The password is never logged or stored.
    """
    if not password:
        return False
    anon = get_settings().supabase_anon_key.get_secret_value()
    async with _supabase_client() as client:
        resp = await client.post("/auth/v1/token?grant_type=password", headers={"apikey": anon},
                                 json={"email": email, "password": password})
        if resp.status_code != 200:
            return False
        access = resp.json().get("access_token")
        if access:
            await client.post("/auth/v1/logout?scope=local", headers={"apikey": anon, "Authorization": f"Bearer {access}"})
    return True


async def scrub_auth_identity(user_id: UUID) -> bool:
    """Replace the e-mail and metadata of an erased user in Supabase Auth and ban the account.

    The auth user row is kept (its UUID anchors the retained, pseudonymised clinical records) but holds no
    personal data and can never sign in again; existing refresh tokens stop working with the ban.
    """
    body = {"email": erased_email(user_id), "email_confirm": True, "user_metadata": {}, "ban_duration": "876000h"}
    async with _supabase_client() as client:
        resp = await client.put(f"/auth/v1/admin/users/{user_id}", headers=_admin_headers(), json=body)
    if resp.status_code >= 400:
        log.error("auth_identity_scrub_failed", extra={"status": resp.status_code})
        return False
    return True


async def delete_storage_objects(paths: Iterable[str]) -> int:
    """Delete objects from the private bucket; returns how many were removed (or were already gone)."""
    removed = 0
    async with _supabase_client() as client:
        for path in paths:
            resp = await client.delete(f"/storage/v1/object/{STORAGE_BUCKET}/{path}", headers=_admin_headers())
            if resp.status_code < 400 or resp.status_code == 404:
                removed += 1
            else:
                log.error("storage_purge_failed", extra={"status": resp.status_code})
    return removed


class StoragePurgeIncomplete(RuntimeError):
    """Raised so the caller's transaction rolls back and the claimed paths stay queued for the next run."""


async def drain_storage_queue(conn: AsyncConnection, limit: int = 100) -> int:
    """Remove files of purged patients (queued by run_retention_purge) from Storage.

    Run inside its own transaction: the queue rows are claimed (deleted) and only committed when every
    object was removed, otherwise StoragePurgeIncomplete rolls the claim back.
    """
    rows = await fetch_all(conn, "select object_path from public.claim_storage_purge_batch(%s) as object_path", (limit,))
    paths = [r["object_path"] for r in rows]
    removed = await delete_storage_objects(paths) if paths else 0
    if removed < len(paths):
        raise StoragePurgeIncomplete(f"{len(paths) - removed} file(s) could not be removed")
    return removed
