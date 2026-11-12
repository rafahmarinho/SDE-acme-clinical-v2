---
name: t751-provide-users-with-a-notification-of-personal-info
description: Add a versioned privacy notice to ACME Clinical, linked from every page and shown just in time on login, profile, staff onboarding and observation forms, stating purposes, data categories, recipients and retention.
---

# T751: Provide users with a notification of personal information processing

**Category:** CODE_FIX
**SD Elements:** [T751](https://sde-ent-echo.sdelab.net/bunits/afrika-sc-labs/acme-clinical-v2/acme-clinical-v2/tasks/phase/requirements/32-T751/)
**Priority:** 5/10 · **Phase:** requirements

**Spec Context:**
> "Use inglês como idioma padrão em todas as telas, mensagens, relatórios e dados de exemplo."
> (EN: Use English as the default language on all screens, messages, reports and sample data.)
> Source: specs/PRD.md, line 3

**What the spec implies (naive approach):**
The PRD lists screens but no privacy notice. A typical build has a login form and profile form with no explanation of what staff and patient data is processed, by whom (Supabase, Vercel as processors) or for how long.

**Secure Implementation Pattern:**
```typescript
// frontend/src/components/PrivacyNotice.tsx
export const PRIVACY_NOTICE_VERSION = "2026-11-01";

export const privacyNotice = {
  purposes: ["Patient monitoring and alarm handling", "Staff authentication and audit"],
  categories: ["Staff: name, email, phone, role", "Patients: pseudonymized ID, vitals, observations"],
  recipients: ["Supabase (database, auth, storage)", "Vercel (hosting)"],
  retention: "Observations: 365 days after discharge; staff profiles: 90 days after deactivation",
};

export function PrivacyFooterLink() {
  return <a href="/privacy" className="footer-link">Privacy notice</a>;
}

export function JustInTimeNotice({ context }: { context: "login" | "profile" | "observation" }) {
  const text = {
    login: "We use your email to sign you in and to record actions for audit.",
    profile: "Your name and phone are shown to your team. Phone is optional.",
    observation: "Observations are part of the patient record and kept per retention policy.",
  }[context];
  return <p role="note" className="jit-notice">{text} <a href="/privacy">Learn more</a></p>;
}
```

**Implementation Guidance:**
- Create a `/privacy` route in `frontend/src/screens/` rendering the notice (purposes, categories, recipients, retention period and criteria) in clear English (PRD default language), with version and effective date.
- Add `PrivacyFooterLink` to the app layout so it appears on every page, including the unauthenticated login and password recovery screens.
- Add `JustInTimeNotice` to login, profile, staff invite and observation forms.
- Store `notice_version` acceptance in `consents` (see T239); when the version changes, show the notice again at next login.
- Keep the notice content in sync with `docs/security/data-classification.md` and retention settings (T607).
- Reference: SD Elements guidance for T751.

**Success Criteria:**
- [ ] `/privacy` is reachable without login and from every page footer.
- [ ] Notice includes purpose, categories, recipients and retention.
- [ ] Just-in-time notes appear on all data-collection forms.
- [ ] A new notice version triggers re-display at next login.

**Status:** Pending
