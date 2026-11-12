"""Operator CLI.

    python -m app.cli create-demo-staff

Creates one demo account per role through the Supabase Admin API with a unique, randomly
generated password (secrets module), prints each credential ONCE to the terminal, and binds
the 10 simulated monitors to the first 10 beds. Nothing is written to disk or git. Run it only
against a demo project; rotate or delete the accounts afterwards.
"""

from __future__ import annotations

import asyncio
import secrets
import string
import sys

import httpx
import psycopg

from app.core.config import get_settings

DEMO = [("Nora Nurse", "nurse"), ("Paul Physician", "physician"), ("Bea Biomed", "biomed_tech"), ("Ada Admin", "admin")]


def _password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!@#"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            return pw


async def create_demo_staff(email_domain: str) -> None:
    s = get_settings()
    key = s.supabase_service_role_key.get_secret_value()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    created: list[tuple[str, str, str, str]] = []
    async with httpx.AsyncClient(base_url=str(s.supabase_url).rstrip("/"), timeout=15, verify=True) as client:
        for name, role in DEMO:
            email = f"{role.replace('_', '.')}.{secrets.token_hex(3)}@{email_domain}"
            pw = _password()
            resp = await client.post("/auth/v1/admin/users", headers=headers,
                                     json={"email": email, "password": pw, "email_confirm": True})
            resp.raise_for_status()
            created.append((resp.json()["id"], email, name, role))
            print(f"{role:12} {email}  password: {pw}")
    with psycopg.connect(s.database_url.get_secret_value()) as conn, conn.cursor() as cur:
        for uid, email, name, role in created:
            cur.execute("insert into public.staff_profiles (user_id, email, full_name, role) values (%s, %s, %s, %s)",
                        (uid, email, name, role))
            if role in ("nurse", "physician"):
                cur.execute("insert into public.staff_ward_assignments (user_id, ward_id) select %s, id from public.wards", (uid,))
        admin_id = next(uid for uid, _, _, role in created if role == "admin")
        cur.execute("""insert into public.monitor_assignments (monitor_id, bed_id, assigned_by)
                       select m.id, b.id, %s from
                         (select id, row_number() over (order by serial) rn from public.monitors) m
                         join (select id, row_number() over (order by label) rn from public.beds) b using (rn)
                       where m.rn <= 10 on conflict do nothing""", (admin_id,))
    print("\nStore these passwords in a password manager now; they are not saved anywhere. "
          "The admin account must enrol TOTP MFA at first sign-in.")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "create-demo-staff":
        asyncio.run(create_demo_staff(sys.argv[2] if len(sys.argv) > 2 else "example.test"))
    else:
        print(__doc__)
        sys.exit(2)
