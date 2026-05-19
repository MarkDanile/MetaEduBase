from celery import Celery

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

# Manually import all tasks to ensure they are registered
# Document tasks
from app.contexts.document.tasks import (
    parse_document,
    chunk_document,
    embed_chunks,
    index_tsvector,
    extract_template,
    extract_knowledge_graph,
)

# Structured data tasks
from app.contexts.structured_data.tasks import (
    ds_parse,
    ds_embed,
    ds_extract_kg,
    ds_build_cross_dataset_edges,
)
