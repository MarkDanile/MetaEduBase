"""`backfill_file_metadata` 单元测试 — Slice 6.

REQ-010 AC-9 / AC-10：覆盖率统计 + 幂等。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.contexts.document.application.backfill_file_metadata import (
    backfill_file_metadata,
    infer_doc_type,
)


def _mock_session_with_files(files: list[dict]):
    session = MagicMock()
    captured_updates: list[dict] = []

    async def execute(stmt, params=None):
        stmt_str = str(stmt)
        if "SELECT id, filename, file_type" in stmt_str:
            r = MagicMock()
            r.mappings.return_value.all.return_value = files
            return r
        if "UPDATE metaedu.files" in stmt_str:
            captured_updates.append(params)
            return MagicMock()
        return MagicMock()

    session.execute = AsyncMock(side_effect=execute)
    session.commit = AsyncMock()
    return session, captured_updates


async def test_backfill_file_metadata_infers_doc_type_from_file_type() -> None:
    files = [
        {
            "id": uuid.uuid4(),
            "filename": "电路基础.pdf",
            "file_type": "pdf",
            "doc_type": None,
            "tags": [],
        }
    ]
    session, updates = _mock_session_with_files(files)
    stats = await backfill_file_metadata(session, uuid.uuid4())

    assert stats.scanned == 1
    assert stats.updated_doc_type == 1
    assert len(updates) == 1
    assert updates[0]["dt"] == "document"


async def test_backfill_file_metadata_skips_files_with_existing_doc_type() -> None:
    files = [
        {
            "id": uuid.uuid4(),
            "filename": "x.pdf",
            "file_type": "pdf",
            "doc_type": "syllabus",  # already set
            "tags": [],
        }
    ]
    session, updates = _mock_session_with_files(files)
    stats = await backfill_file_metadata(session, uuid.uuid4())

    assert stats.scanned == 1
    assert stats.updated_doc_type == 0
    assert stats.skipped_already_present == 1
    assert len(updates) == 0


async def test_backfill_file_metadata_skips_unknown_file_type() -> None:
    files = [
        {
            "id": uuid.uuid4(),
            "filename": "x.xyz",
            "file_type": "xyz",
            "doc_type": None,
            "tags": [],
        }
    ]
    session, updates = _mock_session_with_files(files)
    stats = await backfill_file_metadata(session, uuid.uuid4())

    assert stats.skipped_already_present == 1
    assert len(updates) == 0


async def test_infer_doc_type() -> None:
    assert infer_doc_type("pdf") == "document"
    assert infer_doc_type("PDF") == "document"
    assert infer_doc_type("docx") == "document"
    assert infer_doc_type("md") == "document"
    assert infer_doc_type("xyz") is None
    assert infer_doc_type(None) is None
    assert infer_doc_type("") is None


async def test_backfill_file_metadata_is_idempotent() -> None:
    """AC-10: 重复执行 → 第二次扫描全是有 doc_type 的文件。"""
    files = [
        {
            "id": uuid.uuid4(),
            "filename": "x.pdf",
            "file_type": "pdf",
            "doc_type": "document",  # already set
            "tags": [],
        }
    ]
    session, updates = _mock_session_with_files(files)
    stats = await backfill_file_metadata(session, uuid.uuid4())

    assert stats.updated_doc_type == 0
    assert stats.skipped_already_present == 1
