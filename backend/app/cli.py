"""Operator CLI (run from a trusted workstation, never from the deployed API).

    python -m app.cli create-demo-staff [email-domain] [--allow-demo]
    python -m app.cli provision-monitor-secrets

create-demo-staff
    Creates one personal demo account per role (a distinct, named fictional person each - never a
    shared or role-named login) through the Supabase Admin API. Each account gets a unique random
    password generated with `secrets` that satisfies the password policy (app.services.passwords),
    printed ONCE to the terminal and never written to disk or git. Refuses to run when
    APP_ENV=production unless --allow-demo is given. Binds the 10 simulated monitors to the first beds.
    The administrator must enrol TOTP MFA at first sign-in (the API rejects admin tokens below aal2).

provision-monitor-secrets
    Issues a new per-device secret ("pairing code") for every monitor, stores only its SHA-256 and
    prints each code once (to be put on the device label). Old codes stop working immediately.

Both commands write with ADMIN_DATABASE_URL (the migration/operator role, TLS required except for a
local `supabase start` database); the API's own DATABASE_URL role cannot create accounts.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from urllib.parse import urlsplit

import httpx
import psycopg

from app.core.config import get_settings
from app.services.device_auth import new_device_secret
from app.services.identity import canonical_email
from app.services.passwords import PasswordPolicy, context_words, generate_password

# Fictional people, one per role. Accounts are personal: never share them between staff members.
DEMO = [("Nora Lindqvist", "nurse"), ("Paul Okoye", "physician"), ("Bea Moreau", "biomed_tech"), ("Ada Brennan", "admin")]
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _password(full_name: str = "", email: str = "") -> str:
    """Unique random one-time password that satisfies the policy (no context words)."""
    return generate_password(PasswordPolicy(min_length=16), context_words(email, full_name), length=20)


def operator_dsn() -> str:
    dsn = os.environ.get("ADMIN_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("ADMIN_DATABASE_URL is required (operator role; never the API's DATABASE_URL).")
    host = urlsplit(dsn).hostname or ""
    if host not in _LOCAL_HOSTS and "sslmode=verify-full" not in dsn and "sslmode=require" not in dsn:
        raise SystemExit("ADMIN_DATABASE_URL must enforce TLS (sslmode=verify-full).")
    return dsn


def demo_email(full_name: str, domain: str) -> str:
    first, last = full_name.lower().split()[0], full_name.lower().split()[-1]
    return canonical_email(f"{first}.{last}.{secrets.token_hex(3)}@{domain}")


async def create_demo_staff(email_domain: str) -> None:
    s = get_settings()
    dsn = operator_dsn()
    key = s.supabase_service_role_key.get_secret_value()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    created: list[tuple[str, str, str, str]] = []
    async with httpx.AsyncClient(base_url=str(s.supabase_url).rstrip("/"), timeout=15, verify=True,
                                 follow_redirects=False) as client:
        for name, role in DEMO:
            email = demo_email(name, email_domain)
            pw = _password(name, email)
            resp = await client.post("/auth/v1/admin/users", headers=headers,
                                     json={"email": email, "password": pw, "email_confirm": True,
                                           "app_metadata": {"demo": True}})
            resp.raise_for_status()
            created.append((resp.json()["id"], email, name, role))
            print(f"{role:12} {email}  one-time password: {pw}")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
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
    print("\nStore these passwords in a password manager now; they are not saved anywhere. Hand each one "
          "only to its owner, who should change it at first sign-in (Profile > Change password). The admin account must enrol TOTP MFA at first sign-in. "
          "Deactivate the demo accounts (Team) when the demo window ends.")


def provision_monitor_secrets() -> None:
    with psycopg.connect(operator_dsn()) as conn, conn.cursor() as cur:
        cur.execute("select id, serial from public.monitors where status <> 'retired' order by serial")
        for monitor_id, serial in cur.fetchall():
            secret, digest = new_device_secret()
            cur.execute("update public.monitors set device_secret_hash = %s, authenticated_at = null where id = %s",
                        (digest, monitor_id))
            print(f"{serial}  pairing code: {secret}")
    print("\nPut each pairing code on its monitor label now; only the hashes are stored.")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "create-demo-staff":
        if get_settings().is_production and "--allow-demo" not in argv:
            print("Refusing to create demo staff in production (pass --allow-demo for a public demo project).")
            return 2
        domain = next((a for a in argv[2:] if not a.startswith("--")), "example.test")
        asyncio.run(create_demo_staff(domain))
        return 0
    if len(argv) >= 2 and argv[1] == "provision-monitor-secrets":
        provision_monitor_secrets()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
