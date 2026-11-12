---
name: t2652-consider-adding-plugins-for-stronger-authenticatio
description: MariaDB authentication and password-complexity plugins are not applicable to ACME Clinical's Supabase PostgreSQL; the equivalent is SCRAM-SHA-256 role authentication, strong DB passwords and locked unused roles, plus Supabase Auth password policy for end users.
---

# T2652: Consider adding plugins for stronger authentication protocols and stricter password complexity rules (MariaDB) (NON-CODE)

**Category:** INFRA
**SD Elements:** [T2652](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/deployment/32-T2652/)
**Priority:** 9/10 · **Phase:** deployment

**Guidance:** For MariaDB, replace `mysql_native_password` with `ed25519` (or another strong plugin), enforce password complexity with `simple_password_check`/`cracklib_password_check`, set `default_password_lifetime`, and lock unused accounts.

**Why Not Code-Fixable:**
- Searched specs: specs/PRD.md (full document; deployment/stack statements, e.g. line 5 "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e" (EN: "Use current, stable versions of the technologies and Supabase for PostgreSQL, email and [password] login"))
- Found: the database is Supabase PostgreSQL; MariaDB is not part of the stack.
- Missing: a MariaDB server; these plugins and `mariadb.cnf` do not exist here.
- Conclusion: Not applicable as written. PostgreSQL equivalents: SCRAM-SHA-256 authentication (Supabase default, see T2616), strong random passwords for database roles, `alter role <unused> nologin` to lock unused roles, and `valid until` for expiring temporary roles. End-user password complexity for email/password login is a Supabase Auth setting.

**Recommended Action:** Platform owner: (1) mark T2652 "not applicable – no MariaDB"; (2) confirm DB roles use SCRAM-SHA-256 with long random passwords; (3) lock or drop unused login roles (`alter role ... nologin`); (4) in Supabase Auth settings, set minimum password length/character requirements and enable leaked-password protection for clinical staff accounts.

**Status:** Documented
