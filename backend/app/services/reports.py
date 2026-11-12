"""Report generation in Python.

Reports aggregate alarm and reading activity (log reduction) per ward and period. They contain
counts and durations only: no patient names, free-text observations or staff emails.
"""

from __future__ import annotations

from datetime import UTC, datetime

from psycopg import AsyncConnection

from app.db import fetch_all, fetch_one


async def ward_activity(conn: AsyncConnection, ward_id: str | None, start: datetime, end: datetime) -> dict:
    params = {"ward": ward_id, "start": start, "end": end}
    scope = "(%(ward)s::uuid is null or p.ward_id = %(ward)s::uuid)"
    counts = await fetch_all(conn, f"""
        select a.type::text as type, count(*)::int as n
        from public.alarms a left join public.patients p on p.id = a.patient_id
        where a.raised_at >= %(start)s and a.raised_at < %(end)s and {scope}
        group by a.type order by a.type""", params)
    ack = await fetch_one(conn, f"""
        select avg(extract(epoch from a.acknowledged_at - a.raised_at))::float as mean_ack,
               count(*) filter (where a.priority = 'high' and a.acknowledged_at is null and a.state = 'active')::int as open_high
        from public.alarms a left join public.patients p on p.id = a.patient_id
        where a.raised_at >= %(start)s and a.raised_at < %(end)s and {scope}""", params)
    readings = await fetch_one(conn, f"""
        select count(*)::int as n from public.readings r left join public.patients p on p.id = r.patient_id
        where r.recorded_at >= %(start)s and r.recorded_at < %(end)s and {scope}""", params)
    return {
        "ward_id": ward_id,
        "period_start": start,
        "period_end": end,
        "alarm_counts": {r["type"]: r["n"] for r in counts},
        "mean_time_to_ack_seconds": ack["mean_ack"] if ack else None,
        "unacknowledged_high_priority": ack["open_high"] if ack else 0,
        "readings_count": readings["n"] if readings else 0,
        "generated_at": datetime.now(UTC),
    }
