from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_MAX_SAFE_INTEGER = 2**53 - 1


def _quoted(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("JSON strings must be valid Unicode scalar values") from exc
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be")
    except UnicodeEncodeError as exc:
        raise ValueError("JSON object keys must be valid Unicode") from exc


def _canonicalize(value: Any) -> str:
    """RFC 8785 ordering for the integer-only I-JSON subset used by V1 DTOs."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, int):
        if not -_MAX_SAFE_INTEGER <= value <= _MAX_SAFE_INTEGER:
            raise ValueError("JSON integers must be IEEE-754 safe integers")
        return str(value)
    if isinstance(value, float):
        raise ValueError("floating-point values require a typed canonical schema")
    if isinstance(value, list | tuple):
        return "[" + ",".join(_canonicalize(item) for item in value) + "]"
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(
            f"{_quoted(key)}:{_canonicalize(value[key])}" for key in keys
        ) + "}"
    raise ValueError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return _canonicalize(value).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
