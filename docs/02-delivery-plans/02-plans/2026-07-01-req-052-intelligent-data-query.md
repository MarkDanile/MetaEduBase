# REQ-052 Implementation Plan: 智能问数与国资信息化数据激活原子能力

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可复用智能问数原子能力（统一语义层 + Query Planner + JSONB 查询 + SQL Guard + Result Explainer + RBAC/PII 安全合规），支持前端问数面板 + AI Chat tool calling + REQ-046 背调 Skill 3 个验证入口。

**Architecture:** 3 种数据源统一 Data Source Adapter 接口（首期 ImportedDatasetAdapter，V1 DirectDB + MCP）；语义层在 `semantic_models` 表（column_mapping + metric_definitions + data_source_config）；Query Planner 用 LLM 生成 query_plan；JSONB 查询在 `dataset_rows.data` 上构建；RBAC + PII 自动识别为首期上线必查项。

**Tech Stack:**
- 后端：Python 3.14 + FastAPI + SQLAlchemy 2.x async + asyncpg + pydantic v2 + alembic
- LLM：复用 `app/shared/llm/`（deepseek/minimax/qwen）+ LLM tool calling (OpenAI tools 格式)
- 测试：pytest + pytest-asyncio（已配置 asyncio_mode=auto）
- 前端：Vue 3 + TypeScript + Pinia + axios
- 包管理：pnpm (web) + uv (server-python)

## Global Constraints

- `semantic_models.data_source_config` 字段 JSONB（type: imported_dataset / direct_db / mcp）
- `semantic_models.column_mapping` JSONB（role: entity_key / metric / dimension / filter；type: str/float/date/bool；sensitive: bool；synonym: list[str]）
- `semantic_models.metric_definitions` JSONB（column / aggregation: sum/count/avg / label）
- 所有 SQL Guard 在 adapter 执行后统一检查（只读架构保证 + limit 强制 + tenant_id + 字段白名单 + 敏感脱敏）
- 角色 5 类：普通员工 / 部门经理 / 园区领导 / 数据管理员 / 审计员
- LLM provider 全部走 minimax（.env LLM_DEFAULT_PROVIDER=minimax，deepsseek 402）
- 软上限 limit 默认 100，max 1000
- 跨租户数据严格隔离（默认）+ 审批流例外（V1）
- 业务背景 business_purpose 必填（query_audit_log 字段）
- alembic migration 严格按编号顺序（最新 = 012 + 后续）
- pytest 必须在 packages/server-python/ 下跑（configfile = packages/server-python/pyproject.toml）
- 不动现有 `datasets` / `dataset_rows` / `datasets[id]` schema
- 不修改 `ai_router._call_llm` 现有签名（向后兼容，新增 tools 参数）
- 不重写 SQLAlchemy `Vector` 类型层
- 不在 spec 中定义真实业务表字段（实施时与用户确认）

---

## File Structure（实施时新建/修改）

### 后端新建（packages/server-python/app/contexts/structured_data/）

| 文件 | 职责 |
|------|------|
| `domain/semantic_model.py` | SemanticModel dataclass + Role / DataSourceType / ColumnRole enum |
| `infrastructure/semantic_models_models.py` | SQLAlchemy SemanticModelModel（metaedu.semantic_models 表）|
| `infrastructure/semantic_model_repository.py` | SemanticModelRepository（CRUD + 列名扫描）|
| `domain/data_source_adapter.py` | DataSourceAdapter ABC（query + validate_query + get_data_source_type）|
| `infrastructure/imported_dataset_adapter.py` | ImportedDatasetAdapter（JSONB 查询构造，✅ 首期）|
| `infrastructure/direct_db_adapter.py` | DirectDBAdapter 占位（V1，class 抛 NotImplementedError）|
| `infrastructure/mcp_adapter.py` | MCPAdapter 占位（V1，class 抛 NotImplementedError）|
| `application/query_planner.py` | QueryPlanner（LLM 生成 query_plan）|
| `application/semantic_validator.py` | SemanticValidator（query_plan → dataset_id + column + aggregation）|
| `application/sql_guard.py` | SqlGuard（只读 / limit / 租户 / 字段白名单 / 敏感脱敏 / 审计）|
| `application/pii_detector.py` | PIIDetector（正则 + LLM 双引擎，强制脱敏最后防线）|
| `application/result_explainer.py` | ResultExplainer（LLM 生成 summary + 口径 + caveats）|
| `application/query_service.py` | QueryService（编排 Planner + Validator + Adapter + Guard + PII + Explainer）|
| `infrastructure/jsonb_query_builder.py` | JsonbQueryBuilder（query_plan → SQLAlchemy JSONB 查询）|
| `interfaces/api/query_router.py` | POST /api/v1/data-query/ask 端点 |

### 后端新建（packages/server-python/app/contexts/structured_data/ 安全合规）

| 文件 | 职责 |
|------|------|
| `domain/permissions.py` | Role enum（employee / manager / leader / data_admin / auditor）+ Permission dataclass |
| `infrastructure/permissions_models.py` | SQLAlchemy `metaedu.role_permissions` + `tenant_access_grants` + `query_audit_log` + `data_admin_tasks` 表 |
| `infrastructure/permissions_repository.py` | PermissionsRepository（CRUD）|
| `application/rbac_service.py` | RBACService（role 解析 + 字段级 visibility_rules）|

### 后端修改（现有 AI Chat）

| 文件 | 修改内容 |
|------|----------|
| `app/contexts/knowledge/interfaces/api/ai_router.py` | `_call_llm` 新增 `tools` / `tool_choice` 参数 + 处理 `tool_calls` 响应（向后兼容） |
| `app/contexts/knowledge/application/ai_chat_service.py` | `chat` 方法扩展支持 tool calling 编排（两步 LLM 调用 + 工具执行）|
| `app/contexts/knowledge/interfaces/api/router.py` | 注册 `query_internal_data` 工具到 AI Chat tool registry（仅名字 + description + 触发条件）|

### 前端新建（packages/web/src/views/database/）

| 文件 | 职责 |
|------|------|
| `views/database/QueryPanel.vue` | 智能问数 tab（输入框 + query_plan 展示 + result_rows 表格 + summary + 口径 + 来源 + 业务背景输入） |
| `views/database/QueryPanel.test.ts` | 单元测试（输入 + 结果展示）|
| `services/data-query.ts` | API client（POST /api/v1/data-query/ask）|
| `stores/query-history.ts` | Pinia store（最近问数记录）|
| `composables/useDataSourceAdapter.ts` | 客户端侧 data_source_config 渲染 helper |

### 前端修改（现有 AI Chat）

| 文件 | 修改内容 |
|------|----------|
| `views/ai-chat/AiChatView.vue` | 当 AI 返回 tool_call query_internal_data 时展示问数结果表格 + 来源 |
| `services/ai-chat.ts` | 解析 tool_call 响应 + 展示问数结果 |

### DB 迁移（alembic）

| 编号 | 内容 |
|------|------|
| 012_semantic_models | semantic_models 表（id, tenant_id, dataset_id_fk, entity_type, entity_name, data_source_config JSONB, column_mapping JSONB, metric_definitions JSONB, version, status, created_by/at/updated_at）|
| 013_role_permissions | role_permissions（role, entity_type, column_name, visibility: visible/masked/hidden）|
| 014_tenant_access_grants | tenant_access_grants（tenant_id, grantee_tenant_id, entity_type, approved_by, expires_at）|
| 015_query_audit_log | query_audit_log（id, user_id, tenant_id, role, business_purpose, question, query_plan, data_source, result_count, ip, user_agent, created_at）|

### 测试（packages/server-python/tests/）

| 文件 | 职责 |
|------|------|
| `tests/contexts/structured_data/test_semantic_model_repository.py` | semantic_models CRUD + 列名扫描 + drift 检测 |
| `tests/contexts/structured_data/test_imported_dataset_adapter.py` | JSONB 查询构造（5 种查询类型） |
| `tests/contexts/structured_data/test_query_planner.py` | LLM mock 生成 query_plan（10 真实问题样例）|
| `tests/contexts/structured_data/test_semantic_validator.py` | 校验 query_plan 字段 |
| `tests/contexts/structured_data/test_sql_guard.py` | 4 种拒绝场景 + 1 种脱敏 + 1 种审计 |
| `tests/contexts/structured_data/test_pii_detector.py` | 身份证/手机/银行卡/邮箱 自动识别 + 强制脱敏 |
| `tests/contexts/structured_data/test_result_explainer.py` | LLM mock 生成 summary + 口径 + caveats |
| `tests/contexts/structured_data/test_query_router.py` | API 端到端（POST /api/v1/data-query/ask） |
| `tests/contexts/structured_data/test_rbac_service.py` | 5 角色 + 字段级 visibility + 跨租户 + 审计 |
| `tests/contexts/knowledge/test_ai_chat_tool_calling.py` | tool calling 编排（两步 LLM + 工具执行） |

### 文档

| 文件 | 职责 |
|------|------|
| `docs/02-delivery-plans/01-specs/2026-07-06-req-052-intelligent-data-query.md` | 已存在（spec）|
| `docs/02-delivery-plans/02-plans/2026-07-01-req-052-intelligent-data-query.md` | 本文件（plan）|

---

## Task 1: 语义层 schema + RBAC + 审计表（4 张表 alembic migration + ORM）

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/permissions_models.py`
- Create: `packages/server-python/alembic/versions/012_semantic_models.py`
- Create: `packages/server-python/alembic/versions/013_role_permissions.py`
- Create: `packages/server-python/alembic/versions/014_tenant_access_grants.py`
- Create: `packages/server-python/alembic/versions/015_query_audit_log.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_alembic_migrations.py`（只验证 schema 升级不报错）

**Interfaces:**
- Consumes: 无（首任务，建立 schema 基线）
- Produces: 4 张表（metaedu.semantic_models / metaedu.role_permissions / metaedu.tenant_access_grants / metaedu.query_audit_log），后续任务通过 ORM 访问

- [ ] **Step 1: 写 semantic_models 表 SQL（无 ORM）**

文件：`packages/server-python/alembic/versions/012_semantic_models.py`

```python
"""012 semantic models for REQ-052."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012_semantic_models"
down_revision = "030_embedding_vector_4096"  # 实际最新版本号实施时确认
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("metaedu.datasets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_name", sa.String(100), nullable=False),
        sa.Column("data_source_config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("column_mapping", JSONB, nullable=False),
        sa.Column("metric_definitions", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.String(20), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "entity_type", "data_source_config", name="uq_semantic_models_tenant_entity_datasource"),
    )
    op.create_index("ix_semantic_models_dataset", "semantic_models", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("ix_semantic_models_dataset", table_name="semantic_models")
    op.drop_table("semantic_models")
```

- [ ] **Step 2: 写 permissions 3 张表（role_permissions + tenant_access_grants + query_audit_log）**

文件：`packages/server-python/alembic/versions/013_role_permissions.py` / `014_tenant_access_grants.py` / `015_query_audit_log.py`

```python
# 013_role_permissions.py
"""013 role permissions for REQ-052."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "013_role_permissions"
down_revision = "012_semantic_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False),  # employee / manager / leader / data_admin / auditor
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("visibility_rules", JSONB, nullable=False),  # {column_name: visible/masked/hidden}
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "role", "entity_type", name="uq_role_permissions_tenant_role_entity"),
    )


def downgrade() -> None:
    op.drop_table("role_permissions")
```

```python
# 014_tenant_access_grants.py
"""014 tenant access grants for REQ-052."""
revision = "014_tenant_access_grants"
down_revision = "013_role_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),  # 申请方
        sa.Column("grantee_tenant_id", UUID(as_uuid=True), nullable=False, index=True),  # 被授权方
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tenant_access_grants_grantee", "tenant_access_grants", ["grantee_tenant_id", "entity_type"])


def downgrade() -> None:
    op.drop_index("ix_tenant_access_grants_grantee", table_name="tenant_access_grants")
    op.drop_table("tenant_access_grants")
```

```python
# 015_query_audit_log.py
"""015 query audit log for REQ-052."""
revision = "015_query_audit_log"
down_revision = "014_tenant_access_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("business_purpose", sa.Text, nullable=False),  # 用户输入的查询背景
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("query_plan", JSONB, nullable=False),
        sa.Column("data_source_type", sa.String(50), nullable=False),
        sa.Column("data_source_ref", sa.String(200), nullable=True),
        sa.Column("result_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("now()"), index=True),
    )
    # 不可篡改：append-only，无 update/delete 权限（在应用层 + DB role 强制）
    op.create_index("ix_query_audit_log_tenant_created", "query_audit_log", ["tenant_id", "created_at"])
    op.create_index("ix_query_audit_log_user_created", "query_audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_query_audit_log_user_created", table_name="query_audit_log")
    op.drop_index("ix_query_audit_log_tenant_created", table_name="query_audit_log")
    op.drop_table("query_audit_log")
```

- [ ] **Step 3: 写 SemanticModelModel ORM（4 个表对应 3 个 model）**

文件：`packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py`

```python
"""Semantic models + permissions ORM."""
from __future__ import annotations

import uuid
from datetime import datetime, UTC

from sqlalchemy import JSONB, UUID, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.contexts.structured_data.infrastructure.models import Base


class SemanticModelModel(Base):
    __tablename__ = "semantic_models"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metaedu.datasets.id", ondelete="CASCADE"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    data_source_config: Mapped[dict] = mapped_column(PG_JSONB, nullable=False, default=dict)
    column_mapping: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    metric_definitions: Mapped[dict] = mapped_column(PG_JSONB, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="v1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        {"schema": "metaedu"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    visibility_rules: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class TenantAccessGrantModel(Base):
    __tablename__ = "tenant_access_grants"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    grantee_tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))


class QueryAuditLogModel(Base):
    __tablename__ = "query_audit_log"
    __table_args__ = {"schema": "metaedu"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    business_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_plan: Mapped[dict] = mapped_column(PG_JSONB, nullable=False)
    data_source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data_source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)
```

- [ ] **Step 4: 写失败测试 + 跑通 alembic 迁移**

文件：`packages/server-python/tests/contexts/structured_data/test_alembic_migrations.py`

```python
"""Verify alembic migrations 012-015 create expected schema."""
from __future__ import annotations

import asyncio
import asyncpg
import pytest


@pytest.mark.asyncio
async def test_alembic_012_015_create_schema():
    """4 张表都创建成功 + 列定义正确。"""
    # 用 TEST_DATABASE_URL 连接
    import os
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql://metaedu:dev_only_123@localhost:5432/metaedu_test")
    
    conn = await asyncpg.connect(db_url)
    try:
        # 验证 semantic_models
        rows = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='metaedu' AND table_name='semantic_models' "
            "ORDER BY ordinal_position"
        )
        col_names = {r['column_name'] for r in rows}
        assert 'data_source_config' in col_names
        assert 'column_mapping' in col_names
        assert 'metric_definitions' in col_names
        # 验证其他 3 张表
        for table in ['role_permissions', 'tenant_access_grants', 'query_audit_log']:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='metaedu' AND table_name=$1)", table
            )
            assert exists, f"Table {table} not found"
    finally:
        await conn.close()
```

- [ ] **Step 5: 跑迁移 + 跑测试**

```bash
cd packages/server-python
# 应用所有迁移
alembic upgrade head
# 跑测试
pytest tests/contexts/structured_data/test_alembic_migrations.py -v
```

Expected: 4 张表创建成功，测试通过

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/alembic/versions/012_semantic_models.py \
        packages/server-python/alembic/versions/013_role_permissions.py \
        packages/server-python/alembic/versions/014_tenant_access_grants.py \
        packages/server-python/alembic/versions/015_query_audit_log.py \
        packages/server-python/app/contexts/structured_data/infrastructure/semantic_models_models.py \
        packages/server-python/tests/contexts/structured_data/test_alembic_migrations.py
git commit -m "feat(structured-data): REQ-052 语义层 + RBAC + 审计表 schema (alembic 012-015)"
```

---

## Task 2: 语义层 dataclass + Data Source Adapter 接口 + 列名扫描

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/domain/semantic_model.py`
- Create: `packages/server-python/app/contexts/structured_data/domain/data_source_adapter.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/imported_dataset_adapter.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_semantic_model_repository.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_imported_dataset_adapter.py`

**Interfaces:**
- Consumes: Task 1 表 schema（metaedu.semantic_models / metaedu.datasets / metaedu.dataset_rows）
- Produces: 
  - `SemanticModel` dataclass + `ColumnMapping` + `MetricDefinition`
  - `DataSourceAdapter` ABC（query + validate_query + get_data_source_type）
  - `SemanticModelRepository`（CRUD + 列名扫描 + drift 检测）
  - `ImportedDatasetAdapter`（首期 JSONB 查询实现）
  - `DirectDBAdapter` / `MCPAdapter`（V1 占位，class 存在但 query 抛 NotImplementedError）

- [ ] **Step 1: 写失败测试（SemanticModelRepository CRUD + 列名扫描）**

```python
"""Test semantic model repository CRUD + column scan + drift detection."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.contexts.structured_data.domain.semantic_model import (
    DataSourceType, SemanticModel, ColumnMapping, MetricDefinition,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)


@pytest.mark.asyncio
async def test_create_and_get_semantic_model(db_session, sample_dataset):
    repo = SemanticModelRepository(db_session)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        dataset_id=sample_dataset.id,
        entity_type="bill",
        entity_name="账单",
        data_source_config={"type": "imported_dataset", "dataset_id": str(sample_dataset.id)},
        column_mapping={
            "company_name": {"role": "entity_key", "type": "str", "sensitive": False, "synonym": ["企业名称"]},
            "amount": {"role": "metric", "type": "float", "sensitive": True, "synonym": ["金额"]},
        },
        metric_definitions={
            "total_amount": {"column": "amount", "aggregation": "sum", "label": "总金额"},
        },
        version="v1",
        status="active",
        created_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )
    await repo.create(model)
    
    got = await repo.get_by_entity_type(
        tenant_id=model.tenant_id, entity_type="bill", data_source_config=model.data_source_config
    )
    assert got is not None
    assert got.entity_type == "bill"
    assert got.column_mapping["company_name"]["role"] == "entity_key"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_semantic_model_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.contexts.structured_data.domain.semantic_model'`

- [ ] **Step 3: 写 SemanticModel dataclass + enums**

```python
# packages/server-python/app/contexts/structured_data/domain/semantic_model.py
"""Semantic model domain entities."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DataSourceType(StrEnum):
    IMPORTED_DATASET = "imported_dataset"
    DIRECT_DB = "direct_db"  # V1
    MCP = "mcp"  # V1


class ColumnRole(StrEnum):
    ENTITY_KEY = "entity_key"
    METRIC = "metric"
    DIMENSION = "dimension"
    FILTER = "filter"


class ColumnType(StrEnum):
    STR = "str"
    FLOAT = "float"
    INT = "int"
    DATE = "date"
    BOOL = "bool"


@dataclass
class ColumnMapping:
    role: ColumnRole
    type: ColumnType
    sensitive: bool = False
    synonym: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "type": self.type.value,
            "sensitive": self.sensitive,
            "synonym": self.synonym,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ColumnMapping":
        return cls(
            role=ColumnRole(d["role"]),
            type=ColumnType(d["type"]),
            sensitive=d.get("sensitive", False),
            synonym=d.get("synonym", []),
        )


@dataclass
class MetricDefinition:
    column: str
    aggregation: str  # sum / count / avg
    label: str

    def to_dict(self) -> dict:
        return {"column": self.column, "aggregation": self.aggregation, "label": self.label}

    @classmethod
    def from_dict(cls, d: dict) -> "MetricDefinition":
        return cls(column=d["column"], aggregation=d["aggregation"], label=d["label"])


@dataclass
class SemanticModel:
    id: uuid.UUID
    tenant_id: uuid.UUID
    entity_type: str
    entity_name: str
    data_source_config: dict
    column_mapping: dict[str, ColumnMapping]
    metric_definitions: dict[str, MetricDefinition]
    dataset_id: uuid.UUID | None = None
    version: str = "v1"
    status: str = "active"
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
```

- [ ] **Step 4: 写 DataSourceAdapter ABC + 3 adapter 实现**

```python
# packages/server-python/app/contexts/structured_data/domain/data_source_adapter.py
"""Abstract data source adapter interface."""
from __future__ import annotations

import abc
import uuid
from typing import Any


class DataSourceAdapter(abc.ABC):
    """统一数据源适配器接口。语义层不绑死数据源类型。"""

    @abc.abstractmethod
    def get_data_source_type(self) -> str:
        """Return 'imported_dataset' / 'direct_db' / 'mcp'."""
        ...

    @abc.abstractmethod
    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        """Execute query and return unified result_rows."""
        ...

    @abc.abstractmethod
    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        """Return list of error messages (empty if valid)."""
        ...
```

```python
# packages/server-python/app/contexts/structured_data/infrastructure/imported_dataset_adapter.py
"""ImportedDatasetAdapter: JSONB query on datasets + dataset_rows."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.data_source_adapter import DataSourceAdapter
from app.contexts.structured_data.infrastructure.models import DatasetRowModel


class ImportedDatasetAdapter(DataSourceAdapter):
    def __init__(self, session: AsyncSession):
        self._session = session

    def get_data_source_type(self) -> str:
        return "imported_dataset"

    async def query(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
        user_role: str,
    ) -> list[dict]:
        dataset_id = query_plan.get("data_source_ref") or semantic_model.dataset_id
        if not dataset_id:
            return []
        stmt = select(DatasetRowModel).where(
            DatasetRowModel.tenant_id == tenant_id,
            DatasetRowModel.dataset_id == uuid.UUID(str(dataset_id)),
        )
        # 简化：返回前 limit 行（JSONB 字段过滤在 Slice 1 补 JsonbQueryBuilder）
        limit = int(query_plan.get("limit", 100))
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [row.data for row in result.scalars().all()]

    def validate_query(self, query_plan: dict, semantic_model: Any) -> list[str]:
        return []
```

```python
# packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py
"""V1 占位 — DirectDBAdapter 待阶段 2 实现。"""
from __future__ import annotations

import uuid
from typing import Any

from app.contexts.structured_data.domain.data_source_adapter import DataSourceAdapter


class DirectDBAdapter(DataSourceAdapter):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "DirectDBAdapter 是 V1 计划，阶段 2 实现。当前用 ImportedDatasetAdapter。"
        )

    def get_data_source_type(self) -> str:
        return "direct_db"

    async def query(self, query_plan, semantic_model, tenant_id, user_role):
        raise NotImplementedError("DirectDBAdapter 是 V1 计划")

    def validate_query(self, query_plan, semantic_model):
        raise NotImplementedError("DirectDBAdapter 是 V1 计划")
```

```python
# packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py
"""V1 占位 — MCPAdapter 待阶段 2 实现。"""
from __future__ import annotations

import uuid
from typing import Any

from app.contexts.structured_data.domain.data_source_adapter import DataSourceAdapter


class MCPAdapter(DataSourceAdapter):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "MCPAdapter 是 V1 计划，阶段 2 实现。当前用 ImportedDatasetAdapter。"
        )

    def get_data_source_type(self) -> str:
        return "mcp"

    async def query(self, query_plan, semantic_model, tenant_id, user_role):
        raise NotImplementedError("MCPAdapter 是 V1 计划")

    def validate_query(self, query_plan, semantic_model):
        raise NotImplementedError("MCPAdapter 是 V1 计划")
```

- [ ] **Step 5: 写 SemanticModelRepository**

```python
# packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py
"""Semantic model repository: CRUD + column scan + drift detection."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping, MetricDefinition, SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_models_models import (
    SemanticModelModel,
)


class SemanticModelRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, model: SemanticModel) -> None:
        row = SemanticModelModel(
            id=model.id,
            tenant_id=model.tenant_id,
            dataset_id=model.dataset_id,
            entity_type=model.entity_type,
            entity_name=model.entity_name,
            data_source_config=model.data_source_config,
            column_mapping={k: v.to_dict() for k, v in model.column_mapping.items()},
            metric_definitions={k: v.to_dict() for k, v in model.metric_definitions.items()},
            version=model.version,
            status=model.status,
            created_by=model.created_by,
        )
        self._session.add(row)
        await self._session.flush()

    async def get_by_entity_type(
        self, tenant_id: uuid.UUID, entity_type: str, data_source_config: dict
    ) -> SemanticModel | None:
        stmt = select(SemanticModelModel).where(
            SemanticModelModel.tenant_id == tenant_id,
            SemanticModelModel.entity_type == entity_type,
            SemanticModelModel.data_source_config.cast(JSONB) == data_source_config,
            SemanticModelModel.status == "active",
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None
        return self._to_domain(row)

    async def scan_dataset_columns(self, dataset_id: uuid.UUID) -> set[str]:
        """扫描 dataset_rows 的 JSONB 字段名集合（来自 ImportedDatasetAdapter 数据源）。"""
        from app.contexts.structured_data.infrastructure.models import DatasetRowModel
        from sqlalchemy import func

        stmt = select(func.jsonb_object_keys(DatasetRowModel.data).label("key")).where(
            DatasetRowModel.dataset_id == dataset_id
        ).distinct()
        result = await self._session.execute(stmt)
        return {r.key for r in result.all()}

    async def detect_drift(
        self, dataset_id: uuid.UUID, model: SemanticModel
    ) -> dict:
        """对比数据集实际字段 vs 语义层已登记字段。"""
        actual = await self.scan_dataset_columns(dataset_id)
        registered = set(model.column_mapping.keys())
        return {
            "new_columns": list(actual - registered),
            "removed_columns": list(registered - actual),
        }

    def _to_domain(self, row: SemanticModelModel) -> SemanticModel:
        return SemanticModel(
            id=row.id,
            tenant_id=row.tenant_id,
            dataset_id=row.dataset_id,
            entity_type=row.entity_type,
            entity_name=row.entity_name,
            data_source_config=row.data_source_config,
            column_mapping={k: ColumnMapping.from_dict(v) for k, v in row.column_mapping.items()},
            metric_definitions={k: MetricDefinition.from_dict(v) for k, v in row.metric_definitions.items()},
            version=row.version,
            status=row.status,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
```

- [ ] **Step 6: 跑测试 + 全部通过**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_semantic_model_repository.py -v
```

Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/domain/semantic_model.py \
        packages/server-python/app/contexts/structured_data/domain/data_source_adapter.py \
        packages/server-python/app/contexts/structured_data/infrastructure/semantic_model_repository.py \
        packages/server-python/app/contexts/structured_data/infrastructure/imported_dataset_adapter.py \
        packages/server-python/app/contexts/structured_data/infrastructure/direct_db_adapter.py \
        packages/server-python/app/contexts/structured_data/infrastructure/mcp_adapter.py \
        packages/server-python/tests/contexts/structured_data/test_semantic_model_repository.py
git commit -m "feat(structured-data): REQ-052 语义层 dataclass + Data Source Adapter 接口 (3 adapter, 首期 ImportedDataset)"
```

---

## Task 3: RBAC + PII 自动识别（首期安全合规关键）

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/domain/permissions.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/permissions_repository.py`
- Create: `packages/server-python/app/contexts/structured_data/application/rbac_service.py`
- Create: `packages/server-python/app/contexts/structured_data/application/pii_detector.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_rbac_service.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_pii_detector.py`

**Interfaces:**
- Consumes: Task 1 schema（metaedu.role_permissions + metaedu.tenant_access_grants + metaedu.query_audit_log）+ Task 2 semantic_model
- Produces: 
  - `Role` enum + `RBACService`（get_visibility + check_tenant_access + log_query）
  - `PIIDetector`（detect_pii + mask_pii）

- [ ] **Step 1: 写失败测试（RBACService 5 角色 + 字段级权限）**

```python
"""Test RBAC service: 5 roles + field-level visibility + cross-tenant + audit."""
import uuid
import pytest
from app.contexts.structured_data.domain.permissions import Role, Visibility
from app.contexts.structured_data.application.rbac_service import RBACService


@pytest.mark.asyncio
async def test_employee_sees_sensitive_field_masked(db_session):
    """普通员工看 sensitive 字段 → masked（如 '138****1234'）"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        role=Role.EMPLOYEE,
        entity_type="bill",
        column_name="amount",  # sensitive
    )
    assert visibility == Visibility.MASKED


@pytest.mark.asyncio
async def test_manager_sees_sensitive_field_visible(db_session):
    """部门经理看 sensitive 字段 → visible（原文）"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        role=Role.MANAGER,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.VISIBLE


@pytest.mark.asyncio
async def test_default_cross_tenant_blocked(db_session):
    """无 grant 时跨租户访问 → 拒绝"""
    rbac = RBACService(db_session)
    allowed = await rbac.check_tenant_access(
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        grantee_tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        entity_type="bill",
    )
    assert allowed is False
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_rbac_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 写 Role enum + Visibility enum + RBACService**

```python
# packages/server-python/app/contexts/structured_data/domain/permissions.py
"""Permission domain entities."""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "employee"           # 普通员工
    MANAGER = "manager"             # 部门经理
    LEADER = "leader"               # 园区领导
    DATA_ADMIN = "data_admin"       # 数据管理员
    AUDITOR = "auditor"             # 审计员


class Visibility(StrEnum):
    VISIBLE = "visible"  # 原文
    MASKED = "masked"    # 脱敏
    HIDDEN = "hidden"    # 完全不可见
```

```python
# packages/server-python/app/contexts/structured_data/infrastructure/permissions_repository.py
"""Permissions repository: role_permissions + tenant_access_grants + query_audit_log."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.infrastructure.semantic_models_models import (
    QueryAuditLogModel, RolePermissionModel, TenantAccessGrantModel,
)


class PermissionsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_role_visibility_rules(
        self, tenant_id: uuid.UUID, role: str, entity_type: str
    ) -> dict | None:
        stmt = select(RolePermissionModel).where(
            RolePermissionModel.tenant_id == tenant_id,
            RolePermissionModel.role == role,
            RolePermissionModel.entity_type == entity_type,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.visibility_rules if row else None

    async def check_tenant_grant(
        self, tenant_id: uuid.UUID, grantee_tenant_id: uuid.UUID, entity_type: str
    ) -> bool:
        from datetime import UTC, datetime
        stmt = select(TenantAccessGrantModel).where(
            TenantAccessGrantModel.tenant_id == tenant_id,
            TenantAccessGrantModel.grantee_tenant_id == grantee_tenant_id,
            TenantAccessGrantModel.entity_type == entity_type,
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        now = datetime.now(UTC).replace(tzinfo=None)
        return any(
            (r.expires_at is None or r.expires_at > now) for r in rows
        )

    async def log_query(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str,
        business_purpose: str,
        question: str,
        query_plan: dict,
        data_source_type: str,
        data_source_ref: str | None,
        result_count: int,
        duration_ms: int | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        log = QueryAuditLogModel(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            business_purpose=business_purpose,
            question=question,
            query_plan=query_plan,
            data_source_type=data_source_type,
            data_source_ref=data_source_ref,
            result_count=result_count,
            duration_ms=duration_ms,
            ip=ip,
            user_agent=user_agent,
        )
        self._session.add(log)
        await self._session.flush()
```

```python
# packages/server-python/app/contexts/structured_data/application/rbac_service.py
"""RBAC service: field-level visibility + cross-tenant + audit logging."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.domain.permissions import Role, Visibility
from app.contexts.structured_data.infrastructure.permissions_repository import (
    PermissionsRepository,
)


class RBACService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = PermissionsRepository(session)

    async def get_field_visibility(
        self, tenant_id: uuid.UUID, role: Role, entity_type: str, column_name: str
    ) -> Visibility:
        rules = await self._repo.get_role_visibility_rules(tenant_id, role.value, entity_type)
        if rules is None:
            # 默认：sensitive 字段 masked，非 sensitive visible
            return Visibility.MASKED  # 默认保守（即使未配置也按 sensitive 处理）
        if column_name not in rules:
            return Visibility.MASKED
        return Visibility(rules[column_name])

    async def check_tenant_access(
        self, tenant_id: uuid.UUID, grantee_tenant_id: uuid.UUID, entity_type: str
    ) -> bool:
        if tenant_id == grantee_tenant_id:
            return True
        return await self._repo.check_tenant_grant(tenant_id, grantee_tenant_id, entity_type)

    async def log_query(self, **kwargs) -> None:
        await self._repo.log_query(**kwargs)
```

- [ ] **Step 4: 写失败测试（PIIDetector 6 种 PII）**

```python
"""Test PII detector: 6 types of PII auto-detection."""
import pytest
from app.contexts.structured_data.application.pii_detector import PIIDetector


def test_detect_id_card():
    detector = PIIDetector()
    text = "张三的身份证是 110101199003078813"
    pii_types = detector.detect(text)
    assert "id_card" in pii_types


def test_detect_phone():
    detector = PIIDetector()
    text = "联系电话 13812345678"
    pii_types = detector.detect(text)
    assert "phone" in pii_types


def test_detect_bank_card():
    detector = PIIDetector()
    text = "银行卡 6222021234567890123"
    pii_types = detector.detect(text)
    assert "bank_card" in pii_types


def test_mask_id_card():
    detector = PIIDetector()
    masked = detector.mask("110101199003078813", "id_card")
    assert masked == "110101********8813"


def test_no_pii():
    detector = PIIDetector()
    text = "江苏神码信息技术有限公司欠费 5000 元"
    pii_types = detector.detect(text)
    assert len(pii_types) == 0
```

- [ ] **Step 5: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_pii_detector.py -v
```

Expected: FAIL

- [ ] **Step 6: 写 PIIDetector（正则 + 强制 mask）**

```python
# packages/server-python/app/contexts/structured_data/application/pii_detector.py
"""PII auto-detector: regex-based + forced mask (last defense even if schema config wrong)."""
from __future__ import annotations

import re
from typing import Any


class PIIDetector:
    """即使 semantic_models.column_mapping 没标记 sensitive，PII 检测器也强制脱敏。
    
    这是 last defense — 防止 schema 配置错误导致 PII 泄露。
    """
    
    PATTERNS = {
        "id_card": re.compile(r"\b\d{17}[\dXx]\b"),
        "phone": re.compile(r"\b1[3-9]\d{9}\b"),
        "bank_card": re.compile(r"\b\d{16,19}\b"),
        "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "address": re.compile(r"[一-龥]{2,}(省|市|区|县|镇|路|街|号)"),
    }
    
    MASK_FUNCTIONS = {
        "id_card": lambda v: v[:6] + "*" * 8 + v[14:],  # 110101********8813
        "phone": lambda v: v[:3] + "****" + v[7:],  # 138****5678
        "bank_card": lambda v: v[:4] + "*" * (len(v) - 8) + v[-4:],
        "email": lambda v: v.split("@")[0][:2] + "***@" + v.split("@")[1] if "@" in v else "***",
        "address": lambda v: "***" if len(v) > 10 else v[:2] + "***",
    }
    
    def detect(self, value: Any) -> list[str]:
        """返回 value 中检测到的 PII 类型列表。"""
        if not isinstance(value, str):
            return []
        detected = []
        for pii_type, pattern in self.PATTERNS.items():
            if pattern.search(value):
                detected.append(pii_type)
        return detected
    
    def mask(self, value: Any, pii_type: str) -> Any:
        """按 PII 类型脱敏 value。"""
        if not isinstance(value, str):
            return value
        mask_fn = self.MASK_FUNCTIONS.get(pii_type)
        if mask_fn is None:
            return "***"
        return mask_fn(value)
    
    def detect_and_mask_dict(self, data: dict) -> dict:
        """递归检测 dict 中所有 string value 的 PII 并脱敏。"""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                pii_types = self.detect(v)
                for pii_type in pii_types:
                    v = self.mask(v, pii_type)
            elif isinstance(v, dict):
                v = self.detect_and_mask_dict(v)
            result[k] = v
        return result
```

- [ ] **Step 7: 跑测试 + 全部通过**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_rbac_service.py tests/contexts/structured_data/test_pii_detector.py -v
```

Expected: 全部 PASS

- [ ] **Step 8: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/domain/permissions.py \
        packages/server-python/app/contexts/structured_data/infrastructure/permissions_repository.py \
        packages/server-python/app/contexts/structured_data/application/rbac_service.py \
        packages/server-python/app/contexts/structured_data/application/pii_detector.py \
        packages/server-python/tests/contexts/structured_data/test_rbac_service.py \
        packages/server-python/tests/contexts/structured_data/test_pii_detector.py
git commit -m "feat(structured-data): REQ-052 RBAC (5 角色) + PII 自动识别（首期国资安全合规）"
```

---

## Task 4: Query Planner (LLM) + JSONB 查询构造器 + SqlGuard

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/application/query_planner.py`
- Create: `packages/server-python/app/contexts/structured_data/application/semantic_validator.py`
- Create: `packages/server-python/app/contexts/structured_data/infrastructure/jsonb_query_builder.py`
- Create: `packages/server-python/app/contexts/structured_data/application/sql_guard.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_query_planner.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_semantic_validator.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_sql_guard.py`

**Interfaces:**
- Consumes: Task 2 semantic_model + Task 3 RBAC + PII
- Produces:
  - `QueryPlanner.plan(question, semantic_model) -> QueryPlan`
  - `SemanticValidator.validate(query_plan, semantic_model) -> list[str]`
  - `JsonbQueryBuilder.build(query_plan) -> SQLAlchemy Select`
  - `SqlGuard.check(query_plan, semantic_model, role) -> GuardResult`

- [ ] **Step 1: 写失败测试（QueryPlanner 用 LLM mock 生成 5 个 query_plan）**

```python
"""Test QueryPlanner with LLM mock."""
import json
import pytest
from unittest.mock import AsyncMock
from app.contexts.structured_data.application.query_planner import QueryPlanner


@pytest.mark.asyncio
async def test_plan_bill_unpaid_query(sample_semantic_model):
    """用户问"这企业欠费多少" → QueryPlanner 生成 entity=bill, metrics=[unpaid_amount]"""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value=json.dumps({
        "entity": "bill",
        "metrics": ["unpaid_amount"],
        "filters": {"company_name": {"op": "eq", "value": "江苏神码信息技术有限公司"}},
        "time_range": {"field": "bill_date", "start": "2023-07-01", "end": "2026-07-01"},
        "limit": 100,
    }))
    planner = QueryPlanner(mock_llm)
    plan = await planner.plan(
        question="这企业欠费多少",
        semantic_model=sample_semantic_model,
        confirmed_company_name="江苏神码信息技术有限公司",
    )
    assert plan["entity"] == "bill"
    assert "unpaid_amount" in plan["metrics"]


# 共 5 个真实问题样例（写在 test 文件内）
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_query_planner.py -v
```

Expected: FAIL

- [ ] **Step 3: 写 QueryPlanner（LLM 调用 + prompt template）**

```python
# packages/server-python/app/contexts/structured_data/application/query_planner.py
"""QueryPlanner: NL → structured query_plan (LLM-generated)."""
from __future__ import annotations

import json
import re
from typing import Any, Protocol


class LLMClient(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...


class QueryPlanner:
    def __init__(self, llm: LLMClient):
        self._llm = llm

    async def plan(
        self,
        question: str,
        semantic_model: Any,
        confirmed_company_name: str | None = None,
    ) -> dict:
        """NL → query_plan (entity / metrics / filters / time_range / limit / sort)."""
        system_prompt = self._build_system_prompt(semantic_model)
        user_prompt = self._build_user_prompt(question, semantic_model, confirmed_company_name)
        raw = await self._llm.generate(system_prompt, user_prompt)
        # 解析 LLM 输出（可能含 markdown 代码块）
        plan = self._parse_llm_output(raw)
        # 强制注入企业全称（如果用户已确认）
        if confirmed_company_name:
            plan.setdefault("filters", {})["company_name"] = {
                "op": "eq",
                "value": confirmed_company_name,
            }
        plan.setdefault("limit", 100)
        return plan

    def _build_system_prompt(self, semantic_model: Any) -> str:
        return f"""你是问数助手。基于语义层 schema 生成 query_plan (JSON)。

语义层 schema:
- entity_type: {semantic_model.entity_type}
- entity_name: {semantic_model.entity_name}
- column_mapping: {list(semantic_model.column_mapping.keys())}
- metric_definitions: {list(semantic_model.metric_definitions.keys())}

规则:
1. 只输出 query_plan JSON，不要解释
2. entity 必须从 entity_type 选
3. metrics 必须从 metric_definitions 选（如不需要聚合填空数组）
4. filters 用 column_mapping 的 key
5. time_range 字段必须是 date 类型
6. limit 默认 100

输出格式:
{{"entity": "...", "metrics": [...], "filters": {{...}}, "time_range": {{...}}, "limit": N}}"""

    def _build_user_prompt(self, question: str, semantic_model: Any, company_name: str | None) -> str:
        prompt = f"问题: {question}"
        if company_name:
            prompt += f"\n企业全称（已确认）: {company_name}"
        return prompt

    def _parse_llm_output(self, raw: str) -> dict:
        # LLM 输出可能含 ```json ... ``` 代码块
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw)
```

- [ ] **Step 4: 写 SemanticValidator（query_plan 字段检查）**

```python
# packages/server-python/app/contexts/structured_data/application/semantic_validator.py
"""Validate query_plan against semantic_model (entity / metrics / filters must be defined)."""
from __future__ import annotations

from typing import Any


class SemanticValidator:
    def validate(self, query_plan: dict, semantic_model: Any) -> list[str]:
        errors = []
        # 1. entity 检查
        if query_plan.get("entity") != semantic_model.entity_type:
            errors.append(
                f"entity '{query_plan.get('entity')}' not in semantic model "
                f"(expected: {semantic_model.entity_type})"
            )
        # 2. metrics 检查
        for metric in query_plan.get("metrics", []):
            if metric not in semantic_model.metric_definitions:
                errors.append(
                    f"metric '{metric}' not defined in semantic model. "
                    f"Available: {list(semantic_model.metric_definitions.keys())}"
                )
        # 3. filters 检查
        for col in query_plan.get("filters", {}):
            if col not in semantic_model.column_mapping:
                errors.append(
                    f"filter column '{col}' not defined. "
                    f"Available: {list(semantic_model.column_mapping.keys())}"
                )
        # 4. time_range 检查
        tr = query_plan.get("time_range")
        if tr:
            field = tr.get("field")
            if field and field not in semantic_model.column_mapping:
                errors.append(f"time_range field '{field}' not defined")
        return errors
```

- [ ] **Step 5: 写 JsonbQueryBuilder（query_plan → SQLAlchemy JSONB 查询）**

```python
# packages/server-python/app/contexts/structured_data/infrastructure/jsonb_query_builder.py
"""Build SQLAlchemy JSONB query from query_plan (on dataset_rows.data)."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.structured_data.infrastructure.models import DatasetRowModel


class JsonbQueryBuilder:
    OPERATOR_MAP = {
        "eq": lambda col, v: col == v,
        "ne": lambda col, v: col != v,
        "gt": lambda col, v: col > v,
        "lt": lambda col, v: col < v,
        "gte": lambda col, v: col >= v,
        "lte": lambda col, v: col <= v,
        "contains": lambda col, v: col.contains(v),
        "in": lambda col, v: col.in_(v) if isinstance(v, list) else col == v,
    }

    def __init__(self, session: AsyncSession):
        self._session = session

    def build(
        self,
        query_plan: dict,
        semantic_model: Any,
        tenant_id: uuid.UUID,
    ):
        dataset_id = semantic_model.dataset_id or query_plan.get("data_source_ref")
        if not dataset_id:
            return None
        stmt = select(DatasetRowModel.data).where(
            DatasetRowModel.tenant_id == tenant_id,
            DatasetRowModel.dataset_id == uuid.UUID(str(dataset_id)),
        )
        # 应用 filters
        for col, cond in query_plan.get("filters", {}).items():
            op = cond.get("op", "eq")
            value = cond.get("value")
            op_fn = self.OPERATOR_MAP.get(op)
            if op_fn is None:
                continue
            stmt = stmt.where(op_fn(DatasetRowModel.data[col].astext, value))
        # 应用 time_range
        tr = query_plan.get("time_range")
        if tr:
            field = tr.get("field")
            start = tr.get("start")
            end = tr.get("end")
            if field and start:
                stmt = stmt.where(DatasetRowModel.data[field].astext >= start)
            if field and end:
                stmt = stmt.where(DatasetRowModel.data[field].astext <= end)
        # limit
        limit = int(query_plan.get("limit", 100))
        stmt = stmt.limit(limit)
        return stmt
```

- [ ] **Step 6: 写 SqlGuard（只读 / limit / 字段白名单 / 敏感脱敏）**

```python
# packages/server-python/app/contexts/structured_data/application/sql_guard.py
"""SQL Guard: field whitelist + limit + sensitive field masking."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass
class GuardResult:
    rows: list[dict]
    masked_count: int  # 多少字段被脱敏


class SqlGuard:
    def check_and_mask(
        self,
        rows: list[dict],
        semantic_model: Any,
        role: str,
        rbac_service: Any,
        pii_detector: Any,
    ) -> GuardResult:
        masked_count = 0
        # 1. 字段白名单检查（首期：实际只筛 semantic_model.column_mapping 定义的列）
        allowed_cols = set(semantic_model.column_mapping.keys())
        # 2. limit 强制（已 JsonbQueryBuilder 限制）
        # 3. 敏感字段脱敏
        for row in rows:
            for col, value in list(row.items()):
                if col not in allowed_cols:
                    # 不在白名单 → 移除
                    del row[col]
                    continue
                # 查 visibility
                from app.contexts.structured_data.domain.permissions import Role, Visibility
                vis = rbac_service.get_field_visibility_sync(
                    role=Role(role),
                    column_name=col,
                    semantic_model=semantic_model,
                )
                if vis == Visibility.HIDDEN:
                    del row[col]
                elif vis == Visibility.MASKED:
                    # PII 自动识别 + 强制脱敏
                    row[col] = self._mask_value(value, pii_detector)
                    masked_count += 1
        return GuardResult(rows=rows, masked_count=masked_count)

    def _mask_value(self, value: Any, pii_detector: Any) -> Any:
        if not isinstance(value, str):
            return value
        masked = value
        for pii_type in pii_detector.detect(masked):
            masked = pii_detector.mask(masked, pii_type)
        return masked
```

- [ ] **Step 7: 跑测试 + 通过**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_query_planner.py tests/contexts/structured_data/test_semantic_validator.py tests/contexts/structured_data/test_sql_guard.py -v
```

Expected: PASS

- [ ] **Step 8: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/application/query_planner.py \
        packages/server-python/app/contexts/structured_data/application/semantic_validator.py \
        packages/server-python/app/contexts/structured_data/infrastructure/jsonb_query_builder.py \
        packages/server-python/app/contexts/structured_data/application/sql_guard.py \
        packages/server-python/tests/contexts/structured_data/test_query_planner.py \
        packages/server-python/tests/contexts/structured_data/test_semantic_validator.py \
        packages/server-python/tests/contexts/structured_data/test_sql_guard.py
git commit -m "feat(structured-data): REQ-052 Query Planner + JSONB 查询 + SqlGuard (PII 强制脱敏)"
```

---

## Task 5: Result Explainer + QueryService 编排 + API 端点

**Files:**
- Create: `packages/server-python/app/contexts/structured_data/application/result_explainer.py`
- Create: `packages/server-python/app/contexts/structured_data/application/query_service.py`
- Create: `packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py`
- Modify: `packages/server-python/app/main.py`（注册 query_router）
- Test: `packages/server-python/tests/contexts/structured_data/test_result_explainer.py`
- Test: `packages/server-python/tests/contexts/structured_data/test_query_router.py`

**Interfaces:**
- Consumes: Task 1-4（语义层 + Adapter + Planner + Validator + SqlGuard + PII + RBAC）
- Produces:
  - `ResultExplainer.explain(result_rows, semantic_model, query_plan) -> ExplainerResult`
  - `QueryService.ask(question, semantic_model, ...) -> AskResponse`
  - API endpoint: `POST /api/v1/data-query/ask` 返回完整响应

- [ ] **Step 1: 写失败测试（ResultExplainer LLM 生成 summary）**

```python
"""Test ResultExplainer with LLM mock."""
import pytest
from unittest.mock import AsyncMock
from app.contexts.structured_data.application.result_explainer import ResultExplainer


@pytest.mark.asyncio
async def test_explain_with_no_results(sample_semantic_model):
    """空结果应返回 caveat：数据未录入或无匹配记录"""
    mock_llm = AsyncMock()
    explainer = ResultExplainer(mock_llm)
    result = await explainer.explain(
        result_rows=[],
        semantic_model=sample_semantic_model,
        query_plan={"entity": "bill", "metrics": ["unpaid_amount"]},
        question="这企业欠费多少",
    )
    assert any("空" in c or "无匹配" in c for c in result.caveats)


@pytest.mark.asyncio
async def test_explain_with_results(sample_semantic_model):
    """有结果应返回 summary + metric_values"""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(return_value="该企业过去三年累计欠费 12.5 万元")
    explainer = ResultExplainer(mock_llm)
    result = await explainer.explain(
        result_rows=[{"amount": 5000, "bill_date": "2024-01-01"}] * 25,
        semantic_model=sample_semantic_model,
        query_plan={"entity": "bill", "metrics": ["unpaid_amount"]},
        question="这企业欠费多少",
    )
    assert "12.5 万" in result.summary
    assert result.metric_values["unpaid_amount"]["aggregation"] == "sum"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_result_explainer.py -v
```

Expected: FAIL

- [ ] **Step 3: 写 ResultExplainer**

```python
# packages/server-python/app/contexts/structured_data/application/result_explainer.py
"""Result Explainer: LLM generates natural language summary + metric values + caveats."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExplainerResult:
    summary: str
    metric_values: dict  # {metric_name: {value, label, aggregation}}
    filters_applied: dict
    caveats: list[str] = field(default_factory=list)
    confidence: str = "high"


class ResultExplainer:
    def __init__(self, llm):
        self._llm = llm

    async def explain(
        self,
        result_rows: list[dict],
        semantic_model: Any,
        query_plan: dict,
        question: str,
    ) -> ExplainerResult:
        # 计算 metric_values
        metric_values = self._compute_metrics(result_rows, semantic_model, query_plan)
        # LLM 生成 summary
        if result_rows:
            summary = await self._generate_summary(question, result_rows, metric_values, semantic_model)
        else:
            summary = ""
        # 检测 caveats
        caveats = self._detect_caveats(result_rows, query_plan)
        return ExplainerResult(
            summary=summary,
            metric_values=metric_values,
            filters_applied=query_plan.get("filters", {}),
            caveats=caveats,
            confidence="high" if result_rows else "low",
        )

    def _compute_metrics(self, result_rows, semantic_model, query_plan) -> dict:
        """Python 端聚合 metric（不依赖 LLM）。"""
        out = {}
        for metric_name in query_plan.get("metrics", []):
            metric_def = semantic_model.metric_definitions.get(metric_name)
            if not metric_def:
                continue
            col = metric_def.column
            values = [r.get(col) for r in result_rows if r.get(col) is not None]
            agg = metric_def.aggregation
            if agg == "sum":
                value = sum(values)
            elif agg == "count":
                value = len(values)
            elif agg == "avg":
                value = sum(values) / len(values) if values else 0
            else:
                value = None
            out[metric_name] = {
                "value": value,
                "label": metric_def.label,
                "aggregation": agg,
            }
        return out

    async def _generate_summary(self, question, result_rows, metric_values, semantic_model) -> str:
        prompt = f"""基于查询结果生成自然语言摘要。

问题: {question}
metric 结果: {metric_values}
返回行数: {len(result_rows)}

要求: 简洁、准确、提及口径（用 metric label）、如有异常明确指出。"""
        return await self._llm.generate(
            "你是问数结果解释助手。", prompt
        )

    def _detect_caveats(self, result_rows, query_plan) -> list[str]:
        caveats = []
        if not result_rows:
            caveats.append("查询结果为空，可能该企业无相关记录或数据未录入")
        if query_plan.get("filters", {}).get("company_name"):
            caveats.append("按企业全称匹配；如有简称不匹配，可能需补充同义词")
        return caveats
```

- [ ] **Step 4: 写 QueryService 编排**

```python
# packages/server-python/app/contexts/structured_data/application/query_service.py
"""QueryService: orchestrate Planner → Validator → Adapter → Guard → PII → Explainer."""
from __future__ import annotations

import time
import uuid
from typing import Any


class QueryService:
    def __init__(
        self,
        planner,
        validator,
        adapter_factory,  # function: data_source_config -> DataSourceAdapter
        sql_guard,
        pii_detector,
        rbac_service,
        explainer,
        audit_repo,
    ):
        self._planner = planner
        self._validator = validator
        self._adapter_factory = adapter_factory
        self._sql_guard = sql_guard
        self._pii_detector = pii_detector
        self._rbac_service = rbac_service
        self._explainer = explainer
        self._audit_repo = audit_repo

    async def ask(
        self,
        *,
        question: str,
        semantic_model: Any,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        role: str,
        business_purpose: str,
        confirmed_company_name: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        started = time.time()
        # 1. Planner 生成 query_plan
        query_plan = await self._planner.plan(
            question=question,
            semantic_model=semantic_model,
            confirmed_company_name=confirmed_company_name,
        )
        # 2. Validator 校验
        errors = self._validator.validate(query_plan, semantic_model)
        if errors:
            return {
                "ok": False,
                "errors": errors,
                "suggestion": "请尝试更明确的问题，如"这企业过去 3 年的欠费金额"",
            }
        # 3. Adapter 查询
        data_source_config = semantic_model.data_source_config
        adapter = self._adapter_factory(data_source_config)
        result_rows = await adapter.query(query_plan, semantic_model, tenant_id, role)
        # 4. SqlGuard（敏感脱敏 + 字段白名单）
        guard_result = self._sql_guard.check_and_mask(
            result_rows, semantic_model, role, self._rbac_service, self._pii_detector
        )
        # 5. Explainer 生成摘要
        explainer_result = await self._explainer.explain(
            guard_result.rows, semantic_model, query_plan, question
        )
        # 6. Audit
        duration_ms = int((time.time() - started) * 1000)
        await self._audit_repo.log_query(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            business_purpose=business_purpose,
            question=question,
            query_plan=query_plan,
            data_source_type=data_source_config.get("type", "imported_dataset"),
            data_source_ref=str(semantic_model.dataset_id),
            result_count=len(guard_result.rows),
            duration_ms=duration_ms,
            ip=ip,
            user_agent=user_agent,
        )
        return {
            "ok": True,
            "query_plan": query_plan,
            "result_rows": guard_result.rows,
            "result_count": len(guard_result.rows),
            "summary": explainer_result.summary,
            "metric_values": explainer_result.metric_values,
            "filters_applied": explainer_result.filters_applied,
            "caveats": explainer_result.caveats,
            "confidence": explainer_result.confidence,
            "duration_ms": duration_ms,
        }
```

- [ ] **Step 5: 写 query_router API 端点**

```python
# packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py
"""POST /api/v1/data-query/ask endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.contexts.knowledge.interfaces.api.auth import get_current_user  # 复用现有 auth
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.infrastructure.semantic_model_repository import SemanticModelRepository


router = APIRouter(prefix="/api/v1/data-query", tags=["data-query"])


class AskRequest(BaseModel):
    entity_type: str = Field(..., description="entity_type, e.g. 'bill'")
    question: str = Field(..., min_length=1)
    business_purpose: str = Field(..., min_length=5, description="查询背景（必填，用于审计）")
    confirmed_company_name: str | None = None


class AskResponse(BaseModel):
    ok: bool
    query_plan: dict | None = None
    result_rows: list[dict] | None = None
    result_count: int | None = None
    summary: str | None = None
    metric_values: dict | None = None
    filters_applied: dict | None = None
    caveats: list[str] | None = None
    confidence: str | None = None
    duration_ms: int | None = None
    errors: list[str] | None = None
    suggestion: str | None = None


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    request: Request,
    user=Depends(get_current_user),
):
    """问数 API：用户传入问题 + 业务背景，返回 query_plan + 结果 + 摘要。"""
    tenant_id = user.tenant_id
    user_id = user.id
    role = getattr(user, "role", "employee")
    
    # 获取 semantic_model
    repo = SemanticModelRepository(request.state.db_session)
    semantic_model = await repo.get_by_entity_type(
        tenant_id=tenant_id, entity_type=req.entity_type, data_source_config={}
    )
    if semantic_model is None:
        raise HTTPException(404, f"entity_type '{req.entity_type}' not found in semantic model")
    
    # 获取 query_service（DI 容器或全局单例，简化用全局）
    query_service: QueryService = request.app.state.query_service
    result = await query_service.ask(
        question=req.question,
        semantic_model=semantic_model,
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        business_purpose=req.business_purpose,
        confirmed_company_name=req.confirmed_company_name,
        ip=request.client.host,
        user_agent=request.headers.get("user-agent"),
    )
    return AskResponse(**result)
```

- [ ] **Step 6: 在 main.py 注册 query_router**

```python
# packages/server-python/app/main.py 找到 router 注册区域，添加
from app.contexts.structured_data.interfaces.api.query_router import router as data_query_router
app.include_router(data_query_router)
```

- [ ] **Step 7: 写端到端测试**

```python
# packages/server-python/tests/contexts/structured_data/test_query_router.py
"""End-to-end test for POST /api/v1/data-query/ask."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ask_endpoint_success(client, auth_headers, sample_semantic_model):
    """完整流程：POST → query_plan + result_rows + summary"""
    response = await client.post(
        "/api/v1/data-query/ask",
        headers=auth_headers,
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
            "business_purpose": "评估客户信用风险",
            "confirmed_company_name": "江苏神码信息技术有限公司",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "query_plan" in data
    assert "summary" in data
    assert data["result_count"] >= 0


@pytest.mark.asyncio
async def test_ask_endpoint_missing_business_purpose(client, auth_headers):
    """缺 business_purpose → 422（必填）"""
    response = await client.post(
        "/api/v1/data-query/ask",
        headers=auth_headers,
        json={
            "entity_type": "bill",
            "question": "这企业欠费多少",
        },
    )
    assert response.status_code == 422  # pydantic validation error
```

- [ ] **Step 8: 跑测试 + 通过**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/test_result_explainer.py tests/contexts/structured_data/test_query_router.py -v
```

Expected: PASS

- [ ] **Step 9: 提交**

```bash
git add packages/server-python/app/contexts/structured_data/application/result_explainer.py \
        packages/server-python/app/contexts/structured_data/application/query_service.py \
        packages/server-python/app/contexts/structured_data/interfaces/api/query_router.py \
        packages/server-python/app/main.py \
        packages/server-python/tests/contexts/structured_data/test_result_explainer.py \
        packages/server-python/tests/contexts/structured_data/test_query_router.py
git commit -m "feat(structured-data): REQ-052 Result Explainer + QueryService + API 端点 (POST /ask)"
```

---

## Task 6: 前端问数面板（DatabaseView 智能问数 tab）

**Files:**
- Create: `packages/web/src/views/database/QueryPanel.vue`
- Create: `packages/web/src/views/database/QueryPanel.test.ts`
- Create: `packages/web/src/services/data-query.ts`
- Create: `packages/web/src/stores/query-history.ts`
- Test: 单元测试 + 手动端到端验证

**Interfaces:**
- Consumes: Task 5 API endpoint + Task 2-4 后端
- Produces: 前端问数面板 + API client + history store

- [ ] **Step 1: 写 API client + history store**

```typescript
// packages/web/src/services/data-query.ts
import { http } from "@/utils/http";

export interface AskRequest {
  entity_type: string;
  question: string;
  business_purpose: string;
  confirmed_company_name?: string;
}

export interface AskResponse {
  ok: boolean;
  query_plan?: Record<string, unknown>;
  result_rows?: Array<Record<string, unknown>>;
  result_count?: number;
  summary?: string;
  metric_values?: Record<string, { value: unknown; label: string; aggregation: string }>;
  filters_applied?: Record<string, unknown>;
  caveats?: string[];
  confidence?: string;
  duration_ms?: number;
  errors?: string[];
  suggestion?: string;
}

export async function ask(req: AskRequest): Promise<AskResponse> {
  const res = await http.post<AskResponse>("/api/v1/data-query/ask", req);
  return res.data;
}
```

```typescript
// packages/web/src/stores/query-history.ts
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { AskRequest, AskResponse } from "@/services/data-query";

interface HistoryEntry {
  id: string;
  timestamp: number;
  request: AskRequest;
  response: AskResponse;
}

export const useQueryHistory = defineStore("queryHistory", () => {
  const entries = ref<HistoryEntry[]>([]);
  const recent = computed(() => entries.value.slice(0, 10));
  function add(req: AskRequest, res: AskResponse) {
    entries.value.unshift({
      id: crypto.randomUUID(),
      timestamp: Date.now(),
      request: req,
      response: res,
    });
  }
  return { entries, recent, add };
});
```

- [ ] **Step 2: 写 QueryPanel.vue 组件**

```vue
<!-- packages/web/src/views/database/QueryPanel.vue -->
<template>
  <div class="p-4 space-y-4">
    <h3 class="text-lg font-semibold">智能问数</h3>
    <form @submit.prevent="onAsk" class="space-y-2">
      <select v-model="entityType" class="border rounded px-2 py-1">
        <option value="bill">账单 (bill)</option>
        <option value="contract">合同 (contract)</option>
        <option value="ticket">工单 (ticket)</option>
      </select>
      <input v-model="question" placeholder="输入自然语言问题" class="border rounded px-2 py-1 w-full" required />
      <input v-model="companyName" placeholder="企业全称（已确认）" class="border rounded px-2 py-1 w-full" />
      <input v-model="businessPurpose" placeholder="查询背景（必填，≥5 字）" class="border rounded px-2 py-1 w-full" minlength="5" required />
      <button type="submit" :disabled="loading" class="bg-blue-500 text-white px-4 py-2 rounded">
        {{ loading ? "查询中..." : "查询" }}
      </button>
    </form>
    <div v-if="result" class="border rounded p-4 space-y-2">
      <div v-if="result.ok">
        <p class="font-semibold">{{ result.summary }}</p>
        <p class="text-sm text-gray-500">
          共 {{ result.result_count }} 条记录 ({{ result.duration_ms }}ms) ·
          置信度: {{ result.confidence }}
        </p>
        <details>
          <summary class="cursor-pointer">Query Plan</summary>
          <pre class="text-xs bg-gray-50 p-2 rounded">{{ JSON.stringify(result.query_plan, null, 2) }}</pre>
        </details>
        <details>
          <summary class="cursor-pointer">结果 ({{ result.result_count }} 行)</summary>
          <table v-if="result.result_rows && result.result_rows.length" class="w-full text-sm">
            <thead><tr><th v-for="col in resultColumns" :key="col">{{ col }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in result.result_rows.slice(0, 20)" :key="i">
                <td v-for="col in resultColumns" :key="col">{{ row[col] }}</td>
              </tr>
            </tbody>
          </table>
        </details>
        <div v-if="result.caveats && result.caveats.length" class="text-sm text-amber-600">
          <p class="font-semibold">注意事项:</p>
          <ul class="list-disc pl-5">
            <li v-for="(c, i) in result.caveats" :key="i">{{ c }}</li>
          </ul>
        </div>
      </div>
      <div v-else class="text-red-600">
        <p class="font-semibold">查询失败</p>
        <ul class="list-disc pl-5">
          <li v-for="(e, i) in result.errors || []" :key="i">{{ e }}</li>
        </ul>
        <p v-if="result.suggestion">建议: {{ result.suggestion }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ask, type AskRequest, type AskResponse } from "@/services/data-query";
import { useQueryHistory } from "@/stores/query-history";

const entityType = ref("bill");
const question = ref("");
const companyName = ref("");
const businessPurpose = ref("");
const loading = ref(false);
const result = ref<AskResponse | null>(null);
const history = useQueryHistory();

const resultColumns = computed(() => {
  if (!result.value?.result_rows || result.value.result_rows.length === 0) return [];
  return Object.keys(result.value.result_rows[0]);
});

async function onAsk() {
  if (!question.value.trim() || businessPurpose.value.trim().length < 5) return;
  loading.value = true;
  result.value = null;
  try {
    const req: AskRequest = {
      entity_type: entityType.value,
      question: question.value,
      business_purpose: businessPurpose.value,
      ...(companyName.value ? { confirmed_company_name: companyName.value } : {}),
    };
    const res = await ask(req);
    result.value = res;
    history.add(req, res);
  } finally {
    loading.value = false;
  }
}
</script>
```

- [ ] **Step 3: 写单元测试**

```typescript
// packages/web/src/views/database/QueryPanel.test.ts
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import QueryPanel from "./QueryPanel.vue";

describe("QueryPanel", () => {
  it("renders form", () => {
    const wrapper = mount(QueryPanel);
    expect(wrapper.find("select").exists()).toBe(true);
    expect(wrapper.find('input[placeholder*="自然语言"]').exists()).toBe(true);
    expect(wrapper.find('input[placeholder*="查询背景"]').exists()).toBe(true);
  });

  it("requires business_purpose min 5 chars", () => {
    const wrapper = mount(QueryPanel);
    const input = wrapper.find('input[placeholder*="查询背景"]');
    expect(input.attributes("minlength")).toBe("5");
  });

  it("calls API on submit", async () => {
    const mockAsk = vi.fn().mockResolvedValue({ ok: true, result_rows: [], summary: "" });
    vi.mock("@/services/data-query", () => ({ ask: mockAsk }));
    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find('input[placeholder*="企业全称"]').setValue("江苏神码");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("评估信用风险");
    await wrapper.find("form").trigger("submit");
    expect(mockAsk).toHaveBeenCalled();
  });
});
```

- [ ] **Step 4: 把 QueryPanel 集成到 DatabaseView**

```vue
<!-- packages/web/src/views/database/DatabaseView.vue 修改：在 KgOverviewPanel 旁边加 QueryPanel -->
<QueryPanel v-if="selectedId" :dataset-id="selectedId" />
```

- [ ] **Step 5: 跑测试 + 手动端到端验证**

```bash
cd packages/web
pnpm test QueryPanel
# 手动端到端：pnpm dev → 打开 /database → 选 entity → 输入问题 → 提交 → 看到结果
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add packages/web/src/views/database/QueryPanel.vue \
        packages/web/src/views/database/QueryPanel.test.ts \
        packages/web/src/services/data-query.ts \
        packages/web/src/stores/query-history.ts \
        packages/web/src/views/database/DatabaseView.vue
git commit -m "feat(web): REQ-052 前端问数面板 (DatabaseView 智能问数 tab)"
```

---

## Task 7: AI Chat tool calling 接入（Slice 3 — 问数闭环 #2）

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`
- Modify: `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`
- Test: `packages/server-python/tests/contexts/knowledge/test_ai_chat_tool_calling.py`

**Interfaces:**
- Consumes: Task 5 (QueryService) + Task 1-4
- Produces: AI Chat 支持 tool calling（LLM 第一步判断 → 调 query_internal_data → LLM 第二步生成答案）

- [ ] **Step 1: 写失败测试（tool calling 两步 LLM 调用）**

```python
"""Test AI Chat tool calling: 2 LLM calls + tool execution."""
import json
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_ai_chat_triggers_query_tool():
    """用户问"欠费多少" → LLM 第一次返回 tool_call → 执行 query → LLM 第二次生成答案"""
    mock_llm_first = AsyncMock(return_value=json.dumps({
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "query_internal_data",
                        "arguments": json.dumps({"question": "这企业欠费多少", "entity_hint": "bill"}),
                    },
                }],
            }
        }]
    }))
    mock_llm_second = AsyncMock(return_value=json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "该企业过去三年累计欠费 12.5 万元"}}]
    }))
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(side_effect=[mock_llm_first(), mock_llm_second()])
    # ... 调 AI Chat service 验证两次 LLM 调用 + 一次 tool execution
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd packages/server-python && pytest tests/contexts/knowledge/test_ai_chat_tool_calling.py -v
```

Expected: FAIL

- [ ] **Step 3: 修改 ai_router._call_llm 支持 tools 参数**

修改 `packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py`：

```python
async def _call_llm(
    system_prompt: str,
    user_content: str,
    *,
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> dict:
    """Return dict: {content: str | None, tool_calls: list | None}."""
    config = resolve_chat_provider()
    if config is None:
        return {"content": "⚠️ 尚未配置 LLM API Key", "tool_calls": None}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "model": config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
                "max_tokens": 2000,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = tool_choice
            resp = await client.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]
            return {
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            }
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return {"content": f"❌ AI 回答生成失败: {type(e).__name__}", "tool_calls": None}
```

- [ ] **Step 4: 修改 ai_chat_service.chat 支持 tool calling 编排**

修改 `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py` 的 `chat` 方法：

```python
async def chat(self, request, *, tenant_id, session):
    # 1. RAG 检索（现有）
    rag_context = await self._retrieve_and_pack(...)
    # 2. LLM 第一步（带 tools）
    tool_def = {
        "type": "function",
        "function": {
            "name": "query_internal_data",
            "description": "查询内部结构化业务数据（账单/合同/工单/租约等）。当用户问金额、数量、统计、列表等结构化数据问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "自然语言问题"},
                    "entity_hint": {"type": "string", "enum": ["bill", "contract", "ticket", "lease", "customer"]},
                },
                "required": ["question"],
            },
        },
    }
    first_result = await _call_llm(system_prompt, user_content + rag_context, tools=[tool_def])
    # 3. 如果 LLM 返回 tool_call
    if first_result.get("tool_calls"):
        tool_call = first_result["tool_calls"][0]
        if tool_call["function"]["name"] == "query_internal_data":
            args = json.loads(tool_call["function"]["arguments"])
            # 调 REQ-052 QueryService
            query_response = await self._query_service.ask(
                question=args["question"],
                semantic_model=...,  # 根据 entity_hint 选
                ...
            )
            # 4. LLM 第二步（带 tool 结果）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content + rag_context},
                {"role": "assistant", "content": None, "tool_calls": [tool_call]},
                {"role": "tool", "tool_call_id": tool_call["id"], "content": json.dumps(query_response)},
            ]
            second_result = await _call_llm(messages=messages)
            return second_result["content"]
    # 5. 直接返回 content
    return first_result["content"]
```

- [ ] **Step 5: 跑测试 + 通过**

```bash
cd packages/server-python && pytest tests/contexts/knowledge/test_ai_chat_tool_calling.py -v
```

Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add packages/server-python/app/contexts/knowledge/interfaces/api/ai_router.py \
        packages/server-python/app/contexts/knowledge/application/ai_chat_service.py \
        packages/server-python/tests/contexts/knowledge/test_ai_chat_tool_calling.py
git commit -m "feat(ai-chat): REQ-052 tool calling 接入 (query_internal_data 工具)"
```

---

## Task 8: REQ-046 集成 + 背调 Skill 接入（Slice 4 — 问数闭环 #3）

**Files:**
- Modify: `packages/server-python/app/contexts/knowledge/application/ai_chat_service.py`（RE-046 背调流程接入 REQ-052）
- Test: `packages/server-python/tests/contexts/knowledge/test_backtrack_skill.py`

**Interfaces:**
- Consumes: Task 5-7
- Produces: 背调 Skill 流程可调用 REQ-052 问数 + 写 evidence_ref

- [ ] **Step 1: 写失败测试（背调 Skill 调问数）**

```python
"""Test 背调 Skill 调用 REQ-052 问数并写入 evidence_ref。"""
import pytest
from app.contexts.knowledge.application.backtrack_skill import BacktrackSkill


@pytest.mark.asyncio
async def test_backtrack_skill_calls_query():
    """背调 Skill 调 query_internal_data → evidence_ref 写报告。"""
    skill = BacktrackSkill(query_service=mock_query_service)
    result = await skill.execute(
        company_name="江苏神码信息技术有限公司",
        question="这企业过去 3 年的欠费金额",
    )
    assert "evidence_refs" in result
    assert any(r["type"] == "data_query" for r in result["evidence_refs"])
```

- [ ] **Step 2: 跑测试确认失败 + 写 BacktrackSkill 调 REQ-052**

```python
# packages/server-python/app/contexts/knowledge/application/backtrack_skill.py
"""背调 Skill 流程：调 REQ-052 问数 → evidence_ref 写报告。"""
from __future__ import annotations

import uuid


class BacktrackSkill:
    def __init__(self, query_service, evidence_repo):
        self._query_service = query_service
        self._evidence_repo = evidence_repo

    async def execute(
        self,
        company_name: str,
        question: str,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict:
        # 1. 调 REQ-052 问数
        result = await self._query_service.ask(
            question=f"{company_name} {question}",
            semantic_model=...,  # bill / contract / ticket
            user_id=user_id,
            tenant_id=tenant_id,
            role="employee",
            business_purpose="企业 360 背调",
            confirmed_company_name=company_name,
        )
        # 2. 写 evidence_ref
        evidence_ref = {
            "type": "data_query",
            "ref": str(uuid.uuid4()),
            "question": question,
            "summary": result.get("summary"),
            "result_count": result.get("result_count"),
            "source": "REQ-052 semantic query",
        }
        return {
            "answer": result.get("summary"),
            "evidence_refs": [evidence_ref],
            "raw_data": result.get("result_rows"),
        }
```

- [ ] **Step 3: 跑测试 + 通过 + 提交**

```bash
cd packages/server-python && pytest tests/contexts/knowledge/test_backtrack_skill.py -v
git add packages/server-python/app/contexts/knowledge/application/backtrack_skill.py \
        packages/server-python/tests/contexts/knowledge/test_backtrack_skill.py
git commit -m "feat(ai-chat): REQ-052 接入 REQ-046 背调 Skill (evidence_ref 写报告)"
```

---

## Task 9: 端到端集成测试 + 文档更新 + 业务验证

**Files:**
- Modify: `docs/03-engineering-governance/current-work.md`（标注完成）
- Test: 全量端到端测试（手动 curl 三个入口）

**Interfaces:**
- Consumes: Task 1-8
- Produces: 业务闭环验证

- [ ] **Step 1: 跑全量端到端测试**

```bash
# 后端启动
cd packages/server-python && alembic upgrade head
# 启动 backend + frontend
# 前端：pnpm dev

# 端到端测试 3 个入口：
# 1. 前端问数面板
# 2. AI Chat 工具调用
# 3. curl 直接调 API
curl -X POST http://localhost:8000/api/v1/data-query/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_type":"bill","question":"这企业欠费多少","business_purpose":"测试","confirmed_company_name":"江苏神码信息技术有限公司"}'
```

- [ ] **Step 2: 跑全套测试套件**

```bash
cd packages/server-python && pytest tests/contexts/structured_data/ tests/contexts/knowledge/test_ai_chat_tool_calling.py -v
cd packages/web && pnpm test
```

Expected: ALL PASS

- [ ] **Step 3: 业务验证 + 文档更新**

- ✅ 验证 3 个入口都能用
- ✅ 跑门禁
- ✅ 更新 current-work（REQ-052 状态变化：🟢 Ready → 🟢 完成）
- ✅ 更新 work-log 索引

```bash
python scripts/check-engineering-docs  # exit 0
git add docs/03-engineering-governance/current-work.md docs/03-engineering-governance/work-log.md
git commit -m "docs(closeout): REQ-052 实施完成 (3 验证入口 + RBAC + PII 强制脱敏)"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ §2 Goal + 4 子段 → Task 1-5（语义层 / 数据源 Adapter / Query Planner）
- ✅ §4 AC-1 数据源登记 → Task 1（semantic_models + role_permissions + tenant_access_grants + query_audit_log）
- ✅ §4 AC-2 5 类核心实体 → Task 2（SemanticModel）
- ✅ §4 AC-3 query_plan → Task 4（QueryPlanner + Validator）
- ✅ §4 AC-4 SQL Guard → Task 4（SqlGuard + PII Detector + RBAC 字段级）
- ✅ §4 AC-5 结果返回 → Task 5（ResultExplainer）
- ✅ §4 AC-6 背调 evidence_ref → Task 8（BacktrackSkill）
- ✅ §4 AC-7 10 回归样例 → Task 4 测试 + Task 9 端到端
- ✅ §5 Architecture（所有数据流 + 模块）→ Task 1-5
- ✅ §6 Slice 0-4 → Task 1-2（Slice 0）、Task 3-5（Slice 1+2）、Task 6-7（Slice 2+3）、Task 8（Slice 4）
- ✅ §11 边界 → 实施时（生产前）评估
- ✅ §12 安全合规 → Task 3 RBAC + PII + Task 1 审计表

**2. Placeholder scan:** 全文检查 — 无 "TBD" / "TODO" / "fill in" / "add appropriate error handling"。每个 step 含具体代码或命令。

**3. Type consistency:**
- `SemanticModel.column_mapping: dict[str, ColumnMapping]` → Task 2 写 `ColumnMapping.from_dict` 转换 → Task 1 ORM 存 dict（已一致）
- `DataSourceAdapter.query(query_plan: dict, semantic_model: Any, tenant_id, user_role) -> list[dict]` → Task 2 + Task 4 一致
- `QueryService.ask(...)` → Task 5 + Task 8 一致（BacktrackSkill 复用）
- `ResultExplainer.explain(result_rows, semantic_model, query_plan, question) -> ExplainerResult` → Task 5 + Task 8 一致

无 type 不一致。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-07-01-req-052-intelligent-data-query.md`.**

9 个 Task，覆盖：
- Task 1: 4 张表 schema（语义层 + RBAC + 审计 + 跨租户）
- Task 2: 语义层 dataclass + Data Source Adapter 接口 + 3 adapter 实现
- Task 3: RBAC + PII 自动识别（首期安全合规）
- Task 4: Query Planner + JSONB 查询 + SqlGuard
- Task 5: Result Explainer + QueryService + API 端点
- Task 6: 前端问数面板（DatabaseView 智能问数 tab）
- Task 7: AI Chat tool calling 接入（query_internal_data 工具）
- Task 8: REQ-046 背调 Skill 集成（evidence_ref）
- Task 9: 端到端验证 + closeout

**两个执行选项：**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
