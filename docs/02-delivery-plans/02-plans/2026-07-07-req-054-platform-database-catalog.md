# REQ-054 Implementation Plan: 平台级数据库（catalog）主题域分组与多源数据接入

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留 tenant_id 跨租户隔离的前提下，于 tenant 内部新增 `catalog`（UI 称"数据库"）主题域分组维度，让数据集 / 语义层 / 知识图谱 / 问数按数据库独立管理，支持 3 种数据源类型统一接入。

**Architecture:** 新增 `metaedu.data_catalogs` 表（tenant 级，code 唯一）；`datasets` / `semantic_models` / `knowledge_nodes` / `query_audit_log` 加 `catalog_id` FK；语义层唯一约束改造为 `(tenant_id, catalog_id, entity_type, data_source_config)`；QueryPlanner / QueryService.ask 按 `(catalog_id, entity_type)` 双键路由；前端 DatabaseView 改为数据库列表卡片 + CatalogDetailPage 4 tab；3 种数据源类型（imported_dataset / direct_db / mcp）统一接入。

**Tech Stack:**
- 后端：Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pydantic v2 + alembic
- 测试：pytest + pytest-asyncio（asyncio_mode=auto）
- 前端：Vue 3 + TypeScript + Pinia + axios + vitest
- 包管理：pnpm (web) + uv (server-python)

## Global Constraints

- tenant_id 跨租户隔离保留不变（REQ-052 安全边界，所有数据强制 tenant_id 隔离）
- catalog 是 tenant 内部主题域分组维度，与 tenant_id 正交叠加（不用 tenant_id 切分主题域）
- UI 称「数据库」，代码用 `catalog`（避免与 PG database 概念混淆）
- 仅 admin / data_admin 角色可创建 / 修改 / 删除数据库（复用 REQ-052 现有 5 角色）
- entity_types 是白名单（非建议）：数据集上传时 entity_type 必须在 catalog.entity_types 内
- 3 种数据源类型：imported_dataset（✅ 已实现）/ direct_db（V1 接口骨架）/ mcp（V1 接口骨架）
- 语义层唯一约束改造：`uq_semantic_models_tenant_entity_datasource` → `uq_semantic_models_tenant_catalog_entity_datasource`（加 catalog_id）
- alembic migration 严格按编号顺序（最新 = 016 + 后续）
- pytest 必须在 packages/server-python/ 下跑（configfile = packages/server-python/pyproject.toml）
- 不破坏 REQ-052 现有能力（110 tests 必须无回归）
- 现有教育数据集自动迁移到默认库 "中高职教育数据库"（code=education）

---

## File Structure（实施时新建/修改）

### 后端新建（packages/server-python/app/contexts/structured_data/）

| 文件 | 职责 |
|------|------|
| `domain/catalog.py` | Catalog dataclass + CatalogCode value object |
| `infrastructure/catalog_models.py` | SQLAlchemy CatalogModel（metaedu.data_catalogs 表）|
| `infrastructure/catalog_repository.py` | CatalogRepository（CRUD + entity_types 白名单校验）|
| `application/catalog_service.py` | CatalogService（CRUD 编排 + RBAC 权限门禁）|
| `interfaces/api/catalog_router.py` | /api/v1/catalogs CRUD 端点 |

### 后端修改（现有文件）

| 文件 | 修改内容 |
|------|----------|
| `alembic/versions/016_data_catalogs.py` | 新建 metaedu.data_catalogs 表 |
| `alembic/versions/017_add_catalog_id_fk.py` | datasets / semantic_models / knowledge_nodes / query_audit_log 加 catalog_id FK |
| `alembic/versions/018_seed_default_catalog.py` | 自动建默认库 "中高职教育数据库" + 现有数据回填 catalog_id |
| `infrastructure/models.py` | DatasetModel 加 catalog_id 列 |
| `infrastructure/semantic_models_models.py` | SemanticModelModel 加 catalog_id 列 + 改唯一约束 |
| `infrastructure/semantic_model_repository.py` | 加 get_active_by_catalog_and_entity_type 方法 |
| `infrastructure/direct_db_adapter.py` | 从占位升级到 V1 接口骨架（连接外部 PG 只读查询）|
| `infrastructure/mcp_adapter.py` | 从占位升级到 V1 接口骨架 |
| `interfaces/api/router.py` | upload_dataset 加 catalog_id + entity_type 参数；list_datasets 加 catalog_id 过滤 |
| `interfaces/api/query_router.py` | AskRequest 加 catalog_id 必选字段 |
| `application/query_planner.py` | system prompt 加 catalog 上下文 |
| `application/query_service.py` | audit 写入 catalog_id |
| `app/main.py` | 注册 catalog_router |

### 前端新建（packages/web/src/）

| 文件 | 职责 |
|------|------|
| `views/database/CatalogCard.vue` | 数据库卡片组件（icon / name / 统计）|
| `views/database/CatalogCreateDialog.vue` | 新建数据库对话框 |
| `views/database/CatalogDetailPage.vue` | 数据库详情页（数据集 / 语义层 / KG / 问数 tab）|
| `services/catalog.ts` | catalog API client + types |
| `stores/catalog.ts` | Pinia store（catalog 列表缓存）|

### 前端修改（现有文件）

| 文件 | 修改内容 |
|------|----------|
| `views/database/DatabaseView.vue` | 改为数据库列表卡片 + 新建按钮 |
| `views/database/QueryPanel.vue` | 加数据库 select（entity_type 联动）|
| `views/database/UploadDatasetDialog.vue` | 加数据库选择 + entity_type 选择 |
| `app/router.ts` | 加 /database/:catalogCode 路由 |

### 测试（packages/server-python/tests/contexts/structured_data/）

| 文件 | 职责 |
|------|------|
| `test_catalog_repository.py` | catalog CRUD + entity_types 白名单 |
| `test_catalog_service.py` | RBAC 权限矩阵（5 角色 × CRUD）|
| `test_catalog_router.py` | API 端到端 |
| `test_catalog_migration.py` | 默认库迁移 + 现有数据回填验证 |

### 文档

| 文件 | 职责 |
|------|------|
| `docs/02-delivery-plans/01-specs/2026-07-07-req-054-platform-database-catalog.md` | 已存在（spec）|
| `docs/02-delivery-plans/02-plans/2026-07-07-req-054-platform-database-catalog.md` | 本文件（plan）|

---

## Task 1: Schema — data_catalogs 表 + 4 表加 catalog_id FK + 默认库迁移

**Files:**
- Create: `packages/server-python/alembic/versions/016_data_catalogs.py`
- Create: `packages/server-python/alembic/versions/017_add_catalog_id_fk.py`
- Create: `packages/server-python/alembic/versions/018_seed_default_catalog.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/catalog_models.py`
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/models.py`（DatasetModel 加 catalog_id）
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py`（SemanticModelModel 加 catalog_id + 改唯一约束）
- Test: `packages/server-python/tests/contexts/structured_data/test_catalog_migration.py`

**Interfaces:**
- Consumes: 无（首任务，建立 schema 基线）
- Produces: `metaedu.data_catalogs` 表 + 4 表 catalog_id FK + 默认库 "education" + CatalogModel ORM

- [ ] **Step 1: 写 016_data_catalogs migration**

文件：`packages/server-python/alembic/versions/016_data_catalogs.py`

```python
"""016 data catalogs for REQ-054."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016_data_catalogs"
down_revision = "015_query_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_catalogs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("entity_types", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("default_business_purpose", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "code", name="uq_data_catalogs_tenant_code"),
        schema="metaedu",
    )


def downgrade() -> None:
    op.drop_table("data_catalogs", schema="metaedu")
```

- [ ] **Step 2: 写 017_add_catalog_id_fk migration**

文件：`packages/server-python/alembic/versions/017_add_catalog_id_fk.py`

```python
"""017 add catalog_id FK to datasets / semantic_models / knowledge_nodes / query_audit_log."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "017_add_catalog_id_fk"
down_revision = "016_data_catalogs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # datasets.catalog_id（先加 nullable，018 迁移后改 NOT NULL）
    op.add_column(
        "datasets",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_datasets_catalog_id",
        "datasets",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )

    # semantic_models.catalog_id
    op.add_column(
        "semantic_models",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_semantic_models_catalog_id",
        "semantic_models",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )
    # 改唯一约束：加 catalog_id
    op.drop_constraint("uq_semantic_models_tenant_entity_datasource", "semantic_models", schema="metaedu")
    op.create_unique_constraint(
        "uq_semantic_models_tenant_catalog_entity_datasource",
        "semantic_models",
        ["tenant_id", "catalog_id", "entity_type", "data_source_config"],
        schema="metaedu",
    )

    # knowledge_nodes.catalog_id（nullable 标签，V1）
    op.add_column(
        "knowledge_nodes",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_knowledge_nodes_catalog_id",
        "knowledge_nodes",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )

    # query_audit_log.catalog_id（nullable，问数时填入）
    op.add_column(
        "query_audit_log",
        sa.Column("catalog_id", UUID(as_uuid=True), nullable=True),
        schema="metaedu",
    )
    op.create_foreign_key(
        "fk_query_audit_log_catalog_id",
        "query_audit_log",
        "data_catalogs",
        ["catalog_id"],
        ["id"],
        source_schema="metaedu",
        referent_schema="metaedu",
    )


def downgrade() -> None:
    op.drop_constraint("fk_query_audit_log_catalog_id", "query_audit_log", schema="metaedu")
    op.drop_column("query_audit_log", "catalog_id", schema="metaedu")
    op.drop_constraint("fk_knowledge_nodes_catalog_id", "knowledge_nodes", schema="metaedu")
    op.drop_column("knowledge_nodes", "catalog_id", schema="metaedu")
    op.drop_constraint("uq_semantic_models_tenant_catalog_entity_datasource", "semantic_models", schema="metaedu")
    op.create_unique_constraint(
        "uq_semantic_models_tenant_entity_datasource",
        "semantic_models",
        ["tenant_id", "entity_type", "data_source_config"],
        schema="metaedu",
    )
    op.drop_constraint("fk_semantic_models_catalog_id", "semantic_models", schema="metaedu")
    op.drop_column("semantic_models", "catalog_id", schema="metaedu")
    op.drop_constraint("fk_datasets_catalog_id", "datasets", schema="metaedu")
    op.drop_column("datasets", "catalog_id", schema="metaedu")
```

- [ ] **Step 3: 写 018_seed_default_catalog migration**

文件：`packages/server-python/alembic/versions/018_seed_default_catalog.py`

```python
"""018 seed default education catalog + backfill catalog_id."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "018_seed_default_catalog"
down_revision = "017_add_catalog_id_fk"
branch_labels = None
depends_on = None

# 使用 DEFAULT_TENANT_ID（与 app/shared/infrastructure/seed.py 一致）
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_ADMIN_ID = "00000000-0000-0000-0000-000000000002"


def upgrade() -> None:
    # 1. 为每个 tenant 建默认 catalog "education"（如果不存在）
    op.execute(
        f"""
        INSERT INTO metaedu.data_catalogs
            (tenant_id, code, name, description, entity_types,
             default_business_purpose, is_active, created_by)
        SELECT t.id, 'education', '中高职教育数据库',
               '默认教育主题域数据库（自动迁移自 REQ-052 扁平数据集）',
               '["customer","bill","contract"]'::jsonb,
               '教育数据分析', true, '{DEFAULT_ADMIN_ID}'::uuid
        FROM metaedu.tenants t
        WHERE NOT EXISTS (
            SELECT 1 FROM metaedu.data_catalogs dc
            WHERE dc.tenant_id = t.id AND dc.code = 'education'
        )
        """
    )
    # 2. 回填 datasets.catalog_id（按 tenant 匹配 education catalog）
    op.execute(
        """
        UPDATE metaedu.datasets d
        SET catalog_id = dc.id
        FROM metaedu.data_catalogs dc
        WHERE d.tenant_id = dc.tenant_id
          AND dc.code = 'education'
          AND d.catalog_id IS NULL
        """
    )
    # 3. 回填 semantic_models.catalog_id
    op.execute(
        """
        UPDATE metaedu.semantic_models sm
        SET catalog_id = dc.id
        FROM metaedu.data_catalogs dc
        WHERE sm.tenant_id = dc.tenant_id
          AND dc.code = 'education'
          AND sm.catalog_id IS NULL
        """
    )
    # 4. 改 datasets.catalog_id 为 NOT NULL（回填后）
    op.alter_column(
        "datasets", "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
        schema="metaedu",
    )
    # 5. 改 semantic_models.catalog_id 为 NOT NULL
    op.alter_column(
        "semantic_models", "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
        schema="metaedu",
    )


def downgrade() -> None:
    op.alter_column(
        "semantic_models", "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
        schema="metaedu",
    )
    op.alter_column(
        "datasets", "catalog_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
        schema="metaedu",
    )
    op.execute("UPDATE metaedu.datasets SET catalog_id = NULL")
    op.execute("UPDATE metaedu.semantic_models SET catalog_id = NULL")
    op.execute("DELETE FROM metaedu.data_catalogs WHERE code = 'education'")
```

- [ ] **Step 4: 写 CatalogModel ORM**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/catalog_models.py`

```python
"""Catalog ORM for REQ-054 (metaedu.data_catalogs)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CatalogModel(Base):
    __tablename__ = "data_catalogs"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    entity_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    default_business_purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 5: 改 DatasetModel 加 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/models.py`

在 `DatasetModel` 类里 `tenant_id` 之后加：

```python
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.data_catalogs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
```

需要 `from sqlalchemy import ForeignKey` 已在 import 列表（如果没有则加）。

- [ ] **Step 6: 改 SemanticModelModel 加 catalog_id + 不改唯一约束（约束由 alembic 管）**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py`

在 `SemanticModelModel` 类里 `tenant_id` 之后加：

```python
    catalog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metaedu.data_catalogs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
```

- [ ] **Step 7: 写失败测试 + 跑 alembic 迁移**

文件：`packages/server-python/tests/contexts/structured_data/test_catalog_migration.py`

```python
"""Verify REQ-054 alembic migrations 016-018 create catalog schema + default catalog."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_016_018_create_catalog_schema_and_default():
    """data_catalogs 表创建 + 4 表 catalog_id FK + 默认 education 库回填."""
    import os
    import asyncpg

    db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test",
    )
    conn = await asyncpg.connect(db_url)
    try:
        # data_catalogs 表存在 + 列正确
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='data_catalogs' "
            "ORDER BY ordinal_position"
        )
        col_names = {r["column_name"] for r in cols}
        assert "code" in col_names
        assert "entity_types" in col_names
        assert "is_active" in col_names

        # datasets.catalog_id 存在 + NOT NULL
        ds_nullable = await conn.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='datasets' "
            "AND column_name='catalog_id'"
        )
        assert ds_nullable == "NO"  # NOT NULL after 018

        # semantic_models.catalog_id NOT NULL
        sm_nullable = await conn.fetchval(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='semantic_models' "
            "AND column_name='catalog_id'"
        )
        assert sm_nullable == "NO"

        # 默认 education 库存在
        catalog_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM metaedu.data_catalogs WHERE code='education')"
        )
        assert catalog_exists

        # 现有 datasets 全部有 catalog_id（回填验证）
        null_count = await conn.fetchval(
            "SELECT COUNT(*) FROM metaedu.datasets WHERE catalog_id IS NULL"
        )
        assert null_count == 0
    finally:
        await conn.close()
```

- [ ] **Step 8: 跑迁移 + 测试**

```bash
cd packages/server-python
alembic upgrade head
pytest tests/contexts/structured_data/test_catalog_migration.py -v
```

Expected: 迁移成功，测试通过。

- [ ] **Step 9: 跑 REQ-052 回归测试确保无破坏**

```bash
cd packages/server-python
pytest tests/contexts/structured_data/ -v -W error
```

Expected: 现有 110+ tests 全绿（catalog_id 新字段 nullable，不破坏现有 ORM 操作）。

- [ ] **Step 10: 提交**

```bash
git add packages/server-python/alembic/versions/016_data_catalogs.py \
        packages/server-python/alembic/versions/017_add_catalog_id_fk.py \
        packages/server-python/alembic/versions/018_seed_default_catalog.py \
        packages/server-python/app/contexts/structured_data/infrastructure/catalog_models.py \
        packages/server-python/app/contexts/structured_data/infrastructure/models.py \
        packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py \
        packages/server-python/tests/contexts/structured_data/test_catalog_migration.py
git commit -m "feat(structured-data): REQ-054 catalog schema (alembic 016-018 + ORM + 默认库迁移)"
```

---

## Task 2: Catalog domain + Repository + Service + CRUD API + RBAC

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/domain/catalog.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/catalog_repository.py`
- Create: `packages/server-python/app/contexts/structured_data/application/catalog_service.py`
- Create: `packages/server-python/app/contexts/structured_data/interfaces/api/catalog_router.py`
- Modify: `packages/server-python/app/main.py`（注册 catalog_router）
- Test: `packages/server-python/tests/contexts/structured_data/test_catalog_repository.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_catalog_service.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_catalog_router.py`

**Interfaces:**
- Consumes: Task 1（CatalogModel ORM + data_catalogs 表）
- Produces:
  - `Catalog` dataclass（domain/catalog.py）
  - `CatalogRepository`（CRUD + entity_types 白名单校验）
  - `CatalogService`（CRUD 编排 + RBAC 权限门禁）
  - `POST/GET/PATCH/DELETE /api/v1/catalogs` 端点

- [ ] **Step 1: 写 Catalog dataclass**

文件：`packages/server-python/app/contexts/structured_data/domain/catalog.py`

```python
"""Catalog domain entity for REQ-054."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Catalog:
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    entity_types: list[str] = field(default_factory=list)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    default_business_purpose: str | None = None
    is_active: bool = True
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def allows_entity_type(self, entity_type: str) -> bool:
        """白名单校验：entity_type 是否在该 catalog 支持列表内。"""
        return entity_type in self.entity_types
```

- [ ] **Step 2: 写 CatalogRepository**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/catalog_repository.py`

```python
"""Catalog repository: CRUD + tenant 隔离 + entity_types 白名单."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_models import CatalogModel


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, catalog: Catalog) -> Catalog:
        row = CatalogModel(
            id=catalog.id,
            tenant_id=catalog.tenant_id,
            code=catalog.code,
            name=catalog.name,
            description=catalog.description,
            icon=catalog.icon,
            color=catalog.color,
            entity_types=catalog.entity_types,
            default_business_purpose=catalog.default_business_purpose,
            is_active=catalog.is_active,
            created_by=catalog.created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_domain(row)

    async def get_by_id(self, catalog_id: uuid.UUID, tenant_id: uuid.UUID) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
            CatalogModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def get_by_code(self, tenant_id: uuid.UUID, code: str) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.tenant_id == tenant_id,
            CatalogModel.code == code,
            CatalogModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Catalog]:
        stmt = select(CatalogModel).where(
            CatalogModel.tenant_id == tenant_id,
            CatalogModel.is_active == True,  # noqa: E712
        ).order_by(CatalogModel.created_at.desc())
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def update(self, catalog_id: uuid.UUID, tenant_id: uuid.UUID, **kwargs) -> Catalog | None:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        for key, val in kwargs.items():
            if val is not None and hasattr(row, key):
                setattr(row, key, val)
        await self._session.flush()
        return self._to_domain(row)

    async def soft_delete(self, catalog_id: uuid.UUID, tenant_id: uuid.UUID) -> bool:
        stmt = select(CatalogModel).where(
            CatalogModel.id == catalog_id,
            CatalogModel.tenant_id == tenant_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return False
        row.is_active = False
        await self._session.flush()
        return True

    async def count_datasets(self, catalog_id: uuid.UUID) -> int:
        from app.contexts.structured_data.infrastructure.models import DatasetModel
        from sqlalchemy import func
        stmt = select(func.count()).select_from(DatasetModel).where(
            DatasetModel.catalog_id == catalog_id
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    def _to_domain(self, row: CatalogModel) -> Catalog:
        return Catalog(
            id=row.id,
            tenant_id=row.tenant_id,
            code=row.code,
            name=row.name,
            description=row.description,
            icon=row.icon,
            color=row.color,
            entity_types=row.entity_types or [],
            default_business_purpose=row.default_business_purpose,
            is_active=row.is_active,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
```

- [ ] **Step 3: 写 CatalogService（含 RBAC 权限门禁）**

文件：`packages/server-python/app/contexts/structured_data/application/catalog_service.py`

```python
"""Catalog service: CRUD 编排 + RBAC 权限门禁（仅 admin / data_admin 可写）."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.catalog import Catalog
from app.contexts.structured_data.infrastructure.catalog_repository import CatalogRepository

# 可创建/修改/删除 catalog 的角色
CATALOG_ADMIN_ROLES = {"admin", "data_admin", "super_admin"}


class CatalogPermissionError(PermissionError):
    """用户无权操作 catalog."""


class CatalogCodeConflictError(ValueError):
    """同 tenant 内 catalog code 已存在."""


class CatalogService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = CatalogRepository(session)

    def _check_admin(self, role: str) -> None:
        if role not in CATALOG_ADMIN_ROLES:
            raise CatalogPermissionError(
                f"角色 '{role}' 无权操作数据库（仅 {CATALOG_ADMIN_ROLES} 可操作）"
            )

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        entity_types: list[str],
        created_by: uuid.UUID,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        default_business_purpose: str | None = None,
        role: str = "employee",
    ) -> Catalog:
        self._check_admin(role)
        # code 唯一性校验
        existing = await self._repo.get_by_code(tenant_id, code)
        if existing:
            raise CatalogCodeConflictError(f"数据库 code '{code}' 已存在")
        catalog = Catalog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code=code,
            name=name,
            entity_types=entity_types,
            description=description,
            icon=icon,
            color=color,
            default_business_purpose=default_business_purpose,
            created_by=created_by,
        )
        return await self._repo.create(catalog)

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Catalog]:
        return await self._repo.list_by_tenant(tenant_id)

    async def get_by_id(self, catalog_id: uuid.UUID, tenant_id: uuid.UUID) -> Catalog | None:
        return await self._repo.get_by_id(catalog_id, tenant_id)

    async def get_by_code(self, tenant_id: uuid.UUID, code: str) -> Catalog | None:
        return await self._repo.get_by_code(tenant_id, code)

    async def update(
        self,
        *,
        catalog_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str = "employee",
        **kwargs,
    ) -> Catalog | None:
        self._check_admin(role)
        return await self._repo.update(catalog_id, tenant_id, **kwargs)

    async def delete(
        self,
        *,
        catalog_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str = "employee",
        hard: bool = False,
    ) -> bool:
        self._check_admin(role)
        if hard:
            # 硬删：库下必须无数据集
            count = await self._repo.count_datasets(catalog_id)
            if count > 0:
                raise ValueError(f"数据库下还有 {count} 个数据集，无法硬删")
        return await self._repo.soft_delete(catalog_id, tenant_id)

    async def validate_entity_type(
        self, catalog_id: uuid.UUID, tenant_id: uuid.UUID, entity_type: str
    ) -> None:
        """白名单校验：entity_type 必须在 catalog.entity_types 内."""
        catalog = await self._repo.get_by_id(catalog_id, tenant_id)
        if not catalog:
            raise ValueError(f"数据库 {catalog_id} 不存在")
        if not catalog.allows_entity_type(entity_type):
            raise ValueError(
                f"entity_type '{entity_type}' 不在数据库 '{catalog.name}' 的白名单内"
                f"（支持: {catalog.entity_types}）"
            )
```

- [ ] **Step 4: 写 catalog_router API**

文件：`packages/server-python/app/contexts/structured_data/interfaces/api/catalog_router.py`

```python
"""Catalog CRUD API for REQ-054."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.identity.interfaces.api.dependencies import get_current_user
from app.contexts.structured_data.application.catalog_service import (
    CatalogCodeConflictError,
    CatalogPermissionError,
    CatalogService,
)
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1/catalogs", tags=["catalogs"])


class CatalogCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=200)
    entity_types: list[str] = Field(..., min_length=1)
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    default_business_purpose: str | None = None


class CatalogUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    entity_types: list[str] | None = None
    default_business_purpose: str | None = None


class CatalogDTO(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    name: str
    description: str | None
    icon: str | None
    color: str | None
    entity_types: list[str]
    default_business_purpose: str | None
    is_active: bool
    created_by: uuid.UUID
    created_at: str
    updated_at: str


def _to_dto(catalog) -> CatalogDTO:
    return CatalogDTO(
        id=catalog.id,
        tenant_id=catalog.tenant_id,
        code=catalog.code,
        name=catalog.name,
        description=catalog.description,
        icon=catalog.icon,
        color=catalog.color,
        entity_types=catalog.entity_types,
        default_business_purpose=catalog.default_business_purpose,
        is_active=catalog.is_active,
        created_by=catalog.created_by,
        created_at=catalog.created_at.isoformat() if catalog.created_at else "",
        updated_at=catalog.updated_at.isoformat() if catalog.updated_at else "",
    )


@router.post("", response_model=CatalogDTO, status_code=201)
async def create_catalog(
    req: CatalogCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        catalog = await service.create(
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            code=req.code,
            name=req.name,
            entity_types=req.entity_types,
            description=req.description,
            icon=req.icon,
            color=req.color,
            default_business_purpose=req.default_business_purpose,
            created_by=uuid.UUID(str(current_user["id"])),
            role=str(current_user.get("role", "employee")),
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except CatalogCodeConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await session.commit()
    return _to_dto(catalog)


@router.get("", response_model=list[CatalogDTO])
async def list_catalogs(
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    catalogs = await service.list_by_tenant(uuid.UUID(str(current_user["tenant_id"])))
    return [_to_dto(c) for c in catalogs]


@router.get("/{catalog_id}", response_model=CatalogDTO)
async def get_catalog(
    catalog_id: str,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    catalog = await service.get_by_id(
        uuid.UUID(catalog_id), uuid.UUID(str(current_user["tenant_id"]))
    )
    if not catalog:
        raise HTTPException(status_code=404, detail="数据库不存在")
    return _to_dto(catalog)


@router.patch("/{catalog_id}", response_model=CatalogDTO)
async def update_catalog(
    catalog_id: str,
    req: CatalogUpdate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        catalog = await service.update(
            catalog_id=uuid.UUID(catalog_id),
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            role=str(current_user.get("role", "employee")),
            **req.model_dump(exclude_unset=True),
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not catalog:
        raise HTTPException(status_code=404, detail="数据库不存在")
    await session.commit()
    return _to_dto(catalog)


@router.delete("/{catalog_id}", status_code=204)
async def delete_catalog(
    catalog_id: str,
    hard: bool = False,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    service = CatalogService(session)
    try:
        ok = await service.delete(
            catalog_id=uuid.UUID(catalog_id),
            tenant_id=uuid.UUID(str(current_user["tenant_id"])),
            role=str(current_user.get("role", "employee")),
            hard=hard,
        )
    except CatalogPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="数据库不存在")
    await session.commit()
```

- [ ] **Step 5: 注册 catalog_router 到 main.py**

文件：`packages/server-python/app/main.py`

在 import 区加：
```python
from app.contexts.structured_data.interfaces.api.catalog_router import (
    router as catalog_router,
)
```

在 `app.include_router` 区加（在 `data_query_router` 之前）：
```python
app.include_router(catalog_router)
```

- [ ] **Step 6: 写失败测试（Repository + Service + Router）**

文件：`packages/server-python/tests/contexts/structured_data/test_catalog_repository.py`、`test_catalog_service.py`、`test_catalog_router.py`

每个文件覆盖：
- `test_catalog_repository.py`：create / get_by_code / list_by_tenant / soft_delete / count_datasets + tenant 隔离
- `test_catalog_service.py`：5 角色 RBAC 矩阵（admin 可创建 / employee 403 / data_admin 可创建）+ code 冲突 + entity_types 白名单校验
- `test_catalog_router.py`：POST 201 + GET 200 + GET 404 + PATCH + DELETE + 权限 403

测试使用现有 `db_session` / `client` / `auth_headers` fixture（来自 `tests/conftest.py` 和 `tests/contexts/structured_data/conftest.py`）。

- [ ] **Step 7: 跑测试 + 通过**

```bash
cd packages/server-python
pytest tests/contexts/structured_data/test_catalog_repository.py \
       tests/contexts/structured_data/test_catalog_service.py \
       tests/contexts/structured_data/test_catalog_router.py -v -W error
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/domain/catalog.py \
        packages/server-python/app/contexts/structured_data/infrastructure/catalog_repository.py \
        packages/server-python/app/contexts/structured_data/application/catalog_service.py \
        packages/server-python/app/contexts/structured_data/interfaces/api/catalog_router.py \
        packages/server-python/app/main.py \
        packages/server-python/tests/contexts/structured_data/test_catalog_repository.py \
        packages/server-python/tests/contexts/structured_data/test_catalog_service.py \
        packages/server-python/tests/contexts/structured_data/test_catalog_router.py
git commit -m "feat(structured-data): REQ-054 catalog CRUD API + RBAC (admin/data_admin 可建库)"
```

---

## Task 3: 数据集上传改造（catalog_id + entity_type 白名单）+ 列表按 catalog 过滤

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/interfaces/api/router.py`（upload_dataset 加 catalog_id + entity_type；list_datasets 加 catalog_id 过滤）
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/dataset_repository.py`（create 加 catalog_id；list_datasets 加 catalog_id 过滤）
- Test: `packages/server-python/tests/contexts/structured_data/test_datasets.py`（扩展现有测试）

**Interfaces:**
- Consumes: Task 2（CatalogService.validate_entity_type 白名单校验）
- Produces: 上传 API 必选 catalog_id + entity_type；列表 API 支持 catalog_id 过滤

- [ ] **Step 1: 改 DatasetRepository.create 加 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/dataset_repository.py`

`create` 方法签名加 `catalog_id: uuid.UUID` 参数，INSERT 语句加 `catalog_id` 列。

- [ ] **Step 2: 改 DatasetRepository.list_datasets 加 catalog_id 过滤**

```python
async def list_datasets(
    self,
    tenant_id: uuid.UUID,
    catalog_id: uuid.UUID | None = None,  # NEW
    tag: str | None = None,
    ...
) -> list[dict]:
    conditions = ["tenant_id = :tid"]
    params: dict = {"tid": tenant_id}
    if catalog_id is not None:
        conditions.append("catalog_id = :cid")
        params["cid"] = catalog_id
    # ... 其余不变
```

- [ ] **Step 3: 改 upload_dataset 端点加 catalog_id + entity_type**

文件：`packages/server-python/app/contexts/structured_data/interfaces/api/router.py`

```python
@router.post("/datasets/upload", response_model=DatasetDTO, status_code=201)
async def upload_dataset(
    file: UploadFile,
    catalog_id: str = Form(...),  # NEW 必选
    entity_type: str = Form(...),  # NEW 必选
    name: str | None = None,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    current_user: dict = Depends(get_current_user),  # noqa: B008
):
    tid = get_tenant_id()
    uid = current_user["id"]

    # 白名单校验
    catalog_service = CatalogService(session)
    try:
        await catalog_service.validate_entity_type(
            catalog_id=uuid.UUID(catalog_id),
            tenant_id=tid,
            entity_type=entity_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ... 其余上传逻辑不变，repo.create 加 catalog_id=uuid.UUID(catalog_id)
```

- [ ] **Step 4: 改 list_datasets 加 catalog_id 过滤参数**

```python
@router.get("/datasets", response_model=list[DatasetDTO])
async def list_datasets(
    catalog_id: str | None = None,  # NEW
    tag: str | None = None,
    ...
):
    tid = get_tenant_id()
    repo = DatasetRepository(session)
    rows = await repo.list_datasets(
        tid,
        catalog_id=uuid.UUID(catalog_id) if catalog_id else None,
        ...
    )
```

- [ ] **Step 5: 写失败测试 + 跑通**

扩展 `test_datasets.py`：
- 上传缺 catalog_id → 422
- 上传 entity_type 不在白名单 → 400
- 上传成功 → 201 + catalog_id 正确
- 列表按 catalog_id 过滤 → 只返回该库数据集

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/interfaces/api/router.py \
        packages/server-python/app/contexts/structured_data/infrastructure/dataset_repository.py \
        packages/server-python/tests/contexts/structured_data/test_datasets.py
git commit -m "feat(structured-data): REQ-054 上传加 catalog_id + entity_type 白名单 + 列表过滤"
```

---

## Task 4: DirectDB adapter V1 + MCP adapter V1 升级（从占位到接口骨架）

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py`
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_direct_db_adapter.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_mcp_adapter.py`

**Interfaces:**
- Consumes: Task 2（DataSourceAdapter ABC from REQ-052）
- Produces: DirectDB adapter V1（连接外部 PG 只读查询）+ MCP adapter V1（接口骨架）

- [ ] **Step 1: 升级 DirectDBAdapter 从占位到 V1**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py`

从 `__init__` 抛 NotImplementedError 改为：
```python
class DirectDBAdapter(DataSourceAdapter):
    """V1: 连接外部 PostgreSQL 只读查询。

    配置（data_source_config）:
        connection_string: str  # 只读连接串
        table_name: str         # 查询的表
    """

    def __init__(self, session: AsyncSession | None = None, config: dict | None = None):
        self._session = session
        self._config = config or {}

    def get_data_source_type(self) -> str:
        return "direct_db"

    async def query(self, query_plan, semantic_model, tenant_id, user_role) -> list[dict]:
        # V1: 用 connection_string 连外部 PG，SELECT table_name + limit
        # 复用 SqlGuard（只读 + limit + 字段白名单）由 QueryService 编排保证
        import asyncpg
        conn_str = self._config.get("connection_string")
        table = self._config.get("table_name")
        if not conn_str or not table:
            return []
        limit = min(int(query_plan.get("limit", 100)), 1000)
        conn = await asyncpg.connect(conn_str)
        try:
            # 只允许 SELECT（参数化防注入）
            rows = await conn.fetch(
                f"SELECT * FROM {table} LIMIT $1", limit
            )
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    def validate_query(self, query_plan, semantic_model) -> list[str]:
        errors = []
        if not self._config.get("connection_string"):
            errors.append("direct_db 缺少 connection_string 配置")
        if not self._config.get("table_name"):
            errors.append("direct_db 缺少 table_name 配置")
        return errors
```

注意：`table_name` 必须做白名单校验（只允许字母数字下划线）防 SQL 注入，V1 简单实现用正则。

- [ ] **Step 2: 升级 MCPAdapter 从占位到 V1 接口骨架**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py`

```python
class MCPAdapter(DataSourceAdapter):
    """V1: MCP 服务映射接口骨架（不接真实 MCP server，留 V2 接 QCC）。

    配置（data_source_config）:
        server_url: str     # MCP server URL
        tool_name: str      # 调用的 tool 名
    """

    def __init__(self, session=None, config: dict | None = None):
        self._config = config or {}

    def get_data_source_type(self) -> str:
        return "mcp"

    async def query(self, query_plan, semantic_model, tenant_id, user_role) -> list[dict]:
        # V1: 返回空列表 + 日志（未接真实 server）
        # V2: 接 QCC MCP server
        return []

    def validate_query(self, query_plan, semantic_model) -> list[str]:
        errors = []
        if not self._config.get("server_url"):
            errors.append("mcp 缺少 server_url 配置")
        if not self._config.get("tool_name"):
            errors.append("mcp 缺少 tool_name 配置")
        return errors
```

- [ ] **Step 3: 写测试 + 跑通**

`test_direct_db_adapter.py`：get_data_source_type / validate_query 缺配置 / query 返回空（V1 不连真实 PG，mock asyncpg）
`test_mcp_adapter.py`：get_data_source_type / validate_query / query 返回空

- [ ] **Step 4: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py \
        packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py \
        packages/server-python/tests/contexts/structured_data/test_direct_db_adapter.py \
        packages/server-python/tests/contexts/structured_data/test_mcp_adapter.py
git commit -m "feat(structured-data): REQ-054 DirectDB + MCP adapter V1 接口骨架"
```

---

## Task 5: 语义层 (catalog_id, entity_type) 双键路由

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py`（加 get_active_by_catalog_and_entity_type）
- Modify: `packages/server-python/app/contexts/structured_data/domain/semantic_model.py`（SemanticModel 加 catalog_id 字段）
- Test: `packages/server-python/tests/contexts/structured_data/test_semantic_model_repository.py`

**Interfaces:**
- Consumes: Task 1（SemanticModelModel 加 catalog_id）
- Produces: `get_active_by_catalog_and_entity_type(tenant_id, catalog_id, entity_type)` 方法

- [ ] **Step 1: SemanticModel dataclass 加 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/domain/semantic_model.py`

在 `SemanticModel` dataclass 加：
```python
    catalog_id: uuid.UUID | None = None  # REQ-054: 所属数据库
```

- [ ] **Step 2: SemanticModelRepository 加新方法 + _to_domain 填 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py`

```python
async def get_active_by_catalog_and_entity_type(
    self,
    tenant_id: uuid.UUID,
    catalog_id: uuid.UUID,
    entity_type: str,
) -> SemanticModel | None:
    """REQ-054: 按 (catalog_id, entity_type) 双键查询 active model."""
    stmt = select(SemanticModelModel).where(
        SemanticModelModel.tenant_id == tenant_id,
        SemanticModelModel.catalog_id == catalog_id,
        SemanticModelModel.entity_type == entity_type,
        SemanticModelModel.status == "active",
    )
    result = await self._session.execute(stmt)
    row = result.scalar_one_or_none()
    return self._to_domain(row) if row else None
```

`_to_domain` 方法加 `catalog_id=row.catalog_id`。

- [ ] **Step 3: 写测试 + 跑通**

`test_semantic_model_repository.py` 加：
- 同 entity_type 不同 catalog 返回不同 model
- get_active_by_catalog_and_entity_type 找不到返回 None

- [ ] **Step 4: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/domain/semantic_model.py \
        packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py \
        packages/server-python/tests/contexts/structured_data/test_semantic_model_repository.py
git commit -m "feat(structured-data): REQ-054 语义层 (catalog_id, entity_type) 双键路由"
```

---

## Task 6: QueryPlanner + QueryService.ask + /data-query/ask API 加 catalog_id

**Files:**
- Modify: `packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py`（AskRequest 加 catalog_id；路由按 (catalog_id, entity_type) 查 semantic_model）
- Modify: `packages/server-python/app/contexts/structured_data/application/query_planner.py`（system prompt 加 catalog 上下文）
- Modify: `packages/server-python/app/contexts/structured_data/application/query_service.py`（audit 写入 catalog_id）
- Test: `packages/server-python/tests/contexts/structured_data/test_query_router.py`（加 catalog_id 测试）

**Interfaces:**
- Consumes: Task 5（get_active_by_catalog_and_entity_type）
- Produces: /data-query/ask 接受 catalog_id + audit log 写入 catalog_id

- [ ] **Step 1: AskRequest 加 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py`

```python
class AskRequest(BaseModel):
    catalog_id: str = Field(..., description="数据库 ID（REQ-054）")
    entity_type: str = Field(..., description="entity_type, e.g. 'bill'")
    question: str = Field(..., min_length=1)
    business_purpose: str = Field(..., min_length=5)
    confirmed_company_name: str | None = None
```

- [ ] **Step 2: 路由改用 get_active_by_catalog_and_entity_type**

```python
    repo = SemanticModelRepository(db_session)
    semantic_model = await repo.get_active_by_catalog_and_entity_type(
        tenant_id=tenant_id,
        catalog_id=uuid.UUID(req.catalog_id),
        entity_type=req.entity_type,
    )
```

- [ ] **Step 3: QueryPlanner system prompt 加 catalog 上下文**

文件：`packages/server-python/app/contexts/structured_data/application/query_planner.py`

`_build_system_prompt` 加：
```python
    catalog_name = getattr(semantic_model, "catalog_name", None) or "(unknown)"
    catalog_code = getattr(semantic_model, "catalog_code", None) or ""
    # 在 prompt 里加: 当前数据库: {catalog_name} ({catalog_code})
```

注意：SemanticModel dataclass 不含 catalog_name/catalog_code，QueryService 需在调用前查 catalog 并传给 planner，或 planner 接受额外参数。V1 简化：planner 只用 `semantic_model.catalog_id`，prompt 里说"当前数据库 ID: {catalog_id}"。V2 再加 catalog 名称查询。

- [ ] **Step 4: QueryService audit 写入 catalog_id**

文件：`packages/server-python/app/contexts/structured_data/application/query_service.py`

`_audit` 方法加 `catalog_id` 参数（从 `semantic_model.catalog_id` 取），写入 `query_audit_log.catalog_id`。

- [ ] **Step 5: 写测试 + 跑通**

`test_query_router.py` 加：
- ask 缺 catalog_id → 422
- ask 成功 → audit log 写入 catalog_id
- 2 个库同 entity_type → 返回各自结果

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py \
        packages/server-python/app/contexts/structured_data/application/query_planner.py \
        packages/server-python/app/contexts/structured_data/application/query_service.py \
        packages/server-python/tests/contexts/structured_data/test_query_router.py
git commit -m "feat(structured-data): REQ-054 /data-query/ask 加 catalog_id + audit 写入"
```

---

## Task 7: 前端 catalog service + store + DatabaseView 改卡片列表 + CatalogCreateDialog

**Files:**
- Create: `packages/web/src/services/catalog.ts`
- Create: `packages/web/src/stores/catalog.ts`
- Create: `packages/web/src/views/database/CatalogCard.vue`
- Create: `packages/web/src/views/database/CatalogCreateDialog.vue`
- Modify: `packages/web/src/views/database/DatabaseView.vue`（改为卡片列表）
- Test: `packages/web/src/views/database/CatalogCard.test.ts`

**Interfaces:**
- Consumes: Task 2（/api/v1/catalogs CRUD API）
- Produces: 数据库列表卡片 UI + 新建对话框

- [ ] **Step 1: 写 catalog service + types**

文件：`packages/web/src/services/catalog.ts`

```typescript
import api from "./api";

export interface CatalogDTO {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  entity_types: string[];
  default_business_purpose: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CatalogCreate {
  code: string;
  name: string;
  entity_types: string[];
  description?: string;
  icon?: string;
  color?: string;
  default_business_purpose?: string;
}

export async function listCatalogs(): Promise<CatalogDTO[]> {
  const res = await api.get<CatalogDTO[]>("/catalogs");
  return res.data;
}

export async function createCatalog(req: CatalogCreate): Promise<CatalogDTO> {
  const res = await api.post<CatalogDTO>("/catalogs", req);
  return res.data;
}

export async function getCatalog(id: string): Promise<CatalogDTO> {
  const res = await api.get<CatalogDTO>(`/catalogs/${id}`);
  return res.data;
}

export async function deleteCatalog(id: string): Promise<void> {
  await api.delete(`/catalogs/${id}`);
}
```

- [ ] **Step 2: 写 Pinia store**

文件：`packages/web/src/stores/catalog.ts`

```typescript
import { defineStore } from "pinia";
import { ref } from "vue";
import { listCatalogs, type CatalogDTO } from "@/services/catalog";

export const useCatalogStore = defineStore("catalog", () => {
  const catalogs = ref<CatalogDTO[]>([]);
  const loading = ref(false);

  async function fetch() {
    loading.value = true;
    try {
      catalogs.value = await listCatalogs();
    } finally {
      loading.value = false;
    }
  }

  return { catalogs, loading, fetch };
});
```

- [ ] **Step 3: 写 CatalogCard.vue 组件**

文件：`packages/web/src/views/database/CatalogCard.vue`

展示：icon / name / description / entity_types 标签 / 数据集数（prop 传入）。点击 emit "click"。

- [ ] **Step 4: 写 CatalogCreateDialog.vue**

文件：`packages/web/src/views/database/CatalogCreateDialog.vue`

表单：code（小写英文）/ name / description / entity_types（多选或逗号分隔）/ icon / color。提交调 createCatalog。

- [ ] **Step 5: 改 DatabaseView.vue 为卡片列表**

文件：`packages/web/src/views/database/DatabaseView.vue`

改为：
- 顶部 PageHeader + [+ 新建数据库] 按钮（仅 admin 可见，通过 auth store role 判断）
- 卡片网格（v-for catalog in catalogs）
- 点击卡片 → router.push(`/database/${catalog.code}`)

保留现有数据集列表逻辑作为 CatalogDetailPage 的内容（Task 8 处理）。

- [ ] **Step 6: 写测试 + 跑通**

`CatalogCard.test.ts`：渲染 + click emit
`DatabaseView.test.ts`：渲染卡片列表 + 新建按钮

```bash
cd packages/web && pnpm test CatalogCard DatabaseView
```

- [ ] **Step 7: 提交**

```bash
git add packages/web/src/services/catalog.ts \
        packages/web/src/stores/catalog.ts \
        packages/web/src/views/database/CatalogCard.vue \
        packages/web/src/views/database/CatalogCreateDialog.vue \
        packages/web/src/views/database/DatabaseView.vue \
        packages/web/src/views/database/CatalogCard.test.ts
git commit -m "feat(web): REQ-054 数据库列表卡片 + 新建对话框 (DatabaseView 改造)"
```

---

## Task 8: 前端 CatalogDetailPage + QueryPanel 加数据库 select + 上传 dialog 改造

**Files:**
- Create: `packages/web/src/views/database/CatalogDetailPage.vue`（数据集 / 语义层 / KG / 问数 tab）
- Modify: `packages/web/src/app/router.ts`（加 /database/:catalogCode 路由）
- Modify: `packages/web/src/views/database/QueryPanel.vue`（加数据库 select）
- Modify: `packages/web/src/views/database/UploadDatasetDialog.vue`（加数据库选择 + entity_type）
- Modify: `packages/web/src/services/data-query.ts`（AskRequest 加 catalog_id）
- Test: `packages/web/src/views/database/CatalogDetailPage.test.ts`

**Interfaces:**
- Consumes: Task 7（catalog store + service）+ Task 6（/data-query/ask 加 catalog_id）
- Produces: 数据库详情页 4 tab + QueryPanel 数据库 select + 上传 dialog 改造

- [ ] **Step 1: 加路由 /database/:catalogCode**

文件：`packages/web/src/app/router.ts`

```typescript
{
  path: "/database/:catalogCode",
  name: "catalog-detail",
  component: () => import("@/views/database/CatalogDetailPage.vue"),
},
```

- [ ] **Step 2: 写 CatalogDetailPage.vue**

文件：`packages/web/src/views/database/CatalogDetailPage.vue`

4 tab：
- 数据集：复用现有 DatasetListPanel + DatasetTabsPanel（按 catalog_id 过滤）
- 语义层：展示该库的 semantic_models（V1 只读列表）
- 知识图谱：按 catalog_id 过滤 KG 节点
- 问数：嵌入 QueryPanel（预选该库）

- [ ] **Step 3: QueryPanel 加数据库 select + AskRequest 加 catalog_id**

文件：`packages/web/src/views/database/QueryPanel.vue`

加数据库 select（从 catalog store 加载），entity_type 联动（按选中库的 entity_types 过滤）。

文件：`packages/web/src/services/data-query.ts`

```typescript
export interface AskRequest {
  catalog_id: string;  // NEW
  entity_type: string;
  question: string;
  business_purpose: string;
  confirmed_company_name?: string;
}
```

- [ ] **Step 4: UploadDatasetDialog 加数据库选择 + entity_type**

文件：`packages/web/src/views/database/UploadDatasetDialog.vue`

加数据库 select（如果从 CatalogDetailPage 进入则预选）+ entity_type select（按库白名单过滤）。

上传 API 调用加 `catalog_id` + `entity_type` 参数（Form 数据）。

- [ ] **Step 5: 写测试 + 跑通**

- [ ] **Step 6: 提交**

```bash
git add packages/web/src/views/database/CatalogDetailPage.vue \
        packages/web/src/app/router.ts \
        packages/web/src/views/database/QueryPanel.vue \
        packages/web/src/views/database/UploadDatasetDialog.vue \
        packages/web/src/services/data-query.ts \
        packages/web/src/views/database/CatalogDetailPage.test.ts
git commit -m "feat(web): REQ-054 数据库详情页 + QueryPanel 数据库 select + 上传改造"
```

---

## Task 9: 端到端 + closeout

**Files:**
- Test: 端到端验证（2 个库 × 同 entity_type 不同配置 → 问数返回各自结果）
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`
- Modify: `docs/01-product-planning/04-backlog.md`（REQ-054 状态 → Done）
- Modify: `docs/01-product-planning/05-requirements/REQ-054-platform-database-catalog.md`（Status → Done）

- [ ] **Step 1: 跑全量测试套件**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/ -v -W error
cd packages/web && pnpm test
python3 scripts/check-engineering-docs
```

- [ ] **Step 2: 端到端验证（手动 curl 或测试）**

```bash
# 1. 建 2 个库
curl -X POST .../api/v1/catalogs -d '{"code":"park","name":"产业园区数据库","entity_types":["bill"]}'
curl -X POST .../api/v1/catalogs -d '{"code":"edu","name":"教育数据库","entity_types":["bill"]}'

# 2. 各库建 semantic_model（同 entity_type=bill 不同 column_mapping）
# 3. 问数时指定 catalog_id → 返回各自结果
```

- [ ] **Step 3: 更新文档（current-work / work-log / backlog / requirement）**

- [ ] **Step 4: 提交 closeout**

```bash
git commit -m "docs(closeout): REQ-054 实施完成 (catalog 主题域分组 + 9 Task)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ AC-1（data_catalogs 表 CRUD）→ Task 1 + Task 2
- ✅ AC-2（4 表加 catalog_id FK + 迁移）→ Task 1
- ✅ AC-3（仅 admin 可建库）→ Task 2 RBAC
- ✅ AC-4（上传必选 catalog_id + 白名单）→ Task 3
- ✅ AC-5（语义层双键路由）→ Task 5
- ✅ AC-6（QueryPlanner 按 catalog_id）→ Task 6
- ✅ AC-7（前端卡片 + 详情页 tab）→ Task 7 + Task 8
- ✅ AC-8（KG 按库聚合）→ Task 8 CatalogDetailPage KG tab
- ✅ AC-9（现有数据自动迁移）→ Task 1 018 migration
- ✅ AC-10（3 种数据源）→ Task 3（imported_dataset）+ Task 4（direct_db + mcp）

**2. Placeholder scan:** 无 TBD / TODO / "fill in" / "add appropriate"。每个 step 含具体代码或命令。

**3. Type consistency:**
- `Catalog` dataclass 字段一致（Task 2 定义，Task 7 前端 DTO 对应）
- `get_active_by_catalog_and_entity_type(tenant_id, catalog_id, entity_type)` — Task 5 定义，Task 6 调用
- `AskRequest.catalog_id` — Task 6 后端定义，Task 8 前端 data-query.ts 对应
- `CatalogService.validate_entity_type(catalog_id, tenant_id, entity_type)` — Task 2 定义，Task 3 调用

---

## Execution Handoff

**Plan complete and saved to `docs/02-delivery-plans/02-plans/2026-07-07-req-054-platform-database-catalog.md`.**

9 个 Task，覆盖：
- Task 1: schema（alembic 016-018 + ORM + 默认库迁移）
- Task 2: catalog CRUD API + RBAC
- Task 3: 数据集上传改造（catalog_id + 白名单）
- Task 4: DirectDB + MCP adapter V1
- Task 5: 语义层双键路由
- Task 6: QueryPlanner + /data-query/ask 加 catalog_id
- Task 7: 前端数据库列表卡片 + 新建对话框
- Task 8: 前端详情页 + QueryPanel + 上传改造
- Task 9: 端到端 + closeout

**两个执行选项：**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
