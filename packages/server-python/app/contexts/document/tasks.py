"""Proxy tasks module for autodiscover — re-exports from application layer."""
from app.contexts.document.application.tasks import (
    chunk_document,
    embed_chunks,
    extract_knowledge_graph,
    extract_template,
    index_tsvector,
    parse_document,
)

__all__ = [
    "parse_document",
    "chunk_document",
    "embed_chunks",
    "index_tsvector",
    "extract_template",
    "extract_knowledge_graph",
]
