"""Password policy (single definition for the API, the CLI and the UI rules).

ACME Clinical never stores or verifies passwords itself: Supabase Auth keeps salted bcrypt hashes and
performs every password check. This module defines the *policy*:

* minimum length from ``public.security_settings.password_min_length`` (administrator-configurable,
  never below the platform floor of 12 set in supabase/config.toml), maximum 128;
* lower-case, upper-case and digit required (mirrors ``password_requirements =
  "lower_upper_letters_digits"`` in supabase/config.toml);
* no common, repetitive or sequential values and no account/context words (e-mail local part, name,
  service name). Breached passwords are rejected by Supabase leaked-password protection.

It is used by every server-side password path (the operator CLI generating one-time demo passwords)
and is exposed to the UI as a rule list (frontend/src/lib/authPolicy.ts mirrors it; tests compare).
It also validates system (server-to-server) secrets such as the database password (T230).
"""

from __future__ import annotations

import re
import secrets
import string
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

PLATFORM_MIN_LENGTH = 12  # supabase/config.toml [auth] minimum_password_length
MAX_LENGTH = 128
SERVICE_WORDS = ("acme", "clinical")
COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "p@ssw0rd", "passw0rd", "qwerty123", "qwertyuiop", "123456789012",
    "welcome123", "letmein", "changeme", "admin123", "iloveyou", "monkey123", "football", "baseball",
    "sunshine", "princess", "dragon", "trustno1", "abc123456789", "hospital", "nurse", "doctor",
})
_SEQUENCES = ("abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm")
WEAK_SYSTEM_SECRETS = frozenset({"changeme", "secret", "password", "postgres", "example", "test", "admin",
                                 "your-secret-here", "x"})


class PasswordPolicyError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = PLATFORM_MIN_LENGTH
    max_length: int = MAX_LENGTH
    require_lower: bool = True
    require_upper: bool = True
    require_digit: bool = True
    banned_words: tuple[str, ...] = field(default=SERVICE_WORDS)

    def __post_init__(self) -> None:
        if not PLATFORM_MIN_LENGTH <= self.min_length <= self.max_length <= MAX_LENGTH:
            raise ValueError(f"min_length must be between {PLATFORM_MIN_LENGTH} and {MAX_LENGTH}")

    def rules(self) -> list[str]:
        """Human-readable rules shown in the UI."""
        out = [f"{self.min_length} to {self.max_length} characters"]
        if self.require_lower:
            out.append("a lower-case letter")
        if self.require_upper:
            out.append("an upper-case letter")
        if self.require_digit:
            out.append("a digit")
        out.append("no common words, sequences or parts of your name or e-mail")
        return out


def policy_from_settings(row: dict[str, Any] | None) -> PasswordPolicy:
    """Build the policy from a public.security_settings row (falls back to safe defaults)."""
    configured = int((row or {}).get("password_min_length") or PLATFORM_MIN_LENGTH)
    return PasswordPolicy(min_length=max(PLATFORM_MIN_LENGTH, min(configured, MAX_LENGTH)))


async def load_policy(conn: Any) -> PasswordPolicy:
    from app.db import fetch_one

    return policy_from_settings(await fetch_one(conn, "select password_min_length from public.security_settings where id = 1"))


def context_words(email: str | None = None, full_name: str | None = None) -> list[str]:
    words: list[str] = []
    if email:
        local = email.split("@", 1)[0].lower()
        words.append(local)
        words.extend(p for p in re.split(r"[._+\-]", local) if p)
    if full_name:
        words.extend(p.lower() for p in re.split(r"\W+", full_name) if p)
    return [w for w in words if len(w) >= 3]


def _is_repetitive_or_sequential(pw: str) -> bool:
    low = pw.lower()
    if len(set(low)) <= 3 or re.search(r"(.)\1{3,}", low):
        return True
    for seq in _SEQUENCES:
        for i in range(len(seq) - 4):
            chunk = seq[i:i + 5]
            if chunk in low or chunk[::-1] in low:
                return True
    return False


def violations(password: str, policy: PasswordPolicy, context: list[str] | None = None) -> list[str]:
    """Every rule the password breaks (empty list = acceptable). Never logs or echoes the password."""
    problems: list[str] = []
    if not policy.min_length <= len(password) <= policy.max_length:
        problems.append(f"Use {policy.min_length} to {policy.max_length} characters.")
    if policy.require_lower and not any(c.islower() for c in password):
        problems.append("Add a lower-case letter.")
    if policy.require_upper and not any(c.isupper() for c in password):
        problems.append("Add an upper-case letter.")
    if policy.require_digit and not any(c.isdigit() for c in password):
        problems.append("Add a digit.")
    low = password.lower()
    stripped = re.sub(r"[\d\W_]+$", "", low)
    if low in COMMON_PASSWORDS or stripped in COMMON_PASSWORDS or _is_repetitive_or_sequential(password):
        problems.append("Avoid common passwords, repeated characters and sequences.")
    words = [*policy.banned_words, *(context or [])]
    if any(w and len(w) >= 3 and w.lower() in low for w in words):
        problems.append("Do not use your name, e-mail address or the service name.")
    return problems


def assert_acceptable(password: str, policy: PasswordPolicy, context: list[str] | None = None) -> None:
    problems = violations(password, policy, context)
    if problems:
        raise PasswordPolicyError(problems)


def generate_password(policy: PasswordPolicy, context: list[str] | None = None, length: int | None = None) -> str:
    """Random password (secrets module) that satisfies the policy; used for one-time operator credentials."""
    size = max(length or 20, policy.min_length)
    alphabet = string.ascii_letters + string.digits + "-_.!@#%"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(size))
        if not violations(candidate, policy, context):
            return candidate


# ---------------------------------------------------------------------------
# System (server-to-server) credentials - T230
# ---------------------------------------------------------------------------
def _mostly_sequential(value: str) -> bool:
    """True when most neighbouring characters repeat or step by one ("abcdef...", "0123...", "aaaa...")."""
    if len(value) < 2:
        return True
    steps = sum(1 for a, b in zip(value.lower(), value.lower()[1:]) if abs(ord(a) - ord(b)) <= 1)
    return steps / (len(value) - 1) > 0.5


def system_secret_problems(name: str, value: str, *, min_length: int = 16) -> list[str]:
    """Problems with a non-human credential (DB password, service key, shared secret) (T69).

    System accounts are held to at least the end-user policy: the floor is never below PLATFORM_MIN_LENGTH, and
    placeholder, dictionary, low-entropy or sequential values are refused."""
    problems: list[str] = []
    min_length = max(min_length, PLATFORM_MIN_LENGTH)
    if len(value) < min_length:
        problems.append(f"{name} must be at least {min_length} characters")
    if (value.lower() in WEAK_SYSTEM_SECRETS or value.lower() in COMMON_PASSWORDS or value.startswith("<")
            or len(set(value)) < 8 or _mostly_sequential(value)):
        problems.append(f"{name} is a placeholder or low-entropy value")
    return problems


def database_url_problems(database_url: str) -> list[str]:
    """The API's Postgres DSN must use a dedicated least-privilege role, a strong password and TLS."""
    parts = urlsplit(database_url)
    problems = system_secret_problems("Database password", parts.password or "")
    if (parts.username or "") in ("postgres", "supabase_admin", ""):
        problems.append("DATABASE_URL must use the dedicated acme_api role, not a superuser")
    # verify-full only: "require" encrypts but does not authenticate the server (T558/T156).
    if "sslmode=verify-full" not in database_url:
        problems.append("DATABASE_URL must enforce TLS with certificate verification (sslmode=verify-full)")
    return problems
