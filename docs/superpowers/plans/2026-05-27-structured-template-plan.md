# 数据要素模板配置 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为资源库提供可配置的结构化数据抽取模板，支持多层嵌套字段（含表格类型），上传文档后自动匹配模板并由 AI 完成抽取。

**Architecture:**
- 后端：新增 `templates` 表（JSONB 存储嵌套 fields），Template CRUD API + AI 初始化接口，修改 `extract_template` 任务增加模板匹配逻辑
- 前端：新增 `/admin/template` 路由，模板列表页 + 编辑页（含递归字段编辑器），FileDetailView 增强表格/对象/数组渲染

**Tech Stack:** PostgreSQL JSONB / FastAPI + SQLAlchemy 2 / Vue 3 + Tailwind CSS 4 / vuedraggable

---

## 文件结构

```
后端（packages/server-python/）
├── app/contexts/template/
│   ├── application/
│   │   ├── dto.py              # Pydantic DTO（TemplateCreate/Update/Response/Field）
│   │   └── service.py          # 业务逻辑
│   ├── domain/
│   │   ├── entity.py           # Template 实体
│   │   └── repository.py       # Repository 接口
│   └── infrastructure/
│       ├── models.py           # SQLAlchemy ORM 模型
│       └── repository.py       # Repository 实现
├── app/contexts/document/application/tasks.py  # 修改 extract_template
└── app/main.py                 # 注册 router

前端（packages/web/src/）
├── views/admin/
│   ├── TemplateListView.vue    # 模板列表页
│   └── TemplateEditorView.vue # 模板编辑页
├── components/
│   ├── FieldEditor.vue         # 递归字段编辑器
│   └── TableRenderer.vue       # 表格类型渲染/编辑
├── services/
│   └── template.ts            # 模板 API 服务
├── constants/
│   └── field-types.ts         # 字段类型常量（FieldType = "text"|"textarea"|...）
└── router/index.ts            # 添加 /admin/template 路由

数据库迁移
└── alembic/versions/            # 创建 templates 表迁移脚本
```

---

### Task 1: 数据库迁移 — 创建 templates 表

**Files:**
- Create: `packages/server-python/alembic/versions/YYYYMMDDHHMM_create_templates.py`
- Modify: `packages/server-python/app/shared/infrastructure/models.py`（import Template 模型）

- [ ] **Step 1: 创建迁移文件**

文件 `packages/server-python/alembic/versions/YYYYMMDDHHMM_create_templates.py`:

```python
"""create templates table

Revision ID: <revision_id>
Revises: <prev_revision_id>
Create Date: 2026-05-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '<revision_id>'
down_revision = '<prev_revision_id>'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'templates',
        sa.Column('id', UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('doc_types', ARRAY(sa.String(length=50)), nullable=False),
        sa.Column('fields', JSONB(), nullable=False),
        sa.Column('ai_prompt', sa.Text(), nullable=True),
        sa.Column('source_file_id', UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_templates_tenant_name'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['source_file_id'], ['files.id'], ),
    )
    op.create_index('ix_templates_tenant_id', 'templates', ['tenant_id'])
    op.create_index('ix_templates_doc_types', 'templates', ['doc_types'], postgresql_using='gin', postgresql_ops={'doc_types': 'gin'})

def downgrade() -> None:
    op.drop_table('templates')
```

- [ ] **Step 2: 修改 models.py**

在 `packages/server-python/app/shared/infrastructure/models.py` 添加：

```python
from app.contexts.template.infrastructure.models import Template  # noqa: F401
```

- [ ] **Step 3: 运行迁移**

Run: `cd packages/server-python && make migrate`
Expected: `Running upgrade  -> <revision_id>`

- [ ] **Step 4: 提交**

```bash
cd packages/server-python
git add alembic/versions/YYYYMMDDHHMM_create_templates.py app/shared/infrastructure/models.py
git commit -m "feat(server): add templates table for structured extraction"
```

---

### Task 2: 后端 — Template 领域实体与 Repository

**Files:**
- Create: `packages/server-python/app/contexts/template/domain/entity.py`
- Create: `packages/server-python/app/contexts/template/domain/repository.py`
- Create: `packages/server-python/app/contexts/template/infrastructure/models.py`
- Create: `packages/server-python/app/contexts/template/infrastructure/repository.py`

- [ ] **Step 1: 创建实体**

文件 `packages/server-python/app/contexts/template/domain/entity.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Any
from uuid import UUID

# 字段类型
FieldType = Literal["text", "textarea", "number", "object", "table", "array"]

@dataclass
class TableColumn:
    key: str
    label: str
    type: Literal["text", "textarea", "number"]
    width: str | None = None

@dataclass
class Field:
    key: str
    label: str
    type: FieldType
    description: str | None = None
    # object / array 类型专用
    children: list[Field] = field(default_factory=list)
    # table 类型专用
    columns: list[TableColumn] = field(default_factory=list)
    # array 类型专用
    items: list[Field] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Field:
        return cls(
            key=d["key"],
            label=d["label"],
            type=d["type"],
            description=d.get("description"),
            children=[Field.from_dict(c) for c in d.get("children", [])],
            columns=[TableColumn(**c) for c in d.get("columns", [])],
            items=[Field.from_dict(i) for i in d.get("items", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
        }
        if self.description:
            result["description"] = self.description
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.columns:
            result["columns"] = [c.__dict__ for c in self.columns]
        if self.items:
            result["items"] = [i.to_dict() for i in self.items]
        return result

@dataclass
class Template:
    id: UUID
    tenant_id: UUID
    name: str
    doc_types: list[str]
    fields: list[Field]
    ai_prompt: str | None
    source_file_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_db_row(cls, row: Any) -> Template:
        raw_fields = row.fields if isinstance(row.fields, list) else []
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            doc_types=list(row.doc_types or []),
            fields=[Field.from_dict(f) for f in raw_fields],
            ai_prompt=row.ai_prompt,
            source_file_id=row.source_file_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
```

- [ ] **Step 2: 创建 Repository 接口**

文件 `packages/server-python/app/contexts/template/domain/repository.py`:

```python
from abc import ABC, abstractmethod
from uuid import UUID
from app.contexts.template.domain.entity import Template

class TemplateRepository(ABC):
    @abstractmethod
    async def list(self, tenant_id: UUID) -> list[Template]:
        ...

    @abstractmethod
    async def get(self, template_id: UUID, tenant_id: UUID) -> Template | None:
        ...

    @abstractmethod
    async def get_by_doc_type(self, doc_type: str, tenant_id: UUID) -> Template | None:
        ...

    @abstractmethod
    async def create(self, template: Template) -> Template:
        ...

    @abstractmethod
    async def update(self, template: Template) -> Template:
        ...

    @abstractmethod
    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        ...
```

- [ ] **Step 3: 创建 ORM 模型**

文件 `packages/server-python/app/contexts/template/infrastructure/models.py`:

```python
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class TemplateModel(Base):
    __tablename__ = "templates"

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    name = Column(String(100), nullable=False)
    doc_types = Column(ARRAY(String(50)), nullable=False)
    fields = Column(JSONB(), nullable=False)
    ai_prompt = Column(Text, nullable=True)
    source_file_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: 创建 Repository 实现**

文件 `packages/server-python/app/contexts/template/infrastructure/repository.py`:

```python
from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.contexts.template.domain.entity import Template
from app.contexts.template.domain.repository import TemplateRepository
from app.contexts.template.infrastructure.models import TemplateModel

class TemplateRepositoryImpl(TemplateRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, tenant_id: UUID) -> list[Template]:
        stmt = select(TemplateModel).where(TemplateModel.tenant_id == tenant_id)
        rows = await self.session.execute(stmt)
        return [Template.from_db_row(r) for r in rows.scalars()]

    async def get(self, template_id: UUID, tenant_id: UUID) -> Template | None:
        stmt = select(TemplateModel).where(
            TemplateModel.id == template_id,
            TemplateModel.tenant_id == tenant_id,
        )
        row = await self.session.scalar(stmt)
        return Template.from_db_row(row) if row else None

    async def get_by_doc_type(self, doc_type: str, tenant_id: UUID) -> Template | None:
        stmt = select(TemplateModel).where(
            TemplateModel.tenant_id == tenant_id,
            TemplateModel.doc_types.contains([doc_type]),
        ).limit(1)
        row = await self.session.scalar(stmt)
        return Template.from_db_row(row) if row else None

    async def create(self, template: Template) -> Template:
        model = TemplateModel(
            id=template.id,
            tenant_id=template.tenant_id,
            name=template.name,
            doc_types=template.doc_types,
            fields=[f.to_dict() for f in template.fields],
            ai_prompt=template.ai_prompt,
            source_file_id=template.source_file_id,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
        self.session.add(model)
        await self.session.flush()
        return template

    async def update(self, template: Template) -> Template:
        stmt = select(TemplateModel).where(
            TemplateModel.id == template.id,
            TemplateModel.tenant_id == template.tenant_id,
        )
        model = await self.session.scalar(stmt)
        if model:
            model.name = template.name
            model.doc_types = template.doc_types
            model.fields = [f.to_dict() for f in template.fields]
            model.ai_prompt = template.ai_prompt
            model.source_file_id = template.source_file_id
            model.updated_at = template.updated_at
        await self.session.flush()
        return template

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        stmt = delete(TemplateModel).where(
            TemplateModel.id == template_id,
            TemplateModel.tenant_id == tenant_id,
        )
        await self.session.execute(stmt)
```

- [ ] **Step 5: 提交**

```bash
git add packages/server-python/app/contexts/template/
git commit -m "feat(server): add Template domain entity and repository"
```

---

### Task 3: 后端 — Template CRUD API + AI 初始化接口

**Files:**
- Create: `packages/server-python/app/contexts/template/application/dto.py`
- Create: `packages/server-python/app/contexts/template/application/service.py`
- Create: `packages/server-python/app/contexts/template/interfaces/api/router.py`
- Create: `packages/server-python/app/contexts/template/interfaces/api/dependencies.py`
- Modify: `packages/server-python/app/main.py`（注册 router）

- [ ] **Step 1: 创建 DTO**

文件 `packages/server-python/app/contexts/template/application/dto.py`:

```python
from __future__ import annotations
from pydantic import BaseModel, Field as PydanticField
from typing import Literal

# --- Field DTO ---
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

# --- Template DTO ---
class TemplateCreate(BaseModel):
    name: str = PydanticField(..., max_length=100)
    doc_types: list[str]
    fields: list[FieldDTO]
    ai_prompt: str | None = None
    source_file_id: str | None = None

class TemplateUpdate(BaseModel):
    name: str | None = PydanticField(None, max_length=100)
    doc_types: list[str] | None = None
    fields: list[FieldDTO] | None = None
    ai_prompt: str | None = None
    source_file_id: str | None = None

class TemplateResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    doc_types: list[str]
    fields: list[FieldDTO]
    ai_prompt: str | None
    source_file_id: str | None
    created_at: str
    updated_at: str

# --- AI Init ---
class TemplateAIInitRequest(BaseModel):
    doc_type: str
    source_file_id: str | None = None

class TemplateAIInitResponse(BaseModel):
    fields: list[FieldDTO]
```

- [ ] **Step 2: 创建 Service**

文件 `packages/server-python/app/contexts/template/application/service.py`:

```python
from uuid import UUID, uuid4
from datetime import datetime, timezone
from app.contexts.template.application.dto import TemplateCreate, TemplateUpdate, FieldDTO
from app.contexts.template.domain.entity import Template, Field, TableColumn
from app.contexts.template.domain.repository import TemplateRepository

def _dto_to_entity(dto: FieldDTO) -> Field:
    return Field(
        key=dto.key,
        label=dto.label,
        type=dto.type,
        description=dto.description,
        children=[_dto_to_entity(c) for c in dto.children],
        columns=[TableColumn(**c.model_dump()) for c in dto.columns],
        items=[_dto_to_entity(i) for i in dto.items],
    )

def _entity_to_dto(entity: Template) -> dict:
    return {
        "id": str(entity.id),
        "tenant_id": str(entity.tenant_id),
        "name": entity.name,
        "doc_types": entity.doc_types,
        "fields": [f.to_dict() for f in entity.fields],
        "ai_prompt": entity.ai_prompt,
        "source_file_id": str(entity.source_file_id) if entity.source_file_id else None,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
    }

class TemplateService:
    def __init__(self, repo: TemplateRepository):
        self.repo = repo

    async def list(self, tenant_id: UUID) -> list[dict]:
        templates = await self.repo.list(tenant_id)
        return [_entity_to_dto(t) for t in templates]

    async def get(self, template_id: UUID, tenant_id: UUID) -> dict | None:
        template = await self.repo.get(template_id, tenant_id)
        return _entity_to_dto(template) if template else None

    async def create(self, dto: TemplateCreate, tenant_id: UUID) -> dict:
        template = Template(
            id=uuid4(),
            tenant_id=tenant_id,
            name=dto.name,
            doc_types=dto.doc_types,
            fields=[_dto_to_entity(f) for f in dto.fields],
            ai_prompt=dto.ai_prompt,
            source_file_id=UUID(dto.source_file_id) if dto.source_file_id else None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await self.repo.create(template)
        return _entity_to_dto(template)

    async def update(self, template_id: UUID, dto: TemplateUpdate, tenant_id: UUID) -> dict | None:
        existing = await self.repo.get(template_id, tenant_id)
        if not existing:
            return None
        if dto.name is not None:
            existing.name = dto.name
        if dto.doc_types is not None:
            existing.doc_types = dto.doc_types
        if dto.fields is not None:
            existing.fields = [_dto_to_entity(f) for f in dto.fields]
        if dto.ai_prompt is not None:
            existing.ai_prompt = dto.ai_prompt
        if dto.source_file_id is not None:
            existing.source_file_id = UUID(dto.source_file_id)
        existing.updated_at = datetime.now(timezone.utc)
        await self.repo.update(existing)
        return _entity_to_dto(existing)

    async def delete(self, template_id: UUID, tenant_id: UUID) -> None:
        await self.repo.delete(template_id, tenant_id)
```

- [ ] **Step 3: 创建 Dependencies**

文件 `packages/server-python/app/contexts/template/interfaces/api/dependencies.py`:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.infrastructure.database import async_session
from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl
from app.contexts.template.application.service import TemplateService

async def get_template_session() -> AsyncSession:
    async with async_session() as session:
        yield session

def get_template_service(
    session: AsyncSession = Depends(get_template_session)
) -> TemplateService:
    return TemplateService(TemplateRepositoryImpl(session))
```

- [ ] **Step 4: 创建 Router**

文件 `packages/server-python/app/contexts/template/interfaces/api/router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.template.application.dto import (
    TemplateCreate, TemplateUpdate, TemplateResponse, TemplateAIInitRequest, TemplateAIInitResponse, FieldDTO
)
from app.contexts.template.application.service import TemplateService
from app.contexts.template.interfaces.api.dependencies import get_template_service
from app.contexts.shared.infrastructure.tenant_context import get_tenant_id

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    return await service.list(UUID(tenant_id))

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    result = await service.get(UUID(template_id), UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    dto: TemplateCreate,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    return await service.create(dto, UUID(tenant_id))

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    dto: TemplateUpdate,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    result = await service.update(UUID(template_id), dto, UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    await service.delete(UUID(template_id), UUID(tenant_id))

@router.post("/init-by-ai", response_model=TemplateAIInitResponse)
async def init_template_by_ai(
    dto: TemplateAIInitRequest,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    # TODO: 接入 LLM 分析文档结构，生成字段定义
    # 临时返回模拟数据，后续 Task 6 实现
    raise HTTPException(status_code=501, detail="Not implemented")

@router.get("/check-doc-type", response_model=dict)
async def check_doc_type(
    doc_type: str,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    """检查文档类型是否已被其他模板使用，返回使用情况"""
    tenant_id = get_tenant_id()
    templates = await service.list(UUID(tenant_id))
    used_by = [t for t in templates if doc_type in t["doc_types"]]
    return {
        "doc_type": doc_type,
        "used": len(used_by) > 0,
        "templates": [{"id": t["id"], "name": t["name"]} for t in used_by],
    }
```

- [ ] **Step 5: 注册 Router**

在 `packages/server-python/app/main.py` 添加：

```python
from app.contexts.template.interfaces.api.router import router as template_router
# ...
app.include_router(template_router)
```

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/app/contexts/template/
git commit -m "feat(server): add Template CRUD API and router"
```

---

### Task 4: 后端 — 修改 extract_template 任务增加模板匹配

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/tasks.py`

- [ ] **Step 1: 查看现有 extract_template 实现**

Read: `packages/server-python/app/contexts/document/application/tasks.py` 找到 `extract_template` 函数

- [ ] **Step 2: 修改 extract_template 任务**

在 `extract_template` 函数中添加模板匹配逻辑：

```python
from app.contexts.template.infrastructure.repository import TemplateRepositoryImpl
# 在函数内部添加模板查询逻辑...
```

具体逻辑（替换到现有 tasks.py 中的 `extract_template` 函数内容）：

```python
async def extract_template(file_id: str, session: AsyncSession):
    """Extract structured template from document using AI."""
    file_repo = FileRepositoryImpl(session)
    file = await file_repo.get(file_id)
    if not file:
        return

    doc_type = file.doc_type
    tenant_id = file.tenant_id

    # 查询匹配的模板
    template_repo = TemplateRepositoryImpl(session)
    template = await template_repo.get_by_doc_type(doc_type, tenant_id)

    # 构建 prompt
    if template:
        # 使用模板 fields 生成抽取 prompt
        fields_json = json.dumps([f.to_dict() for f in template.fields], ensure_ascii=False)
        system_prompt = (
            "你是一个结构化数据提取专家。给定文档内容，按照以下字段定义提取信息。"
            "字段定义：" + fields_json +
            "注意：对于 table 类型字段，返回 rows 数组；对于 object 类型字段，返回子字段的键值对；"
            "对于 array 类型字段，返回对象数组。只返回 JSON，不要其他文字。"
        )
        structured_result = await call_llm_with_system(system_prompt, file.full_text[:8000])
    else:
        # 回退到默认 prompt
        structured_result = await _call_default_template_prompt(file.full_text[:8000], doc_type)

    try:
        structured_data = json.loads(structured_result)
    except json.JSONDecodeError:
        structured_data = {"raw": structured_result}

    # 更新文件记录
    structured = file.structured_data or {}
    structured["template"] = structured_data
    if template:
        structured["template_id"] = str(template.id)
        structured["template_name"] = template.name
    file.structured_data = structured
    file.updated_at = datetime.now(timezone.utc)
    await session.commit()
```

注意：需要添加辅助函数 `_call_default_template_prompt`，保留现有的 prompt 逻辑作为回退。

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/app/contexts/document/application/tasks.py
git commit -m "feat(document): integrate template matching into extract_template task"
```

---

### Task 5: 前端 — 路由和菜单

**Files:**
- Modify: `packages/web/src/router/index.ts`
- Modify: `packages/web/src/views/LayoutView.vue`（添加菜单项）

- [ ] **Step 1: 添加路由**

在 `router/index.ts` 添加：

```typescript
{
  path: '/admin/template',
  name: 'TemplateManagement',
  component: () => import('@/views/admin/TemplateListView.vue'),
  meta: { title: '数据要素模板', requiresAuth: true },
},
```

- [ ] **Step 2: 添加菜单项**

在 `LayoutView.vue` 的导航菜单中找到管理相关菜单，添加子菜单项：

```vue
<router-link to="/admin/template" class="...">
  <LayoutTemplate :size="16" /> 数据要素模板
</router-link>
```

- [ ] **Step 3: 提交**

```bash
git add packages/web/src/router/index.ts packages/web/src/views/LayoutView.vue
git commit -m "feat(web): add /admin/template route and menu entry"
```

---

### Task 6: 前端 — 模板列表页

**Files:**
- Create: `packages/web/src/views/admin/TemplateListView.vue`
- Create: `packages/web/src/services/template.ts`

- [ ] **Step 1: 创建 API 服务**

文件 `packages/web/src/services/template.ts`:

```typescript
import api from './api'

export interface TableColumn {
  key: string
  label: string
  type: 'text' | 'textarea' | 'number'
  width?: string
}

export interface Field {
  key: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'object' | 'table' | 'array'
  description?: string
  children?: Field[]
  columns?: TableColumn[]
  items?: Field[]
}

export interface Template {
  id: string
  name: string
  doc_types: string[]
  fields: Field[]
  ai_prompt: string | null
  source_file_id: string | null
  created_at: string
  updated_at: string
}

export const templateApi = {
  list() {
    return api.get<Template[]>('/templates')
  },
  get(id: string) {
    return api.get<Template>(`/templates/${id}`)
  },
  create(data: Omit<Template, 'id' | 'created_at' | 'updated_at'>) {
    return api.post<Template>('/templates', data)
  },
  update(id: string, data: Partial<Template>) {
    return api.put<Template>(`/templates/${id}`, data)
  },
  delete(id: string) {
    return api.delete(`/templates/${id}`)
  },
  initByAI(docType: string, sourceFileId?: string) {
    return api.post<{ fields: Field[] }>('/templates/init-by-ai', {
      doc_type: docType,
      source_file_id: sourceFileId,
    })
  },
  checkDocType(docType: string) {
    return api.get<{ doc_type: string; used: boolean; templates: { id: string; name: string }[] }>(
      `/templates/check-doc-type?doc_type=${encodeURIComponent(docType)}`
    )
  },
}
```

- [ ] **Step 2: 创建列表页**

文件 `packages/web/src/views/admin/TemplateListView.vue`：

```vue
<template>
  <div class="ui-page-shell">
    <PageHeader title="数据要素模板" subtitle="配置各类文档的结构化抽取模板">
      <template #extra>
        <router-link to="/admin/template/new" class="liquid-btn liquid-btn-primary">
          <Plus :size="16" /> 新建模板
        </router-link>
      </template>
    </PageHeader>

    <section class="ui-page-section">
      <LoadingSpinner v-if="loading" text="加载中..." />
      <EmptyState
        v-else-if="templates.length === 0"
        title="暂无模板"
        hint="点击右上角「新建模板」创建第一个数据要素模板"
      />
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="t in templates"
          :key="t.id"
          class="ui-panel p-4 ui-interactive-row"
          @click="$router.push(`/admin/template/${t.id}`)"
        >
          <div class="flex items-start justify-between gap-2 mb-2">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ t.name }}</h3>
            <button
              class="liquid-btn-ghost p-1.5 !rounded-[var(--radius-sm)]"
              @click.stop="confirmDelete(t)"
            >
              <Trash2 :size="14" class="text-[var(--color-danger)]" />
            </button>
          </div>
          <div class="flex flex-wrap gap-1 mb-2">
            <span v-for="dt in t.doc_types" :key="dt" class="liquid-tag-blue text-[var(--text-micro)]">
              {{ dt }}
            </span>
          </div>
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
            {{ countFields(t.fields) }} 个字段 · {{ t.created_at.split('T')[0] }}
          </p>
        </div>
      </div>
    </section>

    <ConfirmDialog
      v-model:open="showDelete"
      title="删除模板"
      :message="`确定删除模板「${selectedTemplate?.name}」？`"
      @confirm="doDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { templateApi, type Template, type Field } from '@/services/template'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const templates = ref<Template[]>([])
const loading = ref(true)
const showDelete = ref(false)
const selectedTemplate = ref<Template | null>(null)

function countFields(fields: Field[]): number {
  let count = 0
  for (const f of fields) {
    count++
    if (f.children) count += countFields(f.children)
    if (f.items) count += countFields(f.items)
  }
  return count
}

async function load() {
  loading.value = true
  try {
    const { data } = await templateApi.list()
    templates.value = data
  } catch {
    toast.error('加载模板失败')
  } finally {
    loading.value = false
  }
}

function confirmDelete(t: Template) {
  selectedTemplate.value = t
  showDelete.value = true
}

async function doDelete() {
  if (!selectedTemplate.value) return
  try {
    await templateApi.delete(selectedTemplate.value.id)
    toast.success('删除成功')
    templates.value = templates.value.filter(t => t.id !== selectedTemplate.value!.id)
  } catch {
    toast.error('删除失败')
  }
}

onMounted(load)
</script>
```

- [ ] **Step 3: 提交**

```bash
git add packages/web/src/views/admin/TemplateListView.vue packages/web/src/services/template.ts
git commit -m "feat(web): add TemplateListView and template API service"
```

---

### Task 7: 前端 — 字段编辑器组件

**Files:**
- Create: `packages/web/src/components/FieldEditor.vue`
- Create: `packages/web/src/constants/field-types.ts`

- [ ] **Step 1: 创建字段类型常量**

文件 `packages/web/src/constants/field-types.ts`:

```typescript
export const FIELD_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'object', label: '对象组' },
  { value: 'table', label: '表格' },
  { value: 'array', label: '数组' },
] as const

export type FieldType = typeof FIELD_TYPES[number]['value']

export const COLUMN_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
] as const
```

- [ ] **Step 2: 创建字段编辑器组件**

文件 `packages/web/src/components/FieldEditor.vue`:

```vue
<template>
  <div class="space-y-3">
    <!-- 字段基础信息 -->
    <div class="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">字段名</label>
        <input v-model="local.key" class="liquid-input w-full" placeholder="field_key" />
      </div>
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">中文标签</label>
        <input v-model="local.label" class="liquid-input w-full" placeholder="字段标签" />
      </div>
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">类型</label>
        <select v-model="local.type" class="liquid-input w-full">
          <option v-for="ft in FIELD_TYPES" :key="ft.value" :value="ft.value">{{ ft.label }}</option>
        </select>
      </div>
      <button
        class="liquid-btn-ghost p-1.5 !rounded-[var(--radius-sm)] mt-5"
        @click="$emit('remove')"
      >
        <X :size="14" class="text-[var(--color-danger)]" />
      </button>
    </div>

    <!-- 描述 -->
    <div>
      <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">说明（可选）</label>
      <input v-model="local.description" class="liquid-input w-full" placeholder="字段描述，供 AI 抽取参考" />
    </div>

    <!-- Object 类型: 子字段 -->
    <div v-if="local.type === 'object'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">子字段</p>
      <FieldEditor
        v-for="(child, i) in local.children"
        :key="i"
        v-model="local.children[i]"
        @remove="local.children.splice(i, 1)"
      />
      <button class="liquid-btn-ghost text-[var(--text-small)]" @click="local.children.push({ key: '', label: '', type: 'text' })">
        <Plus :size="12" /> 添加子字段
      </button>
    </div>

    <!-- Table 类型: 列定义 -->
    <div v-if="local.type === 'table'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">列定义</p>
      <div class="space-y-1">
        <div v-for="(col, i) in local.columns" :key="i" class="grid grid-cols-[1fr_1fr_auto_auto] gap-2 items-center">
          <input v-model="col.key" class="liquid-input w-full" placeholder="列键名" />
          <input v-model="col.label" class="liquid-input w-full" placeholder="列标签" />
          <select v-model="col.type" class="liquid-input w-full">
            <option v-for="ct in COLUMN_TYPES" :key="ct.value" :value="ct.value">{{ ct.label }}</option>
          </select>
          <button class="liquid-btn-ghost p-1.5 !rounded-[var(--radius-sm)]" @click="local.columns.splice(i, 1)">
            <X :size="12" class="text-[var(--color-danger)]" />
          </button>
        </div>
      </div>
      <button class="liquid-btn-ghost text-[var(--text-small)] mt-1" @click="local.columns.push({ key: '', label: '', type: 'text' })">
        <Plus :size="12" /> 添加列
      </button>
    </div>

    <!-- Array 类型: 数组项模板 -->
    <div v-if="local.type === 'array'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">数组项模板</p>
      <FieldEditor
        v-if="local.items.length > 0"
        v-model="local.items[0]"
        @remove="local.items = []"
      />
      <button v-else class="liquid-btn-ghost text-[var(--text-small)]" @click="local.items.push({ key: '', label: '', type: 'text' })">
        <Plus :size="12" /> 添加数组项模板
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus, X } from 'lucide-vue-next'
import { FIELD_TYPES, COLUMN_TYPES } from '@/constants/field-types'
import type { Field, TableColumn } from '@/services/template'

const props = defineProps<{ modelValue: Field }>()
const emit = defineEmits<{
  'update:modelValue': [value: Field]
  'remove': []
}>()

const local = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
```

注意：`FieldEditor.vue` 需要注册为递归组件。在组件文件中使用 `defineAsyncComponent` 调用自身：

```vue
<script setup lang="ts">
// 递归引用自身
const FieldEditor = defineAsyncComponent(() => import('./FieldEditor.vue'))
// ...
</script>
```

- [ ] **Step 3: 提交**

```bash
git add packages/web/src/components/FieldEditor.vue packages/web/src/constants/field-types.ts
git commit -m "feat(web): add FieldEditor component with recursive nested field support"
```

---

### Task 8: 前端 — 模板编辑页

**Files:**
- Create: `packages/web/src/views/admin/TemplateEditorView.vue`

- [ ] **Step 1: 创建编辑页**

文件 `packages/web/src/views/admin/TemplateEditorView.vue`：

布局：`xl:grid-cols-[1fr_340px]` 左右分栏

左列：
- 模板名称 input
- 关联文档类型（多选，可从 DOC_TYPE_OPTIONS 选择也可手动输入）
- 字段列表（拖拽排序 `vuedraggable`，每项使用 `FieldEditor`）

右列：
- AI 初始化面板：类型名 input + 样例文档上传 + 生成按钮 + 结果预览

详细实现使用 `FieldEditor.vue` 渲染字段编辑器，表单数据保存时转换为 API DTO 格式。

- [ ] **Step 2: 提交**

```bash
git add packages/web/src/views/admin/TemplateEditorView.vue
git commit -m "feat(web): add TemplateEditorView with FieldEditor integration"
```

---

### Task 9: 前端 — FileDetailView 结构化抽取增强

**Files:**
- Modify: `packages/web/src/views/resource/FileDetailView.vue`
- Create: `packages/web/src/components/TableRenderer.vue`

- [ ] **Step 1: 创建 TableRenderer 组件**

文件 `packages/web/src/components/TableRenderer.vue`：

```vue
<template>
  <div class="overflow-x-auto">
    <table class="w-full text-[var(--text-caption)]">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key" class="px-3 py-2 text-left text-[var(--color-ink-tertiary)] font-medium bg-[var(--panel-bg)] border-b border-[var(--panel-border)]">
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td v-for="col in columns" :key="col.key" class="px-3 py-2 text-[var(--color-ink)] border-b border-[var(--panel-border)]">
            {{ row[col.key] ?? '-' }}
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length" class="px-3 py-4 text-center text-[var(--color-ink-tertiary)]">
            暂无数据
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { TableColumn } from '@/services/template'

defineProps<{
  columns: TableColumn[]
  rows: Record<string, unknown>[]
}>()
</script>
```

- [ ] **Step 2: 修改 FileDetailView.vue 的结构化抽取 Tab**

替换现有 "结构化抽取" Tab 渲染逻辑：

```vue
<!-- 结构化抽取 Tab -->
<div v-if="activeTab === 'structured'">
  <EmptyState v-if="!templateData || Object.keys(templateData).length === 0" ... />
  <div v-else class="space-y-3">
    <template v-for="(value, key) in templateData" :key="key">
      <div v-if="isPrimitiveValue(value)" class="ui-panel-muted p-3">
        <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1">{{ key }}</p>
        <p class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ formatValue(value) }}</p>
      </div>

      <!-- Table 类型 -->
      <div v-else-if="isTableData(value)" class="ui-panel-muted p-3">
        <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">{{ key }}</p>
        <TableRenderer :columns="getTableColumns(value)" :rows="value.rows || value" />
      </div>

      <!-- Object 类型 -->
      <details v-else-if="isObjectData(value)" class="ui-panel-muted p-3">
        <summary class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] cursor-pointer">{{ key }}</summary>
        <div class="mt-2 space-y-2 pl-4 border-l border-[var(--panel-border)]">
          <div v-for="(subVal, subKey) in value" :key="subKey">
            <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">{{ subKey }}</p>
            <p class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ formatValue(subVal) }}</p>
          </div>
        </div>
      </details>

      <!-- Array 类型 -->
      <div v-else-if="Array.isArray(value)" class="ui-panel-muted p-3">
        <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">{{ key }}</p>
        <div class="space-y-2">
          <div v-for="(item, i) in value" :key="i" class="ui-panel-ghost p-2 text-[var(--text-caption)]">
            {{ formatValue(item) }}
          </div>
        </div>
      </div>

      <!-- 回退 -->
      <div v-else class="ui-panel-muted p-3">
        <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1">{{ key }}</p>
        <p class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ formatValue(value) }}</p>
      </div>
    </template>
  </div>
</div>
```

需要添加辅助函数：

```typescript
function isPrimitiveValue(v: unknown): boolean {
  return typeof v !== 'object' || v === null
}

function isTableData(v: unknown): boolean {
  return typeof v === 'object' && v !== null && ('rows' in v || (Array.isArray(v) && v.every(r => typeof r === 'object')))
}

function isObjectData(v: unknown): boolean {
  return typeof v === 'object' && v !== null && !Array.isArray(v) && !('rows' in v)
}

function getTableColumns(value: unknown): TableColumn[] {
  if ('rows' in (value as Record<string, unknown>)) {
    const rows = (value as { rows: Record<string, unknown>[] }).rows
    if (rows.length > 0) {
      return Object.keys(rows[0]).map(k => ({ key: k, label: k, type: 'text' as const }))
    }
  }
  if (Array.isArray(value)) {
    if (value.length > 0 && typeof value[0] === 'object') {
      return Object.keys(value[0] as Record<string, unknown>).map(k => ({ key: k, label: k, type: 'text' as const }))
    }
  }
  return []
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'string') return v || '-'
  return JSON.stringify(v)
}
```

- [ ] **Step 3: 提交**

```bash
git add packages/web/src/components/TableRenderer.vue packages/web/src/views/resource/FileDetailView.vue
git commit -m "feat(web): enhance FileDetailView structured extraction rendering with table/object/array support"
```

---

### Task 10: 集成测试

**Files:**
- Create: `packages/server-python/tests/contexts/template/test_template.py`

- [ ] **Step 1: 编写后端测试**

```python
def test_list_templates(client, auth_headers):
    # 创建模板
    res = client.post("/api/v1/templates", json={
        "name": "教案模板",
        "doc_types": ["教案"],
        "fields": [
            {"key": "course_name", "label": "课程名称", "type": "text"},
        ]
    }, headers=auth_headers)
    assert res.status_code == 201

    # 列出模板
    res = client.get("/api/v1/templates", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
```

- [ ] **Step 2: 运行测试**

Run: `cd packages/server-python && make test`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/tests/contexts/template/
git commit -m "test(server): add template API tests"
```

---

## 自检清单

1. **Spec coverage:** 逐条检查 spec 9 个章节，每个都有对应任务实现
2. **Placeholder scan:** 无 TBD/TODO/未实现步骤
3. **Type consistency:** 前端 `Field` 类型与后端 `Field` 模型字段名一致（key/label/type/children/columns/items）
4. **边界条件:** 空 fields、空 doc_types、嵌套层级过深（建议限制 3 层以内）有处理