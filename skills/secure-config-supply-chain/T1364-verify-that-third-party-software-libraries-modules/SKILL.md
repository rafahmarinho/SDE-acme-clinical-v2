---
name: t1364-verify-that-third-party-software-libraries-modules
description: Test recipe verifying ACME Clinical uses third-party components (Supabase, Vercel, Python and pnpm packages) securely - inventory, vulnerability scanning that actually detects vulnerable JS libraries, license checks, least privilege and secure channels.
---

# T1364: Verify that third party software libraries/modules and open source/COTS components are used securely

**Category:** CODE_FIX
**SD Elements:** [T1364](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T1364/)
**Priority:** 6/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel. Use pnpm no"
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel. Use pnpm on the)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
The stack depends on many open-source packages and two SaaS platforms. Teams often add an audit command but never confirm it detects anything, skip license review, and give third parties broad privileges (service role key in every function, Supabase key with full access in the frontend).

**Secure Implementation Pattern:**
```bash
# scripts/verify-scanner-detects.sh (manual/CI canary in a throwaway branch)
set -euo pipefail
tmp=$(mktemp -d); cp -r frontend "$tmp/fe"; cd "$tmp/fe"
pnpm add lodash@4.17.15 --save-exact           # known-vulnerable canary (prototype pollution)
if pnpm audit --audit-level=high; then
  echo "FAIL: scanner did not detect vulnerable lodash"; exit 1
fi
echo "PASS: scanner detects vulnerable JS dependency"
```

```bash
# license review
pnpm --dir frontend licenses list --json > artifacts/frontend-licenses.json
pip-licenses --from=mixed --format=json > artifacts/backend-licenses.json
```

**Implementation Guidance:**
- Verify a component inventory exists (SBOM from T241) with vendor, version, purpose and risk; check Supabase/Vercel are approved vendors in `docs/security/dependencies.md`.
- Run the canary above to prove `pnpm audit` (or Snyk/OSV-Scanner) detects a vulnerable JS library; repeat for Python with an old `jinja2` pinned in a temp venv and `pip-audit`.
- Check licenses against an allow-list (MIT, BSD, Apache-2.0, ISC); flag GPL/AGPL for review.
- Least privilege: frontend uses only the anon key + RLS; service role key only in backend functions that need it.
- Secure channels: all Supabase/Vercel traffic over HTTPS/WSS (T175); packages installed from the official registries with lockfile integrity hashes.
- Verify packages come from maintained upstreams (no abandoned forks) and pre-configured defaults are changed (T2349).
- Reference: SD Elements guidance for T1364.

**Success Criteria:**
- [ ] Canary test proves the JS and Python scanners detect vulnerable libraries.
- [ ] License report generated and reviewed; no unapproved licenses.
- [ ] Component inventory current and documented.
- [ ] Service role key confined to the backend; frontend bundle grep is clean.

**Status:** Pending
