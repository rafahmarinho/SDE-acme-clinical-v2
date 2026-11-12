---
name: t370-follow-best-practices-for-using-third-party-softwa
description: Establish ACME Clinical's third-party component practices - vetted dependencies, lockfiles with integrity hashes, Dependabot and audit gates, SBOM and component register, least privilege for Supabase/Vercel, and end-of-life tracking.
---

# T370: Follow best practices for using third-party software libraries/modules and open source/COTS components

**Category:** CODE_FIX
**SD Elements:** [T370](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/architecture-design/32-T370/)
**Priority:** 6/10 · **Phase:** architecture-design

**Spec Context:**
> "Use versões atuais e estáveis das tecnologias e Supabase para PostgreSQL, login por e-mail e"
> (EN: Use current and stable versions of the technologies and Supabase for PostgreSQL, email and)
> Source: specs/PRD.md, line 5

**What the spec implies (naive approach):**
To deliver "complete code" quickly, developers add packages freely (3D engines, chart libs, ECG renderers), install without lockfile enforcement and never revisit them. There is no register of components, no license check and no plan for unmaintained packages.

**Secure Implementation Pattern:**
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule: { interval: "weekly" }
    open-pull-requests-limit: 5
  - package-ecosystem: "npm"          # works with pnpm-lock.yaml
    directory: "/frontend"
    schedule: { interval: "weekly" }
    groups: { minor-and-patch: { update-types: ["minor", "patch"] } }
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "monthly" }
```

```ini
# frontend/.npmrc
engine-strict=true
save-exact=true
registry=https://registry.npmjs.org/
```

**Implementation Guidance:**
- Before adding a dependency: check maintenance activity, known CVEs (OSV), license and download provenance; prefer packages already in the stack. Record decision in `docs/security/dependencies.md` (component, vendor, version, capability, risk, EOL date, owner).
- Pin and verify: `backend/requirements.txt` with `--require-hashes` (pip-tools/uv), `frontend/pnpm-lock.yaml` with `pnpm install --frozen-lockfile` in Vercel build settings.
- Enable Dependabot (above), `pip-audit`/`pnpm audit` gates (T241), and SAST (Semgrep/CodeQL) on the repo.
- Least privilege for third parties: Supabase anon key in the browser, service role only server-side; Vercel tokens scoped per project; disable unused Supabase features (e.g. unused auth providers, public buckets).
- Plan for EOL: track Python, Node and major library support dates; schedule upgrades before EOL.
- Reference: SD Elements guidance for T370.

**Success Criteria:**
- [ ] Component register exists and is updated with each dependency PR.
- [ ] Lockfiles with integrity hashes enforced in CI and Vercel.
- [ ] Dependabot and audit gates active.
- [ ] Unused Supabase features and public access disabled.

**Status:** Applied
