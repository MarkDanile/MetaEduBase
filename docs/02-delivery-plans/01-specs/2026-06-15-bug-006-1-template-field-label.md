# BUG-006 #1: 模板字段 label 渲染修复（递归查 children + dot-path）

**Date**: 2026-06-15
**Status**: Design — awaiting approval
**Branch**: `fix/bug-006-1-template-field-label`
**Owner**: Claude Code
**Bug source**: [BUG-006 #1](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md)

## 1. Context（背景）

### 1.1 Bug 现象

资源库 → 文件详情 → 结构化抽取 tab 渲染字段名为英文 key 而非中文 label：

```
显示：major_name: 环境监测技术
应示：专业名称: 环境监测技术
```

涉及字段：`major_name` / `degree` / `training_level` / `enrollment_object` / `educational_system` / `teaching_plan` / `practice_links` / `degree_requirements` / `graduation_requirements` / `curriculum_system` / `training_objective` / `basic_info` 等。

### 1.2 真因（已 100% 定位）

**模板 `人才培养方案` 的 fields 数据完整且 label 都填了**（dev PG 真查）：

```
template 50070278-...:
  fields: 7
    - key=basic_info              label=基本信息           type=object
    - key=training_objective      label=培养目标           type=textarea
    - key=graduation_requirements  label=毕业要求           type=table
    - key=curriculum_system        label=课程体系           type=array
    - key=teaching_plan            label=教学计划           type=array
    - key=practice_links           label=实践环节           type=table
    - key=degree_requirements      label=学位要求           type=object
```

**但前端 helper `getFieldLabel` ([FileTabsPanel.vue:216-246](../../../packages/web/src/views/resource/FileTabsPanel.vue)) 存在 3 类问题**：

1. **L218-220 只查 top-level field**：`t.fields.find(f => f.key === key)` — 不会递归查 `field.children[]`，所以 `basic_info.major_name` 这种嵌套字段永远找不到 label
2. **dot-path 不支持**：真实数据中 `basic_info` 是 object 子树（`{"major_name": "环境监测技术", "degree": "-", ...}`），前端 `FieldValue` 渲染嵌套时只传子 key（`String(childKey)` = "major_name"），不会带上 parent 路径
3. **hard-coded map 只覆盖 16 个 legacy course 模板的 top-level key**（`course_name` / `semester` 等），**人才培养方案 / 教案 / 课程标准 模板的 key 一个都没列**——只 fallback `?? key` 返英文

### 1.3 为何模板有 label 但 UI 显示 key

`basic_info` 这个 object 字段在 UI 显示时，先调 `getFieldLabel("basic_info")` → 模板查到 label="基本信息" → 渲染中文 ✓（这一层 OK）。

展开 `basic_info` 内部，UI 渲染子字段 `major_name` 时调 `getFieldLabel("major_name")` → 模板 `fields` 没这个 top-level key → 走 hard-coded map → 没列 → 走 `?? key` → 渲染 "major_name" ✗

## 2. Goal（目标）

- 资源库文件详情 → 结构化抽取 tab 渲染字段名时，**优先用模板配置的 label**，rendering key 仅为最终 fallback
- 至少 90% 字段名展示中文 label（10% 容错给历史模板未填 label / hard-coded map 未列的 key）
- 嵌套对象（如 `basic_info`）的子字段（`major_name`）也能正确查找 label

## 3. Design（设计）

### 3.1 修复策略：递归查 templates（含 children）+ dot-path

**新算法骨架**（`getFieldLabel`）：

```
输入: key (string), prefix (string, optional)
伪代码:
  full_key = prefix ? `${prefix}.${key}` : key

  1. 精确查 top-level field (templates[*].fields[?].key == full_key)
     → return field.label

  2. 递归查 children (templates[*].fields[?].children[?].key == full_key)
     → return found.label

  3. dot-path 拆解: full_key 包含 "."
     first = full_key.split(".")[0]
     rest  = full_key.split(".").slice(1).join(".")
     找 top field with key=first, recurse into its children with key=rest
     → return found.label

  4. hard-coded map fallback (legacy course 模板)

  5. 最终 fallback: return full_key
```

### 3.2 改动文件清单

| File | 改动 | 行数估算 |
|------|------|----------|
| `packages/web/src/views/resource/FileTabsPanel.vue` | 改造 `getFieldLabel` 递归 + dot-path + accept context prefix | ~35 行 (含注释) |
| `packages/web/src/views/resource/FileTabsPanel.vue` | 改 `FieldValue` 嵌套子字段 label 传 `getFieldLabel(childKey, parentKey)` | ~5 行 |
| `packages/web/src/views/resource/FileTabsPanel.spec.ts` | 新增 4 vitest 用例 | ~80 行 |

**仅前端改动**。后端 / alembic / 测试代码 0 改动。

### 3.3 详细实现

#### `getFieldLabel` 改造

改造前（L216-246）：

```typescript
function getFieldLabel(key: string): string {
  // Try to find a template field with matching key
  for (const t of props.templates) {
    const field = t.fields.find((f) => f.key === key);
    if (field) return field.label;
  }
  // Fallback to hard-coded map
  const labels: Record<string, string> = { ... };
  return labels[key] ?? key;
}
```

改造后（伪代码示例，实际 TypeScript 完整版 plan step 给出）：

```typescript
function getFieldLabel(key: string, prefix: string = ""): string {
  const fullKey = prefix ? `${prefix}.${key}` : key;

  // 1. top-level exact match
  for (const t of props.templates) {
    const field = t.fields.find((f) => f.key === fullKey);
    if (field) return field.label;
  }

  // 2. recursive children search
  for (const t of props.templates) {
    const found = findLabelInFields(t.fields, fullKey);
    if (found) return found;
  }

  // 3. dot-path: "basic_info.major_name" → 找 basic_info 然后递归
  if (fullKey.includes(".")) {
    const [first, ...rest] = fullKey.split(".");
    const restPath = rest.join(".");
    for (const t of props.templates) {
      const topField = t.fields.find((f) => f.key === first);
      if (topField?.children) {
        const found = findLabelInFields(topField.children, restPath);
        if (found) return found;
      }
    }
  }

  // 4. hard-coded map (legacy course 模板: course_name / semester / etc.)
  return HARDCODED_LABELS[fullKey] ?? fullKey;
}

function findLabelInFields(
  fields: ReadonlyArray<{ key: string; label: string; children?: ReadonlyArray<{ key: string; label: string }> }>,
  targetKey: string,
): string | null {
  for (const f of fields) {
    if (f.key === targetKey) return f.label;
    if (Array.isArray(f.children)) {
      const found = findLabelInFields(f.children, targetKey);
      if (found) return found;
    }
  }
  return null;
}
```

#### FieldValue 嵌套子字段 label 修正

当前 L22：

```typescript
:label="String(childKey)"  // ← "major_name" 丢失 parent context
```

改为：

```typescript
:label="getFieldLabel(String(childKey), parentKey)"  // parentKey 是父字段的 key
```

需要在 `objectValue` 上下文记录 parent key：

```vue
<FieldValue
  v-for="(childVal, childKey) in objectValue"
  :key="String(childKey)"
  :label="getFieldLabel(String(childKey), label)"  <!-- 'label' 是父 FieldValue 的 props.label（=父字段 key）-->
  ...
/>
```

但 `FieldValue` 的 `props.label` 已经是渲染后的中文（"基本信息"），不是 key。需要在 `FileTabsPanel.vue` 父调用点显式传 `parentKey` 上下文 prop：

更干净的方案：在 `FieldValue.vue` 加一个 `fieldKey: string` prop（默认空），表示"当前 field 在模板 schema 中的 key path"。调用点：

```vue
<!-- FileTabsPanel.vue L51-58 -->
<FieldValue
  v-for="(value, key) in filteredTemplateData"
  :key="key"
  :field-key="String(key)"
  :label="getFieldLabel(String(key))"
  :value="value"
  :depth="0"
/>
```

`FieldValue.vue` 嵌套调用时把父 `fieldKey` + 子 `childKey` 拼成 dot-path 传给 `getFieldLabel`：

```typescript
const props = defineProps<{
  label: string;
  value: unknown;
  depth?: number;
  fieldKey?: string;  // ← 新增
}>();

// 在 object 分支渲染子 FieldValue 时
:field-key="fieldKey ? `${fieldKey}.${String(childKey)}` : String(childKey)"
:label="getFieldLabel(String(childKey), fieldKey ? fieldKey : '')"
```

但 `FieldValue.vue` 在 `views/resource/` 下，**不能 import** `FileTabsPanel.vue` 的私有函数 `getFieldLabel`。需要**提取 `getFieldLabel` 到独立模块**（如 `packages/web/src/utils/templateLabels.ts`），让两边都引用。

#### 模块化方案

新建 `packages/web/src/utils/templateLabels.ts`：

```typescript
// BUG-006 #1: 模板字段 label 解析工具

import type { Template } from "@/services/template";

export interface FieldNode {
  key: string;
  label: string;
  children?: ReadonlyArray<FieldNode>;
}

const HARDCODED_LABELS: Readonly<Record<string, string>> = {
  course_name: "课程名称",
  // ... 16 个 legacy course 模板 key
};

/** Recursively find label in templates' fields tree (including children). */
function findLabelInFields(
  fields: ReadonlyArray<FieldNode>,
  targetKey: string,
): string | null {
  for (const f of fields) {
    if (f.key === targetKey) return f.label;
    if (Array.isArray(f.children)) {
      const found = findLabelInFields(f.children, targetKey);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Resolve a field key to its Chinese label, supporting nested object fields
 * via dot-path (e.g. "basic_info.major_name").
 *
 * Lookup order:
 *   1. Exact match in templates[*].fields (top-level)
 *   2. Recursive search in templates[*].fields[*].children
 *   3. Dot-path split: find top field, then recurse into its children
 *   4. Hard-coded legacy map (course templates)
 *   5. Fallback: return key itself
 */
export function getTemplateFieldLabel(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  key: string,
  prefix: string = "",
): string {
  const fullKey = prefix ? `${prefix}.${key}` : key;

  // 1. top-level exact match
  for (const t of templates) {
    const field = t.fields.find((f) => f.key === fullKey);
    if (field) return field.label;
  }

  // 2. recursive children search
  for (const t of templates) {
    const found = findLabelInFields(t.fields, fullKey);
    if (found) return found;
  }

  // 3. dot-path: split on first ".", find top, recurse
  if (fullKey.includes(".")) {
    const [first, ...rest] = fullKey.split(".");
    const restPath = rest.join(".");
    for (const t of templates) {
      const topField = t.fields.find((f) => f.key === first);
      if (topField?.children) {
        const found = findLabelInFields(topField.children, restPath);
        if (found) return found;
      }
    }
  }

  // 4. hard-coded map
  return HARDCODED_LABELS[fullKey] ?? fullKey;
}
```

`FileTabsPanel.vue` 改：

```typescript
// 旧 (L211-246): 私有函数 getFieldLabel
// 新: import + 包装, 接受 templates prop
import { getTemplateFieldLabel } from "@/utils/templateLabels";

function getFieldLabel(key: string, prefix: string = ""): string {
  return getTemplateFieldLabel(props.templates, key, prefix);
}
```

`FieldValue.vue` 改：加 `fieldKey?: string` prop + 把子 `FieldValue` 的 `fieldKey` 传 `${parentFieldKey}.${childKey}` + `label` 传 `getTemplateFieldLabel(templates, childKey, parentFieldKey)`。

但 `FieldValue.vue` 没有 `templates` prop，需要在 prop list 加 `templates?: ReadonlyArray<...>`。调用点传 `templates` 进来。

### 3.4 简化版本（如果 spec 觉得模块化太重）

如果觉得 `utils/templateLabels.ts` 模块化 + `FieldValue.vue` 加 2 个 prop 太重，可以**保留 `getFieldLabel` 在 `FileTabsPanel.vue` 内部**，但递归子字段查找在 `FileValue` 嵌套子调用时直接传 `getFieldLabel(childKey, parentKey)`。

**推荐走模块化版本**，因为：
- 单一事实源（hard-coded map 只在一处）
- `FieldValue.vue` 是可复用组件，模板字段 label 解析应可被其他 view 复用（未来 admin / KG 视图都需）
- 减少 hard-coded 字段名映射的扩散

### 3.5 vitest 用例设计

新建/修改 `packages/web/src/views/resource/FileTabsPanel.spec.ts`，新增 4 用例：

1. **`renders top-level field label not key`**
   - Mock templates `[{fields: [{key: "title", label: "标题", type: "text"}]}]`
   - 传入 `structuredData: {template: {title: "X"}}`
   - 断言 DOM 含 "标题" 不含 "title:" 文本

2. **`renders nested object field label via dot-path`**
   - Mock templates `[{fields: [{key: "basic_info", label: "基本信息", type: "object", children: [{key: "major_name", label: "专业名称", type: "text"}]}]}]`
   - 传入 `structuredData: {template: {basic_info: {major_name: "环境监测技术"}}}`
   - 断言 DOM 含 "基本信息" 和 "专业名称"，不含 "basic_info:" 或 "major_name:"

3. **`falls back to key when label not configured`**
   - Mock templates `[]`（空）
   - 传入 `structuredData: {template: {some_unconfigured_key: "X"}}`
   - 断言 DOM 含 "some_unconfigured_key"（接受 fallback）
   - 关键: 至少 1 个英文 key 仍显示，证明 fallback 路径

4. **`falls back to hard-coded map for legacy course keys`**
   - Mock templates `[]`（空）
   - 传入 `structuredData: {template: {course_name: "X"}}`
   - 断言 DOM 含 "课程名称" 不含 "course_name:" 文本

### 3.6 真 PG 复测

修复合 main 后维护者跑：

```bash
# 1. 浏览器手测 3 个文件 → 结构化抽取 tab
# 期望:
#   教案 / 课程标准 / 人才培养方案 字段名 90% 渲染中文
#   人才培养方案 basic_info 嵌套下的 6 个子字段全部显示中文 label
# 2. SQL 验证
python3 -c "
import asyncio, json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.shared.infrastructure.database import engine

async def main():
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        r = await session.execute(text(\"\"\"
            SELECT id, name, jsonb_array_length(fields) AS field_count
            FROM metaedu.templates
            WHERE '人才培养方案' = ANY(doc_types)
        \"\"\"))
        for row in r:
            print(f'template {row[0]}: {row[1]}, {row[2]} fields with labels')
asyncio.run(main())
"
# 期望: 输出 template 50070278 + 7 fields
"
```

### 3.7 Out of Scope

- BUG-006 #2 (pdf_parser 中文章节) — 独立 PR
- BUG-006 #3 (TD-067 nested) — 独立 PR
- BUG-006 #5 (返回按钮) — 独立 PR
- 移除/重写 `FieldValue.vue` 整个组件（仅加 1 个 prop + 微调嵌套调用）
- 移除 hard-coded map（保留兼容老 course 模板的 key）
- 国际化 / i18n 框架引入
- 模板编辑器（`FieldEditor.vue` / `TemplateModal.vue`）— 那是 admin view, BUG-006 #1 不涉及
- 后端 / alembic / 后端测试代码

## 4. Validation（验证）

### 4.1 自动化测试

- `pnpm test -- FileTabsPanel` → 4/4 新 vitest 通过
- `pnpm test` → 现有 55+ frontend tests 不退化
- `pnpm typecheck` → 0 errors
- `pnpm lint` → 0 errors

### 4.2 真 PG 复测

- 3 文件 (人才培养方案 / 教案 / 课程标准) 浏览器手测: 字段名 90% 渲染中文
- 嵌套字段 (人才培养方案 basic_info → major_name/degree 等 6 个) 全部显示中文

### 4.3 质量门禁

- `pnpm typecheck / lint / test` 全过
- `git diff --check` clean
- `scripts/check-engineering-docs` 退出码 0
- 后端 pytest 不需跑（无后端改动）

## 5. Risks（风险）

| 风险 | 缓解 |
|------|------|
| hard-coded map 与模板 fields 同时存在时优先级 | 顺序: 1. top-level exact → 2. children → 3. dot-path → 4. hard-coded → 5. fallback。模板优先 hard-coded（更准确）|
| 模板 `field.children` 字段形状差异 | `FieldNode` interface 兼容多种 children 形态（ReadonlyArray）|
| `FieldValue.vue` 加 `fieldKey` + `templates` prop 破坏现有调用 | 2 个 prop 都是 optional，调用点不传也能用（旧 label 行为保留）|
| dot-path 解析错误（多 . 嵌套）| 拆 first. 拆 rest. recurse，符合嵌套 object 实际结构 |
| 递归死循环 | 字段树有界（无 self-reference），TS 类型层强制 |
| FieldValue 是 admin 也用 | 仍兼容，admin 路径不传 templates prop 走原 String(childKey) label 行为 |

## 6. Plan

进入 writing-plans skill 编写实施计划后落地：

1. `fix/bug-006-1-template-field-label` 分支已建（spec commit 0 个，本 spec 是首个 commit）
2. 新建 `packages/web/src/utils/templateLabels.ts` (60 行)
3. 改 `FileTabsPanel.vue` 1 个 import + 1 个包装函数 (5 行)
4. 改 `FieldValue.vue` 加 2 个 optional prop + 1 处嵌套调用 (10 行)
5. 改 `FileTabsPanel.spec.ts` 加 4 vitest (80 行)
6. 跑 pnpm typecheck / lint / test
7. commit + push + PR (fix 分支) → merge
8. 真 PG 复测 (用户)
9. post-merge 收口 PR (docs 分支)
10. 删分支
