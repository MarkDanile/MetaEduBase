"""Structured data processing Celery tasks — 4-step pipeline.

Pipeline: ds_parse → ds_embed → ds_extract_kg → ds_build_cross_dataset_edges

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-3-backend-tasks-split.md`
拆分自原单文件 `tasks.py`（671 行）。Celery worker 通过 `@shared_task(name=...)` 注册，
本 `__init__.py` 仅 re-export 让既有 import 路径继续工作。
"""

from __future__ import annotations

from .ds_cross_dataset_edges import ds_build_cross_dataset_edges
from .ds_embed import ds_embed
from .ds_extract_kg import ds_extract_kg
from .ds_parse import ds_parse

__all__ = [
    "ds_parse",
    "ds_embed",
    "ds_extract_kg",
    "ds_build_cross_dataset_edges",
]
