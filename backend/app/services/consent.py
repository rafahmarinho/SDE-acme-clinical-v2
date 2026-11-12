"""Purpose-level consent for OPTIONAL personal data (skills/privacy T178 / T604).

Everything ACME Clinical needs to run (work account, sign-in and audit data, clinical records) is processed on
the employment / legal-obligation / care basis described in the privacy notice and does NOT rely on consent.
Anything beyond that is listed in CONSENT_PURPOSES and may only be collected while the person has an active
grant (public.consent_grants, 0013_consent_and_restriction.sql):

* a grant records the purpose, the notice version and language it was given under, the request id and time;
* consumers call ``has()`` at the time of use (never a cached flag); the database repeats the check in the RLS
  policy of the table that stores the optional data (public.has_active_consent);
* withdrawal keeps the grant row as evidence (``withdrawn_at``) and stops processing immediately: the data held
  for the purpose is deleted (``STOP_PROCESSING``). Withdrawal is as easy as granting (one toggle).

Patient data is processed for care, never on consent: these purposes apply to staff accounts only.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection

from app.db import fetch_all, fetch_one

CONSENT_LANGUAGE = "en"

CONSENT_PURPOSES: dict[str, dict[str, Any]] = {
    "escalation_contact": {
        "title": "Alarm escalation by text message",
        "description": "Use a mobile phone number you provide to reach you when a high-priority alarm on one of "
                       "your wards stays unacknowledged.",
        "data_categories": ["Mobile phone number"],
        "retention": "Until you withdraw consent or your account is erased; deleted immediately on withdrawal.",
        "third_parties": ["Text-message provider (simulated in this demo: no message is sent)."],
        "withdrawal": "Switch the toggle off on your profile at any time; the number is deleted immediately.",
        "required": False,
    },
}

# What withdrawal of each purpose stops at once (data deleted, dependent features disabled).
STOP_PROCESSING: dict[str, tuple[str, ...]] = {
    "escalation_contact": ("delete from public.staff_optional_contacts where user_id = %s",),
}


class UnknownPurpose(ValueError):
    pass


def check_purpose(purpose: str) -> str:
    if purpose not in CONSENT_PURPOSES:
        raise UnknownPurpose(purpose)
    return purpose


async def has(conn: AsyncConnection, user_id: UUID | str, purpose: str) -> bool:
    """Time-of-use check: True only while an active (not withdrawn) grant exists."""
    row = await fetch_one(conn, "select public.has_active_consent(%s, %s) as ok", (str(user_id), check_purpose(purpose)))
    return bool(row and row["ok"])


async def history(conn: AsyncConnection, user_id: UUID | str) -> list[dict[str, Any]]:
    """Every grant and withdrawal of the user (evidence; included in the personal-data export)."""
    return await fetch_all(conn, """select id, purpose, notice_version, language, granted_at, withdrawn_at
           from public.consent_grants where user_id = %s order by granted_at""", (str(user_id),))


async def grant(conn: AsyncConnection, user_id: UUID | str, purpose: str, notice_version: str,
                request_id: str | None) -> dict[str, Any]:
    """Record a new grant (idempotent while one is active)."""
    check_purpose(purpose)
    existing = await fetch_one(conn, """select id, purpose, notice_version, language, granted_at, withdrawn_at
           from public.consent_grants where user_id = %s and purpose = %s and withdrawn_at is null""",
                               (str(user_id), purpose))
    if existing:
        return existing
    return await fetch_one(conn, """insert into public.consent_grants (user_id, purpose, notice_version, language, request_id)
           values (%s, %s, %s, %s, %s)
           returning id, purpose, notice_version, language, granted_at, withdrawn_at""",
                           (str(user_id), purpose, notice_version, CONSENT_LANGUAGE, request_id))


async def withdraw(conn: AsyncConnection, user_id: UUID | str, purpose: str, request_id: str | None) -> bool:
    """Withdraw an active grant and stop the dependent processing. Returns False when nothing was active."""
    check_purpose(purpose)
    row = await fetch_one(conn, """update public.consent_grants set withdrawn_at = now(), withdrawal_request_id = %s
           where user_id = %s and purpose = %s and withdrawn_at is null returning id""",
                          (request_id, str(user_id), purpose))
    if row is None:
        return False
    for statement in STOP_PROCESSING.get(purpose, ()):
        await conn.execute(statement, (str(user_id),))
    return True
