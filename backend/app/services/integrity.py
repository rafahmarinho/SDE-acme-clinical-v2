"""Cryptographic integrity helpers: audit-record signatures and configuration MACs.

* Audit records are signed with ECDSA P-521 / SHA-512 (non-repudiation, T485). The private key
  comes from the AUDIT_SIGNING_KEY environment variable (PEM, never in the repo). If it is not
  set, a deterministic key is derived from the server-only JWT secret with HKDF so every Vercel
  instance signs with the same key; production deployments should set a dedicated key.
* Critical configuration rows (alarm thresholds, simulation state) carry an HMAC-SHA256 written
  only by the backend (T345). The key comes from CONFIG_INTEGRITY_KEY, or is derived (HKDF,
  separate label) from the JWT secret.

The server signature attests the authenticated session (user id, session id, AAL) that performed
the action; user-held signing keys are out of scope for this demo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

log = logging.getLogger("acme.integrity")

SIGNATURE_ALGORITHM = "ECDSA-P521-SHA512"
_CURVE = ec.SECP521R1()


def canonical(record: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding used for signing and MACs."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True).encode()


def _secret_setting(name: str) -> str | None:
    value = getattr(get_settings(), name, None)
    if value is not None and hasattr(value, "get_secret_value"):
        value = value.get_secret_value()
    return value or os.environ.get(name.upper()) or None


def _derive(label: bytes, length: int) -> bytes:
    root = get_settings().supabase_jwt_secret.get_secret_value().encode()
    return HKDF(algorithm=hashes.SHA512(), length=length, salt=b"acme-clinical", info=label).derive(root)


@lru_cache
def _signing_key() -> ec.EllipticCurvePrivateKey:
    pem = _secret_setting("audit_signing_key")
    if pem:
        key = serialization.load_pem_private_key(pem.replace("\\n", "\n").encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != _CURVE.name:
            raise ValueError("AUDIT_SIGNING_KEY must be an EC P-521 private key")
        return key
    log.warning("audit_signing_key_derived", extra={"reason": "AUDIT_SIGNING_KEY not set"})
    # 512 derived bits + 1 is always within [1, n-1] for the P-521 group order (n > 2^520).
    scalar = int.from_bytes(_derive(b"audit-signing-key-v1", 64), "big") + 1
    return ec.derive_private_key(scalar, _CURVE)


def public_key_pem() -> str:
    return _signing_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


@lru_cache
def key_id() -> str:
    der = _signing_key().public_key().public_bytes(serialization.Encoding.DER,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()[:16]


def sign(payload: dict[str, Any]) -> str:
    return base64.b64encode(_signing_key().sign(canonical(payload), ec.ECDSA(hashes.SHA512()))).decode()


def verify(payload: dict[str, Any], signature_b64: str, public_key: ec.EllipticCurvePublicKey | None = None) -> bool:
    pub = public_key or _signing_key().public_key()
    try:
        pub.verify(base64.b64decode(signature_b64, validate=True), canonical(payload), ec.ECDSA(hashes.SHA512()))
        return True
    except (InvalidSignature, ValueError):
        return False


@lru_cache
def _config_key() -> bytes:
    raw = _secret_setting("config_integrity_key")
    if raw:
        return raw.encode()
    return _derive(b"config-integrity-key-v1", 32)


def config_mac(kind: str, payload: dict[str, Any]) -> str:
    return hmac.new(_config_key(), canonical({"kind": kind, "data": payload}), hashlib.sha256).hexdigest()


def config_mac_valid(kind: str, payload: dict[str, Any], mac: str | None) -> bool:
    return bool(mac) and hmac.compare_digest(str(mac), config_mac(kind, payload))
