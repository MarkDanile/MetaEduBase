"""BUG-005: extract_template._update_files_doc_type backfills files rows.

The helper writes `doc_type` + `template_id` in the same transaction as
the structured_data UPDATE in extract_template._do. It must:

1. L1 / L2 / L3 with template_obj present → write `doc_type` + `template_id`.
2. L3 with confidence below threshold (template_obj is None) → skip.
3. layer="none" (template_obj is None) → skip.

Test pattern mirrors test_backfill_file_metadata.py: MagicMock session +
AsyncMock execute, pattern-matching SQL strings to capture UPDATE params.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.contexts.document.application.tasks.extract_template import (
    _update_files_doc_type,
)

pytestmark = pytest.mark.asyncio


def _make_template(template_id: uuid.UUID | None = None) -> MagicMock:
    tpl = MagicMock()
    tpl.id = template_id or uuid.uuid4()
    tpl.name = "人才培养方案"
    return tpl


def _mock_session_capturing_files_updates() -> tuple[MagicMock, list[dict]]:
    """Mock session.execute that captures any UPDATE metaedu.files SET doc_type.

    Returns (session, captured_updates). captured_updates entries are the
    param dicts passed to the matching execute() call.
    """
    captured: list[dict] = []

    async def execute(stmt, params=None):
        stmt_str = str(stmt)
        if "UPDATE metaedu.files" in stmt_str and "doc_type" in stmt_str:
            captured.append(params or {})
        return MagicMock()

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute)
    return session, captured


async def test_l2_hit_backfills_doc_type_and_template_id() -> None:
    """L2 filename substring match: template_obj is set → both fields written."""
    session, captured = _mock_session_capturing_files_updates()
    tpl = _make_template()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, tpl, matched_type="人才培养方案", layer="L2"
    )

    assert len(captured) == 1
    update = captured[0]
    assert update["dt"] == "人才培养方案"
    assert update["tid"] == tpl.id
    assert update["fid"] == file_id


async def test_l1_hit_backfills_doc_type_and_template_id() -> None:
    """L1 exact doc_type match: same backfill behavior as L2."""
    session, captured = _mock_session_capturing_files_updates()
    tpl = _make_template()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, tpl, matched_type="授课计划", layer="L1"
    )

    assert len(captured) == 1
    assert captured[0]["dt"] == "授课计划"
    assert captured[0]["tid"] == tpl.id


async def test_l3_hit_backfills_doc_type_and_template_id() -> None:
    """L3 AI confidence match: same backfill behavior as L1/L2."""
    session, captured = _mock_session_capturing_files_updates()
    tpl = _make_template()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, tpl, matched_type="教案", layer="L3"
    )

    assert len(captured) == 1
    assert captured[0]["dt"] == "教案"
    assert captured[0]["tid"] == tpl.id


async def test_l3_below_threshold_skips_backfill() -> None:
    """L3 with confidence below threshold: template_obj is None → no write."""
    session, captured = _mock_session_capturing_files_updates()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, None, matched_type="授课计划", layer="L3"
    )

    assert captured == []


async def test_layer_none_skips_backfill() -> None:
    """layer=none: template_obj is None → no write (regression lock)."""
    session, captured = _mock_session_capturing_files_updates()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, None, matched_type="", layer="none"
    )

    assert captured == []


async def test_template_id_missing_skips_backfill() -> None:
    """Defensive: template_obj without an `id` attribute → no write.

    Guards against future Template refactors that might drop `.id` —
    the helper should fail safe rather than write a NULL template_id.
    """
    session, captured = _mock_session_capturing_files_updates()
    tpl = MagicMock(spec=[])  # no `id` attribute
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, tpl, matched_type="人才培养方案", layer="L2"
    )

    assert captured == []


async def test_backfill_uses_existing_session_transaction() -> None:
    """The helper does NOT call session.commit() — caller owns the transaction.

    BUG-005 spec requires same-transaction consistency with the
    structured_data UPDATE. A stray session.commit() here would split
    the transaction and risk partial-write visibility.
    """
    session, _ = _mock_session_capturing_files_updates()
    session.commit = AsyncMock()
    tpl = _make_template()
    file_id = uuid.uuid4()

    await _update_files_doc_type(
        session, file_id, tpl, matched_type="人才培养方案", layer="L2"
    )

    session.commit.assert_not_called()
