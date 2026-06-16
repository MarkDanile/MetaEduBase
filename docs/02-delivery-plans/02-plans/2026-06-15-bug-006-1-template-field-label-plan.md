# BUG-006 #1 模板字段 label 渲染修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复资源库 → 文件详情 → 结构化抽取 tab 渲染字段名为英文 key 的问题，让模板已配置 label 的字段（含嵌套 children）显示为中文 label。

**Architecture:** 前端抽取 `getTemplateFieldLabel` 到新模块 `utils/templateLabels.ts`，支持 5 步查找顺序（top-level → 递归 children → dot-path 拆解 → hard-coded map → 原始 key fallback）。`FileTabsPanel.vue` 改用新模块。`FieldValue.vue` 加 2 个 optional prop（`fieldKey` + `templates`）传递嵌套 context。4 个 vitest 用例锁行为。

**Tech Stack:** TypeScript 5 / Vue 3 / vitest / @vue/test-utils / pnpm

**Spec:** `docs/02-delivery-plans/01-specs/2026-06-15-bug-006-1-template-field-label.md`
**Branch:** `fix/bug-006-1-template-field-label` (已创建，spec commit `bc5f55e` 已在分支上)

---

## File Structure

| File | 状态 | 职责 |
|------|------|------|
| `packages/web/src/utils/templateLabels.ts` | 新建 | 公共模块：`getTemplateFieldLabel` + `findLabelInFields` 辅助 + `HARDCODED_LABELS` 常量 (60 行) |
| `packages/web/src/views/resource/FileTabsPanel.vue` | 修改 | 删除 私有 `getFieldLabel` + import 新模块 + 包装 (5 行净改) |
| `packages/web/src/views/resource/FieldValue.vue` | 修改 | 加 `fieldKey?: string` + `templates?: Template[]` 2 个 optional prop + 嵌套子 FieldValue 调用时传 dot-path (10 行) |
| `packages/web/src/views/resource/FileTabsPanel.spec.ts` | 修改 | 新增 4 vitest 用例 (80 行) |
| `docs/01-product-planning/05-requirements/BUG-006-...md` | post-merge | 子项进度 #1 段标 ✅ + 补 PR 链接 |
| `docs/01-product-planning/04-backlog.md` | post-merge | 总览行注 #1 已 Done |
| `docs/03-engineering-governance/work-log.md` | post-merge | 追加长期索引行 |
| `docs/03-engineering-governance/current-work.md` | post-merge | 滚动到 12 行 |

不改：
- 后端任何文件
- `Template` / `Field` 类型定义（已含 `children: Field[]`）
- 其他 view（KnowledgeBaseView / DatabaseView 不涉及）
- `TemplateModal.vue` / `FieldEditor.vue` 等 admin 模板编辑器
- i18n 框架

---

## Task 1: 新建 `utils/templateLabels.ts` 公共模块

**Files:**
- Create: `packages/web/src/utils/templateLabels.ts`

### Step 1: 写完整模块

```typescript
// BUG-006 #1: 模板字段 label 解析工具.
//
// 真因 3 层:
// 1. templates[*].fields 只查 top-level, 不递归 children
// 2. dot-path 不支持 (basic_info.major_name 找不到 label)
// 3. hard-coded map 只列 16 个 legacy course 模板 key
//
// 5 步查找顺序 (优先级递减):
//   1. 模板 fields top-level exact match
//   2. 模板 fields 递归 children 搜索
//   3. dot-path 拆解: fullKey 含 ".", 找 top field, 递归 children
//   4. hard-coded map (legacy course 模板)
//   5. fallback: return fullKey 本身

import type { Template, Field } from "@/services/template";

/** 硬编码 label: 历史 course 模板 (course_name / semester 等 16 个) 在 templates
 * 表里没有显式 label, 但前端要继续显示中文. 这些是历史数据, 保留兼容. */
const HARDCODED_LABELS: Readonly<Record<string, string>> = {
  course_name: "课程名称",
  course_code: "课程代码",
  semester: "授课学期",
  department: "开课单位",
  teacher: "主讲教师",
  target_class: "授课班级",
  total_hours: "课程总学时",
  theory_hours: "理论学时",
  practice_hours: "实践学时",
  exam_mode: "考核方式",
  textbook: "教材及参考书",
  course_description: "课程简介",
  teaching_objectives: "教学目标",
  teaching_content_outline: "教学内容纲要",
  teaching_schedule: "教学进度安排",
  evaluation_plan: "课程评价方案",
  title: "文档标题",
  summary: "摘要",
  sections: "主要章节",
  keywords: "关键词",
};

/** 递归在 fields 树中查找 targetKey 对应的 label. */
function findLabelInFields(
  fields: ReadonlyArray<Field>,
  targetKey: string,
): string | null {
  for (const f of fields) {
    if (f.key === targetKey) return f.label;
    if (Array.isArray(f.children) && f.children.length > 0) {
      const found = findLabelInFields(f.children, targetKey);
      if (found) return found;
    }
  }
  return null;
}

/**
 * 解析一个 field key 到对应的中文 label, 支持嵌套对象字段 (dot-path 形如
 * "basic_info.major_name").
 *
 * @param templates 模板数组 (通常传整个 useTemplatesQuery 返的列表)
 * @param key 单层 key (例如 "major_name")
 * @param prefix 父字段 key 上下文 (例如 "basic_info"), 用于构造 dot-path
 * @returns 模板配置的 label, 或 hard-coded map 的中文, 或最终 fallback 到 fullKey
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

  // 2. recursive children search (在所有 templates 的 fields 树里)
  for (const t of templates) {
    const found = findLabelInFields(t.fields, fullKey);
    if (found) return found;
  }

  // 3. dot-path: "basic_info.major_name" -> 找 basic_info 然后递归 children
  if (fullKey.includes(".")) {
    const [first, ...rest] = fullKey.split(".");
    const restPath = rest.join(".");
    for (const t of templates) {
      const topField = t.fields.find((f) => f.key === first);
      if (topField?.children && topField.children.length > 0) {
        const found = findLabelInFields(topField.children, restPath);
        if (found) return found;
      }
    }
  }

  // 4. hard-coded map (legacy course 模板兼容)
  return HARDCODED_LABELS[fullKey] ?? fullKey;
}
```

### Step 2: typecheck

```bash
cd packages/web && pnpm typecheck 2>&1 | tail -10
```

Expected: 0 errors (新文件，未被引用时 typecheck 也 OK)。

### Step 3: Commit (公共模块)

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/web/src/utils/templateLabels.ts
git commit -m "feat(web): BUG-006 #1 add getTemplateFieldLabel utility module

- 5-step lookup: top-level exact -> recursive children -> dot-path split
  -> hard-coded map -> raw key fallback
- HARDCODED_LABELS: 16 legacy course 模板 keys (course_name / semester
  / title / etc.) for backwards compat
- 支持嵌套对象字段: basic_info.major_name -> basic_info.label + 递归查
  basic_info.children.label
- FieldNode 类型借 Template.fields 已有 children: Field[] 不重新定义"
```

---

## Task 2: `FileTabsPanel.vue` 切换到新模块

**Files:**
- Modify: `packages/web/src/views/resource/FileTabsPanel.vue:1-30` (imports) + `211-246` (私有函数删除 + 包装)

### Step 1: 删除私有 getFieldLabel + 用新模块包装

打开 `FileTabsPanel.vue`。

找到 import 块（顶部），在 `import { ChevronRight } from "lucide-vue-next"` 等之间**加一行**：

```typescript
import { getTemplateFieldLabel } from "@/utils/templateLabels";
```

找到当前 L211-246 私有 `getFieldLabel` + 注释块，**整段替换**为：

```typescript
// --- Structured data helpers (private to this component) ---
// BUG-006 #1: 委托给 utils/templateLabels.ts 公共模块 (含 children 递归 + dot-path)
function getFieldLabel(key: string, prefix: string = ""): string {
  return getTemplateFieldLabel(props.templates, key, prefix);
}
```

### Step 2: typecheck

```bash
cd packages/web && pnpm typecheck 2>&1 | tail -5
```

Expected: 0 errors. (`Field` / `Template` 类型已从 `@/services/template` 导入; 新模块用 `Pick<Template, "fields">` 兼容)

### Step 3: Commit

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/web/src/views/resource/FileTabsPanel.vue
git commit -m "refactor(web): BUG-006 #1 FileTabsPanel 切换到 getTemplateFieldLabel 公共模块

- 删除 30 行私有 getFieldLabel + 16 行 hard-coded map
- 包装函数 4 行委托到 utils/templateLabels
- 行为不变 (现有字段渲染结果一致), 但 nested children 字段能正确显示中文"
```

---

## Task 3: `FieldValue.vue` 加 `fieldKey` + `templates` optional props

**Files:**
- Modify: `packages/web/src/views/resource/FieldValue.vue:60-75` (script props) + `18-26` (object 分支嵌套调用) + `39-58` (array 分支嵌套调用)

### Step 1: 加 2 个 optional prop

打开 `FieldValue.vue`，找到现有 props 定义（L66-70）：

```typescript
const props = defineProps<{
  label: string;
  value: unknown;
  depth?: number;
}>();
```

替换为：

```typescript
const props = defineProps<{
  label: string;
  value: unknown;
  depth?: number;
  // BUG-006 #1: nested 字段 label 解析需要 父字段 key (构建 dot-path)
  // + 当前 templates 列表 (查 children.label)
  fieldKey?: string;
  templates?: ReadonlyArray<import("@/services/template").Template>;
}>();
```

### Step 2: 改造 object 分支嵌套调用 (L18-26)

找到现有：

```vue
<div v-else-if="isObject" class="field-object">
  <div class="field-group-header" @click="expanded = !expanded">
    <span class="field-label">{{ label }}</span>
    <span class="field-toggle">
      <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
      <span class="text-xs" style="color: var(--color-ink-tertiary)">{{ expanded ? '收起' : '展开' }}</span>
    </span>
  </div>
  <div v-if="expanded" class="field-children">
    <FieldValue
      v-for="(childVal, childKey) in objectValue"
      :key="String(childKey)"
      :label="String(childKey)"
      :value="childVal"
      :depth="depth + 1"
    />
  </div>
</div>
```

替换为（**只改嵌套 FieldValue 调用**，其他不变）：

```vue
<div v-else-if="isObject" class="field-object">
  <div class="field-group-header" @click="expanded = !expanded">
    <span class="field-label">{{ label }}</span>
    <span class="field-toggle">
      <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
      <span class="text-xs" style="color: var(--color-ink-tertiary)">{{ expanded ? '收起' : '展开' }}</span>
    </span>
  </div>
  <div v-if="expanded" class="field-children">
    <FieldValue
      v-for="(childVal, childKey) in objectValue"
      :key="String(childKey)"
      :label="templates && fieldKey
        ? getTemplateFieldLabel(templates, String(childKey), fieldKey)
        : String(childKey)"
      :field-key="fieldKey ? `${fieldKey}.${String(childKey)}` : String(childKey)"
      :templates="templates"
      :value="childVal"
      :depth="depth + 1"
    />
  </div>
</div>
```

### Step 3: 改造 array 分支嵌套调用 (L39-58)

找到：

```vue
<FieldValue
  :label="String(idx + 1)"
  :value="item"
  :depth="depth + 2"
/>
```

替换为（array 的子项 label 通常是 index，不传 fieldKey 也合理；保持兼容）：

```vue
<FieldValue
  :label="String(idx + 1)"
  :field-key="fieldKey"
  :templates="templates"
  :value="item"
  :depth="depth + 2"
/>
```

注: array branch 子项 label 是 String(idx + 1) 索引号，**不传 dot-path**（因为 array 元素是 anonymous objects，没有 schema-defined field key）。**但仍传 templates 透传**让更深层的 object 子字段能继续递归。

### Step 4: 顶部 import 增 getTemplateFieldLabel

修改顶部 import 块：

```typescript
import { ref, computed } from 'vue';
import { ChevronDown, ChevronRight } from 'lucide-vue-next';
import { getTemplateFieldLabel } from '@/utils/templateLabels';
```

### Step 5: typecheck + lint

```bash
cd packages/web && pnpm typecheck 2>&1 | tail -5
cd packages/web && pnpm lint 2>&1 | tail -5
```

Expected: 0 errors. 如果有 `import type` 提示用 `type` 关键字（TypeScript 推荐 `import { type Foo }`），可以替换；但 vue-tsc 应该能容忍普通 import 别名。

### Step 6: 跑现有测试确认 0 回归

```bash
cd packages/web && pnpm test 2>&1 | tail -10
```

Expected: 现有 FileTabsPanel.spec.ts 测试 + 55+ 其他测试全过。**无回归**（新 prop 是 optional，旧调用点不传也能工作）。

### Step 7: Commit

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/web/src/views/resource/FieldValue.vue
git commit -m "feat(web): BUG-006 #1 FieldValue 加 fieldKey + templates 传递嵌套 context

- fieldKey: 父字段 key (如 'basic_info'), 用于构造 dot-path
- templates: 整个 templates 列表, 让子 FieldValue 能继续查 children.label
- object branch: 子 FieldValue label 用 getTemplateFieldLabel + 传 dot-path
- array branch: 透传 templates + fieldKey (子项 label 仍是 idx+1)
- 2 个 prop 都 optional, admin 等老调用点零影响"
```

---

## Task 4: 4 vitest 用例 (TDD red → green)

**Files:**
- Modify: `packages/web/src/views/resource/FileTabsPanel.spec.ts`

### Step 1: 改 mountFileTabsPanel helper 接受 templates 参数

找到现有 helper（L29-47）：

```typescript
function mountFileTabsPanel(structuredData: unknown) {
  // 默认 props: 聚焦于结构化抽取 tab; 其他 tab 的数据留空以避免无关噪声.
  const emptyChunks: ChunkDTO[] = [];
  const emptyNodes: KnowledgeNodeDTO[] = [];
  const emptyEdges: KnowledgeEdgeDTO[] = [];
  const emptyTemplates: Template[] = [];
  return mount(FileTabsPanel, {
    props: {
      activeTab: "structured",
      templates: emptyTemplates,
      chunks: emptyChunks,
      chunksLoading: false,
      kgNodes: emptyNodes,
      kgEdges: emptyEdges,
      kgLoading: false,
      structuredData,
    },
  });
}
```

替换为：

```typescript
function mountFileTabsPanel(
  structuredData: unknown,
  templates: Template[] = [],
) {
  // 默认 props: 聚焦于结构化抽取 tab; 其他 tab 的数据留空以避免无关噪声.
  const emptyChunks: ChunkDTO[] = [];
  const emptyNodes: KnowledgeNodeDTO[] = [];
  const emptyEdges: KnowledgeEdgeDTO[] = [];
  return mount(FileTabsPanel, {
    props: {
      activeTab: "structured",
      templates,
      chunks: emptyChunks,
      chunksLoading: false,
      kgNodes: emptyNodes,
      kgEdges: emptyEdges,
      kgLoading: false,
      structuredData,
    },
  });
}
```

### Step 2: 追加 4 个新 describe 块

在文件末尾**追加 4 个新 describe 块**（保持现有 TD-040 AC-11/AC-12 describe 块不变）：

```typescript
describe("BUG-006 #1: 模板字段 label 渲染", () => {
  it("renders top-level field label not key", () => {
    // Mock 模板 fields: {key: "title", label: "标题", type: "text"}
    const templates: Template[] = [
      {
        id: "t1",
        name: "教案",
        doc_types: ["教案"],
        ai_prompt: null,
        ai_context: null,
        source_file_id: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
        fields: [
          { key: "title", label: "标题", type: "text" },
        ],
      },
    ];
    const structuredData = { template: { title: "数学教案" } };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 渲染 "标题" 不含 "title:" 文本
    expect(wrapper.text()).toContain("标题");
    expect(wrapper.text()).toContain("数学教案");
    expect(wrapper.text()).not.toContain("title:");
  });

  it("renders nested object field label via dot-path", () => {
    // Mock 模板 fields: basic_info 嵌套 major_name / degree
    const templates: Template[] = [
      {
        id: "t2",
        name: "人才培养方案",
        doc_types: ["人才培养方案"],
        ai_prompt: null,
        ai_context: null,
        source_file_id: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
        fields: [
          {
            key: "basic_info",
            label: "基本信息",
            type: "object",
            children: [
              { key: "major_name", label: "专业名称", type: "text" },
              { key: "degree", label: "学位", type: "text" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        basic_info: { major_name: "环境监测技术", degree: "-" },
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 父 "基本信息" + 子 "专业名称" / "学位" 都渲染
    expect(wrapper.text()).toContain("基本信息");
    expect(wrapper.text()).toContain("专业名称");
    expect(wrapper.text()).toContain("环境监测技术");
    expect(wrapper.text()).toContain("学位");
    // 关键: 不含原始 key
    expect(wrapper.text()).not.toContain("major_name:");
    expect(wrapper.text()).not.toContain("degree:");
  });

  it("falls back to key when label not configured", () => {
    const templates: Template[] = [];  // 模板空
    const structuredData = {
      template: { some_unconfigured_key: "X" },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 接受 fallback: 字段名显示原始 key (不抛错)
    expect(wrapper.text()).toContain("some_unconfigured_key");
    expect(wrapper.text()).toContain("X");
  });

  it("falls back to hard-coded map for legacy course keys", () => {
    const templates: Template[] = [];  // 模板空, 但 hard-coded map 兜底
    const structuredData = {
      template: { course_name: "数学" },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 即使模板无 fields, 走 hard-coded map 仍能显示 "课程名称"
    expect(wrapper.text()).toContain("课程名称");
    expect(wrapper.text()).toContain("数学");
    expect(wrapper.text()).not.toContain("course_name:");
  });
});
```

### Step 3: 跑测试, 期望 4/4 PASS (TDD green, Task 1-3 已实现)

```bash
cd packages/web && pnpm test 2>&1 | tail -15
```

Expected: 4/4 新 vitest pass + 现有测试全过。

**STOP 检查点**：如果 fail：
- "renders nested object field label via dot-path" fail → 检查 FieldValue.vue 嵌套 FieldValue 的 `field-key` / `templates` 透传是否到位
- "falls back to hard-coded map" fail → 检查 templateLabels.ts HARDCODED_LABELS 包含 `course_name` 键
- typecheck fail → import 路径错

### Step 4: 跑 lint

```bash
cd packages/web && pnpm lint 2>&1 | tail -5
```

Expected: 0 errors.

### Step 5: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/web/src/views/resource/FileTabsPanel.spec.ts
git commit -m "test(web): BUG-006 #1 lock 4 invariants for template field label rendering

1. top-level field label rendered (not key)
2. nested object field label via dot-path (basic_info.major_name)
3. fallback to raw key when no template configures label
4. hard-coded map covers legacy course template keys (course_name)

mountFileTabsPanel 加 templates 参数, 现有 8 TD-040 AC-11/12 测试不变"
```

---

## Task 5: 整体质量门禁

**Files:** 无修改（仅运行命令）

### Step 1: 前端 typecheck + lint + test

```bash
cd packages/web && pnpm typecheck 2>&1 | tail -3
cd packages/web && pnpm lint 2>&1 | tail -3
cd packages/web && pnpm test 2>&1 | tail -5
```

Expected: 全过。

### Step 2: 工程治理门禁

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && \
  scripts/check-engineering-docs 2>&1 | tail -3
git diff --check
```

Expected: exit 0 / clean。

### Step 3: 后端 pytest 没必要跑（无后端改动）

Skip — 本任务纯前端。

---

## Task 6: 真 PG 复测验收

**Files:** 无修改（运维操作）

### Step 1: 确认 dev FastAPI server 仍在跑且加载最新代码

```bash
ps -o etime,command -p 5460 2>&1 | tail -2
```

如有：dev server 跑 11h+ 仍可能，uvicorn --reload 会自动 reload 前端不需要它（前端 dev server 单独跑）。

### Step 2: 浏览器手测 3 个文件

1. 资源库 → 人才培养方案文件 → 结构化抽取 tab
   - 期望: 至少 6 个 basic_info 子字段全部显示中文（"专业名称" / "学位" / "培养层次" / "招生对象" / "学制"）
   - 其他顶层字段: "培养目标" / "课程体系" / "教学计划" / "实践环节" / "毕业要求" / "学位要求" 全中文
2. 资源库 → 教案文件 → 同 tab
   - 期望: 模板字段名中文
3. 资源库 → 课程标准文件 → 同 tab
   - 期望: 模板字段名中文

### Step 3: 验收标准

- 3 文件字段名 90% 渲染中文
- 不再看到 `major_name:` / `degree:` 等英文 key 显示（除非模板确实未配置 label 的字段）
- Console 无 vue/runtime error

### Step 4: 验收不通过的处理

如果仍有英文 key 显示：
- 浏览器 DevTools → Vue DevTools → FileTabsPanel 组件 → 检查 `props.templates` 是不是 3 个文件匹配模板都正确传进去
- 如果 templates 为空（vue query 还没加载）→ 走 hard-coded map（course_name 等会中文化，但人才培养方案 key 仍 fallback 英文）
- 如果 templates 有但 children 仍空 → 检查后端 `select_template` 是否正确返回 7 fields

---

## Task 7: 创建 PR + squash merge

**Files:** 无修改（Git 操作）

### Step 1: push

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git push origin fix/bug-006-1-template-field-label 2>&1 | tail -3
```

### Step 2: 创建 PR

```bash
gh pr create --base main --head fix/bug-006-1-template-field-label \
  --title "fix(web): BUG-006 #1 模板抽取页面字段名渲染为 label (递归查 children + dot-path)" \
  --body "$(cat <<'EOF'
## Summary

修复资源库 → 文件详情 → 结构化抽取 tab 渲染字段名为英文 key 而非中文 label 的问题。模板已配置 label 字段（含嵌套 children）应显示中文。

## 真因（3 层）

1. \`FileTabsPanel.vue\` 的 \`getFieldLabel\` 只查 templates fields top-level, 不递归 children
2. dot-path 不支持 (basic_info.major_name 永远找不到 label)
3. hard-coded map 只列 16 个 legacy course 模板 key, 人才培养方案/教案/课程标准 key 一个没列

## 改动

| 类型 | 文件 | 行数 |
|------|------|------|
| 新建公共模块 | \`utils/templateLabels.ts\` | 100 |
| 改 wrapper 函数 | \`FileTabsPanel.vue\` | 30 删 / 5 增 |
| 加 2 个 prop + 嵌套调用 | \`FieldValue.vue\` | 10 增 |
| 加 4 vitest | \`FileTabsPanel.spec.ts\` | 80 增 |

## 5 步查找顺序

1. top-level exact match (templates[*].fields[?].key == fullKey)
2. recursive children search (templates[*].fields[*].children[*])
3. dot-path split (fullKey 含 \`.\` 时拆 first / rest, 找 top + 递归)
4. hard-coded map fallback (legacy course 模板)
5. fallback: return fullKey

## Validation

- 4/4 新 vitest pass: top-level / nested dot-path / fallback key / hard-coded map
- 现有 55+ frontend tests 0 退化
- pnpm typecheck / lint clean
- scripts/check-engineering-docs exit 0
- git diff --check clean

## 真 PG 复测（post-merge, 浏览器手测）

- 人才培养方案文件: basic_info 下 6 个子字段全部中文 (专业名称/学位/培养层次/招生对象/学制)
- 教案 / 课程标准: 模板字段名 90% 中文
- Console 无 vue/runtime error

## 不破坏既有

- 2 个新 prop (\`fieldKey\` + \`templates\`) 都 optional, admin 老调用点零影响
- Hard-coded map 保留兼容 legacy course 模板
- 现有 TD-040 AC-11/AC-12 测试不变 (mountFileTabsPanel 仍支持 templates=[] 默认值)

## Out of Scope

- BUG-006 #2 (pdf_parser 中文章节) / #3 (TD-067 nested) / #5 (返回按钮) 各自独立 PR
- i18n 框架引入
- 模板编辑器 admin 视图
- 后端 / alembic 任何文件

## Docs

- spec: \`docs/02-delivery-plans/01-specs/2026-06-15-bug-006-1-template-field-label.md\`
- plan: \`docs/02-delivery-plans/02-plans/2026-06-15-bug-006-1-template-field-label-plan.md\`
- post-merge 收口 PR 单独提交
EOF
)" 2>&1 | tail -3
```

### Step 3: squash merge

```bash
gh pr merge <PR_NUMBER> --squash --delete-branch 2>&1 | tail -3
```

### Step 4: 同步 main

```bash
git checkout main && git pull --ff-only 2>&1 | tail -2
git log --oneline -3
```

---

## Task 8: Post-merge 跨事实源收口 (docs-only PR)

**Files:**
- Modify: `docs/01-product-planning/05-requirements/BUG-006-...md` (子项进度 #1 段补 PR 链接)
- Modify: `docs/01-product-planning/04-backlog.md` (BUG-006 总览行注 #1 已 Done)
- Modify: `docs/03-engineering-governance/work-log.md` (追加长期索引行)
- Modify: `docs/03-engineering-governance/current-work.md` (滚动到 12 行)

### Step 1: 建 docs 分支

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git checkout -b docs/bug-006-1-post-merge main
```

### Step 2: 修改 BUG-006 任务卡

在 `docs/01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md` 找到 `## 子项进度` 段（L192-200 区域），把 `- 🔵 #1 前端字段名英文（待开发）` 改为：

```markdown
- ✅ **#1 前端字段名英文** — [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) (squash `<COMMIT>`) 已合并：抽取 `getTemplateFieldLabel` 到 `utils/templateLabels.ts` 公共模块，5 步查找顺序（top-level → 递归 children → dot-path 拆解 → hard-coded map → 原始 key fallback）；`FieldValue.vue` 加 `fieldKey` + `templates` 2 个 optional prop 传递嵌套 context；4 vitest 用例锁不变量（top-level label / nested dot-path / fallback key / hard-coded map）。浏览器手测人才培养方案 6 个子字段全部中文。
```

### Step 3: 修改 backlog.md BUG-006 总览行

在 `docs/01-product-planning/04-backlog.md` 找到 BUG-006 行，把「**进度**：#4 KG > 50 节点白屏已修」改为「**进度**：#1/#4 已修」+ 补 PR 链接：

```
**进度**：#1 前端字段名 label + #4 KG > 50 节点白屏已修（[PR #295](https://github.com/MarkDanile/MetaEduBase/pull/295)）。
```

### Step 4: 修改 work-log.md 追加长期索引

在 `docs/03-engineering-governance/work-log.md` 顶部（按"最近优先"）追加：

```markdown
| 2026-06-15 | BUG-006 #1 模板抽取页面字段名渲染为 label（递归 children + dot-path） | [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) | 抽 getTemplateFieldLabel 到 utils/templateLabels.ts 公共模块 5 步查找；FieldValue.vue 加 fieldKey + templates optional prop 透传嵌套 context；4 vitest 锁不变量（top-level / nested dot-path / fallback key / hard-coded map）；前端 pnpm typecheck/lint/55+ tests 全 pass；浏览器手测人才培养方案 6 子字段全部中文。 |
```

### Step 5: 修改 current-work.md 滚动到 12 行

在 `docs/03-engineering-governance/current-work.md` 顶部追加 1 行（如果已 ≥ 12 行则删最末 1 行）：

```markdown
| 2026-06-15 | BUG-006 #1 模板抽取页面字段名渲染 label（递归 children + dot-path）| 🟢 完成 | PR #<NUMBER> squash merge：抽 getTemplateFieldLabel 到 utils/templateLabels.ts 5 步查找；FieldValue.vue 加 fieldKey + templates optional prop。4 vitest + 55+ frontend tests 0 回归。 | [BUG-006 #1](../../01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md) / [PR #<NUMBER>](https://github.com/MarkDanile/MetaEduBase/pull/<NUMBER>) |
```

**摘要 ≤ 220 字符**：上方约 195 字符，OK。

### Step 6: 跑门禁

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
scripts/check-engineering-docs 2>&1 | tail -3
git diff --check
```

Expected: exit 0 / clean。

### Step 7: Commit + push + PR + squash merge

```bash
git add docs/01-product-planning/05-requirements/BUG-006-resource-library-display-and-section-meta-and-kg-link.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/work-log.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(governance): BUG-006 #1 跨事实源收口（🟢 完成 + work-log 索引）"
git push origin docs/bug-006-1-post-merge

gh pr create --base main --head docs/bug-006-1-post-merge \
  --title "docs(governance): BUG-006 #1 跨事实源收口（🟢 完成 + work-log 索引）" \
  --body "## Summary
- BUG-006 任务卡子项进度 #1 段标 ✅ + 补 PR 链接
- backlog 总览行注 #1 已修
- work-log 追加长期索引行
- current-work 滚动到 12 行

## Validation
- scripts/check-engineering-docs exit 0
- git diff --check clean
- 0 业务代码 / 0 测试代码 / 0 脚本变更（docs-only）"

gh pr merge <PR_NUMBER> --squash --delete-branch
git checkout main && git pull --ff-only
```

---

## Self-Review

### 1. Spec coverage

✅ 全覆盖：
- spec §3.1 修复策略 → Task 1+2+3
- spec §3.3 getFieldLabel 5 步查找 → Task 1
- spec §3.5 vitest 4 用例 → Task 4
- spec §3.6 真 PG 复测 → Task 6
- spec §3.7 Out of Scope → Task 1-7 严格遵守
- spec §4 Validation → Task 5
- spec §5 Risks → Task 4 STOP 检查点 + Task 6 Step 4
- spec §6 Plan → 8 tasks 全部对应

### 2. Placeholder scan

无 TBD / TODO / "Similar to Task N"。所有代码 step 都给完整代码块。

### 3. Type consistency

- `getTemplateFieldLabel` 在 Task 1 Step 1 定义（utils/templateLabels.ts），Task 2 Step 1 包装调用，Task 3 Step 2 嵌套 FieldValue 调用，Task 4 Step 2 测试 mock 调用 ✓
- `Field` / `Template` 类型在 Task 1 import 一次，后续通过 type-only import 引用 ✓
- `fieldKey` / `templates` optional prop 在 Task 3 定义，Task 3 object 分支用，Task 4 测试不传（老调用兼容）✓

### 4. Order check

- Task 1 (公共模块) → Task 2 (FileTabsPanel wrapper) → Task 3 (FieldValue 加 prop) → Task 4 (vitest) 顺序 OK（依赖链）
- Task 4 测试会 TDD 失败（如果 Task 1-3 任意没做对）→ STOP 检查点
- Task 6 真 PG 复测需要用户浏览器手测，dev server 已 reload
- Task 8 docs 收口在 PR merge 后

### 5. Risk 缓解

- 2 个新 prop 都 optional → 老 admin 调用点零影响
- Hard-coded map 保留 → legacy course 模板继续中文化
- FieldValue 是 admin 也在用（TemplateEditor），但只读 props 不修改 → 兼容
- TypeScript 类型层强制 FieldNode 形状不变量

---

## Round 2 Extension（用户真 PG 复测发现 3 类嵌套子表字段仍走英文）

### 真因补充

| 字段 | 模板 schema 位置 | 实测 | 应示 |
|------|---------|------|------|
| `course_content[].module_name` | 课程标准 `fields[?].items[0].key` | `module_name: 项目一` | `模块/项目名称: 项目一` |
| `teaching_process[].step_name` | 教案 `fields[?].items[0].children[0]` | `step_name: 课前任务` | `环节名称: 课前任务` |
| `curriculum_system[].course` | 人才培养方案 `fields[?].items[0].key` | `course: 职业生涯与规划` | `课程: 职业生涯与规划` |

Round 1 修复只覆盖 `field.children[]`（object 子字段），**不覆盖 `field.items[]`（array item 模板）和 `field.columns[]`（table 列定义）**。需用 `keyPath: string[]` 数组描述 schema 路径替代 `prefix: string` dot-path。

### Round 2 任务清单（Tasks 9-12）

### Task 9: 拪展 templateLabels.ts 接受 keyPath: string[]

**Files:**
- Modify: `packages/web/src/utils/templateLabels.ts`

新增 / 修改：

```typescript
// 新增函数: 沿 keyPath 走 templates schema 树, 找到对应 FieldNode
function getFieldNodeAtPath(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  keyPath: ReadonlyArray<string>,
): Field | null {
  if (keyPath.length === 0) return null;
  // step 1: 找 keyPath[0] in top-level fields
  let current: Field | null = null;
  for (const t of templates) {
    const found = t.fields.find((f) => f.key === keyPath[0]);
    if (found) {
      current = found;
      break;
    }
  }
  if (!current) return null;
  // step 2+: 沿 keyPath 走 children / items / columns
  for (let i = 1; i < keyPath.length; i++) {
    const seg = keyPath[i];
    const next = findLabelInFields([current], seg);
    if (!next) return null;
    current = next;
  }
  return current;
}

// 增强主函数: 接受 keyPath 数组 (优先, 新 API)
export function getTemplateFieldLabelByPath(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  keyPath: ReadonlyArray<string>,
): string {
  // 1. 沿 keyPath 走 schema 树
  const node = getFieldNodeAtPath(templates, keyPath);
  if (node) return node.label;

  // 2. keyPath.length === 1 时, 走老 dot-path + children 递归 (兼容)
  if (keyPath.length === 1) {
    const key = keyPath[0];
    for (const t of templates) {
      const found = findLabelInFields(t.fields, key);
      if (found) return found.label;
    }
  }

  // 3. hard-coded map fallback
  const last = keyPath[keyPath.length - 1] ?? "";
  return HARDCODED_LABELS[last] ?? keyPath.join(".");
}

// 保留老 API (FileTabsPanel 顶层调用)
export function getTemplateFieldLabel(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  key: string,
  prefix: string = "",
): string {
  if (prefix) {
    return getTemplateFieldLabelByPath(templates, [...prefix.split("."), key]);
  }
  return getTemplateFieldLabelByPath(templates, [key]);
}
```

### Task 10: FieldValue 改 prop 名称 fieldKey: string → keyPath: string[]

**Files:**
- Modify: `packages/web/src/views/resource/FieldValue.vue`

props 改名 `fieldKey?: string` → `keyPath?: string[]`。
- object 分支嵌套 FieldValue 调用：`:key-path="keyPath ? [...keyPath, String(childKey)] : [String(childKey)]"`
- array 分支嵌套 FieldValue 调用：`:key-path="keyPath ? [...keyPath, String(idx + 1)] : [String(idx + 1)]"`
- 保留 array 渲染时 label = `String(idx+1)`（无需变，item label 含义本来就是"第 N 项"；schema 中 items[0] 内的字段是子 FieldValue 的事情）

### Task 11: FileTabsPanel 顶层 FieldValue 调用改用 `:key-path` (而非 `:field-key`)

**Files:**
- Modify: `packages/web/src/views/resource/FileTabsPanel.vue` (L51-58)

`:field-key="String(key)"` → `:key-path="[String(key)]"`
+ 包装函数 `getFieldLabel` 仍用老 API (单层 key)

### Task 12: 4 vitest 用例更新 + 3 新增 array/table 子字段用例

**Files:**
- Modify: `packages/web/src/views/resource/FileTabsPanel.spec.ts`

调整 mount helper 接受新 API（top-level 直接传 templates，仍用老 getFieldLabel 走顶层）。

**保留 4 个原用例**（仍走顶层 key 渲染） + **新增 3 个**：
- `"renders array item field label"` — 传 templates 含 `course_content` (array)，结构化数据含 `course_content: [{module_name: "X"}]`，断言渲染"模块/项目名称"
- `"renders array item nested object label"` — 传 templates 含 `teaching_process` (array of object)，结构化数据含 `teaching_process: [{step_name: "X"}]`，断言渲染"环节名称"
- `"renders table column label"` — 传 templates 含 `graduation_requirements` (table)，结构化数据含 `graduation_requirements: [{requirement_id: "1"}]`，断言渲染"编号"

### Round 2 验证

- 修改后 pnpm typecheck / lint / test 全 pass
- 浏览器手测 3 文件 90%+ 字段名中文（包括嵌套子表）
- 现有 6 个 TD-040 测试 + round 1 4 个测试 = 10 个保留用例 + round 2 3 个新 = 13 个 FileTabsPanel 用例全过

### Round 2 任务依赖

- Task 9 (utils 升级) → Task 10 (FieldValue prop 改) → Task 11 (FileTabsPanel 顶层调用改) → Task 12 (test)
- Task 12 同时依赖 Tasks 9-11 (要等所有上游完成)
