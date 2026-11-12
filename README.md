# ACME Clinical

Simulated ward patient-monitoring system (fictional patients, simulated monitors). **Placeholder scaffold** generated from `specs/PRD.md` by the SD Elements `create-security-plan-from-specs` skill. No production code yet: implement each feature following the security task recipes in [`AGENTS.md`](./AGENTS.md) and [`skills/`](./skills/).

## Product overview (from PRD)

- English is the default language for all screens, messages, reports and sample data.
- Ward overview, patient list and detail, live monitoring, alarms, devices, alarm-threshold settings, reports and team management (optional 3D visualization of simulated actions).
- Simulated monitors show heart rate, SpO2, respiration, blood pressure and a synthetic ECG trace.
- Bind a monitor to a bed, record observations, acknowledge alarms (acknowledging does NOT clear an ongoing condition) and track maintenance.
- Scenarios: normal readings, low saturation, low battery, sensor fault, connection loss.
- Roles: nurse, physician, biomedical technician, administrator; navigation adapts to role.
- Demo data: 12 patients, 10 monitors. Simulation area to pick scenarios, advance the simulation, query events and reset data. Results persist across reloads.
- Login, password recovery, profile, settings, search, filters, loading states and error messages. External integrations are simulated.
- UI: white background, navy-blue text, large numbers.

## Architecture

| Part | Stack | Deploy |
|------|-------|--------|
| `backend/` | Python, FastAPI, Pydantic (readings, alarms and reports generated in Python) | Vercel (Python runtime) |
| `frontend/` | React, Vite, TypeScript, pnpm (screens, components, services) | Vercel (static) |
| `supabase/` | PostgreSQL schema, RLS, seed data; Supabase Auth (email/password), Storage, Realtime | Supabase |

## Getting started (to be completed during implementation)

1. Copy `backend/.env.example` and `frontend/.env.example` to `.env` and fill in values (never commit secrets).
2. Apply `supabase/migrations/*` and `supabase/seed.sql` to your Supabase project.
3. Backend: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
4. Frontend: `cd frontend && pnpm install && pnpm dev`
5. Publish: create two Vercel projects (root `backend/` and root `frontend/`).

## Security

SD Elements project **ACME Clinical v2** (ID 32). See `AGENTS.md` for the countermeasure index and `.sde-handoff.json` for tooling handoff.
