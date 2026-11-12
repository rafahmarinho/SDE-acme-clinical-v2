"""Shared, framework-independent input validation helpers.

Used by the Pydantic schemas (``app.schemas``) and the HTTP guard middleware
(``app.core.middleware``) so every input surface applies the same rules:

* free text: NFC-normalised, no NUL / C0 / C1 controls, bidi overrides, zero-width or other
  invisible formatting characters, no lone surrogates (T34, T127);
* single-line text additionally refuses tabs and line breaks (T34, T39);
* person names: allow-list of letters and a few separators, NFKC-normalised, one script only
  and no stray combining marks, so look-alike (homoglyph) names are refused (T31, T1038);
* identifiers and e-mail addresses that act as security-relevant identities are ASCII only;
* header values refuse CR/LF and other controls even after repeated URL-decoding (T39);
* JSON request bodies must be a single UTF-8 object with bounded nesting depth, no duplicate
  keys and no NaN/Infinity constants (T1148, T1149).
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from urllib.parse import quote, unquote

# NUL and C0 controls except TAB/LF/CR, DEL, C1 controls, zero-width/bidi/invisible format characters, BOM,
# interlinear annotation characters.
FORBIDDEN_TEXT = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​-‏‪-‮⁠-⁤⁦-⁩﻿￹-￻]"
)
LINE_BREAKS = re.compile("[\t\n\r  ]")
HEADER_CONTROL = re.compile("[\x00-\x1f\x7f]")

NAME_SEPARATORS = frozenset(" .'-’")
# Scripts that are legitimately mixed inside one Japanese name are treated as one group.
_SCRIPT_GROUPS = {"HIRAGANA": "CJK", "KATAKANA": "CJK", "CJK": "CJK"}

MAX_JSON_DEPTH = 8


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise ValueError("contains malformed unicode")


def clean_text(value: str) -> str:
    """Multi-line free text (observations, notes): TAB/LF/CR are the only control characters allowed."""
    _reject_surrogates(value)
    value = unicodedata.normalize("NFC", value)
    if FORBIDDEN_TEXT.search(value):
        raise ValueError("contains control or invisible formatting characters")
    return value.strip()


def single_line(value: str) -> str:
    """Single-line text (names, search terms): additionally refuses tabs and line/paragraph separators."""
    value = clean_text(value)
    if LINE_BREAKS.search(value):
        raise ValueError("must be a single line")
    return value


def scripts_of(value: str) -> set[str]:
    """Unicode script (first word of the character name) of every letter in ``value``."""
    scripts: set[str] = set()
    for ch in value:
        if ch.isalpha():
            first = unicodedata.name(ch, "UNKNOWN").split(" ")[0]
            scripts.add(_SCRIPT_GROUPS.get(first, first))
    return scripts


def person_name(value: str) -> str:
    """Staff display names: letters + space . ' - only, one script, no combining marks (anti-homoglyph)."""
    value = unicodedata.normalize("NFKC", single_line(value))
    if not any(ch.isalpha() for ch in value):
        raise ValueError("must contain letters")
    for ch in value:
        if unicodedata.category(ch).startswith("M"):
            raise ValueError("must not contain combining marks")
        if not (ch.isalpha() or ch in NAME_SEPARATORS):
            raise ValueError("may contain only letters, spaces, periods, apostrophes and hyphens")
    if "  " in value:
        raise ValueError("must not contain consecutive spaces")
    if len(scripts_of(value)) > 1:
        raise ValueError("must not mix character sets (for example Latin and Cyrillic)")
    return value


def ascii_identifier(value: str) -> str:
    """Security-relevant codes (serials, bed labels, pseudonyms): printable ASCII only."""
    if not value.isascii() or not value.isprintable():
        raise ValueError("must contain printable ASCII characters only")
    return value


def ascii_email(value: str) -> str:
    """Staff e-mail addresses are identities: refuse internationalised (look-alike) addresses."""
    if not value.isascii():
        raise ValueError("must be an ASCII e-mail address")
    return value.lower()


def safe_header_value(value: str, *, max_decode_rounds: int = 3) -> str:
    """Return ``value`` unchanged if it is safe to place in an HTTP response header, else raise ValueError.

    CR/LF and other control characters are refused, including when hidden behind (multiple) URL
    encodings such as ``%0d%0a``, ``%250A`` or ``%%0A0A``.
    """
    decoded = value
    for _ in range(max_decode_rounds + 1):
        if HEADER_CONTROL.search(decoded):
            raise ValueError("control characters are not allowed in header values")
        nxt = unquote(decoded)
        if nxt == decoded:
            return value
        decoded = nxt
    raise ValueError("header value is encoded too many times")


def safe_filename(name: str | None, *, default: str = "file", max_length: int = 120) -> str:
    """Display-only file name: basename only, no NUL/controls/separators, conservative character set."""
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return base[:max_length] or default


def content_disposition(filename: str, *, disposition: str = "attachment") -> str:
    """RFC 6266 / RFC 5987 Content-Disposition header value built from a sanitised file name."""
    if disposition not in ("attachment", "inline"):
        raise ValueError("unsupported disposition")
    stem = safe_filename(filename, default="download", max_length=80)
    return safe_header_value(f"{disposition}; filename=\"{stem}\"; filename*=UTF-8''{quote(stem)}")


class JsonStructureError(ValueError):
    """The request body is not a well-formed, single JSON object within the structural limits."""


def json_depth_exceeds(raw: str, max_depth: int) -> bool:
    """Linear scan of container nesting (outside strings) so nesting bombs never reach the parser."""
    depth = 0
    in_string = escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
            if depth > max_depth:
                return True
        elif ch in "}]":
            depth -= 1
    return False


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if key in result:
            raise JsonStructureError("duplicate key in JSON object")
        result[key] = val
    return result


def _reject_constant(name: str) -> Any:
    raise JsonStructureError(f"{name} is not valid JSON")


def parse_json_object(raw: bytes, *, max_depth: int = MAX_JSON_DEPTH) -> dict[str, Any]:
    """Strictly parse a JSON request body: UTF-8, one object, bounded depth, unique keys, finite numbers."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonStructureError("request body is not valid UTF-8") from exc
    if json_depth_exceeds(text, max_depth):
        raise JsonStructureError("JSON nesting is too deep")
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicate_keys, parse_constant=_reject_constant)
    except JsonStructureError:
        raise
    except (ValueError, RecursionError) as exc:
        raise JsonStructureError("malformed JSON") from exc
    if not isinstance(value, dict):
        raise JsonStructureError("JSON body must be an object")
    return value
