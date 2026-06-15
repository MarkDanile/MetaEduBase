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

### 1.1.b Bug 现象（round 2 真 PG 复测补充）

**首次 PR 后用户手测发现 3 类嵌套子表字段仍显示英文**：

| 模板 | 字段路径 | 实测 | 应示 |
|------|---------|------|------|
| 课程标准 | `course_content[].module_name` | `module_name: 项目一` | `模块/项目名称: 项目一` |
| 教案 | `teaching_process[].step_name` | `step_name: 课前任务` | `环节名称: 课前任务` |
| 人才培养方案 | `curriculum_system[].course` | `course: 职业生涯与规划` | `课程: 职业生涯与规划` |

**根因更深一层**：round 1 修复只覆盖 `field.children[]`（object 类型字段的子字段），**不覆盖 `field.items[]`（array 类型的 item 模板）和 `field.columns[]`（table 类型的列定义）**。

### 1.2 真因（已 100% 定位）

**模板 `人才培养方案` 的 fields 数据完整且 label 都填了**（dev PG 真查）：

```
template 50070278-...:
  fields: 7
    - key=basic_info              label=基本信息           type=object
        children: [major_name, degree, training_level, ...]  ← round 1 修
    - key=curriculum_system        label=课程体系           type=array
        items: [{key=course, children: [course_id, course_name, ...]}]  ← round 2 修
    - key=graduation_requirements  label=毕业要求           type=table
        columns: [requirement_id, requirement_content]  ← round 2 修
    - key=teaching_plan            label=教学计划           type=array
        items: [{key=semester, children: [...nested arrays...]}]  ← round 2 修
```

**但前端 helper `getFieldLabel` ([FileTabsPanel.vue:216-246](../../../packages/web/src/views/resource/FileTabsPanel.vue)) 存在 4 类问题**：

1. **L218-220 只查 top-level field**：`t.fields.find(f => f.key === key)` — 不会递归查 `field.children[]`，所以 `basic_info.major_name` 这种嵌套字段永远找不到 label
2. **dot-path 不支持**：真实数据中 `basic_info` 是 object 子树（`{"major_name": "环境监测技术", "degree": "-", ...}`），前端 `FieldValue` 渲染嵌套时只传子 key（`String(childKey)` = "major_name"），不会带上 parent 路径
3. **hard-coded map 只覆盖 16 个 legacy course 模板的 top-level key**（`course_name` / `semester` 等），**人才培养方案 / 教案 / 课程标准 模板的 key 一个都没列**——只 fallback `?? key` 返英文
4. **不查 `field.items[]` (array 模板) 或 `field.columns[]` (table 模板)** — array 类型字段的 item key (e.g. `module_name` / `course`) 和 table 列 key (e.g. `requirement_id`) 全部走 `String(idx + 1)` 或 `String(childKey)` fallback 返英文

### 1.3 为何模板有 label 但 UI 显示 key

`basic_info` 这个 object 字段在 UI 显示时，先调 `getFieldLabel("basic_info")` → 模板查到 label="基本信息" → 渲染中文 ✓（这一层 OK）。

展开 `basic_info` 内部，UI 渲染子字段 `major_name` 时调 `getFieldLabel("major_name")` → 模板 `fields` 没这个 top-level key → 走 hard-coded map → 没列 → 走 `?? key` → 渲染 "major_name" ✗

`curriculum_system` 数组展开后渲染 `curriculum_system[0].course` 字段时，`getFieldLabel` 完全不会查 `field.items[]` 内的 `key` → fallback 返 "course" ✗

`teaching_process[0].step_name` 同理 → 返 "step_name" ✗

## 2. Goal（目标）

- 资源库文件详情 → 结构化抽取 tab 渲染字段名时，**优先用模板配置的 label**，rendering key 仅为最终 fallback
- 至少 90% 字段名展示中文 label（10% 容错给历史模板未填 label / hard-coded map 未列的 key）
- **覆盖 object 子字段 (`field.children[]`)**、**array item 子字段 (`field.items[]`)**、**table 列 (`field.columns[]`)** 三类嵌套
- 嵌套对象（如 `basic_info`）的子字段（`major_name`）也能正确查找 label
- 嵌套 array item key（如 `course_content[].module_name`）也能正确查找 label
- 嵌套 table 列（如 `graduation_requirements[].requirement_id`）也能正确查找 label

## 3. Design（设计）

### 3.1 修复策略：递归查 templates（含 children / items / columns）+ keyPath 数组

**新算法骨架**（`getTemplateFieldLabel`）：

```
输入: templates, keyPath: string[]
  e.g. ["basic_info", "major_name"]                  // object 子字段
  e.g. ["course_content"]                              // array 字段本身 (item 模板)
  e.g. ["course_content", "module_name"]              // array item 内的字段
  e.g. ["teaching_process", "step_name"]              // array item 的 object children
  e.g. ["graduation_requirements", "requirement_id"]  // table 列

伪代码 (keyPath = ["a", "b", "c"]):
  1. 沿 keyPath 在 templates[*].fields 树中走 a → b → c:
     - a: 找 templates[*].fields[?].key == "a"
     - b: 若 field[a] 是 object → 在 field[a].children[?].key == "b" 找
          若 field[a] 是 array  → 在 field[a].items[0] (item 模板):
            - items[0].key == "b" → 命中
            - items[0].children[?].key == "b" → 命中
          若 field[a] 是 table  → 在 field[a].columns[?].key == "b" 找
     - c: 继续在 b 节点的 children/items/columns 树中找
     → 找到 return 找到节点的 label

  2. 兼容老调用 (keyPath.length === 1 时, 等价 dot-path):
     - 精确查 top-level fields[?].key == keyPath[0]
     → 找到 return field.label

  3. 兼容老调用: 递归查 children[] / items[0].children[] / columns[]
     (整个 schema 树单 key 搜, 用于 prefix-style 老 API)
     → 找到 return found.label

  4. 兼容老调用: 拼接 dot-path 走 templates[*].fields[?].key == dotPath
     (用于 prefix-style 老 API)
     → 找到 return found.label

  5. hard-coded map fallback: HARDCODED_LABELS[keyPath.last()] ?? keyPath.join(".")

  6. 最终 fallback: return keyPath.join(".")
```

**为什么用 `keyPath: string[]` 而非 `prefix: string`**：array/table 字段需要从 array 字段本身跳到 items/columns，dot-path string 不能表达这跳转（`course_content.module_name` 会先尝试查 top-level `course_content` 字段的 children `module_name`，但 `module_name` 实际在 `course_content.items[0].key`）。**数组形式的 path 是唯一不歧义的描述方式**。

### 3.2 改动文件清单

| File | 改动 | 行数估算 |
|------|------|----------|
| `packages/web/src/utils/templateLabels.ts` | 重写算法接受 `keyPath: string[]` + 新增 `getFieldNodeAtPath` 辅助 | ~80 行 |
| `packages/web/src/views/resource/FileTabsPanel.vue` | 包装函数 1 个旧 + 1 个新 (`getFieldLabelByPath`); 顶层 FieldValue 改传 `:key-path` | ~15 行净改 |
| `packages/web/src/views/resource/FieldValue.vue` | `fieldKey: string` prop 改为 `keyPath: string[]` + 嵌套调用传 keyPath 数组 | ~10 行净改 |
| `packages/web/src/views/resource/FileTabsPanel.spec.ts` | mount helper 改用 keyPath + 新增 4 vitest (top-level / array item / table column / fallback) | ~80 行 |

**仅前端改动**。后端 / alembic / 测试代码 0 改动。
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
