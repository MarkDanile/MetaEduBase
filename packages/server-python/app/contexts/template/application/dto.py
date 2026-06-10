from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic import Field as PydanticField


class TableColumnDTO(BaseModel):
    key: str
    label: str
    type: Literal["text", "textarea", "number"]
    width: str | None = None

class FieldDTO(BaseModel):
    key: str
    label: str
    type: Literal["text", "textarea", "number", "object", "table", "array"]
    description: str | None = None
    children: list[FieldDTO] = []
    columns: list[TableColumnDTO] = []
    items: list[FieldDTO] = []

class TemplateCreate(BaseModel):
    name: str = PydanticField(..., max_length=100)
    doc_types: list[str]
    fields: list[FieldDTO]
    ai_prompt: str | None = None
    ai_context: str | None = None
    source_file_id: str | None = None

class TemplateUpdate(BaseModel):
    name: str | None = PydanticField(None, max_length=100)
    doc_types: list[str] | None = None
    fields: list[FieldDTO] | None = None
    ai_prompt: str | None = None
    ai_context: str | None = None
    source_file_id: str | None = None
    # REQ-002-4: explicit schema_version bump override
    force_schema_bump: bool = False

class TemplateResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    doc_types: list[str]
    fields: list[FieldDTO]
    ai_prompt: str | None
    ai_context: str | None
    source_file_id: str | None
    created_at: str
    updated_at: str
    # REQ-002-4
    schema_version: int
    is_deprecated: bool
    deprecated_at: str | None
    deprecated_reason: str | None

class TemplateAIInitRequest(BaseModel):
    doc_type: str
    source_file_id: str | None = None
    ai_context: str | None = None

class TemplateAIInitResponse(BaseModel):
    fields: list[FieldDTO]


# REQ-002-2: clone / import / version / export DTOs


class CloneTemplateRequest(BaseModel):
    name: str = PydanticField(..., max_length=100)
    doc_types: list[str]
    source_file_id: str | None = None


class ImportTemplateRequest(BaseModel):
    template: dict
    name_override: str | None = None


class TemplateVersionResponse(BaseModel):
    version_number: int
    name: str
    snapshot_at: str
    schema_version: int
    doc_types: list[str]


class TemplateVersionDetailResponse(BaseModel):
    version_number: int
    name: str
    doc_types: list[str]
    fields: list[FieldDTO]
    ai_prompt: str | None
    ai_context: str | None
    schema_version: int
    snapshot_at: str


class TemplateExportResponse(BaseModel):
    format: str
    template: dict
    schema_version: int
    exported_at: str


# REQ-002-4: deprecation request DTO
class DeprecateTemplateRequest(BaseModel):
    reason: str = PydanticField(..., min_length=1, max_length=500)
