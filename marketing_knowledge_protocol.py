"""Shared wire contract for anonymous Marketing OS knowledge packs."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


PACK_PROTOCOL = "marketing.knowledge-pack.v1"
CONTRIBUTION_PROTOCOL = "marketing.knowledge-contribution.v1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def unsigned_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(pack).items()
        if key not in {"checksum", "signature"}
    }


def pack_checksum(pack: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(unsigned_pack(pack))).hexdigest()


def verify_knowledge_pack(
    pack: Mapping[str, Any], *, public_keys: Mapping[str, bytes | Ed25519PublicKey]
) -> dict[str, Any]:
    value = dict(pack)
    if value.get("protocol") != PACK_PROTOCOL:
        raise ValueError("unsupported knowledge pack protocol")
    checksum = str(value.get("checksum") or "")
    if checksum != pack_checksum(value):
        raise ValueError("knowledge pack checksum mismatch")
    signature = str(value.get("signature") or "")
    try:
        key_id, encoded = signature.split(":", 1)
        raw_signature = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid knowledge pack signature encoding") from exc
    key = public_keys.get(key_id)
    if key is None:
        raise ValueError("knowledge pack signing key is not trusted")
    public_key = key if isinstance(key, Ed25519PublicKey) else Ed25519PublicKey.from_public_bytes(key)
    try:
        public_key.verify(raw_signature, canonical_json(unsigned_pack(value)))
    except InvalidSignature as exc:
        raise ValueError("knowledge pack signature verification failed") from exc
    if int(value.get("sample_size") or 0) < int(value.get("min_cohort_size") or 0):
        raise ValueError("knowledge pack violates minimum cohort size")
    return value
