---
name: t106-test-that-site-is-not-vulnerable-to-direct-object
description: Test that ACME Clinical file and report downloads (Supabase Storage objects, generated Python reports) cannot be accessed by changing file names, object paths or using path traversal, and only via authorized short-lived signed URLs.
---

# T106: Test that site is not vulnerable to direct object access attacks

**Category:** CODE_FIX
**SD Elements:** [T106](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T106/)
**Priority:** 8/10 · **Phase:** testing

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> "senha, arquivos e atualizações em tempo real. Quero as telas funcionando e os dados"
> (EN: "Use current, stable technologies and Supabase for PostgreSQL, email and password login, files and real-time updates. I want the screens working and the data")
> Source: specs/PRD.md, lines 5-7

**What the spec implies (naive approach):**
Reports and uploaded files would be stored in a public Supabase bucket under predictable paths such as `reports/ward-1-2026-11-12.pdf`, or served by an endpoint like `GET /files?name=...`. Editing the name exposes other wards' reports, and `../` sequences might reach unintended objects.

**Secure Implementation Pattern:**
```python
# backend/app/routers/reports.py
@router.get("/reports/{report_id}/download")
async def download(report_id: UUID, user=Depends(require(Perm.REPORT_READ)), db=Depends(get_db)):
    rep = await db.get_report(report_id)
    if rep is None or not can_access_ward(user, rep.ward_id):
        raise HTTPException(404, "Not found")
    # storage path comes from the DB row, never from the request
    url = storage.from_("reports").create_signed_url(rep.storage_path, expires_in=60)
    return {"url": url["signedURL"]}

# backend/tests/test_direct_object_access.py
@pytest.mark.parametrize("name", ["../seed.sql", "..%2f..%2fetc%2fpasswd", "ward-b/report.pdf"])
async def test_filename_params_rejected(client_as, nurse_ward_a, name):
    r = await client_as(nurse_ward_a).get(f"/api/files", params={"name": name})
    assert r.status_code in (404, 422)

async def test_bucket_not_public(anon_http):
    r = await anon_http.get(f"{SUPABASE_URL}/storage/v1/object/public/reports/any.pdf")
    assert r.status_code in (400, 404)
```

**Implementation Guidance:**
- Inventory every file-serving feature: report downloads (`backend/app/services/reports.py`), observation attachments, profile avatars.
- Buckets are private (`supabase/migrations`: `insert into storage.buckets (id, public) values ('reports', false)`); Storage RLS policies on `storage.objects` restrict by ward/owner folder.
- Access by opaque DB ID; resolve the storage path server-side; never accept a filename/path parameter. If one is unavoidable, validate with a strict regex and reject `/`, `\`, `..`, percent-encoding.
- Signed URLs expire quickly (≤ 60 s) and are issued only after the authorization check.
- Test with a proxy: change report IDs and object paths to another ward's files.
- Reference: SD Elements guidance for T106.

**Success Criteria:**
- [ ] No public buckets (`select id from storage.buckets where public` returns none).
- [ ] Cross-ward report IDs and traversal names return 404/422.
- [ ] Expired signed URL returns an error after the TTL.

**Status:** Applied
