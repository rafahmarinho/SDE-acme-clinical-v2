---
name: t329-verify-that-javascript-is-used-in-strict-mode
description: Verifies that all ACME Clinical frontend JavaScript runs in strict mode by checking tsconfig strict settings, that index.html loads only ES module scripts, and that the production bundle contains no classic scripts.
---

# T329: Verify that JavaScript is used in Strict Mode

**Category:** CODE_FIX
**SD Elements:** [T329](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/testing/32-T329/)
**Priority:** 5/10 · **Phase:** testing

**Spec Context:**
> "React com Vite e TypeScript no frontend, publicados separadamente na Vercel."
> (EN: React with Vite and TypeScript on the frontend, published separately on Vercel.)
> Source: specs/PRD.md, line 19

**What the spec implies (naive approach):**
The SD Elements test looks for `"use strict";` at the top of scripts. In a Vite/TypeScript build the output is ES modules, which are strict without the directive, so a literal search would wrongly fail. The test must verify module-ness instead, and catch any classic script that slips in.

**Secure Implementation Pattern:**
```typescript
// frontend/tests/strict-mode.test.ts
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { it, expect } from "vitest";

it("tsconfig enforces strict mode", () => {
  const ts = JSON.parse(readFileSync("tsconfig.json", "utf8"));
  expect(ts.compilerOptions.strict).toBe(true);
  expect(ts.compilerOptions.alwaysStrict ?? ts.compilerOptions.strict).toBe(true);
});

it("index.html only loads ES modules", () => {
  const html = readFileSync(existsSync("dist/index.html") ? "dist/index.html" : "index.html", "utf8");
  const scripts = [...html.matchAll(/<script\b([^>]*)>/gi)].map((m) => m[1]);
  scripts.forEach((attrs) => expect(attrs).toMatch(/type="module"/));
});

it("classic JS files in src opt in to strict mode", () => {
  const walk = (d: string): string[] => readdirSync(d, { withFileTypes: true })
    .flatMap((e) => e.isDirectory() ? walk(join(d, e.name)) : [join(d, e.name)]);
  walk("src").filter((f) => f.endsWith(".cjs"))
    .forEach((f) => expect(readFileSync(f, "utf8").trimStart()).toMatch(/^["']use strict["'];/));
});
```

**Implementation Guidance:**
- If `tsconfig*.json` contains comments (Vite templates do), parse it with `ts.readConfigFile(path, ts.sys.readFile)` from the `typescript` package instead of `JSON.parse`, and check the file that covers `src` (e.g. `tsconfig.app.json`).
- Add the vitest suite under `frontend/tests/`; run it after `pnpm build` in CI so `dist/index.html` is checked; it verifies T325.
- Manual check in the browser: in DevTools on a loaded page, the Sources panel shows `index-*.js` loaded as `type="module"`; module code is strict (e.g. assigning to an undeclared variable throws `ReferenceError`).
- Code review: any new `<script>` without `type="module"` or any `.cjs`/classic JS lacking `"use strict"` fails the test.
- Reference: SD Elements guidance for T329.

**Success Criteria:**
- [ ] Strict-mode vitest suite passes on source and built output.
- [ ] ESLint `strict` rules from T325 pass in CI.

**Status:** Applied
