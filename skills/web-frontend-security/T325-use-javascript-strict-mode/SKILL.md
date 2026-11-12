---
name: t325-use-javascript-strict-mode
description: Ensures all ACME Clinical frontend code runs in JavaScript strict mode by shipping only ES modules from TypeScript (strict by definition), enabling TypeScript strict/alwaysStrict, and forbidding non-module classic scripts.
---

# T325: Use JavaScript Strict Mode

**Category:** CODE_FIX
**SD Elements:** [T325](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T325/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
Vite + TypeScript projects are ES modules, and module code is always strict mode, so most code is already strict. Gaps appear when someone adds a classic `<script>` (analytics snippet, legacy 3D/WebGL helper), a `.cjs` file, or a library loaded as a non-module script; that code runs sloppy (silent failures, implicit globals) while handling patient data in the page.

**Secure Implementation Pattern:**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "alwaysStrict": true,
    "noImplicitAny": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}
```
```typescript
// frontend/eslint.config.js (excerpt)
export default [{
  files: ["**/*.{ts,tsx}"],
  languageOptions: { sourceType: "module" },
  rules: { strict: ["error", "never"], "no-implicit-globals": "error", "no-eval": "error" },
}, {
  files: ["**/*.{js,cjs}"],                       // any non-module JS must opt in explicitly
  languageOptions: { sourceType: "script" },
  rules: { strict: ["error", "global"] },
}];
```

**Implementation Guidance:**
- Keep `"type": "module"` in `frontend/package.json` and only `<script type="module">` in `frontend/index.html`; ES modules (and classes) are strict by spec, so `"use strict"` is redundant there.
- Set `"strict": true` and `"alwaysStrict": true` in `frontend/tsconfig.json` (`alwaysStrict` emits `"use strict"` for any non-module output and parses in strict mode).
- Do not add classic scripts or CDN tags; bundle libraries (including any 3D library) through pnpm so they are module-scoped and covered by CSP `script-src 'self'` (T331).
- If any classic `.js`/`.cjs` file is unavoidable, start it with `"use strict";` (enforced by the ESLint override above).
- Python backend is not affected by this CM.
- Reference: SD Elements guidance for T325.

**Success Criteria:**
- [ ] `tsconfig.json` has `strict` and `alwaysStrict` enabled; `pnpm tsc --noEmit` passes.
- [ ] `index.html` has only `type="module"` scripts; ESLint passes with the strict rules.
- [ ] Verified by T329.

**Status:** Pending
