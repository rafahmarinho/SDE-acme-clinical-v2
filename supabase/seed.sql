-- ACME Clinical demo data: 2 wards, 14 beds, 12 FICTITIOUS patients, 10 simulated monitors.
-- No staff accounts or passwords are seeded (nothing is written to the auth schema here). Demo staff are created with
--   python -m app.cli create-demo-staff
-- which uses the Supabase Admin API, creates one personal account per fictional person (no shared or
-- role-named logins), generates a unique random password per account and prints it once.

insert into public.wards (id, code, name) values
  ('00000000-0000-4000-8000-000000000001', 'ICU-A', 'Intensive Care A'),
  ('00000000-0000-4000-8000-000000000002', 'MED-B', 'Medical Ward B');

insert into public.beds (ward_id, label)
select '00000000-0000-4000-8000-000000000001', 'A' || lpad(g::text, 2, '0') from generate_series(1, 6) g
union all
select '00000000-0000-4000-8000-000000000002', 'B' || lpad(g::text, 2, '0') from generate_series(1, 8) g;

insert into public.patients (pseudonym, display_name, birth_year, ward_id, bed_id, retention_until)
select p.pseudonym, p.display_name, p.birth_year, b.ward_id, b.id, (current_date + 365)
from (values
  ('PT-0001', 'Alex Morgan (fictitious)', 1956, 'A01'), ('PT-0002', 'Jamie Rivera (fictitious)', 1971, 'A02'),
  ('PT-0003', 'Taylor Brooks (fictitious)', 1948, 'A03'), ('PT-0004', 'Jordan Ellis (fictitious)', 1989, 'A04'),
  ('PT-0005', 'Casey Nguyen (fictitious)', 1963, 'A05'), ('PT-0006', 'Riley Patel (fictitious)', 1979, 'A06'),
  ('PT-0007', 'Morgan Reyes (fictitious)', 1952, 'B01'), ('PT-0008', 'Avery Kim (fictitious)', 1995, 'B02'),
  ('PT-0009', 'Quinn Foster (fictitious)', 1967, 'B03'), ('PT-0010', 'Drew Santos (fictitious)', 1941, 'B04'),
  ('PT-0011', 'Skyler Hayes (fictitious)', 1984, 'B05'), ('PT-0012', 'Reese Okafor (fictitious)', 1975, 'B06')
) as p(pseudonym, display_name, birth_year, bed_label)
join public.beds b on b.label = p.bed_label;

-- Each simulated monitor gets a random device secret; only its SHA-256 is stored and the secret itself is
-- discarded, so no monitor can be paired until an operator issues pairing codes with
--   python -m app.cli provision-monitor-secrets
-- (no default device credentials).
insert into public.monitors (serial, model, device_secret_hash, battery_pct, last_heartbeat_at)
select 'MON-' || lpad(g::text, 4, '0'), case when g % 2 = 0 then 'VitalView 300' else 'VitalView 500' end,
       digest(gen_random_bytes(32), 'sha256'), 100, now()
from generate_series(1, 10) g;

-- Ward default thresholds
insert into public.alarm_thresholds (ward_id, parameter, low_limit, high_limit)
select w.id, t.parameter::public.vital_parameter, t.low_limit, t.high_limit
from public.wards w
cross join (values ('heart_rate', 50, 120), ('spo2', 92, 100), ('resp_rate', 8, 25),
                   ('bp_systolic', 90, 160), ('bp_diastolic', 50, 100)) as t(parameter, low_limit, high_limit);

insert into public.simulation_state (id) values (1);
insert into public.security_settings (id) values (1);
