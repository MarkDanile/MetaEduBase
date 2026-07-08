"""Structured data context Pydantic DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# --- Datasets ---


class DatasetCreate(BaseModel):
    name: str
    description: str | None = None
    tags: list[str] | None = None


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    sort_order: int | None = None


class DatasetDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    column_names: list | None
    column_types: list | None
    row_count: int
    source_file: str | None
    tags: list[str] | None
    status: str
    kg_status: str
    sort_order: int
    entity_type: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    # Upload-only: set when entity_type is first occurrence in the catalog.
    # None on all other endpoints (list / get / patch / reinitialize).
    warning: str | None = None

    model_config = {"from_attributes": True}


# --- Dataset Rows ---


class DatasetRowDTO(BaseModel):
    id: UUID
    dataset_id: UUID
    row_index: int
    data: dict
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Tasks ---


class TaskDTO(BaseModel):
    id: UUID
    file_id: UUID | None
    dataset_id: UUID | None
    task_type: str
    status: str
    progress: int
    error_message: str | None
    label: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
