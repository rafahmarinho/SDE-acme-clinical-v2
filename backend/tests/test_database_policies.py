"""Static checks of the Supabase migrations: least-privilege database accounts, RBAC through group
roles, query/column-level grants, row-level security on every table, and parity between the SQL
permission matrix and backend/app/core/security.py.

These run without a database (CI-friendly). They complement, not replace, a live review of
`\\du+`, information_schema.role_table_grants and pg_policies on the hosted project.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.core.config import get_settings
from app.core.security import PERMISSIONS

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _read(path: Path) -> str:
    return _strip_comments(path.read_text(encoding="utf-8")).lower()


ALL_SQL = "\n".join(_read(p) for p in MIGRATIONS)
AUTHZ = next((p for p in MIGRATIONS if p.name.startswith("0003_authz")), None)
AUTHZ_SQL = _read(AUTHZ) if AUTHZ else ""
STATEMENTS = [s.strip() for s in ALL_SQL.split(";") if s.strip()]


def _grants() -> list[str]:
    return [re.sub(r"\s+", " ", s) for s in STATEMENTS if s.startswith("grant ")]


def test_authz_migration_exists():
    assert AUTHZ is not None, "supabase/migrations/0003_authz_*.sql is missing"


def test_every_table_has_rls_enabled_and_forced():
    tables = set(re.findall(r"create table (?:if not exists )?public\.(\w+)", ALL_SQL))
    loop = re.search(r"foreach t in array array\[(.*?)\] loop", ALL_SQL, re.S)
    via_loop = set(re.findall(r"'(\w+)'", loop.group(1))) if loop else set()
    assert "execute format('alter table public.%i enable row level security', t)" in ALL_SQL
    assert "execute format('alter table public.%i force row level security', t)" in ALL_SQL
    missing = []
    for t in sorted(tables):
        enabled = t in via_loop or f"alter table public.{t} enable row level security" in ALL_SQL
        forced = t in via_loop or f"alter table public.{t} force row level security" in ALL_SQL
        if not (enabled and forced):
            missing.append(t)
    assert tables and missing == []


def test_no_privileges_granted_to_anon_or_public():
    offenders = [g for g in _grants() if {"anon", "public"} & {x.strip() for x in g.rsplit(" to ", 1)[-1].split(",")}]
    assert offenders == []
    assert "revoke all on all tables in schema public from anon" in AUTHZ_SQL
    assert "revoke execute on all functions in schema public from anon" in AUTHZ_SQL
    assert "alter default privileges in schema public revoke all on tables from public, anon, authenticated" in AUTHZ_SQL


def test_application_roles_are_not_privileged():
    assert not re.search(r"(?<!no)superuser", ALL_SQL)
    assert not re.search(r"(?<!no)bypassrls", ALL_SQL)
    assert not re.search(r"(?<!no)createrole", ALL_SQL)
    assert not re.search(r"(?<!no)replication", ALL_SQL)
    assert re.search(r"alter role acme_api nosuperuser nocreatedb nocreaterole nobypassrls noreplication inherit", AUTHZ_SQL)
    for role in ("acme_api_rw", "acme_reset_owner"):
        assert re.search(rf"create role {role} nologin nosuperuser nocreatedb nocreaterole nobypassrls", AUTHZ_SQL)


def test_no_ddl_or_ownership_for_application_roles():
    assert not re.search(r"grant (create|all)\b[^;]* on schema", ALL_SQL)
    assert not re.search(r"owner to acme_api\b", ALL_SQL)
    assert not re.search(r"grant all\b", ALL_SQL)
    assert not re.search(r"grant [^;]*\b(truncate|references|trigger)\b", ALL_SQL)


def test_rbac_login_role_has_no_direct_grants():
    """After 0003, acme_api only inherits acme_api_rw; every privilege is granted to group roles."""
    authz_grants = [re.sub(r"\s+", " ", s).strip() for s in AUTHZ_SQL.split(";") if s.strip().startswith("grant ")]
    assert [g for g in authz_grants if re.search(r"\bto acme_api$", g.strip())] == ["grant acme_api_rw to acme_api"]
    for stmt in ("revoke all on all tables in schema public from acme_api",
                 "revoke all on all sequences in schema public from acme_api",
                 "revoke execute on all functions in schema public from acme_api"):
        assert stmt in AUTHZ_SQL
    # the revokes come after the group grants, so the final state has no direct table grants
    assert AUTHZ_SQL.index("grant acme_api_rw to acme_api") < AUTHZ_SQL.index("revoke all on all tables in schema public from acme_api")


def _authz_grants_to(role: str) -> list[str]:
    stmts = [re.sub(r"\s+", " ", s.strip()) for s in AUTHZ_SQL.split(";")]
    return [s for s in stmts if s.startswith("grant ") and s.endswith(f"to {role}")]


def test_api_group_role_is_append_only_on_audit_and_minimal_on_delete():
    grants = _authz_grants_to("acme_api_rw")
    deletes = [g for g in grants if re.match(r"grant [^;]*\bdelete\b", g)]
    assert deletes == ["grant delete on public.staff_ward_assignments to acme_api_rw"]
    events = [g for g in grants if "public.events " in g + " " or g.endswith("public.events to acme_api_rw")]
    assert "grant insert on public.events to acme_api_rw" in grants
    assert not [g for g in events if re.match(r"grant (update|delete)", g)]
    # nobody gets UPDATE/DELETE on the audit log anywhere
    assert not re.search(r"grant [^;]*(update|delete)[^;]* on [^;]*public\.events\b", ALL_SQL)


def test_sensitive_columns_use_column_level_grants():
    grants = _authz_grants_to("acme_api_rw")
    for table in ("staff_profiles", "alarms", "alarm_thresholds", "break_glass_grants", "security_settings", "monitors"):
        table_level_update = [g for g in grants if re.match(rf"grant update on public\.{table} ", g)]
        assert table_level_update == [], table
    alarm_update = next(g for g in grants if g.startswith("grant update (") and "on public.alarms " in g)
    assert "acknowledged_by" in alarm_update
    # browser sessions can never write
    assert not [g for g in _grants() if g.endswith("to authenticated") and re.match(r"grant (insert|update|delete)", g)]


def test_bulk_reset_only_through_security_definer_function():
    fn = re.search(r"create or replace function public\.reset_simulation_data\(\)(.*?)end \$\$", AUTHZ_SQL, re.S)
    assert fn and "security definer" in fn.group(1) and "set search_path" in fn.group(1)
    assert "has_permission('simulation:control')" in fn.group(1)
    assert "revoke execute on function public.reset_simulation_data() from public, anon, authenticated" in AUTHZ_SQL
    assert "alter function public.reset_simulation_data() owner to acme_reset_owner" in AUTHZ_SQL
    assert "drop policy if exists observations_reset" in AUTHZ_SQL and "drop policy if exists alarms_reset" in AUTHZ_SQL


def test_security_definer_functions_pin_search_path():
    for m in re.finditer(r"create or replace function (public\.\w+)\((.*?)\$\$", ALL_SQL, re.S):
        header = m.group(2)
        if "security definer" in header:
            assert "set search_path" in header, m.group(1)


def test_role_permissions_match_python_matrix():
    insert = re.search(r"insert into public\.role_permissions \(role, permission\) values(.*?);", AUTHZ_SQL, re.S)
    assert insert
    sql_pairs = set(re.findall(r"\('(\w+)', '([a-z_]+:[a-z_]+)'\)", insert.group(1)))
    py_pairs = {(role.value, perm.value) for role, perms in PERMISSIONS.items() for perm in perms}
    assert sql_pairs == py_pairs


def test_new_policies_use_shared_helpers_not_role_literals():
    policies = [s for s in AUTHZ_SQL.split(";") if s.strip().startswith("create policy")]
    assert len(policies) >= 15
    for p in policies:
        assert "current_staff_role() =" not in p and "current_staff_role() in" not in p, p
        assert "auth.uid() = '" not in p


def test_permissive_true_policies_only_for_service_roles():
    for p in (s for s in ALL_SQL.split(";") if "create policy" in s):
        if re.search(r"using \(true\)", p):
            assert re.search(r"to (acme_reporting|acme_reset_owner)\b", p), p


def test_break_glass_is_time_boxed_revocable_and_reviewed_by_someone_else():
    can_access = list(re.finditer(r"create or replace function public\.can_access_patient\(.*?\$\$(.*?)\$\$", ALL_SQL, re.S))
    latest = can_access[-1].group(1)
    assert "g.expires_at > now()" in latest and "g.revoked_at is null" in latest
    assert "check (reviewed_by is null or reviewed_by <> user_id)" in AUTHZ_SQL
    assert "expires_at <= granted_at + interval '4 hours'" in ALL_SQL
    assert re.search(r"create policy bg_review .*user_id <> public\.current_staff_id\(\)", AUTHZ_SQL, re.S)
    # alarm-limit changes are never possible through a break-glass grant
    fn = re.search(r"function public\.can_configure_thresholds\(.*?\$\$(.*?)\$\$", AUTHZ_SQL, re.S).group(1)
    assert "break_glass" not in fn and "can_access_ward" in fn


def test_separation_of_duties_enforced_in_database():
    assert "cannot change their own role or activation" in AUTHZ_SQL
    assert "requires approval by a second administrator" in AUTHZ_SQL
    assert "check (decided_by is null or (decided_by <> requested_by and decided_by <> target_user_id))" in AUTHZ_SQL
    assert "events_block_mutation" in ALL_SQL  # audit trail append-only even for the owner
    assert re.search(r"role public\.app_role not null", ALL_SQL)  # exactly one role per staff member


def test_storage_bucket_is_private_and_browser_has_no_storage_policies():
    assert re.search(r"values \('clinical-files', 'clinical-files', false", ALL_SQL)
    assert "on storage.objects" not in ALL_SQL


def test_runtime_database_user_is_least_privilege_api_role():
    url = urlparse(get_settings().database_url.get_secret_value())
    assert (url.username or "").split(".")[0] == "acme_api"
    example = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    db_line = next(line for line in example.splitlines() if line.startswith("DATABASE_URL="))
    assert "acme_api" in db_line and "postgres:" not in db_line.split("@")[0] and "service_role" not in db_line


@pytest.mark.parametrize("path", [p.name for p in MIGRATIONS])
def test_migrations_contain_no_passwords(path):
    text = _read(ROOT / "supabase" / "migrations" / path)
    assert not re.search(r"\bpassword\s+'", text)
