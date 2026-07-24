from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConversationCursor:
    filter_digest: str
    issued_at: datetime
    pinned_sort: datetime
    last_activity_at: datetime
    conversation_id: uuid.UUID


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise InvalidCursorError("invalid cursor encoding") from exc


class ConversationCursorCodec:
    def __init__(self, secret: str):
        if not secret:
            raise ValueError("cursor signing secret must not be empty")
        self._secret = secret.encode("utf-8")

    def encode(self, cursor: ConversationCursor) -> str:
        payload = json.dumps(
            {
                "a": cursor.last_activity_at.isoformat(),
                "f": cursor.filter_digest,
                "i": str(cursor.conversation_id),
                "iat": cursor.issued_at.isoformat(),
                "p": cursor.pinned_sort.isoformat(),
                "v": 1,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_b64encode(payload)}.{_b64encode(signature)}"

    def decode(self, token: str, *, expected_filter_digest: str) -> ConversationCursor:
        try:
            payload_token, signature_token = token.split(".", maxsplit=1)
        except ValueError as exc:
            raise InvalidCursorError("invalid cursor structure") from exc
        payload = _b64decode(payload_token)
        signature = _b64decode(signature_token)
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidCursorError("invalid cursor signature")
        try:
            data = json.loads(payload)
            if data["v"] != 1 or data["f"] != expected_filter_digest:
                raise InvalidCursorError("cursor does not match current filters")
            issued_at = datetime.fromisoformat(data["iat"])
            pinned_sort = datetime.fromisoformat(data["p"])
            last_activity_at = datetime.fromisoformat(data["a"])
            conversation_id = uuid.UUID(data["i"])
            if any(
                value.tzinfo is None
                for value in (issued_at, pinned_sort, last_activity_at)
            ):
                raise InvalidCursorError("cursor timestamps must include timezone")
        except InvalidCursorError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidCursorError("invalid cursor payload") from exc
        return ConversationCursor(
            filter_digest=data["f"],
            issued_at=issued_at,
            pinned_sort=pinned_sort,
            last_activity_at=last_activity_at,
            conversation_id=conversation_id,
        )
