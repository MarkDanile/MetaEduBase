"""Document context Pydantic DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# --- Folders ---


class FolderCreate(BaseModel):
    name: str
    parent_id: UUID | None = None
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


class FolderMove(BaseModel):
    parent_id: UUID | None = None


class FolderDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    parent_id: UUID | None
    path: str
    sort_order: int
    created_at: datetime
    updated_at: datetime
    children: list[FolderDTO] | None = None

    model_config = {"from_attributes": True}


# --- Files ---


class FileUpdate(BaseModel):
    tags: list[str] | None = None
    doc_type: str | None = None
    folder_id: UUID | None = None


class FileDTO(BaseModel):
    id: UUID
    tenant_id: UUID
    folder_id: UUID | None
    filename: str
    file_type: str
    doc_type: str | None
    file_size: int | None
    tags: list[str] | None
    status: str
    structured_data: dict | None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Chunks ---


class ChunkDTO(BaseModel):
    id: UUID
    file_id: UUID
    chunk_index: int
    content: str
    section_title: str | None
    section_path: str | None
    char_start: int | None
    char_end: int | None
    has_embedding: bool = False
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
