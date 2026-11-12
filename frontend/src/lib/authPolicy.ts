// Authentication UI rules. Mirrors backend/app/services/passwords.py and backend/app/services/identity.py
// (backend tests compare the constants). The server side stays authoritative: Supabase Auth enforces the
// platform floor (supabase/config.toml) and the API enforces MFA, lockout and account state.

export const PLATFORM_MIN_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;

/** Shown for every sign-in failure (unknown e-mail, wrong password, locked, unconfirmed, banned, rate limited). */
export const GENERIC_LOGIN_ERROR = "Invalid email or password.";
/** Shown after every password-reset request, whether or not the account exists. */
export const GENERIC_RESET_MESSAGE =
  "If an account exists for that address, a password reset link has been sent. Check your inbox and follow the link within the next hour.";
export const GENERIC_MFA_ERROR = "The code is not valid. Check your authenticator app and try again.";

const SERVICE_WORDS = ["acme", "clinical"];
const COMMON = new Set([
  "password", "password1", "password123", "p@ssw0rd", "passw0rd", "qwerty123", "qwertyuiop", "123456789012",
  "welcome123", "letmein", "changeme", "admin123", "iloveyou", "monkey123", "football", "baseball",
  "sunshine", "princess", "dragon", "trustno1", "abc123456789", "hospital", "nurse", "doctor",
]);
const SEQUENCES = ["abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm"];

/**
 * Same username rule as the API: trim, lower-case. The API additionally rejects addresses with inner
 * whitespace/invisible characters or non-ASCII characters.
 */
export function canonicalEmail(raw: string): string {
  return raw.normalize("NFKC").trim().toLowerCase();
}

export function contextWords(email?: string | null, fullName?: string | null): string[] {
  const words: string[] = [];
  if (email) {
    const local = (email.split("@")[0] ?? "").toLowerCase();
    words.push(local, ...local.split(/[._+-]/).filter(Boolean));
  }
  if (fullName) words.push(...fullName.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean));
  return words.filter((w) => w.length >= 3);
}

function repetitiveOrSequential(pw: string): boolean {
  const low = pw.toLowerCase();
  if (new Set(low).size <= 3 || /(.)\1{3,}/.test(low)) return true;
  return SEQUENCES.some((seq) => {
    for (let i = 0; i + 5 <= seq.length; i++) {
      const chunk = seq.slice(i, i + 5);
      if (low.includes(chunk) || low.includes([...chunk].reverse().join(""))) return true;
    }
    return false;
  });
}

/** Problems with a candidate password (empty = acceptable). Never echoes the password. */
export function passwordProblems(pw: string, minLength: number = PLATFORM_MIN_LENGTH, context: string[] = []): string[] {
  const min = Math.min(Math.max(minLength, PLATFORM_MIN_LENGTH), MAX_PASSWORD_LENGTH);
  const problems: string[] = [];
  if (pw.length < min || pw.length > MAX_PASSWORD_LENGTH) problems.push(`Use ${min} to ${MAX_PASSWORD_LENGTH} characters.`);
  if (!/\p{Ll}/u.test(pw)) problems.push("Add a lower-case letter.");
  if (!/\p{Lu}/u.test(pw)) problems.push("Add an upper-case letter.");
  if (!/\p{Nd}/u.test(pw)) problems.push("Add a digit.");
  const low = pw.toLowerCase();
  const stripped = low.replace(/[\d\W_]+$/u, "");
  if (COMMON.has(low) || COMMON.has(stripped) || repetitiveOrSequential(pw)) {
    problems.push("Avoid common passwords, repeated characters and sequences.");
  }
  if ([...SERVICE_WORDS, ...context].some((w) => w.length >= 3 && low.includes(w.toLowerCase()))) {
    problems.push("Do not use your name, e-mail address or the service name.");
  }
  return problems;
}

export function passwordRules(minLength: number = PLATFORM_MIN_LENGTH): string[] {
  const min = Math.max(minLength, PLATFORM_MIN_LENGTH);
  return [
    `${min} to ${MAX_PASSWORD_LENGTH} characters`,
    "a lower-case letter, an upper-case letter and a digit",
    "no common words, sequences or parts of your name or e-mail",
  ];
}
