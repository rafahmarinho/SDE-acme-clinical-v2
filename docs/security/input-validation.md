# Input validation and API message hygiene

Controls for the `skills/input-validation` and `skills/api-security` countermeasures, where they
live, and the tests that prove them. Server-side validation is authoritative; UI checks only
improve usability.

## Layers (request order)

| Layer | File | What it refuses |
|---|---|---|
| `SecurityHeadersMiddleware` (outermost) | `backend/app/core/middleware.py` | Verbs outside `GET POST PUT PATCH DELETE OPTIONS` (405 + `Allow`), `X-HTTP-Method-Override` / `X-HTTP-Method` / `X-Method-Override` (400), unknown `Host` (400), > 64 headers or > 16 KiB of headers (431), URL > 2048 bytes (414), duplicate single-valued query parameters (400, HTTP parameter pollution). Logs every rejection (route, status, client IP, request id, error code; never values). |
| `BodySizeLimitMiddleware` | same | Bodies > 64 KiB for the JSON API, > 5 MiB under `/v1/files` (413, declared or streamed/chunked); non-`application/json` or non-UTF-8 JSON bodies (415); bodies that are not one JSON object, nest deeper than 8, repeat a key, contain `NaN`/`Infinity` or are malformed (400). |
| CORS | `backend/app/main.py` | Origins outside the configured allow-list; explicit method/header list. |
| `RateLimitMiddleware` | same | Over-budget clients (429 + `Retry-After`). See limits below. |
| Pydantic schemas | `backend/app/schemas/__init__.py`, `backend/app/core/validation.py` | Unknown fields (`extra="forbid"`), wrong types (strict ints/bools: no `"40"`, `40.5`, `true` for numbers), out-of-range numbers, unbounded strings/lists, out-of-enum values, control/bidi/zero-width/NUL characters, mixed-script (homoglyph) names, IDN staff e-mails, implausible alarm limits. 422 with field names only, never echoed values. |
| Database | `supabase/migrations/*` | RLS, CHECK constraints (last line of defence). |

## Field policies

| Type | Rule |
|---|---|
| `CleanText` (observations, notes, reasons) | NFC; refuses C0 except TAB/LF/CR, DEL, C1, U+200B–U+200F, U+202A–U+202E, U+2060–U+2064, U+2066–U+2069, BOM, lone surrogates; explicit `max_length`. |
| `SearchText`, `ShortText` | As above plus single line (no TAB/LF/CR/U+2028/U+2029); 60 / 120 chars. |
| `PersonName` (staff names) | NFKC; letters plus space `.` `'` `-` `’`; no combining marks, no double spaces; **one script** (Latin *or* Cyrillic *or* Greek…, CJK group allowed). `Аdmin` with Cyrillic А is refused. |
| `StaffEmail` | RFC e-mail, ASCII only, lower-cased, ≤ 254 chars. |
| Identifiers | UUIDs; codes via `ascii_identifier`. |
| Numbers | `bounded_int(ge, le)` strict integers; alarm limits also cross-checked (`low < high`, clinical bounds, explicit `confirm`). |
| Lists | `max_length` (≤ 10 items). |
| Query params | Typed `Annotated[..., Query(...)]`; `limit ≤ 100` (readings ≤ 120), `offset ≤ 10 000`. |

## Message limits

| Attribute | Application limit | Platform (Vercel) |
|---|---|---|
| JSON body | 64 KiB (`MAX_JSON_BODY_BYTES`) | 4.5 MB function body |
| Upload body (`/v1/files`) | 5 MiB (`MAX_UPLOAD_BYTES`) | 4.5 MB function body |
| Headers | 64 headers / 16 KiB | platform-managed |
| URL | 2048 bytes | 14 KB |
| JSON depth | 8 | – |
| Page size | 100 items (`MAX_PAGE_SIZE`) | PostgREST max rows (configure in Supabase) |

## Throttling (per instance; Vercel Firewall rate rules are the primary, global control)

| Budget | Key | Limit / min |
|---|---|---|
| Authenticated client | JWT `sub` | 120 (`RATE_LIMIT_PER_MINUTE`) |
| Unauthenticated client | client IP | 30 |
| IP ceiling (token-rotation guard) | client IP | 5 × 120 |
| `/v1/auth/*`, `/v1/break-glass*` | subject or IP | 10 (`AUTH_RATE_LIMIT_PER_MINUTE`) |
| `POST /v1/simulation/reset` | subject or IP | 3 |
| `POST /v1/simulation/*` | subject or IP | 10 |
| `GET /v1/reports/*` | subject or IP | 5 |
| `POST /v1/files/*` | subject or IP | 10 |

Client IP comes from Vercel's `x-vercel-forwarded-for` / `x-real-ip`, never from `X-Forwarded-For`.

## Rules for contributors

* **SQL**: placeholders only (`%s` / `%(name)s`). No f-strings, `%` or `.format()` with variable data.
  The only interpolations allowed are names bound exclusively to string literals (fixed fragments),
  enforced by `test_t101_no_string_built_sql_in_backend`. Scope-dependent statements (thresholds)
  are fully written-out statements chosen from a closed mapping.
* **Connection string**: `DATABASE_URL` from the environment only (`Settings.database_url`,
  `SecretStr`, TLS required); never built from request data, logged or returned.
* **Headers**: never build links or make access decisions from `Host`, `Referer`, `Origin` or
  `X-Forwarded-*`. Absolute links use configured URLs. Response header values built from data go
  through `safe_header_value` / `content_disposition` (`backend/app/core/validation.py`).
* **No redirects, templates or outbound fetches of user input**: the API returns JSON only (no
  `RedirectResponse`, no HTML, no template engine); outbound HTTP only to the configured Supabase
  base URL with relative paths.
* **Responses**: every route declares a `response_model`; collections use the `Page` envelope
  (`{"items": [...], "next_offset": ...}`), never a top-level array.
* **Verbs**: state changes use POST/PUT/PATCH/DELETE; GET handlers only `select`.
* **Repeated query parameters** must be declared as typed, bounded `list[...]` and added to
  `MULTI_VALUED_QUERY_PARAMS`; otherwise duplicates are refused.

## Frontend obligations (enforced in `frontend/`)

* Render user data only as JSX text: no `dangerouslySetInnerHTML`, `innerHTML`, `insertAdjacentHTML`,
  `document.write`, `eval`, `new Function`, client template compilation; ESLint `no-eval`,
  `no-implied-eval`, `no-new-func`, `react/no-danger`.
* URL-derived values (`location`, hash, `error_description`) shown as mapped, fixed messages or text.
* Post-login `next` targets pass `safeNext()` (same origin, internal path allow-list, no `//`, `\`,
  schemes); Supabase `redirectTo` only from `VITE_APP_URL`; Supabase Redirect URLs allow-list.
* Staff names/e-mails: flag non-ASCII names, show IDN e-mail domains as Punycode.
* Build query strings with `URLSearchParams`; mirror server max lengths in inputs.

## Tests

`backend/tests/test_input_validation.py`, `backend/tests/test_api_security.py` (test names carry the
SD Elements task id, e.g. `test_t74_...`).
