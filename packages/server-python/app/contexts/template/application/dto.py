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

class TemplateAIInitRequest(BaseModel):
    doc_type: str
    source_file_id: str | None = None

class TemplateAIInitResponse(BaseModel):
    fields: list[FieldDTO]
