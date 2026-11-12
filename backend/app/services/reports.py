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

from app.core.errors import DomainError
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
def check_private_dir(st: os.stat_result, *, posix: bool = os.name == "posix") -> None:
    """Refuse a report workspace that is not a real directory owned by this process with mode 0700 (T214).

    A directory pre-created by another local user (or left world-writable) could be used to read or swap the
    confidential CSV files. Windows has no POSIX modes/uids: there only the type check applies."""
    if not stat.S_ISDIR(st.st_mode):
        raise PermissionError("report temp root is not a directory")
    if posix and (st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077):
        raise PermissionError("report temp root is not private to this process")


def _ensure_root() -> Path:
    TMP_ROOT.mkdir(mode=0o700, exist_ok=True)
    if TMP_ROOT.is_symlink() or not TMP_ROOT.is_dir():
        raise PermissionError("report temp root is not a private directory")
    check_private_dir(os.lstat(TMP_ROOT))
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
    """Audit rows in the window. Fetches ``limit + 1`` and refuses (422 ``result_too_large``) instead of silently
    truncating, so a report never presents a partial period as complete (T2600).

    Staff whose data is restricted for ``staff_activity_report`` (T754) are left out of this secondary-use
    report; their events stay in public.events, in the hash chain and in the integrity verification."""
    limit = min(limit, MAX_AUDIT_ROWS)
    rows = await fetch_all(conn, """
        select id, occurred_at, actor_id::text as actor_id, actor_role::text as actor_role, action, entity_type,
               entity_id, outcome, error_code, source_ip, request_id
        from public.events
        where occurred_at >= %(start)s and occurred_at < %(end)s
          and (cardinality(%(actions)s::text[]) = 0 or action = any(%(actions)s::text[]))
          and (%(actor)s::uuid is null or actor_id = %(actor)s::uuid)
          and (%(outcome)s::text is null or outcome = %(outcome)s)
          and public.processing_allowed('staff', actor_id, 'staff_activity_report')
        order by id
        limit %(limit)s""", {"start": start, "end": end, "actions": list(actions), "actor": actor_id,
                             "outcome": outcome, "limit": limit + 1})
    if len(rows) > limit:
        raise DomainError("The report period contains too many records. Choose a shorter period or add filters.",
                          422, "result_too_large")
    return rows


def summarize_audit(rows: Sequence[dict], start: datetime, end: datetime, chain_broken_at: int | None) -> dict:
    by_action = Counter(r["action"] for r in rows)
    by_actor = Counter(r["actor_id"] or "system" for r in rows)
    by_outcome = Counter(r["outcome"] for r in rows)
    failures = Counter(r["actor_id"] or "system" for r in rows if r["outcome"] in ("failure", "denied"))
    acked = {r["entity_id"] for r in rows if r["action"] == "alarm.acknowledged"}
    return {
        # "truncated" stays False: oversized periods are refused by audit_rows (result_too_large).
        "period_start": start, "period_end": end, "total": len(rows), "truncated": False,
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
    restricted = await fetch_one(conn, """select count(distinct subject_id)::int as n from public.processing_restrictions
        where subject_type = 'staff' and activity = 'staff_activity_report' and lifted_at is null""")
    summary = summarize_audit(rows, start, end, chain["broken_at"] if chain else None)
    summary["restricted_subjects_excluded"] = restricted["n"] if restricted else 0
    return summary


async def ward_activity(conn: AsyncConnection, ward_id: str | None, start: datetime, end: datetime) -> dict:
    params = {"ward": ward_id, "start": start, "end": end}
    # Statistics are a secondary use: patients restricted for "statistics" (T754) are excluded.
    scope = ("(%(ward)s::uuid is null or p.ward_id = %(ward)s::uuid)"
             " and public.processing_allowed('patient', p.id, 'statistics')")
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


# ---------------------------------------------------------------------------
# De-identified extract for secondary use (research, threshold tuning, training datasets) (T377 / T544)
# ---------------------------------------------------------------------------
# Safe Harbor identifiers that exist in this system and are never copied into an extract: names, dates more
# precise than an offset, record/device numbers, bed/ward-level location below the ward, free text, files.
PHI_DROP = frozenset({"patient_id", "pseudonym", "display_name", "birth_year", "bed_id", "bed_label", "monitor_id",
                      "monitor_serial", "recorded_at", "admitted_at", "discharged_at", "body", "ack_note",
                      "object_path", "original_name", "ecg"})
EXTRACT_COLUMNS = ("subject", "ward_code", "offset_seconds", "heart_rate", "spo2", "resp_rate", "bp_systolic",
                   "bp_diastolic", "quality")
MAX_EXTRACT_ROWS = 20_000


def deidentify_readings(rows: Sequence[dict[str, Any]], *, key: bytes, min_subjects: int) -> list[dict[str, Any]]:
    """Turn identified vital-sign rows into a de-identified extract.

    * the patient id is replaced by a keyed pseudonym (HMAC-SHA256 with a random key per extract, discarded
      afterwards), so the same patient gets different subject codes in two extracts and codes cannot be linked
      back to patients or to the PT-nnnn pseudonyms;
    * timestamps become offsets in seconds from the subject's first reading in the extract;
    * every column in PHI_DROP is removed; only EXTRACT_COLUMNS survive;
    * wards with fewer than ``min_subjects`` distinct patients are dropped entirely (small-cell suppression).
    """
    import hashlib
    import hmac

    per_ward: dict[str, set[str]] = {}
    for r in rows:
        per_ward.setdefault(r["ward_code"], set()).add(str(r["patient_id"]))
    allowed = {w for w, subjects in per_ward.items() if len(subjects) >= min_subjects}
    first_seen: dict[str, datetime] = {}
    for r in rows:
        pid = str(r["patient_id"])
        if r["ward_code"] in allowed and (pid not in first_seen or r["recorded_at"] < first_seen[pid]):
            first_seen[pid] = r["recorded_at"]
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["ward_code"] not in allowed:
            continue
        pid = str(r["patient_id"])
        subject = "S-" + hmac.new(key, pid.encode(), hashlib.sha256).hexdigest()[:16]
        record = {k: v for k, v in r.items() if k in EXTRACT_COLUMNS and k not in PHI_DROP}
        record["subject"] = subject
        record["offset_seconds"] = int((r["recorded_at"] - first_seen[pid]).total_seconds())
        out.append({c: record.get(c) for c in EXTRACT_COLUMNS})
    return out


async def research_extract(conn: AsyncConnection, start: datetime, end: datetime, *, min_subjects: int) -> list[dict]:
    """Vital signs in the window, de-identified. Patients restricted for ``research_extract`` (T754) are skipped.
    Observation text, ECG traces and Storage attachments are never selected."""
    import secrets

    rows = await fetch_all(conn, """
        select r.patient_id, w.code as ward_code, r.recorded_at, r.heart_rate, r.spo2, r.resp_rate,
               r.bp_systolic, r.bp_diastolic, r.quality::text as quality
        from public.readings r
        join public.patients p on p.id = r.patient_id
        join public.wards w on w.id = p.ward_id
        where r.recorded_at >= %(start)s and r.recorded_at < %(end)s
          and public.processing_allowed('patient', p.id, 'research_extract')
        order by r.recorded_at
        limit %(limit)s""", {"start": start, "end": end, "limit": MAX_EXTRACT_ROWS + 1})
    if len(rows) > MAX_EXTRACT_ROWS:
        raise DomainError("The extract period contains too many readings. Choose a shorter period.", 422,
                          "result_too_large")
    return deidentify_readings(rows, key=secrets.token_bytes(32), min_subjects=min_subjects)
