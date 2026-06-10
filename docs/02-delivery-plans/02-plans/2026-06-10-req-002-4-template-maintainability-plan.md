# REQ-002-4 模板可维护性 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让模板在长期演进中保持可控、可追溯、可告警：schema_version 自增 + 破坏性变更二次确认 + deprecated 标记 + 字段命名规范校验（含 REQ-002-3 保留键冲突校验）。决策来源：REQ-002 塑形期 2026-06-10 决议 Q4 + Q6。

**Architecture:** 跨 backend + frontend。后端：新增 4 个 DB 字段 + Alembic 迁移 + 2 个新端点 + 破坏性变更检测算法 + 校验函数。前端：schema_version 显示 + 容器互转二次确认 + deprecated UI + 字段命名实时校验。

**Tech Stack:** Python 3.11+ / FastAPI + SQLAlchemy 2 / PostgreSQL JSONB / Alembic / Vue 3 + TypeScript / Tailwind CSS 4。

**Spec:** `docs/02-delivery-plans/01-specs/2026-06-10-req-002-4-template-maintainability.md`

**Working dirs:**

- Backend: `packages/server-python`
- Frontend: `packages/web`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `alembic/versions/YYYYMMDDHHMM_add_template_schema_version.py`（新建） | 4 个新字段（schema_version / is_deprecated / deprecated_at / deprecated_reason） | AC-1 |
| `app/contexts/template/domain/entity.py`（修改） | Template dataclass 追加 4 字段 | AC-1 |
| `app/contexts/template/infrastructure/models.py`（修改） | TemplateModel 追加 4 列 | AC-1 |
| `app/contexts/template/application/dto.py`（修改） | DeprecateTemplateRequest + TemplateUpdate 加 force_schema_bump | AC-2 ~ AC-15 |
| `app/contexts/template/application/service.py`（修改） | 破坏性变更检测 + deprecate/undeprecate + _validate_fields | AC-2 ~ AC-15 |
| `app/contexts/template/interfaces/api/router.py`（修改） | 2 新端点 + include_deprecated + 校验路由 | AC-2 ~ AC-15 |
| `app/contexts/document/application/template_selector.py`（修改） | deprecated 跳过逻辑 | AC-10 |
| `tests/contexts/template/test_template_maintainability.py`（新建） | ≥8 条新用例 | AC-25 |
| `packages/web/src/services/template.ts`（修改） | 追加 API + 类型 | AC-22 ~ AC-24 |
| `packages/web/src/views/admin/TemplateListView.vue`（修改） | 弃用按钮 + badge | AC-19 |
| `packages/web/src/views/admin/TemplateEditorView.vue`（修改） | schema_version 显示 + 二次确认 + 恢复使用 + 字段校验 | AC-16 ~ AC-18, AC-20 |
| `packages/web/src/views/admin/FieldCard.vue`（修改） | type 变更触发二次确认 emit | AC-17 |

---

## Task 1: Alembic 迁移 — 新增 4 个字段

**Files:**
- Create: `packages/server-python/alembic/versions/YYYYMMDDHHMM_add_template_schema_version.py`

- [ ] **Step 1: 创建迁移文件**

```python
"""add template schema_version + deprecation fields

Revision ID: <revision_id>
Revises: <prev_revision_id>
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = '<revision_id>'
down_revision = '<prev_revision_id>'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('templates',
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('templates',
        sa.Column('is_deprecated', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('templates',
        sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('templates',
        sa.Column('deprecated_reason', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('templates', 'deprecated_reason')
    op.drop_column('templates', 'deprecated_at')
    op.drop_column('templates', 'is_deprecated')
    op.drop_column('templates', 'schema_version')
```

- [ ] **Step 2: 运行迁移**

```bash
cd packages/server-python && make migrate
```

- [ ] **Step 3: 提交**

---

## Task 2: 后端 — entity / models / dto 追加字段

**Files:**
- Modify: `packages/server-python/app/contexts/template/domain/entity.py`
- Modify: `packages/server-python/app/contexts/template/infrastructure/models.py`
- Modify: `packages/server-python/app/contexts/template/application/dto.py`

- [ ] **Step 1: Template dataclass 追加 4 字段**

```python
@dataclass
class Template:
    # ... existing fields ...
    schema_version: int = 1
    is_deprecated: bool = False
    deprecated_at: datetime | None = None
    deprecated_reason: str | None = None
```

- [ ] **Step 2: TemplateModel 追加 4 列**

```python
schema_version = Column(Integer, nullable=False, default=1)
is_deprecated = Column(Boolean, nullable=False, default=False)
deprecated_at = Column(DateTime(timezone=True), nullable=True)
deprecated_reason = Column(Text, nullable=True)
```

- [ ] **Step 3: TemplateUpdate DTO 追加 force_schema_bump**

```python
class TemplateUpdate(BaseModel):
    # ... existing fields ...
    force_schema_bump: bool = False
```

- [ ] **Step 4: 新增 DeprecateTemplateRequest DTO**

```python
class DeprecateTemplateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
```

- [ ] **Step 5: 提交**

---

## Task 3: 后端 — 破坏性变更检测 + _validate_fields + deprecate/undeprecate

**Files:**
- Modify: `packages/server-python/app/contexts/template/application/service.py`

- [ ] **Step 1: _validate_fields 函数**

```python
import re
from app.contexts.template.domain.entity import Field

# REQ-002-3 contract: reserved meta keys must not appear as field keys
_RESERVED_META_KEYS = frozenset({"id", "version", "layer", "matched_type", "confidence", "reason"})
_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

def _validate_fields(fields: list[dict], parent_path: str = "fields") -> list[str]:
    """Validate field keys recursively. Returns list of error messages."""
    errors: list[str] = []
    seen_keys: set[str] = set()
    for i, f in enumerate(fields):
        key = f.get("key", "")
        path = f"{parent_path}[{i}].key"
        # Reserved key check
        if key in _RESERVED_META_KEYS:
            errors.append(f"{path}={key!r}: reserved meta key (conflicts with REQ-002-3 contract)")
        # Pattern check
        elif not _FIELD_KEY_RE.match(key):
            errors.append(f"{path}={key!r}: must match ^[a-z][a-z0-9_]*$")
        # Duplicate check (same level)
        if key in seen_keys:
            errors.append(f"{path}={key!r}: duplicate sibling key")
        seen_keys.add(key)
        # Recurse
        children = f.get("children") or []
        if children:
            errors.extend(_validate_fields(children, f"{path}.children"))
        items = f.get("items") or []
        if items:
            errors.extend(_validate_fields(items, f"{path}.items"))
    return errors
```

- [ ] **Step 2: 破坏性变更检测函数**

```python
def _detect_destructive_changes(old_fields: list[dict], new_fields: list[dict]) -> bool:
    """Return True if any destructive change that requires schema_version bump."""
    # Flatten old + new recursively for comparison
    def _collect(fields: list[dict], prefix: str = "") -> dict[str, str]:
        result: dict[str, str] = {}
        for f in fields:
            path = f"{prefix}.{f.get('key', '')}"
            result[path] = f.get("type", "text")
            if f.get("children"):
                result.update(_collect(f["children"], path + ".children"))
            if f.get("items"):
                result.update(_collect(f["items"], path + ".items"))
        return result

    old_map = _collect(old_fields)
    new_map = _collect(new_fields)

    # 1. Deleted fields (path in old but not in new)
    if set(old_map) - set(new_map):
        return True

    for path, old_type in old_map.items():
        new_type = new_map.get(path)
        if new_type is None:
            continue  # already caught as deleted

        # 2. Key change (path suffix differs) — handled by deleted+added detection above
        # 3. Container type change: object/table/array mutual conversion
        if old_type != new_type:
            container_types = {"object", "table", "array"}
            leaf_types = {"text", "textarea", "number"}
            if old_type in container_types or new_type in container_types:
                # Any change involving a container type is destructive
                return True
            # leaf <-> leaf (text ⇄ textarea ⇄ number) is NOT destructive
            # Only flag if old + new are both leaf (already handled: return False)

    return False
```

- [ ] **Step 3: TemplateService.update 集成**

```python
async def update(self, template_id: UUID, dto: TemplateUpdate, tenant_id: UUID) -> dict | None:
    existing = await self.repo.get(template_id, tenant_id)
    if not existing:
        return None

    # Detect destructive changes
    old_fields_raw = [f.to_dict() for f in existing.fields]
    new_fields_raw = [f.model_dump() if hasattr(f, "model_dump") else f for f in dto.fields] if dto.fields else old_fields_raw
    is_destructive = _detect_destructive_changes(old_fields_raw, new_fields_raw)

    if is_destructive or dto.force_schema_bump:
        existing.schema_version += 1

    # Apply updates (existing code)
    if dto.name is not None:
        existing.name = dto.name
    # ... rest of existing update logic ...

    # Validate fields
    if dto.fields is not None:
        errors = _validate_fields(new_fields_raw)
        if errors:
            raise ValueError(f"Field validation failed: {'; '.join(errors)}")

    existing.updated_at = datetime.now(timezone.utc)
    await self.repo.update(existing)
    return _entity_to_dto(existing)
```

- [ ] **Step 4: deprecate / undeprecate 方法**

```python
async def deprecate(self, template_id: UUID, reason: str, tenant_id: UUID) -> dict | None:
    existing = await self.repo.get(template_id, tenant_id)
    if not existing:
        return None
    existing.is_deprecated = True
    existing.deprecated_at = datetime.now(timezone.utc)
    existing.deprecated_reason = reason
    existing.updated_at = datetime.now(timezone.utc)
    await self.repo.update(existing)
    return _entity_to_dto(existing)

async def undeprecate(self, template_id: UUID, tenant_id: UUID) -> dict | None:
    existing = await self.repo.get(template_id, tenant_id)
    if not existing:
        return None
    existing.is_deprecated = False
    existing.deprecated_at = None
    existing.deprecated_reason = None
    existing.updated_at = datetime.now(timezone.utc)
    await self.repo.update(existing)
    return _entity_to_dto(existing)
```

- [ ] **Step 5: create / clone / import_template 加 _validate_fields**

在 `create` / `clone` / `import_template` 入口调用 `_validate_fields`。

- [ ] **Step 6: 提交**

---

## Task 4: 后端 — router 新增端点 + include_deprecated + 校验

**Files:**
- Modify: `packages/server-python/app/contexts/template/interfaces/api/router.py`

- [ ] **Step 1: deprecate + undeprecate 端点**

```python
@router.post("/{template_id}/deprecate", response_model=TemplateResponse)
async def deprecate_template(
    template_id: str,
    dto: DeprecateTemplateRequest,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    result = await service.deprecate(UUID(template_id), dto.reason, UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result

@router.post("/{template_id}/undeprecate", response_model=TemplateResponse)
async def undeprecate_template(
    template_id: str,
    service: Annotated[TemplateService, Depends(get_template_service)],
    current_user: Annotated[dict, Depends(get_current_user)],
):
    tenant_id = get_tenant_id()
    result = await service.undeprecate(UUID(template_id), UUID(tenant_id))
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result
```

- [ ] **Step 2: list_templates 加 include_deprecated 参数**

```python
@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    include_deprecated: bool = False,
    service: TemplateService = Depends(get_template_service),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = get_tenant_id()
    templates = await service.list(UUID(tenant_id))
    if not include_deprecated:
        templates = [t for t in templates if not t.get("is_deprecated")]
    return templates
```

- [ ] **Step 3: 422 错误处理**

在 router 层捕获 `ValueError` → 422：

```python
from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# In router or in a shared exception handler:
# @router.exception_handler(ValueError)
# async def value_error_handler(request, exc):
#     return JSONResponse(status_code=422, content={"detail": str(exc)})
```

- [ ] **Step 4: 提交**

---

## Task 5: 后端 — template_selector deprecated 跳过逻辑

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/template_selector.py`

- [ ] **Step 1: 在 select_template 中跳过 deprecated 模板**

在 `select_template` 函数中，L1 / L2 / L3 筛选时过滤 `template.is_deprecated`：

```python
# L1: exact doc_type match — skip deprecated
l1_matches = [t for t in templates if not t.is_deprecated and doc_type in t.doc_types]
if l1_matches:
    return SelectionResult(template=l1_matches[0], layer="L1", ...)

# L2: filename match — skip deprecated
l2_matches = [t for t in templates if not t.is_deprecated and any(...)]
# ... etc
```

- [ ] **Step 2: 确保 deprecated 全清时回退到 L3 / none（不报错）**

如果所有 L1/L2 候选都被 deprecated 且 L3 也无结果 → 走 `layer="none"` 路径（旧行为保持）。

- [ ] **Step 3: 跑既有 REQ-004 测试确认 regressions**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q
```

Expected：既有 9 条全过。

- [ ] **Step 4: 提交**

---

## Task 6: 后端 — 新增 test_template_maintainability.py (≥8 条)

**Files:**
- Create: `packages/server-python/tests/contexts/template/test_template_maintainability.py`

- [ ] **Step 1: 写 8 条用例**

覆盖 AC-2 ~ AC-15 的 8 条核心路径：

1. `test_schema_version_no_bump_leaf_type_change`（AC-2）
2. `test_schema_version_no_bump_add_field`（AC-3）
3. `test_schema_version_bump_container_mutual_conversion`（AC-5）
4. `test_schema_version_bump_delete_field`（AC-6）
5. `test_schema_version_bump_rename_key`（AC-7）
6. `test_deprecate_and_skip_in_select`（AC-9 + AC-10）
7. `test_validate_fields_rejects_reserved_key`（AC-14）
8. `test_validate_fields_rejects_duplicate_sibling_key`（AC-13）

类似 `test_template.py` 现有的 pytest 风格，使用 `client` + `auth_headers` fixture。

- [ ] **Step 2: 跑测试**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template/test_template_maintainability.py -q
```

Expected：≥8 passed。

- [ ] **Step 3: 提交**

---

## Task 7: 前端 — template.ts 追加 API + 类型

**Files:**
- Modify: `packages/web/src/services/template.ts`

- [ ] **Step 1: 追加接口定义**

```typescript
export interface Template {
  // ... existing fields ...
  schema_version: number;
  is_deprecated: boolean;
  deprecated_at: string | null;
  deprecated_reason: string | null;
}

export interface TemplateUpdate {
  // ... existing fields ...
  force_schema_bump?: boolean;
}

export const templateApi = {
  // ... existing methods ...
  deprecate(id: string, data: { reason: string }) {
    return api.post<Template>(`/templates/${id}/deprecate`, data);
  },
  undeprecate(id: string) {
    return api.post<Template>(`/templates/${id}/undeprecate`);
  },
};
```

- [ ] **Step 2: 提交**

---

## Task 8: 前端 — TemplateListView deprecated UI

**Files:**
- Modify: `packages/web/src/views/admin/TemplateListView.vue`

- [ ] **Step 1: 弃用按钮 + 确认框**

卡片右上角（删除 / 复制旁）新增"弃用"按钮（`v-if="!t.is_deprecated"`）；点击弹确认框 `DeprecateConfirmDialog`（含 reason textarea + "确认弃用"/"取消"按钮）。

- [ ] **Step 2: 已弃用 badge**

卡片 `v-if="t.is_deprecated"` 显示"已弃用"灰色 badge；卡片背景浅色。

- [ ] **Step 3: 提交**

---

## Task 9: 前端 — TemplateEditorView maintainability UI

**Files:**
- Modify: `packages/web/src/views/admin/TemplateEditorView.vue`
- Modify: `packages/web/src/views/admin/FieldCard.vue`

- [ ] **Step 1: schema_version 显示**

保存按钮旁（编辑模式）显示 `schema_version: {{ form.schema_version }}`。

- [ ] **Step 2: 容器互转二次确认**

FieldCard type 下拉框 `@change` 时检测：old_type 与 new_type 是否属于容器互转；如是，emit `requestConfirm` 事件；TemplateEditorView 捕获后弹 `ConfirmDestructiveChangeDialog`。

- [ ] **Step 3: 字段删除二次确认**

同 REQ-002-1 撤销 toast：删除前先弹确认框（含"已有抽取结果中该字段会被裁剪"提示）；确认后才删除并弹撤销 toast。

- [ ] **Step 4: 恢复使用按钮**

`v-if="form.is_deprecated"` 显示"恢复使用"按钮，点击调用 `templateApi.undeprecate(id)` 后刷新。

- [ ] **Step 5: 字段命名实时校验**

`field.key` input 在 blur 或 input 事件时校验（保留键 / 非法字符 / 同层重复），校验失败显示红框 + 错误提示；保存按钮在校验失败时禁用。

- [ ] **Step 6: 提交**

---

## Task 10: 文档回填

**Files:**
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Modify: `docs/03-engineering-governance/current-work.md`

- [ ] **Step 1: Backlog REQ-002-4 行**

新建 REQ-002-4 行（🔵 Ready），引用本 spec + plan。

- [ ] **Step 2: P2 里程碑 Open Items 加 REQ-002-4 行**

- [ ] **Step 3: current-work.md REQ-002-4 移入当前进行中**

- [ ] **Step 4: 跑工程门禁**

```bash
python3 scripts/check-engineering-docs
```

Expected：`engineering docs checks passed`。

- [ ] **Step 5: 提交**

---

## Task 11: 完整回归

- [ ] **Step 1: 后端 pytest**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/template tests/contexts/document -q
```

- [ ] **Step 2: 后端 ruff**

```bash
cd packages/server-python && .venv/bin/python -m ruff check app/ tests/
```

- [ ] **Step 3: 前端 typecheck + lint**

```bash
cd packages/web && pnpm typecheck && pnpm lint
```

- [ ] **Step 4: 工程门禁 + 源文件基线**

```bash
python3 scripts/check-engineering-docs
git diff --check main...HEAD
bash scripts/scan-source-sizes --diff
```

- [ ] **Step 5: UI 回归（手测或 e2e）**

---

## 自检清单

1. **Spec coverage**：29 个 AC 全部覆盖。
2. **REQ-002-3 contract 保持**：保留键校验在 service 层，不修改 _merge_template_structured_data。
3. **REQ-002-2 兼容**：clone / import 入口加校验，端点契约不变。
4. **REQ-002-1 兼容**：拖拽排序不触发 schema_version 递增。
5. **破坏性变更检测**：仅跟踪 type / key 变更 + 删除字段；忽略 label / description / 数组顺序。
6. **deprecated 跳过**：select_template 跳过 deprecated，L1/L2 为过滤；全 deprecated 时走 L3/none。
