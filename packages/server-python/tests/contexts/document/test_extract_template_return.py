"""TD-061: extract_template must return the extracted-field count.

Follow-up to TD-060 (TD-057 9-task series slice 5).
Same pattern as TD-055/056/057/058/059/060.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.contexts.document.application.tasks.extract_template import extract_template

_TENANT_STR = "00000000-0000-0000-0000-000000000001"
_FID_STR = "12345678-1234-1234-1234-123456789012"


def test_extract_template_returns_field_count() -> None:
    """`extract_template` must return the int that `_do` yields.

    Pre-fix: returned None (asyncio.run's return discarded).
    Post-fix: returns len(template_data) — the field count
    extracted by the LLM.
    """
    with patch("asyncio.run", side_effect=lambda c, r=8: (c.close(), r)[1]):
        result = extract_template(_FID_STR, _TENANT_STR)

    assert result == 8
    assert isinstance(result, int)


def test_extract_template_zero_returns_zero() -> None:
    """When LLM returns no fields (or template_data is empty),
    return 0 (idempotent).
    """
    with patch("asyncio.run", side_effect=lambda c, r=0: (c.close(), r)[1]):
        result = extract_template(_FID_STR, _TENANT_STR)
    assert result == 0
    assert isinstance(result, int)


def test_extract_template_does_not_return_none() -> None:
    """Regression lock against the exact TD-061 bug."""
    for fake_count in (0, 1, 5, 30, 100):
        with patch("asyncio.run", side_effect=lambda c, r=fake_count: (c.close(), r)[1]):
            result = extract_template(_FID_STR, _TENANT_STR)
        assert result is not None
        assert result == fake_count


def test_extract_template_accepts_uuid_strings() -> None:
    parsed_fid = uuid.UUID(_FID_STR)
    parsed_tid = uuid.UUID(_TENANT_STR)
    assert parsed_fid is not None
    assert parsed_tid is not None

    with patch("asyncio.run", side_effect=lambda c, r=42: (c.close(), r)[1]):
        result = extract_template(_FID_STR, _TENANT_STR)
    assert result == 42
