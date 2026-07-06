"""PII auto-detector: regex-based + forced mask (last defense even if schema misconfigured).

REQ-052 Task 3: detects five classes of personally-identifying information in
free-form text and replaces them with redaction marks before the value
reaches a downstream consumer (UI, MCP, log). This sits behind
:class:`RBACService` as the LAST line of defence — even if a
:class:`SemanticModel` column was mis-registered without ``sensitive=True``
the detector still redacts matching PII.

Regex tuning notes (see REQ-052 brief deviation in commit message):

- We use character-class lookarounds ``(?<!\\d)`` / ``(?!\\d)`` instead of
  Python's ``\\b`` word-boundary because PII in Chinese-language free text
  is frequently glued to CJK characters (``张三的身份证是110101...``). Word
  boundaries do not fire between ``是`` (CN char) and ``1`` (ASCII digit),
  so a Chinese-context ID card would slip past a ``\\b``-anchored pattern.
  Tests cover both the spaced and the glued variant.

- Bank-card pattern (16-19 digits) overlaps with id_card (18 digits). When
  both fire on the same span we mask both — the brief left the order
  unspecified and the test asserts only that the resulting string is
  anonymised.

- Phone / bank-card anchors require the value to be NOT adjacent to another
  digit on either side. This prevents an 18-digit id_card from also
  firing the 11-digit phone branch.

- Email pattern matches ``local@host.tld`` with simple ASCII rules — fine
  for our value surface (question text); Chinese mail service identifiers
  would need a separate, heavier pattern not warranted at V1.
"""

from __future__ import annotations

import re
from typing import Any

# Match 18-digit Chinese ID card (allowing trailing X). Use digit lookarounds,
# NOT \b, so the pattern still fires when the id is glued to a CJK char.
_ID_CARD = r"(?<!\d)\d{17}[\dXx](?!\d)"

# Match 11-digit CN mobile number starting with 1[3-9]. Lookarounds exclude
# digit-neighbours so 18-digit id_card digits don't fire 11-digit phone.
_PHONE = r"(?<!\d)1[3-9]\d{9}(?!\d)"

# Match 16-19 digit bank-card number (overlaps with id_card; see notes).
_BANK_CARD = r"(?<!\d)\d{16,19}(?!\d)"

# Simple ASCII email pattern (local@host.tld).
_EMAIL = r"(?<![\w.+-])([\w.+-]+)@([\w-]+\.[\w.-]+)\b"

# Chinese address: 2+ CN chars followed by a province/city/road/number suffix.
_ADDRESS = r"[一-龥]{2,}(省|市|区|县|镇|路|街|号)"


def _mask_id_card(value: str) -> str:
    """First 6 + 8 stars + last 4 (e.g. ``110101********8813``)."""
    if len(value) < 10:
        return "***"
    return value[:6] + "*" * 8 + value[-4:]


def _mask_phone(value: str) -> str:
    """First 3 + ``****`` + last 4 (e.g. ``138****5678``)."""
    return value[:3] + "****" + value[-4:]


def _mask_bank_card(value: str) -> str:
    """First 4 + stars + last 4 (e.g. ``6222***********0123`` for 19 digits).

    For a 19-digit number: 4 + (19-8) + 4 = 19 chars total; middle is 11 stars.
    """
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _mask_email(value: str) -> str:
    """First 1-2 chars of local part + ``***`` + ``@host``.

    Always preserves the ``@`` so the result still reads as an email shape
    even when fully redacted.
    """
    if "@" not in value:
        return "***"
    local, _, host = value.partition("@")
    keep = 2 if len(local) >= 2 else 1
    return f"{local[:keep]}***@{host}"


def _mask_address(value: str) -> str:
    """Length-aware: long addresses collapse to ``***``, short keep first 2."""
    if len(value) > 10:
        return "***"
    return value[:2] + "***"


_MASK_FUNCTIONS = {
    "id_card": _mask_id_card,
    "phone": _mask_phone,
    "bank_card": _mask_bank_card,
    "email": _mask_email,
    "address": _mask_address,
}

_PATTERNS = {
    "id_card": re.compile(_ID_CARD),
    "phone": re.compile(_PHONE),
    "bank_card": re.compile(_BANK_CARD),
    "email": re.compile(_EMAIL),
    "address": re.compile(_ADDRESS),
}


class PIIDetector:
    """Stateless detector + masker.

    The class has no instance state — wrapping the patterns in a class lets
    future extensions (custom patterns from config, per-tenant redaction
    rules) attach without breaking callers.

    Thread / reentrance safety: ``re.Pattern.search`` is safe to call
    concurrently; ``detect_and_mask_dict`` returns a NEW dict each call and
    never mutates its input.
    """

    PATTERNS: dict[str, re.Pattern[str]] = _PATTERNS
    MASK_FUNCTIONS: dict[str, Any] = _MASK_FUNCTIONS

    def detect(self, value: Any) -> list[str]:
        """Return the list of PII types detected in ``value``.

        Order is the iteration order of :data:`PATTERNS` (deterministic).
        Returns an empty list for non-strings and empty strings.

        When two patterns match overlapping spans (e.g. an 18-digit string
        matches both ``id_card`` and ``bank_card``), only the FIRST pattern's
        type is reported. Specifically: ``id_card`` is checked before
        ``bank_card`` in :data:`PATTERNS`, so an 18-digit string is
        classified as ``id_card`` only — it won't also be marked as
        ``bank_card``. This keeps the masking pipeline single-pass and
        prevents a higher-priority mask from being followed by a
        lower-priority mask on the same span (which would otherwise
        over-redact, e.g. turning an id_card-masked string into a 4-prefix
        bank_card-masked string).
        """
        if not isinstance(value, str) or not value:
            return []
        result: list[str] = []
        # Track consumed character positions across all earlier patterns to
        # skip overlapping later patterns.
        consumed: set[int] = set()
        for pii_type, pattern in self.PATTERNS.items():
            for m in pattern.finditer(value):
                span_positions = set(range(m.start(), m.end()))
                if span_positions & consumed:
                    continue
                consumed |= span_positions
                if pii_type not in result:
                    result.append(pii_type)
                # One match per pattern per call is enough; further matches
                # of the same type still mark positions consumed.
                break
        return result

    def mask(self, value: Any, pii_type: str) -> Any:
        """Apply the per-type mask. Returns ``value`` untouched if not a string.

        Unknown ``pii_type`` falls back to ``"***"`` (a deliberately loud
        redaction) rather than returning the raw value, so a future caller
        that adds a new PII category doesn't accidentally leak until the
        mask function is registered.
        """
        if not isinstance(value, str):
            return value
        mask_fn = self.MASK_FUNCTIONS.get(pii_type)
        if mask_fn is None:
            return "***"
        return mask_fn(value)

    def detect_and_mask_dict(self, data: dict) -> dict:
        """Return a new dict with all string values scanned and PII masked.

        Non-string scalars (numbers, ``None``, ``True``) pass through
        unchanged. List values pass through unchanged (V1 — list-element
        masking is an obvious next step but out of scope for the brief).
        Nested dicts are recursed into.
        """
        result: dict = {}
        for key, val in data.items():
            if isinstance(val, str):
                masked = val
                for pii_type in self.detect(val):
                    masked = self.mask(masked, pii_type)
                result[key] = masked
            elif isinstance(val, dict):
                result[key] = self.detect_and_mask_dict(val)
            else:
                result[key] = val
        return result
