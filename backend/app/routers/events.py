"""API router: event / audit log queries, integrity verification and administrator alerts.

* The audit trail is read-only through the API (no update/delete routes; DB grants + trigger make
  it append-only, T350). Non-admins see only their own events (RLS).
* `/integrity` verifies the hash chain (DB) and the ECDSA P-521/SHA-512 signature of the most
  recent signed records (Python), reporting the first broken id and invalid signatures (T485/T486).
* `/signing-key` publishes the public key and key id so auditors can verify records offline.
* `/alerts` lists and acknowledges administrator alerts raised on audit/logging failures,
  integrity violations and malware detections (T431).
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core import logging as app_logging
from app.core.audit import record_event, verify_row
from app.core.security import CurrentPrincipal, Perm, Principal, require
from app.db import fetch_all, fetch_one, transaction
from app.schemas import EventOut, Out, Page
from app.services import integrity

Admin = Annotated[Principal, Depends(require(Perm.EVENTS_READ_ALL))]
SIGNATURE_SAMPLE = 500

router = APIRouter(prefix="/v1/events", tags=["events"])
MAX_EVENT_ID = 2**63 - 1  # bigint upper bound: larger values would overflow the SQL parameter


class IntegrityOut(Out):
    intact: bool
    first_broken_id: int | None
    chain_intact: bool
    checked_records: int
    signed_records: int
    unsigned_records: int
    invalid_signature_ids: list[int]
    algorithm: str
    key_id: str


class SigningKeyOut(Out):
    algorithm: str
    key_id: str
    public_key_pem: str


class AlertOut(Out):
    id: UUID
    raised_at: datetime
    kind: str
    severity: str
    details: dict[str, Any]
    acknowledged_at: datetime | None


class AlertPage(Page[AlertOut]):
    process_failure_counters: dict[str, int]


@router.get("", response_model=Page[EventOut])
async def list_events(
    principal: CurrentPrincipal,
    action: Annotated[str | None, Query(pattern=r"^[a-z_]+(\.[a-z_]+)?$", max_length=60)] = None,
    entity_type: Annotated[str | None, Query(pattern=r"^[a-z_]+$", max_length=40)] = None,
    before_id: Annotated[int | None, Query(ge=1, le=MAX_EVENT_ID)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[EventOut]:
    # RLS limits non-admins to their own events.
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """
            select id, occurred_at, actor_role::text as actor_role, action, entity_type, entity_id, outcome, details
            from public.events
            where (%(action)s::text is null or action = %(action)s or action like %(prefix)s)
              and (%(etype)s::text is null or entity_type = %(etype)s)
              and (%(before)s::bigint is null or id < %(before)s)
            order by id desc limit %(limit)s""",
                               {"action": action, "prefix": f"{action}.%" if action and "." not in action else "",
                                "etype": entity_type, "before": before_id, "limit": limit + 1})
    items = [EventOut(**r) for r in rows[:limit]]
    # Keyset pagination: the next page is requested with before_id=<last id>; next_offset carries that id.
    return Page[EventOut](items=items, next_offset=items[-1].id if len(rows) > limit and items else None)


@router.get("/integrity", response_model=IntegrityOut)
async def verify_integrity(request: Request, principal: Admin,
                           limit: Annotated[int, Query(ge=1, le=SIGNATURE_SAMPLE)] = SIGNATURE_SAMPLE) -> dict:
    async with transaction(principal) as conn:
        chain = await fetch_one(conn, "select public.verify_event_chain() as broken_at")
        rows = await fetch_all(conn, """
            select id, actor_id, actor_role::text as actor_role, session_id, aal, source_ip, action, entity_type, entity_id,
                   outcome, error_code, request_id, details, signed_at, key_id, signature
            from public.events order by id desc limit %s""", (limit,))
    signed = [r for r in rows if r.get("signature")]
    invalid = sorted(r["id"] for r in signed if not verify_row(r))
    result = {"intact": chain["broken_at"] is None and not invalid, "first_broken_id": chain["broken_at"],
              "chain_intact": chain["broken_at"] is None, "checked_records": len(rows), "signed_records": len(signed),
              "unsigned_records": len(rows) - len(signed), "invalid_signature_ids": invalid[:50],
              "algorithm": integrity.SIGNATURE_ALGORITHM, "key_id": integrity.key_id()}
    await record_event(principal, "events.verified", "events", None, outcome="success" if result["intact"] else "failure",
                       details={"checked": len(rows), "invalid": len(invalid), "chain_intact": result["chain_intact"]},
                       request_id=request.state.request_id)
    return result


@router.get("/signing-key", response_model=SigningKeyOut)
async def signing_key(principal: Admin) -> dict:
    return {"algorithm": integrity.SIGNATURE_ALGORITHM, "key_id": integrity.key_id(),
            "public_key_pem": integrity.public_key_pem()}


@router.get("/alerts", response_model=AlertPage)
async def list_alerts(principal: Admin, include_acknowledged: bool = False,

                      limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
    async with transaction(principal) as conn:
        rows = await fetch_all(conn, """
            select id, raised_at, kind, severity, details, acknowledged_at from public.system_alerts
            where %(all)s or acknowledged_at is null order by raised_at desc limit %(limit)s""",
                               {"all": include_acknowledged, "limit": limit})
    return {"items": rows, "process_failure_counters": dict(app_logging.failure_counters)}


@router.post("/alerts/{alert_id}/acknowledge", status_code=204)
async def acknowledge_alert(alert_id: UUID, request: Request, principal: Admin) -> None:
    async with transaction(principal) as conn:
        row = await fetch_one(conn, """update public.system_alerts set acknowledged_at = now(), acknowledged_by = %s
                                       where id = %s and acknowledged_at is null returning id""",
                              (str(principal.user_id), str(alert_id)))
        if row is None:
            raise HTTPException(404, "Alert not found.")
        await record_event(principal, "alert.acknowledged", "system_alert", str(alert_id), conn=conn,
                           request_id=request.state.request_id)
