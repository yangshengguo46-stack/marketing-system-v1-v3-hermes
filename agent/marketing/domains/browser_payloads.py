"""Decode schema-bound payloads returned through browser MCP wrappers."""

from __future__ import annotations

import json
from typing import Any


def decode_schema_payload(result: Any, schema: str) -> dict[str, Any] | None:
    """Find a schema payload inside nested MCP JSON and text envelopes."""

    return _decode_value(result, schema=schema, depth=0)


def _decode_value(value: Any, *, schema: str, depth: int) -> dict[str, Any] | None:
    if depth > 6:
        return None
    if isinstance(value, dict):
        if value.get("schema") == schema:
            return value
        for nested in value.values():
            decoded = _decode_value(nested, schema=schema, depth=depth + 1)
            if decoded is not None:
                return decoded
        return None
    if isinstance(value, list):
        for nested in value:
            decoded = _decode_value(nested, schema=schema, depth=depth + 1)
            if decoded is not None:
                return decoded
        return None
    if not isinstance(value, str) or schema not in value:
        return None

    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character not in "[{":
            continue
        try:
            nested, _ = decoder.raw_decode(value[index:])
        except ValueError:
            continue
        decoded = _decode_value(nested, schema=schema, depth=depth + 1)
        if decoded is not None:
            return decoded
    return None
