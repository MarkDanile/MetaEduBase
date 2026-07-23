"""Document context API router — folders, files, chunks, tasks.

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-5-document-router-split.md`
拆分自原单文件（494 行）。子 router 包含到本 router 后由 `app/main.py` 统一挂载到
`/api/v1/document` prefix。

主 router 模块顶层 re-export `parse_document` 仅保留旧 import 兼容；测试必须 patch
实际调用点 `app.contexts.document.interfaces.api.files.parse_document`。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.contexts.document.application.tasks import parse_document

from .chunks import router as chunks_router
from .files import router as files_router
from .folders import router as folders_router
from .tasks import router as tasks_router

router = APIRouter()
router.include_router(folders_router)
router.include_router(files_router)
router.include_router(chunks_router)
router.include_router(tasks_router)

__all__ = ["router", "parse_document"]
