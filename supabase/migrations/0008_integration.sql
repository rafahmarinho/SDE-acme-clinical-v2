-- 0008_integration.sql - cross-domain integration after the security hardening (2026-11-12).
--
-- 1. Maintenance history read permission: administrators need to VIEW maintenance history (fleet
--    oversight) without being able to RECORD maintenance (separation of duties: maintenance:write stays
--    with biomedical technicians). Mirrors PERMISSIONS in backend/app/core/security.py (a test compares
--    the union of every role_permissions insert with the Python matrix).
-- 2. The maintenance_records read policy uses the shared has_permission() helper instead of role literals.

insert into public.role_permissions (role, permission) values
  ('biomed_tech', 'maintenance:read'), ('admin', 'maintenance:read')
on conflict (role, permission) do nothing;

drop policy if exists maintenance_read on public.maintenance_records;
create policy maintenance_read on public.maintenance_records for select to acme_api
  using (public.has_permission('maintenance:read'));
