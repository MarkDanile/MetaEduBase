"""Proxy tasks module for autodiscover — re-exports from application layer."""
from app.contexts.structured_data.application.tasks import (
    ds_build_cross_dataset_edges,
    ds_embed,
    ds_extract_kg,
    ds_parse,
)

__all__ = [
    "ds_parse",
    "ds_embed",
    "ds_extract_kg",
    "ds_build_cross_dataset_edges",
]
