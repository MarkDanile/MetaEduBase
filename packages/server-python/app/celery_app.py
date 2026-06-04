"""Celery application bootstrap.

Manually import all tasks to ensure they are registered with the worker.

Document tasks
==============
parse_document, chunk_document, embed_chunks, index_tsvector,
extract_template, extract_knowledge_graph

Structured data tasks
=====================
ds_parse, ds_embed, ds_extract_kg, ds_build_cross_dataset_edges
"""
from celery import Celery

from app.contexts.document.tasks import (
    chunk_document,  # noqa: F401  load-bearing: Celery task registration side effect
    embed_chunks,  # noqa: F401  load-bearing: Celery task registration side effect
    extract_knowledge_graph,  # noqa: F401  load-bearing: Celery task registration side effect
    extract_template,  # noqa: F401  load-bearing: Celery task registration side effect
    index_tsvector,  # noqa: F401  load-bearing: Celery task registration side effect
    parse_document,  # noqa: F401  load-bearing: Celery task registration side effect
)
from app.contexts.structured_data.tasks import (
    ds_build_cross_dataset_edges,  # noqa: F401  load-bearing: Celery task registration side effect
    ds_embed,  # noqa: F401  load-bearing: Celery task registration side effect
    ds_extract_kg,  # noqa: F401  load-bearing: Celery task registration side effect
    ds_parse,  # noqa: F401  load-bearing: Celery task registration side effect
)

celery_app = Celery(
    "metaedu",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/2",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
