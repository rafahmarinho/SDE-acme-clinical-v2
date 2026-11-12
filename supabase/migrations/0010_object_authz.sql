-- 0010_object_authz.sql - authorize every request for data objects at the row level (T378).
--
-- 0002 let any staff role UPDATE any alarm row (the API's SELECT policy hid other wards' rows, so the
-- statement matched nothing, but the write policy itself was not object-scoped). Clinical roles may now only
-- update alarms of patients they can access (assigned ward or an active break-glass grant); device alarms
-- (patient_id null) and the device-management / simulation paths (device:write: biomed tech, admin) keep their
-- existing scope. Uses the shared helpers, never role literals. Idempotent.

drop policy if exists alarms_update on public.alarms;
create policy alarms_update on public.alarms for update to acme_api
  using (patient_id is null or public.can_access_patient(patient_id) or public.has_permission('device:write'))
  with check (patient_id is null or public.can_access_patient(patient_id) or public.has_permission('device:write'));
