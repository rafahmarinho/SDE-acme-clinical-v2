"""File-handling tests (skills/file-handling): type spoofing, malware, content validation, storage
naming, path traversal, temp files and symlinks, configuration integrity, resource release."""

from __future__ import annotations

import asyncio
import os
import re
import stat
import struct
import sys
import time
import uuid
import zlib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services import alarms, integrity, reports, simulation
from app.services import files as fs
from tests.conftest import add_identity, make_token
from tests.test_logging_audit import FakeConn, fake_transaction

ROOT = Path(__file__).resolve().parents[2]
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"  # split: avoid local AV quarantine


def _chunk(ctype: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def tiny_png() -> bytes:
    raw = zlib.compress(b"\x00\x00\x00\x00")
    return fs.PNG_MAGIC + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)) + _chunk(b"IDAT", raw) + _chunk(b"IEND", b"")


def tiny_jpeg() -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 1, 1, 1) + b"\x01\x11\x00"
    sos = b"\xff\xda" + struct.pack(">HB", 8, 1) + b"\x01\x00\x00\x3f\x00"
    return b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + sof + sos + b"\x12\x34" + b"\xff\xd9"


def tiny_pdf(extra: bytes = b"") -> bytes:
    return (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n" + extra + b"trailer << /Root 1 0 R >>\n%%EOF\n")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def upload_env(monkeypatch, identities):
    """Upload route with fake DB/Storage; records storage writes and audit/alerts."""
    from app.routers import files as files_router

    stored: list[str] = []
    audited: list[tuple] = []
    alerts: list[str] = []
    conn = FakeConn()

    async def fake_one(c, sql, params=()):
        if sql.startswith("select 1 from public.patients"):
            return {"?column?": 1}
        if "insert into public.attachments" in sql:
            return {"id": uuid.uuid4(), "original_name": params[2], "content_type": params[3], "size_bytes": params[4],
                    "created_at": "2026-11-12T00:00:00Z", "_path": params[1]}
        return None

    class FakeResp:
        status_code = 200

        def json(self):
            return {}

    class FakeStorage:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, **kw):
            stored.append(url)
            return FakeResp()

        async def request(self, method, url, **kw):
            stored.append(f"{method} {url}")
            return FakeResp()

    async def fake_record(principal, action, entity_type, entity_id=None, **kw):
        audited.append((action, kw.get("outcome", "success"), kw.get("error_code")))

    async def fake_notify(kind, details=None):
        alerts.append(kind)

    monkeypatch.setattr(files_router, "transaction", fake_transaction(conn))
    monkeypatch.setattr(files_router, "fetch_one", fake_one)
    from app.routers import break_glass as break_glass_router  # break-glass use lookup (A5) on the same fake

    monkeypatch.setattr(break_glass_router, "fetch_one", fake_one)
    monkeypatch.setattr(files_router, "_storage_client", lambda timeout: FakeStorage())
    monkeypatch.setattr(files_router, "record_event", fake_record)
    monkeypatch.setattr(files_router, "notify_admins", fake_notify)
    return {"stored": stored, "audited": audited, "alerts": alerts, "identities": identities}


def _upload(client, env, role, name, data, ctype):
    uid = add_identity(env["identities"], role)
    return client.post(f"/v1/files/patients/{uuid.uuid4()}", files={"file": (name, data, ctype)},
                       headers={"Authorization": f"Bearer {make_token(uid)}"})


# --------------------------------------------------------------------------- T129 / T54 type and content
SPOOFED = [
    ("photo.jpg", b"<html><script>alert(1)</script></html>", "image/jpeg"),
    ("report.pdf", b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf"),
    ("scan.png", b"GIF89a....", "image/png"),
    ("notes.txt.jpg", b"plain text pretending", "image/jpeg"),
]


@pytest.mark.parametrize("name,content,ctype", SPOOFED)
def test_t129_extension_and_content_type_spoofing_rejected(client, upload_env, name, content, ctype):
    r = _upload(client, upload_env, "nurse", name, content, ctype)
    assert r.status_code in (415, 422), r.text
    assert upload_env["stored"] == []
    assert upload_env["audited"][-1][0] == "file.rejected" and upload_env["audited"][-1][1] == "failure"


def test_t129_valid_png_accepted_regardless_of_name_and_header(client, upload_env):
    r = _upload(client, upload_env, "nurse", "x.bin", tiny_png(), "application/octet-stream")
    assert r.status_code == 201, r.text
    assert r.json()["content_type"] == "image/png"
    assert re.search(r"/storage/v1/object/clinical-files/patients/[0-9a-f-]{36}/[0-9a-f-]{36}\.png$", upload_env["stored"][0])


@pytest.mark.parametrize("data", [tiny_png()[:-6], tiny_png() + b"<script>", tiny_pdf(b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>\n"),
                                  tiny_pdf(b"<< /Encrypt 5 0 R >>\n"), tiny_pdf() + b"trailing junk", tiny_jpeg()[:-2], b"%PDF-1.4 no eof",
                                  b"\x00" * (fs.MAX_BYTES + 1)],
                         ids=["truncated_png", "png_trailing_script", "pdf_javascript", "pdf_encrypted", "pdf_trailing",
                              "truncated_jpeg", "pdf_no_eof", "oversized"])
def test_t54_invalid_or_active_content_rejected(data):
    with pytest.raises(fs.FileRejected):
        fs.validate_content(data)


@pytest.mark.parametrize("builder,mime", [(tiny_png, "image/png"), (tiny_jpeg, "image/jpeg"), (tiny_pdf, "application/pdf")])
def test_t54_well_formed_files_pass_structural_validation(builder, mime):
    assert fs.validate_content(builder())[0] == mime


def test_t54_png_dimension_bomb_rejected():
    png = fs.PNG_MAGIC + _chunk(b"IHDR", struct.pack(">IIBBBBB", 100_000, 100_000, 8, 0, 0, 0, 0)) + _chunk(b"IEND", b"")
    with pytest.raises(fs.FileRejected):
        fs.validate_content(png)


# --------------------------------------------------------------------------- T53 / T107 malware
def test_t107_eicar_in_valid_png_rejected_logged_and_alerted(client, upload_env, caplog):
    r = _upload(client, upload_env, "physician", "eicar.png", tiny_png()[:-12] + EICAR + tiny_png()[-12:], "image/png")
    assert r.status_code == 422 and r.json()["code"] == "malware_detected"
    assert upload_env["stored"] == []
    assert upload_env["alerts"] == ["upload_malware_detected"]
    assert ("file.rejected", "failure", "malware_detected") in upload_env["audited"]


def test_t107_raw_eicar_rejected_before_type_check(client, upload_env):
    r = _upload(client, upload_env, "nurse", "eicar.com", EICAR, "application/octet-stream")
    assert r.status_code in (415, 422) and upload_env["stored"] == []


def test_t53_upload_policy_by_role_and_route_permission(client, upload_env):
    assert _upload(client, upload_env, "biomed_tech", "a.png", tiny_png(), "image/png").status_code == 403
    assert run(fs.screen_upload("nurse", tiny_pdf()))[0] == "application/pdf"
    with pytest.raises(fs.FileRejected) as exc:
        run(fs.screen_upload("admin", tiny_png()))
    assert exc.value.reason == "type_not_allowed"


def test_t53_scanner_is_pluggable_and_fails_closed():
    class Broken:
        name = "external"

        async def scan(self, data):
            raise TimeoutError

    original = fs.get_scanner()
    fs.set_scanner(Broken())
    try:
        with pytest.raises(fs.FileRejected) as exc:
            run(fs.screen_upload("nurse", tiny_png()))
        assert exc.value.status_code == 503
    finally:
        fs.set_scanner(original)


def test_t107_no_direct_browser_upload_path_to_storage():
    sql = (ROOT / "supabase" / "migrations" / "0002_roles_rls.sql").read_text(encoding="utf-8")
    assert "'clinical-files', 'clinical-files', false" in sql
    assert not re.search(r"create policy[^;]*on storage\.objects", sql, re.I)
    src = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "frontend" / "src").rglob("*.ts*"))
    assert ".storage.from(" not in src  # all uploads go through the validating API


# --------------------------------------------------------------------------- T2167 / T162 / T297 storage & paths
def test_t2167_object_key_is_server_generated_and_name_sanitized():
    pid = uuid.uuid4()
    key = fs.new_object_path(pid, "pdf")
    assert key.startswith(f"patients/{pid}/") and fs.OBJECT_PATH.match(key)
    assert fs.display_name("../../evil<script>.html") == "evil_script_.html"
    assert fs.display_name("..\\..\\") == "upload" and fs.display_name(None) == "upload"


PAYLOADS = ["../MYFILE.TXT", "..../MYFILE.TXT", "../..../MYFILE.TXT", "/etc/passwd", "c:\\windows\\win.ini", "%2e%2e/MYFILE.TXT",
            "%2e%2e%2fMYFILE.TXT", "%252E%252E%252FMYFILE.TXT", "patients/other-id/scan.png", "ward_summary\x00.html", "MYFILE..TXT"]


@pytest.mark.parametrize("p", PAYLOADS)
def test_t297_report_kind_and_object_paths_reject_traversal(p):
    with pytest.raises(ValueError):
        reports.report_kind(p)
    with pytest.raises(fs.FileRejected):
        fs.safe_object_path(p)


@pytest.mark.parametrize("p", ["..%2F..%2Fetc%2Fpasswd", "not-a-uuid", "MYFILE..TXT", "%2e%2e"])
def test_t297_file_and_report_endpoints_reject_payloads_without_500(client, identities, p):
    uid = add_identity(identities, "physician")
    h = {"Authorization": f"Bearer {make_token(uid)}"}
    r1 = client.get(f"/v1/files/{p}/url", headers=h)
    r2 = client.get("/v1/reports/export.csv", params={"kind": p}, headers=h)
    assert r1.status_code in (404, 422) and r2.status_code in (404, 422), (r1.text, r2.text)


def test_t162_no_route_takes_a_path_or_object_key_parameter():
    from fastapi.routing import APIRoute

    from app.main import create_app

    for route in create_app().routes:
        if isinstance(route, APIRoute):
            for param in route.dependant.path_params + route.dependant.query_params:
                assert not re.search(r"(path|object|key|file_?name|template)", param.name), (route.path, param.name)


# --------------------------------------------------------------------------- T157 / T300 / T572 / T595 temp files
@pytest.fixture
def isolated_tmp(tmp_path, monkeypatch):
    root = tmp_path / "acme-reports"
    monkeypatch.setattr(reports, "TMP_ROOT", root)
    return root


def test_t300_many_exports_leave_no_temp_files(client, identities, monkeypatch, isolated_tmp):
    from app.routers import reports as rep_router

    async def fake_ward(conn, ward_id, start, end):
        return {"alarm_counts": {"low_spo2": 3, "=HYPERLINK()": 1}}

    async def fake_record(*a, **k):
        return None

    monkeypatch.setattr(rep_router, "transaction", fake_transaction(FakeConn()))
    monkeypatch.setattr(rep_router, "fetch_one", AsyncMock(return_value={"retry_after": 0}))  # shared limit (T1362)
    monkeypatch.setattr(rep_router.reports, "ward_activity", fake_ward)
    monkeypatch.setattr(rep_router, "record_event", fake_record)
    for role in ("physician", "admin"):
        uid = add_identity(identities, role)
        for _ in range(5):
            r = client.get("/v1/reports/export.csv", params={"kind": "ward_activity"},
                           headers={"Authorization": f"Bearer {make_token(uid, aal='aal2')}"})
            assert r.status_code == 200 and "'=HYPERLINK()" in r.text
            assert r.headers["content-type"].startswith("text/csv")
    assert not any(isolated_tmp.iterdir())


def test_t300_failed_render_cleans_up(isolated_tmp):
    def boom(fh, columns, rows):
        fh.write(b"partial")
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError):
        reports.build_csv_export(("a",), [], writer=boom)
    assert not any(isolated_tmp.iterdir())


def test_t157_expired_dirs_swept(isolated_tmp):
    isolated_tmp.mkdir(parents=True)
    old, fresh = isolated_tmp / "r-old", isolated_tmp / "r-new"
    old.mkdir()
    fresh.mkdir()
    t = time.time() - reports.EXPIRY_SECONDS - 5
    os.utime(old, (t, t))
    assert reports.sweep_expired() == 1
    assert not old.exists() and fresh.exists()


def test_t572_private_workdir_removed_and_random(isolated_tmp):
    with reports.private_workdir() as d1, reports.private_workdir() as d2:
        assert d1 != d2 and Path(d1).parent == isolated_tmp and not os.path.islink(d1)
        if sys.platform != "win32":
            assert (os.stat(d1).st_mode & 0o077) == 0
    assert not os.path.exists(d1) and not os.path.exists(d2)


def test_t572_create_exclusive_rejects_existing_and_bad_names(tmp_path):
    (tmp_path / "out.csv").write_text("keep")
    with pytest.raises(FileExistsError):
        reports.create_exclusive(str(tmp_path), "out.csv")
    assert (tmp_path / "out.csv").read_text() == "keep"
    for bad in ("../x.csv", "a/b.csv", ".."):
        with pytest.raises(ValueError):
            reports.create_exclusive(str(tmp_path), bad)


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX link semantics (run in Linux CI)")


@posix_only
def test_t595_read_through_symlink_rejected(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("secret")
    link = tmp_path / "report.csv"
    link.symlink_to(secret)
    with pytest.raises(OSError):
        reports.open_no_follow(str(link))


@posix_only
def test_t595_hard_link_rejected(tmp_path):
    target = tmp_path / "t.txt"
    target.write_text("x")
    os.link(target, tmp_path / "h.txt")
    with pytest.raises(PermissionError):
        reports.open_no_follow(str(tmp_path / "h.txt"))


@posix_only
def test_t595_exclusive_create_does_not_follow_planted_link(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    (tmp_path / "out.pdf").symlink_to(victim)
    with pytest.raises(FileExistsError):
        reports.create_exclusive(str(tmp_path), "out.pdf")
    assert victim.read_text() == "keep"


@posix_only
def test_t595_sweep_removes_planted_symlink_without_following(isolated_tmp, tmp_path):
    isolated_tmp.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("keep")
    (isolated_tmp / "r-evil").symlink_to(victim, target_is_directory=True)
    reports.sweep_expired()
    assert (victim / "keep.txt").exists() and not (isolated_tmp / "r-evil").exists()


def test_t595_regular_file_opens(tmp_path):
    f = tmp_path / "ok.txt"
    f.write_bytes(b"ok")
    with reports.open_no_follow(str(f)) as fh:
        assert fh.read() == b"ok"


def test_t595_no_raw_tmp_opens_in_app_code():
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"open\(\s*f?[\"']/tmp", src), path


# --------------------------------------------------------------------------- T345 / T346 configuration integrity
def _threshold(**over):
    row = {"id": uuid.uuid4(), "ward_id": uuid.uuid4(), "patient_id": None, "parameter": "spo2", "low_limit": 88,
           "high_limit": 100, "updated_at": "2026-11-12T00:00:00+00:00", "is_override": False}
    row.update(over)
    return row


@pytest.fixture
def violations(monkeypatch):
    seen: list[tuple] = []

    async def fake_report(kind, entity_id):
        seen.append((kind, entity_id))

    monkeypatch.setattr(alarms, "report_integrity_violation", fake_report)
    return seen


def _limits(rows):
    async def fake_all(conn, sql, params=()):
        return rows
    return fake_all


def test_t346_signed_threshold_is_used(monkeypatch, violations):
    row = _threshold()
    row["integrity_mac"] = alarms.threshold_mac(row)
    monkeypatch.setattr(alarms, "fetch_all", _limits([row]))
    assert run(alarms.effective_limits(None, None, "w"))["spo2"] == (88, 100)
    assert violations == []


def test_t346_tampered_threshold_detected_and_safe_default_used(monkeypatch, violations):
    row = _threshold()
    row["integrity_mac"] = alarms.threshold_mac(row)
    row["low_limit"] = 50  # out-of-band DB edit that would suppress hypoxia alarms
    monkeypatch.setattr(alarms, "fetch_all", _limits([row]))
    limits = run(alarms.effective_limits(None, None, "w"))
    assert limits["spo2"] == alarms.SAFE_DEFAULT_LIMITS["spo2"]
    assert violations == [("threshold", str(row["id"]))]


def test_t346_unsigned_rows_only_trusted_when_equal_to_safe_defaults(monkeypatch, violations):
    seeded = _threshold(low_limit=92, high_limit=100, integrity_mac=None)
    edited = _threshold(parameter="heart_rate", low_limit=10, high_limit=250, integrity_mac=None)
    monkeypatch.setattr(alarms, "fetch_all", _limits([seeded, edited]))
    limits = run(alarms.effective_limits(None, None, "w"))
    assert limits["spo2"] == (92, 100) and limits["heart_rate"] == alarms.SAFE_DEFAULT_LIMITS["heart_rate"]
    assert [v[1] for v in violations] == [str(edited["id"])]


def test_t346_seal_threshold_recomputes_mac_for_legitimate_updates(monkeypatch):
    row = _threshold(low_limit=90)
    conn = FakeConn()

    async def fake_one(c, sql, params=()):
        return row

    monkeypatch.setattr(alarms, "fetch_one", fake_one)
    run(alarms.seal_threshold(conn, str(row["id"])))
    mac = conn.executed[-1][1][0]
    assert alarms.threshold_trusted({**row, "integrity_mac": mac})


def test_t346_tampered_simulation_state_refused(monkeypatch, violations):
    state = {"scenario": "low_saturation", "monitor_scenarios": {}, "version": 3, "tick": 1}
    state["integrity_mac"] = simulation.state_mac(state)
    assert simulation.state_trusted(state)
    tampered = {**state, "scenario": "normal", "monitor_scenarios": {str(uuid.uuid4()): "connection_loss"}}
    assert not simulation.state_trusted(tampered)
    with pytest.raises(simulation.IntegrityError):
        run(simulation._verify_state(tampered))
    assert violations == [("simulation", "1")]
    assert simulation.state_trusted({"scenario": "normal", "monitor_scenarios": {}, "version": 0, "integrity_mac": None})


def test_t345_config_mac_is_keyed_hmac_sha256():
    mac = integrity.config_mac("alarm_threshold", {"a": 1})
    assert re.fullmatch(r"[0-9a-f]{64}", mac) and integrity.config_mac_valid("alarm_threshold", {"a": 1}, mac)
    assert not integrity.config_mac_valid("alarm_threshold", {"a": 2}, mac)
    assert not integrity.config_mac_valid("simulation_state", {"a": 1}, mac)  # domain separated


def test_t345_uploads_record_sha256_and_migration_adds_macs():
    sql = (ROOT / "supabase" / "migrations" / "0004_ops_audit_resilience.sql").read_text(encoding="utf-8")
    assert "alarm_thresholds add column if not exists integrity_mac" in sql
    assert "simulation_state add column if not exists integrity_mac" in sql
    assert "hashlib.sha256(data).hexdigest()" in (ROOT / "backend" / "app" / "routers" / "files.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- T375 resource release
def test_t375_upload_stream_closed_and_orphan_object_deleted_on_failure(upload_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.routers import files as files_router

    async def failing_one(c, sql, params=()):
        if sql.startswith("select 1"):
            return {"?column?": 1}
        if "consume_rate_limit" in sql:  # shared per-user throttle (T1362)
            return {"retry_after": 0}
        raise RuntimeError("insert failed")

    monkeypatch.setattr(files_router, "fetch_one", failing_one)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        r = _upload(client, upload_env, "nurse", "a.png", tiny_png(), "image/png")
    assert r.status_code == 500
    assert any(s.startswith("DELETE /storage/v1/object/clinical-files") for s in upload_env["stored"])


def test_t375_connections_and_clients_are_context_managed():
    for name in ("routers/files.py", "services/reports.py", "core/audit.py"):
        src = (ROOT / "backend" / "app" / name).read_text(encoding="utf-8")
        assert not re.search(r"=\s*httpx\.AsyncClient\(", src.replace("return httpx.AsyncClient(", "")), name
        assert not re.search(r"(?<!os\.)(?<!def )\bopen\([^)]*\)\s*$", src, re.M), name


# --------------------------------------------------------------------------- T295 confidential data at rest
def test_t295_report_file_is_private_and_removed_after_download(isolated_tmp):
    path, cleanup = reports.build_csv_export(("alarm_type", "count"), [{"alarm_type": "low_spo2", "count": 4}])
    workdir = os.path.dirname(path)
    assert Path(workdir).parent == isolated_tmp
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(workdir).st_mode) == 0o700
    cleanup()  # run as the FileResponse background task once the download completes
    assert not os.path.exists(path) and not os.path.exists(workdir)


def test_t295_storage_private_and_no_plaintext_secrets_in_schema_or_bundle():
    sql = "\n".join(p.read_text(encoding="utf-8").lower() for p in sorted((ROOT / "supabase" / "migrations").glob("*.sql")))
    assert re.search(r"values \('clinical-files', 'clinical-files', false", sql)
    monitors = sql.split("create table public.monitors", 1)[1].split(");", 1)[0]
    secret_columns = re.findall(r"^\s*(\w*secret\w*)\s", monitors, re.M)
    assert secret_columns and all(c.endswith("_hash") for c in secret_columns), secret_columns
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    bundle_check = next(line for line in ci.splitlines() if "grep -rEi" in line and " dist" in line)
    for name in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "DATABASE_URL", "AUDIT_SIGNING_KEY"):
        assert name in bundle_check, name
