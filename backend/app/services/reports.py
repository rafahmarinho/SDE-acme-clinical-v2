"""Report generation in Python.

* `ward_activity` aggregates alarm and reading activity per ward and period. It contains counts
  and durations only: no patient names, free-text observations or staff emails.
* `audit_summary` is the audit log-reduction report (T437): read-only, parameterized, filtered by
  window/action/actor/outcome, ordered by id, with first/last ids, per-action/actor/outcome
  totals, anomaly hints and the chain verification result. It never modifies source rows.
* CSV exports are written to a private, per-request temporary directory created atomically
  (`tempfile.mkdtemp`, mode 0700) with an exclusively created, no-follow file, streamed to the
  client and deleted right after the response (or on failure). Expired leftovers are swept on
  every export (T157/T572). Cell values are neutralised against spreadsheet formula injection.
  Report kinds and formats come from fixed allow-lists; no user input reaches a path (T162).
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import stat
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

from psycopg import AsyncConnection

from app.db import fetch_all, fetch_one

TMP_ROOT = Path(tempfile.gettempdir()) / "acme-reports"
EXPIRY_SECONDS = 600
MAX_AUDIT_ROWS = 10_000
SUSPICIOUS_FAILURES = 5
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_BINARY = getattr(os, "O_BINARY", 0)


class ReportKind(StrEnum):
    """Allow-list of exportable reports; the only way a client selects a report resource."""
    ward_activity = "ward_activity"
    audit_events = "audit_events"


def report_kind(name: str) -> ReportKind:
    try:
        return ReportKind(name)
    except ValueError as exc:
        raise ValueError("unknown report") from exc


# ---------------------------------------------------------------------------
# Safe temporary files (T157, T572)
# ---------------------------------------------------------------------------
def _ensure_root() -> Path:
    TMP_ROOT.mkdir(mode=0o700, exist_ok=True)
    if TMP_ROOT.is_symlink() or not TMP_ROOT.is_dir():
        raise PermissionError("report temp root is not a private directory")
    return TMP_ROOT


def sweep_expired(now: float | None = None) -> int:
    """Remove report work dirs older than EXPIRY_SECONDS (serverless: runs on each export)."""
    root = _ensure_root()
    now = time.time() if now is None else now
    removed = 0
    for entry in root.iterdir():
        try:
            if entry.is_symlink():
                entry.unlink()
                removed += 1
            elif entry.is_dir() and now - entry.stat().st_mtime > EXPIRY_SECONDS:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


@contextmanager
def private_workdir() -> Iterator[str]:
    """Random-named 0700 directory created atomically; always removed on exit."""
    with tempfile.TemporaryDirectory(prefix="r-", dir=_ensure_root()) as d:
        yield d


def create_exclusive(dirpath: str, name: str) -> IO[bytes]:
    """O_CREAT|O_EXCL|O_NOFOLLOW, 0600: fails if anything (including a planted symlink) exists."""
    if os.path.basename(name) != name or name in ("", ".", ".."):
        raise ValueError("invalid file name")
    fd = os.open(os.path.join(dirpath, name), os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_BINARY, 0o600)
    return os.fdopen(fd, "wb")


def open_no_follow(path: str) -> IO[bytes]:
    """Open for reading without following symlinks; reject non-regular and hard-linked files."""
    if os.path.islink(path):
        raise OSError("refusing to follow a symbolic link")
    fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW | _O_BINARY)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        os.close(fd)
        raise PermissionError("unexpected file type")
    return os.fdopen(fd, "rb")


def csv_safe(value: Any) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @, tab, CR) and stringify."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def build_csv_export(columns: Sequence[str], rows: Iterable[dict[str, Any]],
                     writer: Callable[[IO[bytes], Sequence[str], Iterable[dict[str, Any]]], None] | None = None
                     ) -> tuple[str, Callable[[], None]]:
    """Write a CSV into a fresh private work dir. Returns (file path, cleanup). On any error the
    work dir is removed before the exception propagates."""
    sweep_expired()
    workdir = tempfile.mkdtemp(prefix="r-", dir=_ensure_root())

    def cleanup() -> None:
        shutil.rmtree(workdir, ignore_errors=True)

    try:
        with create_exclusive(workdir, "report.csv") as fh:
            (writer or _write_csv)(fh, columns, rows)
    except BaseException:
        cleanup()
        raise
    return os.path.join(workdir, "report.csv"), cleanup


def _write_csv(fh: IO[bytes], columns: Sequence[str], rows: Iterable[dict[str, Any]]) -> None:
    text = io.TextIOWrapper(fh, encoding="utf-8", newline="")
    w = csv.writer(text)
    w.writerow(columns)
    for row in rows:
        w.writerow([csv_safe(row.get(c)) for c in columns])
    text.flush()
    text.detach()


# ---------------------------------------------------------------------------
# Audit log reduction (T437)
# ---------------------------------------------------------------------------
AUDIT_COLUMNS = ("id", "occurred_at", "actor_id", "actor_role", "action", "entity_type", "entity_id", "outcome",
                 "error_code", "source_ip", "request_id")


async def audit_rows(conn: AsyncConnection, start: datetime, end: datetime, actions: Sequence[str] = (),
                     actor_id: str | None = None, outcome: str | None = None, limit: int = MAX_AUDIT_ROWS) -> list[dict]:
    return await fetch_all(conn, """
        select id, occurred_at, actor_id::text as actor_id, actor_role::text as actor_role, action, entity_type,
               entity_id, outcome, error_code, source_ip, request_id
        from public.events
        where occurred_at >= %(start)s and occurred_at < %(end)s
          and (cardinality(%(actions)s::text[]) = 0 or action = any(%(actions)s::text[]))
          and (%(actor)s::uuid is null or actor_id = %(actor)s::uuid)
          and (%(outcome)s::text is null or outcome = %(outcome)s)
        order by id
        limit %(limit)s""", {"start": start, "end": end, "actions": list(actions), "actor": actor_id,
                             "outcome": outcome, "limit": min(limit, MAX_AUDIT_ROWS)})


def summarize_audit(rows: Sequence[dict], start: datetime, end: datetime, chain_broken_at: int | None) -> dict:
    by_action = Counter(r["action"] for r in rows)
    by_actor = Counter(r["actor_id"] or "system" for r in rows)
    by_outcome = Counter(r["outcome"] for r in rows)
    failures = Counter(r["actor_id"] or "system" for r in rows if r["outcome"] in ("failure", "denied"))
    acked = {r["entity_id"] for r in rows if r["action"] == "alarm.acknowledged"}
    return {
        "period_start": start, "period_end": end, "total": len(rows), "truncated": len(rows) >= MAX_AUDIT_ROWS,
        "first_id": rows[0]["id"] if rows else None, "last_id": rows[-1]["id"] if rows else None,
        "totals_by_action": dict(by_action), "totals_by_actor": dict(by_actor), "totals_by_outcome": dict(by_outcome),
        "suspicious_actors": sorted(a for a, n in failures.items() if n >= SUSPICIOUS_FAILURES),
        "acknowledged_alarms": len(acked),
        "chain_intact": chain_broken_at is None, "chain_first_broken_id": chain_broken_at,
        "generated_at": datetime.now(UTC),
    }


async def audit_summary(conn: AsyncConnection, start: datetime, end: datetime, actions: Sequence[str] = (),
                        actor_id: str | None = None, outcome: str | None = None) -> dict:
    rows = await audit_rows(conn, start, end, actions, actor_id, outcome)
    chain = await fetch_one(conn, "select public.verify_event_chain() as broken_at")
    return summarize_audit(rows, start, end, chain["broken_at"] if chain else None)


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
