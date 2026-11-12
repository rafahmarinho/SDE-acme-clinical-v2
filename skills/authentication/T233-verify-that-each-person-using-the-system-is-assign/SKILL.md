---
name: t233-verify-that-each-person-using-the-system-is-assign
description: Verification that every person with ACME Clinical access maps to exactly one unique Supabase Auth user and profile, with no shared or role-named accounts, through an automated SQL check and an administrator account-review report, verifying T135.
---

# T233: Verify that each person using the system is assigned a unique user ID

**Category:** CODE_FIX
**SD Elements:** [T233](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T233/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "configurações de limites, relatórios e gestão da equipe"
> (EN: limit settings, reports and team management)
> Source: specs/PRD.md, line 27

**What the spec implies (naive approach):**
The team-management screen lists staff, but nothing checks that each entry is one real person. Duplicate profiles for one email, auth users without profiles, or generic accounts like "ward-a" could slip in through the seed or manual dashboard edits.

**Secure Implementation Pattern:**
```sql
-- supabase/tests/unique_user_ids.test.sql  (pgTAP)
begin;
select plan(4);
select is((select count(*) from (select lower(email) from public.profiles
           group by 1 having count(*) > 1) d), 0::bigint, 'no duplicate emails');
select is((select count(*) from auth.users u left join public.profiles p on p.id = u.id
           where p.id is null), 0::bigint, 'every auth user has exactly one profile');
select is((select count(*) from (select employee_number from public.profiles
           group by 1 having count(*) > 1) d), 0::bigint, 'no duplicate employee numbers');
select is((select count(*) from public.profiles
           where email ~* '^(admin|nurse|physician|doctor|tech|ward|shared|team|test)[0-9-]*@'),
          0::bigint, 'no generic role-named accounts');
select * from finish();
rollback;
```
```python
# backend/app/routers/admin.py - account review export for the manual check
@router.get("/admin/staff/review", dependencies=[Depends(require_admin_aal2)])
async def staff_review():
    return await db.fetch("""select p.id, p.email, p.full_name, p.employee_number, p.role,
                                    p.is_active, u.last_sign_in_at
                             from public.profiles p join auth.users u on u.id = p.id
                             order by p.role, p.full_name""")
```

**Implementation Guidance:**
- Automated: run the pgTAP test after seed in CI (`supabase test db`) and on a schedule against the hosted project with read-only credentials.
- Manual (step 1): an administrator exports `/admin/staff/review` and gets the complete list of people and user IDs.
- Manual (step 2): HR or the ward lead reconciles the list against the staff roster. Two people sharing one ID, or an ID with no named person, fails the test. Record the review date.
- Reference: SD Elements guidance for T233.

**Success Criteria:**
- [ ] The pgTAP suite passes with zero duplicates, orphans or generic accounts.
- [ ] The account review export is available to administrators only (aal2), and a signed-off review record exists for the release.

**Status:** Applied
