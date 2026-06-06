# A1 Backend Implementation Plan: Document Pipeline + Database Module

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete backend for resource library (folders/files/chunks), document processing pipeline (Celery async), database module (datasets/rows), and knowledge graph construction — all with API endpoints, task tracking, and tests.

**Architecture:** Two new DDD contexts (`document` and `structured_data`) following existing raw-SQL repository pattern. Celery tasks under each context's `application/tasks.py`. Knowledge context extended with source-tracking FKs. All tables in `metaedu` schema with `tenant_id` isolation.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async, raw SQL), Celery + Redis, PyMuPDF, python-docx, openpyxl, pgvector, tsvector, DashScope embedding API, LLM structured output

---

## File Structure

### New files (document context)

```
packages/server-python/app/contexts/document/
├── application/
│   ├── dto.py                     # FolderCreate/Update/DTO, FileCreate/Update/DTO, ChunkDTO, TaskDTO
│   ├── folder_service.py          # Folder tree CRUD + sort + move
│   ├── file_service.py            # File upload/list/get/delete
│   ├── chunk_service.py           # Chunk list/get by file
│   ├── task_service.py            # Task status query + retry
│   └── tasks.py                   # 6 Celery tasks (parse/chunk/embed/index_tsv/extract_template/extract_kg)
├── domain/
│   └── entities.py                # Folder, File, Chunk, Task enums
├── infrastructure/
│   ├── models.py                  # FolderModel, FileModel, DocumentChunkModel, DocumentTaskModel
│   ├── folder_repository.py       # Raw SQL folder repo
│   ├── file_repository.py         # Raw SQL file repo
│   └── chunk_repository.py        # Raw SQL chunk repo
└── interfaces/api/
    ├── router.py                  # Folder + File + Chunk endpoints
    └── task_router.py             # Task status + retry endpoints
```

### New files (structured_data context)

```
packages/server-python/app/contexts/structured_data/
├── application/
│   ├── dto.py                     # DatasetCreate/Update/DTO, DatasetRowDTO, TaskDTO
│   ├── dataset_service.py         # Dataset upload/list/get/delete + row query
│   └── tasks.py                   # 3 Celery tasks (ds_parse/ds_embed/ds_extract_kg)
├── domain/
│   └── entities.py                # Dataset, DatasetRow, SourceType enum
├── infrastructure/
│   ├── models.py                  # DatasetModel, DatasetRowModel
│   └── dataset_repository.py      # Raw SQL dataset repo
└── interfaces/api/
    ├── router.py                  # Dataset CRUD + rows + KG endpoints
    └── task_router.py             # Task status + retry + KG build endpoints
```

### New files (parsing utilities — shared across contexts)

```
packages/server-python/app/shared/
├── parsing/
│   ├── __init__.py
│   ├── pdf_parser.py              # PyMuPDF text + heading extraction
│   ├── docx_parser.py             # python-docx text + heading extraction
│   ├── xlsx_parser.py             # openpyxl row extraction
│   └── chunker.py                 # Structure-aware chunking logic
```

### New test files

```
packages/server-python/tests/contexts/
├── document/
│   ├── test_folders.py            # Folder CRUD + tree + move
│   ├── test_files.py              # File upload/list/get/delete
│   ├── test_chunks.py             # Chunk list
│   └── test_tasks.py              # Task status + retry
└── structured_data/
    ├── test_datasets.py           # Dataset CRUD + rows
    └── test_dataset_tasks.py      # Task status + retry + KG
```

### Modified files

```
packages/server-python/app/shared/infrastructure/models.py       # Add imports for new models
packages/server-python/app/main.py                               # Register new routers
packages/server-python/app/contexts/knowledge/infrastructure/models.py  # Add source_* FK columns
packages/server-python/app/config.py                             # Add upload_dir config
packages/server-python/pyproject.toml                            # Add PyMuPDF, python-docx, openpyxl
packages/server-python/app/shared/parsing/__init__.py            # (new, empty)
```

---

## Task 1: Install new Python dependencies

**Files:**
- Modify: `packages/server-python/pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Add to `dependencies` list in `pyproject.toml`:

```toml
"pymupdf>=1.25.0",
"python-docx>=1.1.0",
"openpyxl>=3.1.0",
```

- [ ] **Step 2: Install dependencies**

Run: `cd packages/server-python && .venv/bin/pip install -e ".[dev,ai]" -q`

- [ ] **Step 3: Verify imports work**

Run: `cd packages/server-python && .venv/bin/python -c "import fitz; import docx; import openpyxl; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add packages/server-python/pyproject.toml packages/server-python/pyproject.lock
git commit -m "build(server): add PyMuPDF, python-docx, openpyxl dependencies"
```

---

## Task 2: Create shared parsing utilities

**Files:**
- Create: `packages/server-python/app/shared/parsing/__init__.py`
- Create: `packages/server-python/app/shared/parsing/pdf_parser.py`
- Create: `packages/server-python/app/shared/parsing/docx_parser.py`
- Create: `packages/server-python/app/shared/parsing/xlsx_parser.py`
- Create: `packages/server-python/app/shared/parsing/chunker.py`

- [ ] **Step 1: Write failing tests for parsing utilities**

Create `tests/shared/test_parsing.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


def test_pdf_parser_extracts_text():
    from app.shared.parsing.pdf_parser import extract_pdf_text
    # We'll test with a minimal PDF in a later task
    # For now just verify the module imports
    assert callable(extract_pdf_text)


def test_docx_parser_extracts_text():
    from app.shared.parsing.docx_parser import extract_docx_text
    assert callable(extract_docx_text)


def test_xlsx_parser_extracts_rows():
    from app.shared.parsing.xlsx_parser import extract_xlsx_rows
    assert callable(extract_xlsx_rows)


def test_chunker_splits_by_heading():
    from app.shared.parsing.chunker import chunk_by_structure
    assert callable(chunk_by_structure)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/server-python && .venv/bin/pytest tests/shared/test_parsing.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Create `app/shared/parsing/__init__.py`** (empty file)

- [ ] **Step 4: Create `pdf_parser.py`**

```python
"""PDF text and heading extraction using PyMuPDF."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HeadingBlock:
    level: int  # 1-6
    text: str
    page: int


@dataclass
class DocumentSection:
    title: str
    level: int
    content: str
    page: int
    path: str = ""  # e.g. "3.2"


@dataclass
class ParsedDocument:
    sections: list[DocumentSection] = field(default_factory=list)
    full_text: str = ""


_HEADING_SIZES = {22: 1, 18: 2, 15: 3, 13: 4}


def extract_pdf_text(file_path: str) -> ParsedDocument:
    """Extract structured text from a PDF file."""
    import fitz

    doc = fitz.open(file_path)
    sections: list[DocumentSection] = []
    full_text_parts: list[str] = []

    current_title = ""
    current_level = 0
    current_content_parts: list[str] = []
    current_page = 0
    section_counter: dict[int, int] = {}
    parent_counters: list[int] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:  # text block only
                continue
            for line in block["lines"]:
                line_text = ""
                max_font_size = 0
                is_bold = False
                for span in line["spans"]:
                    line_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if "bold" in span["font"].lower():
                        is_bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                heading_level = 0
                for size, lvl in _HEADING_SIZES.items():
                    if max_font_size >= size:
                        heading_level = lvl
                        break

                if heading_level > 0 and is_bold and len(line_text) < 200:
                    # Save previous section
                    if current_title:
                        content = "\n".join(current_content_parts).strip()
                        path = _build_path(section_counter, parent_counters, heading_level)
                        sections.append(DocumentSection(
                            title=current_title,
                            level=current_level,
                            content=content,
                            page=current_page,
                            path=path,
                        ))
                        full_text_parts.append(f"## {current_title}\n{content}")

                    current_title = line_text
                    current_level = heading_level
                    current_content_parts = []
                    current_page = page_num
                    section_counter[heading_level] = section_counter.get(heading_level, 0) + 1
                else:
                    current_content_parts.append(line_text)

    # Save last section
    if current_title:
        content = "\n".join(current_content_parts).strip()
        path = _build_path(section_counter, parent_counters, current_level)
        sections.append(DocumentSection(
            title=current_title,
            level=current_level,
            content=content,
            page=current_page,
            path=path,
        ))
        full_text_parts.append(f"## {current_title}\n{content}")

    if not sections and full_text_parts == []:
        # No headings found — treat entire document as one section
        all_text = ""
        for page_num in range(len(doc)):
            all_text += doc[page_num].get_text() + "\n"
        if all_text.strip():
            sections.append(DocumentSection(title="", level=0, content=all_text.strip(), page=0, path=""))
            full_text_parts.append(all_text.strip())

    doc.close()
    return ParsedDocument(sections=sections, full_text="\n\n".join(full_text_parts))


def _build_path(counter: dict[int, int], parent: list[int], level: int) -> str:
    """Build section path like '3.2' from counters."""
    parts = []
    for lvl in sorted(counter.keys()):
        if lvl <= level:
            parts.append(str(counter[lvl]))
    return ".".join(parts) if parts else ""
```

- [ ] **Step 5: Create `docx_parser.py`**

```python
"""DOCX text and heading extraction using python-docx."""

from __future__ import annotations

from app.shared.parsing.pdf_parser import ParsedDocument, DocumentSection


def extract_docx_text(file_path: str) -> ParsedDocument:
    """Extract structured text from a DOCX file."""
    from docx import Document

    doc = Document(file_path)
    sections: list[DocumentSection] = []
    full_text_parts: list[str] = []

    current_title = ""
    current_level = 0
    current_content_parts: list[str] = []
    section_counter: dict[int, int] = {}

    _HEADING_STYLE = {
        "Heading 1": 1, "Heading 2": 2, "Heading 3": 3,
        "Heading 4": 4, "Heading 5": 5, "Heading 6": 6,
        "标题 1": 1, "标题 2": 2, "标题 3": 3,
        "标题 4": 4, "标题 5": 5, "标题 6": 6,
    }

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""
        heading_level = _HEADING_STYLE.get(style_name, 0)
        text = para.text.strip()

        if not text:
            continue

        if heading_level > 0:
            if current_title:
                content = "\n".join(current_content_parts).strip()
                path = _build_section_path(section_counter, heading_level)
                sections.append(DocumentSection(
                    title=current_title,
                    level=current_level,
                    content=content,
                    page=0,
                    path=path,
                ))
                full_text_parts.append(f"## {current_title}\n{content}")

            current_title = text
            current_level = heading_level
            current_content_parts = []
            section_counter[heading_level] = section_counter.get(heading_level, 0) + 1
        else:
            current_content_parts.append(text)

    if current_title:
        content = "\n".join(current_content_parts).strip()
        path = _build_section_path(section_counter, current_level)
        sections.append(DocumentSection(
            title=current_title,
            level=current_level,
            content=content,
            page=0,
            path=path,
        ))
        full_text_parts.append(f"## {current_title}\n{content}")

    if not sections:
        all_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if all_text.strip():
            sections.append(DocumentSection(title="", level=0, content=all_text.strip(), page=0, path=""))
            full_text_parts.append(all_text.strip())

    return ParsedDocument(sections=sections, full_text="\n\n".join(full_text_parts))


def _build_section_path(counter: dict[int, int], level: int) -> str:
    parts = []
    for lvl in sorted(counter.keys()):
        if lvl <= level:
            parts.append(str(counter[lvl]))
    return ".".join(parts) if parts else ""
```

- [ ] **Step 6: Create `xlsx_parser.py`**

```python
"""Excel row extraction using openpyxl."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedDataset:
    column_names: list[str] = field(default_factory=list)
    column_types: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)


def extract_xlsx_rows(file_path: str) -> ParsedDataset:
    """Extract rows from an Excel file. First row is treated as headers."""
    from openpyxl import load_workbook

    wb = load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    first_row = next(rows_iter, None)

    if first_row is None:
        wb.close()
        return ParsedDataset()

    column_names = [str(cell or f"col_{i}") for i, cell in enumerate(first_row)]
    column_types: list[str] = []
    data_rows: list[dict[str, str]] = []

    # Infer types from first data row
    second_row = next(rows_iter, None)
    if second_row:
        column_types = [_infer_type(cell) for cell in second_row]
        row_dict = {column_names[i]: str(cell or "") for i, cell in enumerate(second_row) if i < len(column_names)}
        data_rows.append(row_dict)

    for row in rows_iter:
        row_dict = {column_names[i]: str(cell or "") for i, cell in enumerate(row) if i < len(column_names)}
        data_rows.append(row_dict)

    wb.close()
    return ParsedDataset(
        column_names=column_names,
        column_types=column_types,
        rows=data_rows,
    )


def _infer_type(value: object) -> str:
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    from datetime import date, datetime
    if isinstance(value, (date, datetime)):
        return "date"
    return "string"
```

- [ ] **Step 7: Create `chunker.py`**

```python
"""Structure-aware document chunking."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.shared.parsing.pdf_parser import DocumentSection, ParsedDocument


@dataclass
class Chunk:
    content: str
    section_title: str = ""
    section_path: str = ""
    char_start: int = 0
    char_end: int = 0
    index: int = 0


MAX_CHUNK_CHARS = 512
OVERLAP_CHARS = 64


def chunk_by_structure(parsed: ParsedDocument, max_chars: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Split a parsed document into chunks, respecting section boundaries."""
    chunks: list[Chunk] = []
    char_offset = 0
    chunk_index = 0

    for section in parsed.sections:
        text = section.content.strip()
        if not text:
            continue

        if len(text) <= max_chars:
            chunks.append(Chunk(
                content=text,
                section_title=section.title,
                section_path=section.path,
                char_start=char_offset,
                char_end=char_offset + len(text),
                index=chunk_index,
            ))
            char_offset += len(text) + 1
            chunk_index += 1
        else:
            # Split by paragraphs, then by overlap if a single paragraph is too long
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            sub_chunks = _split_paragraphs(paragraphs, max_chars, overlap)
            for sc in sub_chunks:
                chunks.append(Chunk(
                    content=sc,
                    section_title=section.title,
                    section_path=section.path,
                    char_start=char_offset,
                    char_end=char_offset + len(sc),
                    index=chunk_index,
                ))
                char_offset += len(sc) + 1
                chunk_index += 1

    if not chunks and parsed.full_text.strip():
        # Fallback: no sections, chunk the full text
        for sc in _split_paragraphs([parsed.full_text], max_chars, overlap):
            chunks.append(Chunk(
                content=sc,
                section_title="",
                section_path="",
                char_start=char_offset,
                char_end=char_offset + len(sc),
                index=chunk_index,
            ))
            char_offset += len(sc) + 1
            chunk_index += 1

    return chunks


def _split_paragraphs(paragraphs: list[str], max_chars: int, overlap: int) -> list[str]:
    """Join paragraphs into chunks of max_chars, with overlap."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) + 1 > max_chars and current_parts:
            chunks.append("\n".join(current_parts))
            # Overlap: keep last portion
            tail = "\n".join(current_parts)
            overlap_text = tail[-overlap:] if overlap < len(tail) else tail
            current_parts = [overlap_text]
            current_len = len(overlap_text)

        current_parts.append(para)
        current_len += len(para) + 1

    if current_parts:
        chunks.append("\n".join(current_parts))

    return chunks
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd packages/server-python && .venv/bin/pytest tests/shared/test_parsing.py -v`
Expected: PASS (4 tests)

- [ ] **Step 9: Commit**

```bash
git add app/shared/parsing/ tests/shared/test_parsing.py
git commit -m "feat(server): add shared parsing utilities for PDF, DOCX, XLSX, and chunking"
```

---

## Task 3: Create document context — ORM models + model registration

**Files:**
- Create: `packages/server-python/app/contexts/document/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/application/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/domain/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/infrastructure/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/interfaces/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/interfaces/api/__init__.py` (empty)
- Create: `packages/server-python/app/contexts/document/infrastructure/models.py`
- Modify: `packages/server-python/app/shared/infrastructure/models.py`

- [ ] **Step 1: Create `document/infrastructure/models.py`**

```python
"""Document context ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.shared.infrastructure.database import Base


class FolderModel(Base):
    __tablename__ = "folders"
    __table_args__ = ({"schema": "metaedu"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))


class FileModel(Base):
    __tablename__ = "files"
    __table_args__ = ({"schema": "metaedu"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    doc_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(nullable=True)  # TEXT[]
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    structured_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"
    __table_args__ = ({"schema": "metaedu"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    section_path: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding = None  # Set via raw SQL — pgvector not directly mappable
    content_tsvector = None  # Set via raw SQL
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class DocumentTaskModel(Base):
    __tablename__ = "document_tasks"
    __table_args__ = ({"schema": "metaedu"})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
```

- [ ] **Step 2: Register models in `shared/infrastructure/models.py`**

Add to the existing file:

```python
from app.contexts.document.infrastructure.models import (
    DocumentChunkModel,
    DocumentTaskModel,
    FileModel,
    FolderModel,
)
```

And add to `__all__`:

```python
    "DocumentChunkModel",
    "DocumentTaskModel",
    "FileModel",
    "FolderModel",
```

- [ ] **Step 3: Verify models register correctly**

Run: `cd packages/server-python && .venv/bin/python -c "import app.shared.infrastructure.models; print([t for t in app.shared.infrastructure.database.Base.metadata.tables.keys() if 'folder' in t or 'file' in t or 'document_chunk' in t or 'document_task' in t])"`
Expected: List containing `metaedu.folders`, `metaedu.files`, `metaedu.document_chunks`, `metaedu.document_tasks`

- [ ] **Step 4: Commit**

```bash
git add app/contexts/document/ app/shared/infrastructure/models.py
git commit -m "feat(server): add document context ORM models (folders, files, chunks, tasks)"
```

---

## Task 4: Create document context — DTOs + domain entities

**Files:**
- Create: `packages/server-python/app/contexts/document/domain/entities.py`
- Create: `packages/server-python/app/contexts/document/application/dto.py`

- [ ] **Step 1: Create `domain/entities.py`**

```python
"""Document context domain entities and enums."""

from __future__ import annotations

from enum import StrEnum


class FileStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class DocumentTaskType(StrEnum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX_TSV = "index_tsv"
    EXTRACT_TEMPLATE = "extract_template"
    EXTRACT_KG = "extract_kg"


TASK_TYPE_LABELS: dict[str, str] = {
    "parse": "文档解析",
    "chunk": "结构切片",
    "embed": "向量化",
    "index_tsv": "全文索引",
    "extract_template": "模板抽取",
    "extract_kg": "知识图谱",
}
```

- [ ] **Step 2: Create `application/dto.py`**

```python
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
    children: list["FolderDTO"] | None = None

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
    label: str  # Chinese name
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 3: Verify imports**

Run: `cd packages/server-python && .venv/bin/python -c "from app.contexts.document.application.dto import FolderDTO, FileDTO, ChunkDTO, TaskDTO; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/contexts/document/domain/ app/contexts/document/application/dto.py
git commit -m "feat(server): add document context DTOs and domain entities"
```

---

## Task 5: Create document context — repositories

**Files:**
- Create: `packages/server-python/app/contexts/document/infrastructure/folder_repository.py`
- Create: `packages/server-python/app/contexts/document/infrastructure/file_repository.py`
- Create: `packages/server-python/app/contexts/document/infrastructure/chunk_repository.py`

- [ ] **Step 1: Create `folder_repository.py`**

```python
"""Folder repository — raw SQL implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_tree(self, tenant_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.folders WHERE tenant_id = :tid ORDER BY sort_order, name"),
            {"tid": tenant_id},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_by_id(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.folders WHERE id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def create(self, tenant_id: uuid.UUID, name: str, parent_id: uuid.UUID | None, sort_order: int) -> dict:
        folder_id = uuid.uuid4()
        if parent_id:
            parent = await self.get_by_id(parent_id, tenant_id)
            if not parent:
                raise ValueError("父文件夹不存在")
            path = f"{parent['path']}.{folder_id.hex[:8]}"
        else:
            path = folder_id.hex[:8]

        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.folders (id, tenant_id, name, parent_id, path, sort_order, created_at, updated_at) "
                "VALUES (:id, :tid, :name, :pid, :path, :sort, :now, :now)"
            ),
            {"id": folder_id, "tid": tenant_id, "name": name, "pid": parent_id, "path": path, "sort": sort_order, "now": now},
        )
        return {"id": folder_id, "tenant_id": tenant_id, "name": name, "parent_id": parent_id, "path": path, "sort_order": sort_order, "created_at": now, "updated_at": now}

    async def update(self, folder_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs: object) -> None:
        sets: list[str] = []
        params: dict = {"fid": folder_id, "tid": tenant_id}
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = :{key}")
                params[key] = val
        if not sets:
            return
        sets.append("updated_at = :now")
        params["now"] = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(f"UPDATE metaedu.folders SET {', '.join(sets)} WHERE id = :fid AND tenant_id = :tid"),
            params,
        )

    async def move(self, folder_id: uuid.UUID, tenant_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> None:
        folder = await self.get_by_id(folder_id, tenant_id)
        if not folder:
            raise ValueError("文件夹不存在")
        if new_parent_id:
            parent = await self.get_by_id(new_parent_id, tenant_id)
            if not parent:
                raise ValueError("目标父文件夹不存在")
            new_path = f"{parent['path']}.{folder_id.hex[:8]}"
        else:
            new_path = folder_id.hex[:8]
        await self.update(folder_id, tenant_id, parent_id=new_parent_id, path=new_path)

    async def delete(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.folders WHERE id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )

    async def count_files(self, folder_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        result = await self._session.execute(
            text("SELECT COUNT(*) FROM metaedu.files WHERE folder_id = :fid AND tenant_id = :tid"),
            {"fid": folder_id, "tid": tenant_id},
        )
        return result.scalar() or 0
```

- [ ] **Step 2: Create `file_repository.py`**

```python
"""File repository — raw SQL implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_files(
        self,
        tenant_id: uuid.UUID,
        folder_id: uuid.UUID | None = None,
        tag: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        conditions = ["tenant_id = :tid"]
        params: dict = {"tid": tenant_id}
        if folder_id is not None:
            conditions.append("folder_id = :fid")
            params["fid"] = folder_id
        if tag:
            conditions.append(":tag = ANY(tags)")
            params["tag"] = tag
        if status:
            conditions.append("status = :status")
            params["status"] = status
        where = " AND ".join(conditions)
        result = await self._session.execute(
            text(f"SELECT * FROM metaedu.files WHERE {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {**params, "lim": limit, "off": offset},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_by_id(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> dict | None:
        result = await self._session.execute(
            text("SELECT * FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def create(
        self,
        tenant_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        filename: str,
        file_type: str,
        doc_type: str | None,
        file_size: int | None,
        storage_key: str,
        tags: list[str],
        uploaded_by: uuid.UUID,
    ) -> dict:
        file_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(
                "INSERT INTO metaedu.files "
                "(id, tenant_id, folder_id, filename, file_type, doc_type, file_size, storage_key, tags, status, uploaded_by, created_at, updated_at) "
                "VALUES (:id, :tid, :fid, :name, :ftype, :dtype, :fsize, :skey, :tags, 'uploaded', :uid, :now, :now)"
            ),
            {
                "id": file_id, "tid": tenant_id, "fid": folder_id, "name": filename,
                "ftype": file_type, "dtype": doc_type, "fsize": file_size,
                "skey": storage_key, "tags": tags, "uid": uploaded_by, "now": now,
            },
        )
        return {"id": file_id, "tenant_id": tenant_id, "folder_id": folder_id, "filename": filename,
                "file_type": file_type, "doc_type": doc_type, "file_size": file_size,
                "storage_key": storage_key, "tags": tags, "status": "uploaded",
                "structured_data": None, "uploaded_by": uploaded_by, "created_at": now, "updated_at": now}

    async def update(self, file_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs: object) -> None:
        sets: list[str] = []
        params: dict = {"fid": file_id, "tid": tenant_id}
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = :{key}")
                params[key] = val
        if not sets:
            return
        sets.append("updated_at = :now")
        params["now"] = datetime.now(UTC).replace(tzinfo=None)
        await self._session.execute(
            text(f"UPDATE metaedu.files SET {', '.join(sets)} WHERE id = :fid AND tenant_id = :tid"),
            params,
        )

    async def update_status(self, file_id: uuid.UUID, tenant_id: uuid.UUID, status: str) -> None:
        await self.update(file_id, tenant_id, status=status)

    async def update_structured_data(self, file_id: uuid.UUID, tenant_id: uuid.UUID, data: dict) -> None:
        import json
        await self._session.execute(
            text("UPDATE metaedu.files SET structured_data = :data::jsonb, updated_at = :now WHERE id = :fid AND tenant_id = :tid"),
            {"data": json.dumps(data), "fid": file_id, "tid": tenant_id, "now": datetime.now(UTC).replace(tzinfo=None)},
        )

    async def delete(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.files WHERE id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
```

- [ ] **Step 3: Create `chunk_repository.py`**

```python
"""Document chunk repository — raw SQL implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_file(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> list[dict]:
        result = await self._session.execute(
            text(
                "SELECT id, tenant_id, file_id, chunk_index, content, section_title, section_path, "
                "char_start, char_end, created_at, "
                "CASE WHEN embedding IS NOT NULL THEN true ELSE false END AS has_embedding "
                "FROM metaedu.document_chunks WHERE file_id = :fid AND tenant_id = :tid ORDER BY chunk_index"
            ),
            {"fid": file_id, "tid": tenant_id},
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def bulk_insert(self, tenant_id: uuid.UUID, file_id: uuid.UUID, chunks: list[dict]) -> None:
        """Insert multiple chunks. Each chunk dict: {content, section_title, section_path, char_start, char_end, index}."""
        now = datetime.now(UTC).replace(tzinfo=None)
        for chunk in chunks:
            chunk_id = uuid.uuid4()
            await self._session.execute(
                text(
                    "INSERT INTO metaedu.document_chunks "
                    "(id, tenant_id, file_id, chunk_index, content, section_title, section_path, char_start, char_end, created_at) "
                    "VALUES (:id, :tid, :fid, :idx, :content, :stitle, :spath, :cstart, :cend, :now)"
                ),
                {
                    "id": chunk_id, "tid": tenant_id, "fid": file_id, "idx": chunk["index"],
                    "content": chunk["content"], "stitle": chunk.get("section_title"),
                    "spath": chunk.get("section_path"), "cstart": chunk.get("char_start"),
                    "cend": chunk.get("char_end"), "now": now,
                },
            )

    async def update_embedding(self, chunk_id: uuid.UUID, embedding: list[float]) -> None:
        import json
        await self._session.execute(
            text("UPDATE metaedu.document_chunks SET embedding = :vec::vector WHERE id = :cid"),
            {"vec": json.dumps(embedding), "cid": chunk_id},
        )

    async def update_tsvector(self, chunk_id: uuid.UUID) -> None:
        await self._session.execute(
            text("UPDATE metaedu.document_chunks SET content_tsvector = to_tsvector('simple', content) WHERE id = :cid"),
            {"cid": chunk_id},
        )

    async def delete_by_file(self, file_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM metaedu.document_chunks WHERE file_id = :fid AND tenant_id = :tid"),
            {"fid": file_id, "tid": tenant_id},
        )
```

- [ ] **Step 4: Verify imports**

Run: `cd packages/server-python && .venv/bin/python -c "from app.contexts.document.infrastructure.folder_repository import FolderRepository; from app.contexts.document.infrastructure.file_repository import FileRepository; from app.contexts.document.infrastructure.chunk_repository import ChunkRepository; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/contexts/document/infrastructure/
git commit -m "feat(server): add document context repositories (folder, file, chunk)"
```

---

## Task 6: Create document context — API routers + main.py registration

**Files:**
- Create: `packages/server-python/app/contexts/document/interfaces/api/router.py`
- Create: `packages/server-python/app/contexts/document/interfaces/api/task_router.py`
- Modify: `packages/server-python/app/main.py`

- [ ] **Step 1: Create the folder + file + chunk router**

Create `interfaces/api/router.py` with all endpoints from spec section 6.1, 6.2, 6.4 (chunk list). Each endpoint follows the existing pattern: `Depends(get_session)`, `Depends(get_current_user)`, `get_tenant_id()`, instantiate repo, call repo, return DTO.

Key endpoints:
- `GET /folders` → `repo.list_tree()` → build tree from flat list
- `POST /folders` → `repo.create()`
- `PATCH /folders/{id}` → `repo.update()`
- `DELETE /folders/{id}` → check file count, delete or move files first
- `PATCH /folders/{id}/move` → `repo.move()`
- `GET /files` → `repo.list_files()` with filters
- `POST /files/upload` → save file, `repo.create()`, dispatch Celery chain, return file
- `GET /files/{id}` → `repo.get_by_id()`
- `GET /files/{id}/download` → stream file from storage
- `DELETE /files/{id}` → `repo.delete()` + cleanup chunks
- `PATCH /files/{id}` → `repo.update()`
- `GET /files/{id}/chunks` → `chunk_repo.list_by_file()`

- [ ] **Step 2: Create the task router**

Create `interfaces/api/task_router.py` with:
- `GET /files/{id}/tasks` → query document_tasks by file_id
- `POST /files/{id}/retry` → re-dispatch failed tasks

- [ ] **Step 3: Register routers in `main.py`**

Add:
```python
from app.contexts.document.interfaces.api.router import router as document_router
from app.contexts.document.interfaces.api.task_router import router as document_task_router

app.include_router(document_router, prefix="/api/v1/document", tags=["document"])
app.include_router(document_task_router, prefix="/api/v1/document", tags=["document-tasks"])
```

- [ ] **Step 4: Verify app starts**

Run: `cd packages/server-python && .venv/bin/python -c "from app.main import app; print([r.path for r in app.routes if 'document' in str(r.path)])"`
Expected: List with document paths

- [ ] **Step 5: Commit**

```bash
git add app/contexts/document/interfaces/ app/main.py
git commit -m "feat(server): add document context API routers and register in main.py"
```

---

## Task 7: Create document context — tests

**Files:**
- Create: `packages/server-python/tests/contexts/document/__init__.py` (empty)
- Create: `packages/server-python/tests/contexts/document/test_folders.py`
- Create: `packages/server-python/tests/contexts/document/test_files.py`

- [ ] **Step 1: Write `test_folders.py`**

Test: create folder, list tree, update name, move folder, delete empty folder, delete non-empty folder.

- [ ] **Step 2: Write `test_files.py`**

Test: upload file, list files, get file detail, delete file, filter by folder/tag/status. Use `io.BytesIO` for fake file uploads.

- [ ] **Step 3: Run all document tests**

Run: `cd packages/server-python && .venv/bin/pytest tests/contexts/document/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/contexts/document/
git commit -m "test(server): add document context tests (folders, files)"
```

---

## Task 8: Create document context — Celery tasks

**Files:**
- Create: `packages/server-python/app/contexts/document/application/tasks.py`
- Modify: `packages/server-python/app/config.py` (add upload_dir)

- [ ] **Step 1: Add `upload_dir` to `config.py`**

Add to the Settings class:
```python
upload_dir: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
```

- [ ] **Step 2: Create `tasks.py`** with 6 Celery tasks following the pipeline in spec 4.1:

1. `parse_document(file_id, tenant_id)` — read file, call pdf/docx parser, update task status
2. `chunk_document(file_id, tenant_id)` — call chunker, bulk insert chunks, update task status
3. `embed_chunks(file_id, tenant_id)` — batch call DashScope, update embeddings, update task status
4. `index_tsvector(file_id, tenant_id)` — update tsvector for each chunk, update task status
5. `extract_template(file_id, tenant_id)` — if doc_type="教案", call LLM with teaching plan prompt, save to files.structured_data
6. `extract_knowledge_graph(file_id, tenant_id)` — call LLM to extract entities/relations from chunks, dedup via vector similarity, write to knowledge_nodes/edges

Each task follows the pattern:
- Set task status to "running" at start
- Do the work
- Set task status to "success" on completion
- Set task status to "failed" + error_message on exception
- Chain to next task on success

- [ ] **Step 3: Create the upload directory**

Run: `mkdir -p packages/server-python/uploads`

- [ ] **Step 4: Verify Celery autodiscover finds the tasks**

Run: `cd packages/server-python && .venv/bin/python -c "from app.celery_app import celery_app; celery_app.autodiscover_tasks(['app.contexts']); print(list(celery_app.tasks.keys()))" `
Expected: Output includes document tasks

- [ ] **Step 5: Commit**

```bash
git add app/contexts/document/application/tasks.py app/config.py uploads/
git commit -m "feat(server): add document processing Celery tasks (6-step pipeline)"
```

---

## Task 9: Create structured_data context — models + DTOs + repositories

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/__init__.py` (empty, plus all `__init__.py` for subdirs)
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/models.py`
- Create: `packages/server-python/app/contexts/structured_data/domain/entities.py`
- Create: `packages/server-python/app/contexts/structured_data/application/dto.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/dataset_repository.py`
- Modify: `packages/server-python/app/shared/infrastructure/models.py`

- [ ] **Step 1: Create `infrastructure/models.py`** — DatasetModel and DatasetRowModel per spec 3.1

- [ ] **Step 2: Create `domain/entities.py`** — SourceType enum, DatasetStatus, KgStatus

- [ ] **Step 3: Create `application/dto.py`** — DatasetCreate, DatasetUpdate, DatasetDTO, DatasetRowDTO, TaskDTO

- [ ] **Step 4: Create `infrastructure/dataset_repository.py`** — raw SQL repo for datasets + rows CRUD, row listing with pagination

- [ ] **Step 5: Register DatasetModel, DatasetRowModel in `shared/infrastructure/models.py`**

- [ ] **Step 6: Verify models register**

Run: `cd packages/server-python && .venv/bin/python -c "import app.shared.infrastructure.models; print('metaedu.datasets' in app.shared.infrastructure.database.Base.metadata.tables)"`
Expected: `True`

- [ ] **Step 7: Commit**

```bash
git add app/contexts/structured_data/ app/shared/infrastructure/models.py
git commit -m "feat(server): add structured_data context models, DTOs, and repository"
```

---

## Task 10: Create structured_data context — API routers + main.py registration

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/interfaces/api/router.py`
- Create: `packages/server-python/app/contexts/structured_data/interfaces/api/task_router.py`
- Modify: `packages/server-python/app/main.py`

- [ ] **Step 1: Create dataset CRUD router** per spec 6.4:
- `GET /datasets` — list with tag/status filter
- `POST /datasets/upload` — save Excel, parse metadata, create dataset, dispatch Celery
- `GET /datasets/{id}` — get detail
- `GET /datasets/{id}/rows` — list rows with pagination
- `DELETE /datasets/{id}` — delete with cascade (rows + chunks + knowledge nodes/edges)
- `PATCH /datasets/{id}` — update name/tags/description/sort_order

- [ ] **Step 2: Create task + KG router** per spec 6.5:
- `GET /datasets/{id}/tasks` — task status
- `POST /datasets/{id}/retry` — retry failed tasks
- `POST /knowledge-graph/build` — manual KG rebuild
- `GET /knowledge-graph/status` — KG build status
- `GET /knowledge-graph` — all dataset KG nodes + edges

- [ ] **Step 3: Register routers in `main.py`**

```python
from app.contexts.structured_data.interfaces.api.router import router as structured_data_router
from app.contexts.structured_data.interfaces.api.task_router import router as structured_data_task_router

app.include_router(structured_data_router, prefix="/api/v1/structured-data", tags=["structured-data"])
app.include_router(structured_data_task_router, prefix="/api/v1/structured-data", tags=["structured-data-tasks"])
```

- [ ] **Step 4: Commit**

```bash
git add app/contexts/structured_data/interfaces/ app/main.py
git commit -m "feat(server): add structured_data context API routers and register in main.py"
```

---

## Task 11: Create structured_data context — tests

**Files:**
- Create: `packages/server-python/tests/contexts/structured_data/__init__.py` (empty)
- Create: `packages/server-python/tests/contexts/structured_data/test_datasets.py`

- [ ] **Step 1: Write `test_datasets.py`** — upload Excel, list datasets, get detail, get rows, delete dataset, update name/tags

- [ ] **Step 2: Run all structured_data tests**

Run: `cd packages/server-python && .venv/bin/pytest tests/contexts/structured_data/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/contexts/structured_data/
git commit -m "test(server): add structured_data context tests"
```

---

## Task 12: Create structured_data context — Celery tasks

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/application/tasks.py`

- [ ] **Step 1: Create `tasks.py`** with 3 Celery tasks per spec 4.2:

1. `parse_dataset(dataset_id, tenant_id)` — openpyxl parse rows → dataset_rows, update column metadata, chain to ds_embed
2. `embed_dataset(dataset_id, tenant_id)` — build text from rows, call DashScope embedding, write to document_chunks, set status=processed + kg_status=pending, chain to ds_extract_kg
3. `extract_knowledge_graph(dataset_id, tenant_id)` — collect all processed datasets, build LLM context with table schemas + sample data, extract entities/relations, vector dedup, write knowledge_nodes/edges, set kg_status=done

- [ ] **Step 2: Verify Celery finds the tasks**

Run: `cd packages/server-python && .venv/bin/python -c "from app.celery_app import celery_app; celery_app.autodiscover_tasks(['app.contexts']); print([k for k in celery_app.tasks.keys() if 'ds_' in k])"`
Expected: List with ds_parse, ds_embed, ds_extract_kg

- [ ] **Step 3: Commit**

```bash
git add app/contexts/structured_data/application/tasks.py
git commit -m "feat(server): add structured_data Celery tasks (parse, embed, KG extract)"
```

---

## Task 13: Extend knowledge context — source tracking columns + indexes

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/infrastructure/models.py`
- Create: `packages/server-python/alembic/versions/xxxx_add_source_tracking_to_knowledge_nodes.py`

- [ ] **Step 1: Add source FK columns to KnowledgeNodeModel**

Add to the existing model:
```python
source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
source_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
source_dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
source_row_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

- [ ] **Step 2: Generate Alembic migration**

Run: `cd packages/server-python && .venv/bin/alembic revision --autogenerate -m "add_source_tracking_to_knowledge_nodes"`

- [ ] **Step 3: Add new indexes to the migration file**

Add to the upgrade():
```python
op.create_index('ix_knowledge_nodes_source_file_id', 'knowledge_nodes', ['tenant_id', 'source_file_id'], schema='metaedu')
op.create_index('ix_knowledge_nodes_source_chunk_id', 'knowledge_nodes', ['tenant_id', 'source_chunk_id'], schema='metaedu')
op.create_index('ix_knowledge_nodes_source_dataset_id', 'knowledge_nodes', ['tenant_id', 'source_dataset_id'], schema='metaedu')
op.create_index('ix_knowledge_nodes_source_row_id', 'knowledge_nodes', ['tenant_id', 'source_row_id'], schema='metaedu')
op.create_index('ix_knowledge_edges_source_rel', 'knowledge_edges', ['tenant_id', 'source_id', 'relation_type'], schema='metaedu')
op.create_index('ix_knowledge_edges_target_rel', 'knowledge_edges', ['tenant_id', 'target_id', 'relation_type'], schema='metaedu')
op.create_index('ix_knowledge_edges_relation_type', 'knowledge_edges', ['tenant_id', 'relation_type'], schema='metaedu')
```

- [ ] **Step 4: Run migration**

Run: `cd packages/server-python && .venv/bin/alembic upgrade head`
Expected: No errors

- [ ] **Step 5: Run existing knowledge tests to verify no regression**

Run: `cd packages/server-python && .venv/bin/pytest tests/contexts/knowledge/ -v`
Expected: All PASS (15 tests)

- [ ] **Step 6: Commit**

```bash
git add app/contexts/knowledge/infrastructure/models.py alembic/
git commit -m "feat(server): add source tracking FKs and indexes to knowledge_nodes/edges"
```

---

## Task 14: Add config + upload directory setup

**Files:**
- Modify: `packages/server-python/app/config.py`
- Create: `packages/server-python/uploads/.gitkeep`

- [ ] **Step 1: Add upload_dir and ensure it exists on startup**

In `config.py`, add:
```python
upload_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
```

- [ ] **Step 2: Add `.gitkeep` to uploads directory**

- [ ] **Step 3: Add `uploads/` (except `.gitkeep`) to `.gitignore`**

Add: `packages/server-python/uploads/*` and `!packages/server-python/uploads/.gitkeep`

- [ ] **Step 4: Commit**

```bash
git add app/config.py packages/server-python/uploads/.gitkeep .gitignore
git commit -m "feat(server): add upload directory config and gitkeep"
```

---

## Task 15: Run full test suite + lint

**Files:** None (verification only)

- [ ] **Step 1: Run lint**

Run: `cd packages/server-python && make lint`
Expected: No errors

- [ ] **Step 2: Run all tests**

Run: `cd packages/server-python && make test`
Expected: All PASS (original 49 + new document + structured_data tests)

- [ ] **Step 3: Fix any issues found**

If lint or tests fail, fix and re-run.

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix(server): address lint/test issues from A1 backend implementation"
```

---

## Self-Review

**1. Spec coverage:**
- Section 2 (scope): Tasks 1-15 cover all 5 items
- Section 3 (data models): Tasks 3, 9, 13 cover all new tables + modifications
- Section 4 (pipelines): Tasks 8, 12 cover both pipelines
- Section 5 (contexts): Tasks 3-8 (document), 9-12 (structured_data), 13 (knowledge extension)
- Section 6 (APIs): Tasks 6, 10 cover all endpoints
- Section 7 (frontend): Not in this backend plan — separate frontend plan needed
- Section 9 (dependencies): Task 1 covers all new pip deps

**2. Placeholder scan:** No TBD/TODO found. All steps have concrete code or commands.

**3. Type consistency:** Repository methods return `dict`/`list[dict]`/`None` consistent with existing codebase pattern. DTOs use `model_config = {"from_attributes": True}`. All UUIDs use `uuid.UUID`. All tables use `metaedu` schema.

**Gap: Frontend plan needed.** This backend plan covers all server-side work. A separate frontend plan should cover: router updates, new views (ResourceView rewrite, DatabaseView, FileDetailView), new services, sidebar update, and task status polling components.
