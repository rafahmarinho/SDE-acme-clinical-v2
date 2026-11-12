"""Outbound HTTP policy (SSRF mitigation, T1365 / T1392).

The API only ever talks to the configured Supabase project (Auth Admin, Storage). Every outbound client
is built here so that:

* the destination comes from ``Settings.supabase_url`` and never from request data;
* ``checked_url`` re-validates it: ``https`` only (plain ``http`` solely for a localhost Supabase in
  development, mirroring ``Settings``), no userinfo, no other host, no metadata / link-local addresses;
* redirects are never followed, TLS certificates are verified and timeouts are short.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings

_LOCAL_DEV_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OutboundURLRejected(ValueError):
    """Raised when a URL is not the configured Supabase origin."""


def _is_internal_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
        or ip.is_unspecified


def checked_url(url: str, settings: Settings | None = None) -> str:
    """Return ``url`` unchanged if it points at the configured Supabase origin, else raise."""
    settings = settings or get_settings()
    allowed = urlsplit(str(settings.supabase_url))
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    local_dev = settings.app_env == "development" and host in _LOCAL_DEV_HOSTS
    if parts.scheme != "https" and not (parts.scheme == "http" and local_dev):
        raise OutboundURLRejected("outbound URL must use https")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise OutboundURLRejected("outbound URL must not carry credentials")
    if not host or host != (allowed.hostname or "").lower() or parts.port != allowed.port:
        raise OutboundURLRejected("outbound URL host is not the configured Supabase project")
    if _is_internal_ip(host) and not local_dev:
        raise OutboundURLRejected("outbound URL resolves to an internal address")
    return url


def supabase_client(timeout: float = 10, settings: Settings | None = None, **kwargs: Any) -> httpx.AsyncClient:
    """HTTP client pinned to the configured Supabase origin (relative request paths only)."""
    settings = settings or get_settings()
    base = str(settings.supabase_url).rstrip("/")
    checked_url(base, settings)  # raises OutboundURLRejected for anything but the configured origin
    return httpx.AsyncClient(base_url=base, verify=True, follow_redirects=False, timeout=timeout, **kwargs)
