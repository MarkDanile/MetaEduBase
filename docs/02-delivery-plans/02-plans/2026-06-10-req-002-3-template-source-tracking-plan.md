# REQ-002-3 模板抽取结果溯源字段扩展 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `extract_template` 落盘的 `structured_data["template"]` 从"仅含 LLM 抽取字段"扩展为"溯源元数据 + LLM 抽取字段"，让"该文档究竟用了哪个模板哪个版本、命中哪一层选择"成为可查事实。决策来源：REQ-002 塑形期 2026-06-10 决议 Q3。

**Architecture:**

- **后端**：
  - `_merge_template_structured_data(existing, template_data, meta=None)` 接受可选 `meta` 参数；`meta` 写入 `merged["template"]` 顶部，保留浅拷贝契约（外层新 dict，内嵌同引用）。
  - `meta` 键白名单：`id` / `version` / `layer` / `matched_type` / `confidence` / `reason`，未知键忽略 + WARNING 日志。
  - `meta` 必须含 `id` / `version` / `layer` 三个核心键才写入，否则回退旧行为 + WARNING 日志。
  - `extract_template` Celery 任务在 template_obj 非 None 且 selection.layer in {"L1", "L2", "L3"} 时构造 meta 并传入。
- **前端**：
  - `ExtractedDataRenderer.vue` 过滤 6 个保留键（不渲染为字段）。
  - `FileDetailView.vue` 模板抽取 Tab 顶部新增溯源元信息卡（老数据不显示）。

**Tech Stack:** Python 3.11+ / pytest 8.3+ / FastAPI / Vue 3 + TypeScript / Vue Query / Tailwind。

**Spec:** `docs/02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md`

**Working dirs:**

- Backend: `packages/server-python`
- Frontend: `packages/web`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `app/contexts/document/application/tasks/extract_template_prompts.py`（修改） | `_merge_template_structured_data` 接受 `meta` 参数 + 键白名单 + 浅拷贝契约 | AC-1 ~ AC-5 |
| `app/contexts/document/application/tasks/extract_template.py`（修改） | 在 `_merge_template_structured_data` 调用前构造 meta，layer == "none" 不传 | AC-6, AC-7 |
| `tests/contexts/document/test_structured_data_contract.py`（修改） | 4 条既有断言按新 shape 更新 + 新增 ≥2 条 meta 路径断言 | AC-8 |
| `tests/contexts/document/test_extract_template_prompts.py`（修改） | 新增 ≥1 条 meta + 嵌套浅拷贝组合用例 | AC-9 |
| `tests/e2e/test_p1_demo.py`（修改） | AC-3 步骤新增 `id` / `layer` 断言 | AC-10 |
| `packages/web/src/views/admin/ExtractedDataRenderer.vue`（修改） | 递归渲染 data 时过滤保留键 | AC-11 |
| `packages/web/src/views/resource/FileDetailView.vue`（修改） | 模板抽取 Tab 顶部新增溯源元信息卡 | AC-12 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md`（修改） | Open Items 加 REQ-002-3 行 | AC-16 |
| `docs/01-product-planning/02-milestones/02-growth-phase.md`（修改） | Open Items 加 REQ-002-3 行 | AC-16 |
| `docs/01-product-planning/04-backlog.md`（修改） | 新建 REQ-002-3 行 | AC-16 |
| `docs/03-engineering-governance/current-work.md`（修改） | REQ-002-3 移入"当前进行中" | AC-16 |

---

## Task 1: 后端 — `_merge_template_structured_data` 接受 `meta` 参数

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py`

- [ ] **Step 1: 修改函数签名与实现**

修改 `_merge_template_structured_data` 签名 + 加入 meta 合并逻辑。**保留旧调用行为**（AC-1 / AC-4）。

```python
# 保留键白名单
_TEMPLATE_META_KEYS = ("id", "version", "layer", "matched_type", "confidence", "reason")
# 核心键（缺失时回退旧行为）
_TEMPLATE_META_CORE_KEYS = ("id", "version", "layer")

def _merge_template_structured_data(
    existing: object,
    template_data: dict[str, object],
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    """Merge template extraction output into the structured_data container.

    meta (REQ-002-3): when provided and contains the core keys
    (id, version, layer), the meta fields are written to the top of
    merged["template"], BEFORE the extracted template_data fields. Keys
    outside _TEMPLATE_META_KEYS are silently dropped (with one WARNING
    log per unknown key). If any core key is missing, meta is ignored
    and the legacy shape is preserved (with one WARNING log).
    """
    if not isinstance(template_data, dict):
        raise TypeError("template_data must be a dict")

    if isinstance(existing, str):
        existing = json.loads(existing)

    if isinstance(existing, dict):
        merged: dict[str, object] = dict(existing)
    else:
        merged = {}

    # 浅拷贝契约：外层新 dict，内嵌 list / dict 仍是同一引用
    template_out: dict[str, object] = {}

    # 1. 决定是否写 meta
    if meta is not None:
        unknown = [k for k in meta if k not in _TEMPLATE_META_KEYS]
        for k in unknown:
            logger.warning(
                "extract_template.merge_template: ignored unknown meta key %r", k
            )
        if all(k in meta for k in _TEMPLATE_META_CORE_KEYS):
            for k in _TEMPLATE_META_CORE_KEYS:
                if k in meta:
                    template_out[k] = meta[k]
            for k in ("matched_type", "confidence", "reason"):
                if k in meta:
                    template_out[k] = meta[k]
        else:
            logger.warning(
                "extract_template.merge_template: meta incomplete "
                "(missing one of %s), falling back to legacy shape",
                _TEMPLATE_META_CORE_KEYS,
            )

    # 2. 写入 LLM 抽取字段（覆盖 meta 同名键 — 防御性，正常不应冲突）
    for k, v in template_data.items():
        template_out[k] = v

    merged["template"] = template_out
    return merged
```

- [ ] **Step 2: 在文件顶部加入 logger**

`extract_template_prompts.py` 当前没有 logger。在 import 块下加：

```python
import logging
logger = logging.getLogger("app.contexts.document.application.tasks")
```

- [ ] **Step 3: 提交**（可与 Task 4 合并提交，单独粒度更易回滚）

```bash
git add packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py
git commit -m "feat(REQ-002-3): accept meta in _merge_template_structured_data"
```

---

## Task 2: 后端 — `extract_template` 在命中模板时构造 meta

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/tasks/extract_template.py`

- [ ] **Step 1: 替换 `_merge_template_structured_data` 调用点**

定位到 `extract_template.py` 第 190 行附近（`existing_data = _merge_template_structured_data(existing_raw, template_data)`）。改为：

```python
# REQ-002-3: 当命中模板（L1/L2/L3）时构造溯源 meta；layer == "none" 不传
meta: dict[str, object] | None = None
if (
    template_obj is not None
    and selection.layer in ("L1", "L2", "L3")
):
    meta = {
        "id": str(template_obj.id),
        "version": getattr(template_obj, "schema_version", None),
        "layer": selection.layer,
        "matched_type": selection.matched_type,
        "confidence": selection.confidence,
        "reason": selection.reason,
    }

existing_data = _merge_template_structured_data(existing_raw, template_data, meta)
```

注意：

- 使用 `getattr(template_obj, "schema_version", None)` 兼容 REQ-002-4 未完成的情况（AC-6 风险 #5）。
- `selection.layer == "none"` 时**不**构造 meta → 走旧路径，行为完全等价（AC-7）。
- `template_obj is None` 时也**不**构造 meta（虽然 `layer == "none"` 已隐含此分支，但显式更清晰）。

- [ ] **Step 2: 提交**（可与 Task 1 合并）

```bash
git add packages/server-python/app/contexts/document/application/tasks/extract_template.py
git commit -m "feat(REQ-002-3): write template id/version/layer to structured_data.template"
```

---

## Task 3: 后端 — 更新 `_merge_template_structured_data` 既有 contract 测试

**Files:**
- Modify: `packages/server-python/tests/contexts/document/test_structured_data_contract.py`

- [ ] **Step 1: 更新 AC-1 `test_merge_template_structured_data_preserves_parse_fields`**

由于本任务不改变"无 meta" 调用路径（AC-1 / AC-4），该测试**应继续通过**。但需要在测试顶部添加注释说明本任务背景，便于未来读者理解。

```python
def test_merge_template_structured_data_preserves_parse_fields() -> None:
    """REQ-002-3: 无 meta 调用保留旧 shape（外层新 dict + 内嵌浅拷贝契约）."""
    existing = {"full_text": "正文", "section_count": 2, "custom": ["keep"]}
    template = {"title": "课程标准", "sections": ["一", "二"]}

    data = _merge_template_structured_data(existing, template)

    assert data == {
        "full_text": "正文",
        "section_count": 2,
        "custom": ["keep"],
        "template": {"title": "课程标准", "sections": ["一", "二"]},
    }
    assert data["template"] is not template
```

（实际仅顶部加 docstring；既有断言不变）

- [ ] **Step 2: 新增 ≥2 条 meta 路径断言**

在文件末尾追加：

```python
# --- REQ-002-3: meta 路径 --------------------------------------------------


def test_merge_template_structured_data_writes_meta_at_top() -> None:
    """REQ-002-3 AC-2: meta 字段写入 template 顶部，data 字段紧随其后。"""
    existing = {"full_text": "正文", "section_count": 1}
    template = {"title": "课程", "sections": ["一"]}
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    data = _merge_template_structured_data(existing, template, meta)

    assert data["template"] == {
        "id": "tmpl-1",
        "version": 1,
        "layer": "L1",
        "title": "课程",
        "sections": ["一"],
    }
    # 顺序：先 meta 后 data
    assert list(data["template"].keys()) == ["id", "version", "layer", "title", "sections"]


def test_merge_template_structured_data_ignores_unknown_meta_keys(caplog) -> None:
    """REQ-002-3 AC-3: 未知 meta 键被忽略 + WARNING 日志。"""
    import logging
    existing = {"full_text": "正文"}
    template = {"title": "课程"}
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1", "foo": "bar"}

    with caplog.at_level(logging.WARNING, logger="app.contexts.document.application.tasks"):
        data = _merge_template_structured_data(existing, template, meta)

    assert "foo" not in data["template"]
    assert any("ignored unknown meta key" in rec.message for rec in caplog.records)


def test_merge_template_structured_data_meta_incomplete_falls_back(caplog) -> None:
    """REQ-002-3 AC-4: meta 缺核心键时回退旧 shape + WARNING 日志。"""
    import logging
    existing = {"full_text": "正文"}
    template = {"title": "课程"}

    # 缺 layer
    with caplog.at_level(logging.WARNING, logger="app.contexts.document.application.tasks"):
        data = _merge_template_structured_data(
            existing, template, {"id": "tmpl-1", "version": 1}
        )

    assert data["template"] == {"title": "课程"}
    assert any("meta incomplete" in rec.message for rec in caplog.records)


def test_merge_template_structured_data_meta_none_legacy_shape() -> None:
    """REQ-002-3 AC-1 / AC-4: meta=None 完全保留旧行为。"""
    existing = {"full_text": "正文"}
    template = {"title": "课程"}

    data = _merge_template_structured_data(existing, template, None)

    assert data == {"full_text": "正文", "template": {"title": "课程"}}


def test_merge_template_structured_data_meta_preserves_shallow_copy() -> None:
    """REQ-002-3 AC-5: meta 写入后内嵌 list / dict 仍同引用。"""
    existing = {"full_text": "正文"}
    template = {
        "teaching_process": [{"step": "1"}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    data = _merge_template_structured_data(existing, template, meta)

    assert data["template"] is not template
    assert data["template"]["teaching_process"] is template["teaching_process"]
    assert data["template"]["teaching_process"][0] is template["teaching_process"][0]
    assert data["template"]["assessment"] is template["assessment"]
    assert data["template"]["assessment"][0] is template["assessment"][0]
    # 核心键写入
    assert data["template"]["id"] == "tmpl-1"
    assert data["template"]["layer"] == "L1"
```

- [ ] **Step 3: 跑测试确认通过**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q
```

Expected：5+ 条既有 + 5 条新 = 10+ passed。

- [ ] **Step 4: 提交**

```bash
git add packages/server-python/tests/contexts/document/test_structured_data_contract.py
git commit -m "test(REQ-002-3): cover meta path in _merge_template_structured_data"
```

---

## Task 4: 后端 — extract_template_prompts 测试覆盖 meta + 嵌套组合

**Files:**
- Modify: `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`

- [ ] **Step 1: 新增 ≥1 条 meta + 嵌套浅拷贝组合用例**

在文件末尾追加：

```python
# --- REQ-002-3: meta + 嵌套浅拷贝组合 --------------------------------------


def test_merge_template_structured_data_with_meta_preserves_nested_shallow_copy() -> None:
    """REQ-002-3 AC-9: meta 存在时，嵌套 list / dict 仍浅拷贝（外层新 dict）。"""
    template_data = {
        "basic_info": {"subject": "语文", "grade": "高一"},
        "teaching_process": [{"step": "导入", "duration": 5}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }
    meta = {"id": "tmpl-1", "version": 1, "layer": "L1"}

    merged = _merge_template_structured_data({}, template_data, meta)

    # 浅拷贝契约
    assert merged["template"] is not template_data
    assert merged["template"]["basic_info"] is template_data["basic_info"]
    assert merged["template"]["teaching_process"] is template_data["teaching_process"]
    assert merged["template"]["teaching_process"][0] is template_data["teaching_process"][0]
    assert merged["template"]["assessment"] is template_data["assessment"]
    # 核心键写入
    assert merged["template"]["id"] == "tmpl-1"
    assert merged["template"]["layer"] == "L1"
```

- [ ] **Step 2: 跑测试确认通过**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q
```

Expected：原有 11 条 + 1 条新 = 12 passed。

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/tests/contexts/document/test_extract_template_prompts.py
git commit -m "test(REQ-002-3): lock meta + nested shallow-copy contract"
```

---

## Task 5: e2e — `test_p1_demo_step3_template_extract` 新增 id/layer 断言

**Files:**
- Modify: `packages/server-python/tests/e2e/test_p1_demo.py`

- [ ] **Step 1: 找到 AC-3 步骤并追加断言**

定位到 `test_p1_demo_step3_template_extract`（grep `template` in that file 已确认在第 346 行附近）。在 `assert template, ...` 后追加：

```python
# REQ-002-3: 溯源元数据
assert "id" in template and isinstance(template["id"], str), (
    f"structured_data.template.id must be present and a string, got {template.get('id')!r}"
)
assert "layer" in template and template["layer"] in {"L1", "L2", "L3"}, (
    f"structured_data.template.layer must be one of L1/L2/L3, got {template.get('layer')!r}"
)
# version 可为 None（REQ-002-4 未完成时）或 int
assert "version" in template, (
    "structured_data.template.version must be present (None if REQ-002-4 not yet done)"
)
```

**注意**：AC-10 要求"不验证具体值"，仅验证存在性 + 类型。

- [ ] **Step 2: 跑 e2e 确认通过（仅 AC-3 步骤，节省时间）**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/e2e/test_p1_demo.py::test_p1_demo_step3_template_extract -q
```

Expected：passed（依赖 conftest.py + Redis broker，参见 `tests/e2e/conftest.py`）。

- [ ] **Step 3: 提交**

```bash
git add packages/server-python/tests/e2e/test_p1_demo.py
git commit -m "test(REQ-002-3): assert template id/layer in P1 demo AC-3"
```

---

## Task 6: 前端 — `ExtractedDataRenderer` 过滤保留键

**Files:**
- Modify: `packages/web/src/views/admin/ExtractedDataRenderer.vue`

- [ ] **Step 1: 在递归渲染入口处过滤保留键**

定位到 `ExtractedDataRenderer.vue` 模板 `<!-- Render a single field value recursively -->` 段。改为：

```vue
<template>
  <!-- Render a single field value recursively -->
  <div class="extracted-data-renderer">
    <!-- Primitive: text / number / textarea -->
    <template v-if="isPrimitiveType">
      <!-- ... 既有代码 ... -->
    </template>
    <!-- ... 既有代码 ... -->

    <!-- REQ-002-3: 过滤 6 个保留键，避免被当作字段渲染 -->
    <template v-for="childField in filteredChildren" :key="childField.key">
      <ExtractedDataRenderer
        :field="childField"
        :data="rawValue"
        :depth="depth + 1"
      />
    </template>
  </div>
</template>
```

在 `<script setup>` 段添加：

```typescript
// REQ-002-3: 6 个保留键不入字段渲染
const RESERVED_META_KEYS = new Set([
  "id",
  "version",
  "layer",
  "matched_type",
  "confidence",
  "reason",
])

const filteredChildren = computed(() => {
  const children = fieldChildren.value ?? []
  return children.filter((f) => !RESERVED_META_KEYS.has(f.key))
})
```

注意：当前 ExtractedDataRenderer 是**单字段递归**（接受 `field` + `data`，按 `field.key` 取 `data[field.key]`），不是按 `data` 自身 keys 遍历。所以保留键风险主要在以下两处：

- `FileDetailView` 模板抽取 Tab 把整个 `file.structured_data.template` 当成"字段集合"渲染时：需要确认是按 Template.fields 列表渲染，还是按 template 自身 keys 渲染。
- 如果按 Template.fields 列表渲染：保留键**不会**进入渲染（因为 fields 列表是用户定义的，不含保留键）。
- 如果按 `Object.keys(template)` 渲染：必须过滤保留键。

**实现选择**：先 grep `FileDetailView.vue` 模板抽取 Tab 调用 ExtractedDataRenderer 的方式。如按 fields 列表调用 → 不需要过滤；按 Object.keys 调用 → 加过滤。当前代码（基于现有 ExtractedDataRenderer 形状）应该是按 `field` prop 单字段递归，由父组件按 Template.fields 列表驱动。

**实操步骤**：

1. 读 `packages/web/src/views/resource/FileTabsPanel.vue`（或 FileDetailView 中调用 ExtractedDataRenderer 的位置）。
2. 确认驱动方式：若按 Template.fields 列表 → ExtractedDataRenderer 内部不需要过滤（保留键不会被作为 field 传入）；在 FileDetailView 顶部元信息卡里读 `template.id` 等。
3. 若按 `Object.keys(template)` 驱动 → ExtractedDataRenderer 必须过滤。

本任务先按"按 fields 列表驱动"假设（最可能）。Task 6 的代码可能最终只需要在 `<script setup>` 中**不**加过滤逻辑；在 commit message 注明"按 fields 列表驱动，无需过滤"。

- [ ] **Step 2: 跑 typecheck + lint**

```bash
cd packages/web && pnpm typecheck
cd packages/web && pnpm lint
```

Expected：exit 0。

- [ ] **Step 3: 提交**

```bash
git add packages/web/src/views/admin/ExtractedDataRenderer.vue
git commit -m "refactor(REQ-002-3): no change needed; renderer is field-driven, reserved keys unreachable"
```

（如果实际需要过滤，按实际情况调整 commit message）

---

## Task 7: 前端 — `FileDetailView` 模板抽取 Tab 新增溯源元信息卡

**Files:**
- Modify: `packages/web/src/views/resource/FileDetailView.vue`
- 或: `packages/web/src/views/resource/FileTabsPanel.vue`（取决于结构化 Tab 实际所在组件）

- [ ] **Step 1: 定位结构化 Tab 渲染位置**

当前 FileDetailView 模板如下：

```vue
<FileTabsPanel
  :active-tab="activeTab"
  :templates="templates"
  :chunks="chunks"
  :kg-nodes="kgNodes"
  ...
  :structured-data="file.structured_data"
  ...
/>
```

结构化 Tab 实际渲染在 `FileTabsPanel.vue`。需要：

1. 读 `packages/web/src/views/resource/FileTabsPanel.vue`。
2. 找到结构化 Tab 渲染处（按 `activeTab === 'structured'` 分支）。
3. 在该处顶部加溯源元信息卡。

- [ ] **Step 2: 在结构化 Tab 顶部新增溯源元信息卡**

```vue
<template v-if="activeTab === 'structured'">
  <!-- REQ-002-3: 溯源元信息卡（仅在 template.id 存在时显示） -->
  <div v-if="templateMeta && templateMeta.id" class="ui-panel-muted p-3 mb-3">
    <div class="flex flex-wrap gap-3 text-[var(--text-small)]">
      <span>
        <span class="text-[var(--color-ink-tertiary)]">模板 ID：</span>
        <code class="text-[var(--color-ink)]">{{ templateMeta.id }}</code>
      </span>
      <span>
        <span class="text-[var(--color-ink-tertiary)]">版本：</span>
        <span class="text-[var(--color-ink)]">{{ templateMeta.version ?? '-' }}</span>
      </span>
      <span v-if="templateMeta.layer !== 'none'">
        <span class="text-[var(--color-ink-tertiary)]">命中：</span>
        <span class="text-[var(--color-ink)] font-medium">{{ templateMeta.layer }}</span>
      </span>
      <span v-else>
        <span class="text-[var(--color-ink-tertiary)]">未命中：</span>
        <span class="text-[var(--color-ink)]">{{ templateMeta.reason || '无匹配模板' }}</span>
      </span>
    </div>
  </div>

  <!-- 既有结构化字段渲染 -->
  <ExtractedDataRenderer
    v-for="field in templateFields"
    :key="field.key"
    :field="field"
    :data="structuredTemplate"
    :depth="0"
  />
</template>
```

- [ ] **Step 3: 在 `<script setup>` 中加 computed**

```typescript
const structuredTemplate = computed<Record<string, unknown>>(() => {
  const sd = props.structuredData
  if (sd && typeof sd === "object" && "template" in sd) {
    return ((sd as Record<string, unknown>).template as Record<string, unknown>) || {}
  }
  return {}
})

const templateMeta = computed(() => {
  const t = structuredTemplate.value
  if (!t || typeof t !== "object") return null
  // REQ-002-3: 仅当有 id 字段才视为"有溯源"；老数据 / layer == "none" 不显示卡
  if (!("id" in t)) return null
  return {
    id: t.id as string,
    version: t.version as number | null,
    layer: (t.layer as string) || "none",
    matched_type: t.matched_type as string | null,
    confidence: t.confidence as number | null,
    reason: t.reason as string | null,
  }
})

const templateFields = computed(() => {
  // 从当前选中的模板（按 structuredTemplate 中字段 key 推测或用 templates 列表第一个）
  // 简化：取 structuredTemplate 的 keys 减去保留键
  const RESERVED = new Set(["id", "version", "layer", "matched_type", "confidence", "reason"])
  const t = structuredTemplate.value
  if (!t) return []
  return Object.keys(t)
    .filter((k) => !RESERVED.has(k))
    .map((k) => ({ key: k, label: k, type: "text" as const }))
})
```

**注意**：实际 templateFields 来源应优先用当前选中的 Template（来自 `templates` prop），由 file.doc_type 匹配。如果实现简单，可先按 structuredTemplate keys 渲染（保 AC-11 + AC-12 验收；后续子任务 REQ-002-1 / REQ-002-3 增量优化）。

- [ ] **Step 4: 跑 typecheck + lint**

```bash
cd packages/web && pnpm typecheck
cd packages/web && pnpm lint
```

Expected：exit 0。

- [ ] **Step 5: 提交**

```bash
git add packages/web/src/views/resource/FileTabsPanel.vue
# 或 FileDetailView.vue，看实际修改位置
git commit -m "feat(REQ-002-3): show template source meta card in structured tab"
```

---

## Task 8: 文档回填

**Files:**
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Modify: `docs/03-engineering-governance/current-work.md`

- [ ] **Step 1: 在 Backlog 新建 REQ-002-3 行**

在 Backlog 表的「REQ-002 Ready」行附近插入（Markdown 链接形式，路径以 docs/01-product-planning/04-backlog.md 为基准）：

```
| REQ-002-3 | REQ | 🔵 Ready | P2 | P2 | 模板抽取结果溯源字段扩展（template.{id, version, layer}） | 先于 REQ-002-1 / REQ-002-2 / REQ-002-4 进入开发；contract 扩展先行；Spec + Plan 已建 | Spec: docs/02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md | Plan: docs/02-delivery-plans/02-plans/2026-06-10-req-002-3-template-source-tracking-plan.md |
```

- [ ] **Step 2: P1 / P2 里程碑 Open Items 加 REQ-002-3 行**

在两个 milestone 的 Open Items 表中各加一行：

```text
| REQ-002-3 | 🟡 Planned | 模板抽取结果溯源字段扩展（template.{id, version, layer}） | [Spec](../../02-delivery-plans/01-specs/2026-06-10-req-002-3-template-source-tracking.md) / [Backlog](../../01-product-planning/04-backlog.md) |
```

- [ ] **Step 3: current-work.md 把 REQ-002-3 移入"当前进行中"**

替换原 REQ-002 候选行（REQ-002 在 REQ-002-3 进入开发后回到 candidate 候选，因为子任务才是进行中项）：

```text
## 当前进行中

| 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
|------|------|--------|------|----------|--------|------|
| REQ-002-3 模板抽取结果溯源字段扩展 | 🟡 Planned | P2 | Backend / Frontend / 可观测性 | spec + plan 已建；分支 `feat/req-002-3-template-source-tracking`；后端 contract 扩展 + e2e 同步 + 前端溯源卡分 8 个 task 落地。 | Task 1-2 后端代码 → Task 3-5 测试 → Task 6-7 前端 → Task 8 文档 | 待运行：pytest / pnpm typecheck / pnpm lint / scripts/check-engineering-docs |

## 下一批候选任务

| 任务 | 状态 | 优先级 | 领域 | 下一步 |
|------|------|--------|------|--------|
| REQ-002-1 模板配置效率（拖拽三层 / 子树复制 / 撤销 / 大模板浏览） | ⚫ Candidate | P2 | Frontend | 等 REQ-002-3 合并后再开 spec |
| REQ-002 模板化结构抽取能力的配置与复用体验（父任务） | 🔵 Ready | P2 | 需求 | 子任务链已开工，塑形决议 Q1~Q6 不变 |
| REQ-001 知识资产处理链路的产品化验收视图 | 🟣 Shaping | P2 | 需求 / 产品化验收 | 澄清目标用户、核心场景和验收指标 |
```

- [ ] **Step 4: 跑工程门禁**

```bash
python3 scripts/check-engineering-docs
```

Expected：`engineering docs checks passed`。

- [ ] **Step 5: 提交**

```bash
git add docs/01-product-planning/04-backlog.md \
        docs/01-product-planning/02-milestones/01-validation-phase.md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(REQ-002-3): register in backlog, milestones, current-work"
```

---

## Task 9: 跑完整回归与门禁

- [ ] **Step 1: 后端 pytest**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/ tests/contexts/template/ tests/e2e/ -q
```

Expected：all passed（e2e 依赖 Redis broker，按 `tests/e2e/conftest.py` 启动）。

- [ ] **Step 2: 后端 ruff**

```bash
cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/ tests/contexts/document/ tests/e2e/
```

Expected：All checks passed!

- [ ] **Step 3: 前端 typecheck + lint**

```bash
cd packages/web && pnpm typecheck
cd packages/web && pnpm lint
```

Expected：exit 0。

- [ ] **Step 4: 工程门禁**

```bash
python3 scripts/check-engineering-docs
git diff --check main...HEAD
```

Expected：`engineering docs checks passed`；`diff --check` 干净。

- [ ] **Step 5: 跑源文件大小基线（TD-032）**

```bash
bash scripts/scan-source-sizes --diff
```

Expected：无超限 / `(no differences from baseline)` 或仅在基线内的差异。

---

## 自检清单

1. **Spec coverage**：逐条检查 spec 16 个 AC，每个都有对应 task 实现。
2. **Placeholder scan**：无 TBD / TODO / 未实现步骤（Task 6 / Task 7 已明确"按 fields 列表驱动，无需过滤"分支）。
3. **Type consistency**：后端 `meta` dict 与 `select_template` 返回字段一致；前端 `templateMeta` 与后端落盘 shape 一致。
4. **行为变化**：仅在命中模板时落盘 meta（layer in {L1,L2,L3} 且 template_obj 非 None）；`layer == "none"` 行为完全等价。
5. **依赖顺序**：REQ-002-3 先于 REQ-002-1 / REQ-002-2 / REQ-002-4；commit 不混入无关文件。
6. **回归**：REQ-005 既有 11 条用例（`_merge_template_structured_data` / `build_fields_desc` / `try_parse`）继续通过；REQ-006 Stage 1.5 e2e 6 步继续通过。
