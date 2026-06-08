"""Document processing Celery tasks — 6-step pipeline.

Pipeline: parse → chunk → embed → index_tsv → extract_template → extract_kg

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-3-backend-tasks-split.md`
拆分自原单文件 `tasks.py`（929 行）。Celery worker 通过 `@shared_task(name=...)` 注册，
本 `__init__.py` 仅 re-export 让既有 import 路径继续工作。

历史测试 `tests/contexts/document/test_structured_data_contract.py` 直接 import
`_build_parsed_structured_data` / `_merge_template_structured_data`；这两个 helper
**也**通过 `__init__.py` re-export 保持测试可工作。
"""

from __future__ import annotations

from .chunk import chunk_document
from .embed import embed_chunks
from .extract_knowledge_graph import extract_knowledge_graph
from .extract_template import extract_template
from .extract_template_prompts import (
    _build_parsed_structured_data,
    _merge_template_structured_data,
)
from .index import index_tsvector
from .parse import parse_document

__all__ = [
    "parse_document",
    "chunk_document",
    "embed_chunks",
    "index_tsvector",
    "extract_template",
    "extract_knowledge_graph",
    # Helpers re-exported for backward compatibility with existing tests.
    # New code should import them from `.extract_template_prompts` directly.
    "_build_parsed_structured_data",
    "_merge_template_structured_data",
]
