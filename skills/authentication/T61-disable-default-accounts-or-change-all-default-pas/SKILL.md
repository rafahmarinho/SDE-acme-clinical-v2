---
name: t61-disable-default-accounts-or-change-all-default-pas
description: Ensures ACME Clinical's demo data (twelve patients, ten monitors, staff per role) ships without default or hard-coded passwords. Demo staff are created with one-time random or invite credentials, are forced to change them, and are disabled or removed outside demo environments.
---

# T61: Disable default accounts or change all default passwords

**Category:** CODE_FIX
**SD Elements:** [T61](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T61/)
**Priority:** 9/10 · **Phase:** deployment

**Spec Context:**
> "Prepare dados de demonstração com doze pacientes e dez monitores."
> (EN: Prepare demonstration data with twelve patients and ten monitors.)
> Source: specs/PRD.md, line 41

**What the spec implies (naive approach):**
To make the demo usable, `supabase/seed.sql` would insert `admin@acme.test / Admin123!` and similar logins into `auth.users`, and the README would print them. Every deployment, including the public Vercel one, would then share known administrator credentials with access to the team-management and reset functions.

**Secure Implementation Pattern:**
```python
# backend/scripts/create_demo_staff.py  (run once per environment, never in seed.sql)
import os, secrets, sys
from supabase import create_client

DEMO_STAFF = [("Ana Ribeiro", "nurse"), ("Dr. Lucas Mendes", "physician"),
              ("Carla Souza", "biomedical_technician"), ("Paulo Lima", "administrator")]

def main() -> None:
    if os.environ.get("APP_ENV") == "production" and "--allow-demo" not in sys.argv:
        sys.exit("Refusing to create demo staff in production")
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    domain = os.environ["DEMO_EMAIL_DOMAIN"]                    # an inbox the operator controls
    for name, role in DEMO_STAFF:
        email = f"{name.split()[-1].lower()}.{role}@{domain}"
        pw = secrets.token_urlsafe(18)                          # unique, random, shown once
        res = sb.auth.admin.create_user({"email": email, "password": pw, "email_confirm": True,
                                         "app_metadata": {"role": role, "demo": True}})
        sb.table("profiles").update({"must_change_password": True}).eq("id", res.user.id).execute()
        print(f"{role:24} {email}  one-time password: {pw}")   # operator copies, not committed

if __name__ == "__main__":
    main()
```

**Implementation Guidance:**
- `supabase/seed.sql` seeds only non-credential demo data: 12 fictional patients, 10 simulated monitors, beds, scenarios. It never inserts into `auth.users` and never contains `crypt(` or passwords.
- Create demo staff with the script above, or with `invite_user_by_email` links. Passwords are random per environment, printed once, and never stored in the repo, README or `.env.example`.
- `must_change_password = true` forces the Profile password change (T3, T5) before any other screen loads. The backend returns 403 `password_change_required` for other routes until it is cleared.
- Production: refuse to create demo accounts. In a public demo deployment, disable demo accounts after the demo window by banning everyone with `app_metadata.demo = true` (admin action or scheduled job).
- The simulation "reset data" action (`backend/app/services/simulation.py`) must not recreate staff accounts or reset their passwords.
- Third-party defaults: change the local Supabase dashboard credentials if exposed, and never use the default local `service_role` JWT outside `supabase start`.
- Reference: SD Elements guidance for T61.

**Success Criteria:**
- [ ] `supabase/seed.sql`, the README and the `.env.example` files contain no credentials (CI grep).
- [ ] Each demo account must change its password at first login. The demo creation script exits in production.
- [ ] Simulation reset leaves staff accounts and credentials unchanged (`backend/tests/test_simulation_reset.py`).

**Status:** Applied
