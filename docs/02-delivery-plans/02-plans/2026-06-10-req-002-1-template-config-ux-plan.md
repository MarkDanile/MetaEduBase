# REQ-002-1 模板配置效率（编辑器 UX 补齐） — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 TemplateEditorView 的字段编辑体验从"靠添加/删除按钮"升级为"可拖拽排序、可子树复制、可撤销删除、可在 30+ 字段模板里快速定位"。决策来源：REQ-002 塑形期 2026-06-10 决议 Q5。

**Architecture:** 纯前端 UX 改进，0 个后端文件改动。vuedraggable 已在 `packages/web/package.json` 依赖中（`^4.1.0`），本任务把它集成进 FieldCard + FieldItem + TemplateEditorView。

**Tech Stack:** Vue 3 + TypeScript / vuedraggable 4.1.0 / Tailwind CSS 4 / Vitest（若项目已用）。

**Spec:** `docs/02-delivery-plans/01-specs/2026-06-10-req-002-1-template-config-ux.md`

**Working dir:** `packages/web`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `packages/web/src/views/admin/FieldCard.vue`（修改） | 卡片新增"复制子树"按钮 + 拖拽 handle（左侧"⋮⋮"图标） | AC-5, AC-6, AC-11 |
| `packages/web/src/views/admin/FieldItem.vue`（修改） | 整合 vuedraggable 包裹 root / object children / array items 三层；搜索过滤逻辑 | AC-1, AC-2, AC-3, AC-9, AC-11 |
| `packages/web/src/views/admin/TemplateEditorView.vue`（修改） | 顶部"全部折叠 / 全部展开"按钮 + 搜索框 + 撤销 toast + 拖拽 root 集成 | AC-1, AC-7, AC-8, AC-10 |
| `packages/web/src/views/admin/FieldItem.spec.ts`（新建，可选） | vitest 覆盖拖拽 / 复制 / 撤销 / 搜索 4 项 UI 交互 | AC-15 |

业务代码改动范围：3-4 个前端文件，0 个后端文件，0 个 DB schema，0 个 API 契约。

---

## Task 1: 集成 vuedraggable 到 FieldItem（root + object children + array items 三层）

**Files:**
- Modify: `packages/web/src/views/admin/FieldItem.vue`

- [ ] **Step 1: 在 FieldItem.vue 顶部 import vuedraggable**

```typescript
import draggable from 'vuedraggable'
```

- [ ] **Step 2: 用 draggable 包裹 FieldCard 列表 + 嵌套 children / items**

参考（基于现有 FieldItem 形状）：

```vue
<template>
  <div class="field-cards">
    <!-- Root 层：vuedraggable 包裹整列 FieldCard -->
    <draggable
      :list="modelValue"
      item-key="key"
      handle=".drag-handle"
      @end="onRootDragEnd"
      :animation="150"
    >
      <template #item="{ element: node, index: i }">
        <FieldCard
          :node="{ ...node, depth: 0 }"
          :parent-nodes="modelValue"
          @toggle="toggleExpand"
          @update="onUpdate"
          @remove="emit('remove', $event)"
          @update-field="onUpdateField"
          @change-type="onChangeType"
          @add-child="emit('addChild', $event)"
          @add-column="emit('addColumn', $event)"
          @remove-column="emit('removeColumn', $event, 0)"
          @copy-subtree="onCopySubtree(i)"
        />
      </template>
    </draggable>

    <div v-if="modelValue.length > 0" class="add-root-wrap">
      <button class="add-root-btn" @click="emit('addRoot')">
        <Plus :size="13" /> 添加字段
      </button>
    </div>
  </div>
</template>
```

新增 `onRootDragEnd` 处理函数：

```typescript
function onRootDragEnd(evt: any) {
  // vuedraggable 已经直接修改了 modelValue 数组；emit update 让父组件同步
  emit('update:modelValue', [...modelValue.value])
  emit('update')
}
```

注意：vuedraggable 的 `:list` 是直接修改原数组（不像 v-model 那样 emit）；需要手动 emit `update:modelValue`。

- [ ] **Step 3: 在 FieldCard 内部递归渲染 children / items 时也用 draggable**

在 FieldCard 的 object 字段 children 渲染处：

```vue
<draggable
  v-if="node.type === 'object'"
  :list="node.children || []"
  item-key="key"
  handle=".drag-handle"
  @end="onChildrenDragEnd"
  :animation="150"
>
  <template #item="{ element: child, index: i }">
    <FieldCard
      :node="{ ...child, depth: depth + 1 }"
      ...
    />
  </template>
</draggable>
```

array 字段 items 同理。

- [ ] **Step 4: 验证 TypeScript 类型**

`cd packages/web && pnpm typecheck`，exit 0。

- [ ] **Step 5: 提交**

```bash
git add packages/web/src/views/admin/FieldItem.vue
git commit -m "feat(REQ-002-1): integrate vuedraggable into FieldItem (3 layers)"
```

---

## Task 2: FieldCard 新增"复制子树"按钮 + 拖拽 handle

**Files:**
- Modify: `packages/web/src/views/admin/FieldCard.vue`

- [ ] **Step 1: 引入图标 + 调整 emits**

```typescript
import { GripVertical, Copy, X } from 'lucide-vue-next'

const emit = defineEmits<{
  // ... 既有
  'copySubtree': [nodeId: string]
}>()
```

- [ ] **Step 2: 在卡片顶部加拖拽 handle**

```vue
<template>
  <div class="field-card" :style="{ marginLeft: depth * 16 + 'px' }">
    <!-- 拖拽 handle（左侧） -->
    <button class="drag-handle" aria-label="拖拽排序">
      <GripVertical :size="14" />
    </button>

    <!-- 既有字段名 / 标签 / 类型 ... -->

    <!-- 操作按钮区：复制子树 + 删除 -->
    <div class="field-card-actions">
      <button class="action-btn" @click="emit('copySubtree', node.id)" aria-label="复制子树">
        <Copy :size="14" />
      </button>
      <button class="action-btn danger" @click="emit('remove', node.id)" aria-label="删除">
        <X :size="14" />
      </button>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 添加 CSS（让 handle / 按钮可点）**

```css
.drag-handle {
  cursor: grab;
  padding: 4px;
  color: var(--color-ink-tertiary);
  background: none;
  border: none;
  display: inline-flex;
  align-items: center;
}
.drag-handle:active {
  cursor: grabbing;
}
.drag-handle:hover {
  color: var(--color-ink);
}
```

- [ ] **Step 4: 验证 typecheck + lint**

```bash
cd packages/web && pnpm typecheck && pnpm lint
```

Expected：exit 0。

- [ ] **Step 5: 提交**

```bash
git add packages/web/src/views/admin/FieldCard.vue
git commit -m "feat(REQ-002-1): add copy-subtree button + drag handle to FieldCard"
```

---

## Task 3: TemplateEditorView — 撤销 toast + 折叠/展开按钮 + 搜索框

**Files:**
- Modify: `packages/web/src/views/admin/TemplateEditorView.vue`

- [ ] **Step 1: 在 `<script setup>` 中添加撤销栈 + 折叠状态 + 搜索框状态**

```typescript
import { ref, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'

const toast = useToast()

// 撤销栈：只支持单次撤销
interface DeletedField {
  field: Field
  parentKey: string | null  // null = root
  index: number
}
const deletedStack = ref<DeletedField[]>([])

// 折叠状态：'all' | 'none' | 'partial' 实际为各 FieldCard 内部状态；这里只驱动按钮
const allCollapsed = ref(false)

// 搜索词
const searchQuery = ref('')

// 递归统计 totalFields
const totalFields = computed(() => {
  function count(fields: Field[]): number {
    let n = fields.length
    for (const f of fields) {
      if (f.children) n += count(f.children)
      if (f.items) n += count(f.items)
    }
    return n
  }
  return count(form.value.fields)
})

// 监听 root 删除事件，存到撤销栈
function onFieldRemove(id: string) {
  const stack = findAndRemove(form.value.fields, id)
  if (stack) {
    deletedStack.value = [stack]
    const timer = setTimeout(() => {
      deletedStack.value = []
    }, 5000)
    toast.message(`已删除字段 ${stack.field.key}，5 秒内可撤销`, {
      action: {
        label: '撤销',
        onClick: () => {
          clearTimeout(timer)
          if (deletedStack.value[0]) {
            restoreField(deletedStack.value[0])
            deletedStack.value = []
          }
        },
      },
    })
  }
}

function findAndRemove(fields: Field[], id: string): DeletedField | null {
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].id === id || (fields[i] as any).key === id) {
      const f = fields[i]
      fields.splice(i, 1)
      return { field: f, parentKey: null, index: i }
    }
    if (fields[i].children) {
      const result = findAndRemove(fields[i].children!, id)
      if (result) return { ...result, parentKey: fields[i].key ?? null }
    }
    if (fields[i].items) {
      const result = findAndRemove(fields[i].items!, id)
      if (result) return { ...result, parentKey: fields[i].key ?? null }
    }
  }
  return null
}

function restoreField(stack: DeletedField) {
  if (stack.parentKey === null) {
    form.value.fields.splice(stack.index, 0, stack.field)
  } else {
    const parent = findFieldByKey(form.value.fields, stack.parentKey)
    if (parent && parent.children) {
      parent.children.splice(stack.index, 0, stack.field)
    }
  }
}

function findFieldByKey(fields: Field[], key: string): Field | null {
  for (const f of fields) {
    if (f.key === key) return f
    if (f.children) {
      const r = findFieldByKey(f.children, key)
      if (r) return r
    }
    if (f.items) {
      const r = findFieldByKey(f.items, key)
      if (r) return r
    }
  }
  return null
}

// 折叠/展开
function toggleAllCollapse() {
  allCollapsed.value = !allCollapsed.value
  // 触发 FieldItem 内部折叠状态（通过 emit 或全局 event bus）
  // 简化：通过 window event 触发
  window.dispatchEvent(new CustomEvent('field-card-toggle-all', { detail: { collapsed: allCollapsed.value } }))
}
```

- [ ] **Step 2: 模板顶部加按钮 + 搜索框（仅 totalFields > 30 时显示）**

```vue
<template>
  <div class="ui-page-shell">
    <PageHeader :title="isNew ? '新建模板' : '编辑模板'" subtitle="配置结构化数据抽取字段">
      <template #extra>
        <button class="ui-btn ui-btn-primary" @click="save" :disabled="saving">
          保存
        </button>
      </template>
    </PageHeader>

    <!-- REQ-002-1: 折叠/展开 + 搜索（30+ 字段时显示） -->
    <div v-if="totalFields > 30" class="ui-panel p-3 mb-4 flex gap-2 items-center">
      <button class="ui-btn-ghost text-[var(--text-small)]" @click="toggleAllCollapse">
        {{ allCollapsed ? '全部展开' : '全部折叠' }}
      </button>
      <input
        v-model="searchQuery"
        class="ui-input flex-1"
        placeholder="按 label / key 搜索字段..."
      />
      <span v-if="searchQuery" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
        搜索中：{{ searchQuery }}
      </span>
    </div>

    <div v-if="loading" class="flex justify-center py-12">
      <LoadingSpinner text="加载中..." />
    </div>

    <div v-else class="xl:grid xl:grid-cols-[1fr_340px] gap-6">
      <!-- ... 既有左列 + 右列 ... -->
    </div>
  </div>
</template>
```

- [ ] **Step 3: 把 searchQuery 传给 FieldItem**

FieldItem 接受 `searchQuery` prop，prop 变化时过滤不匹配项（具体在 Task 4 完成）。

- [ ] **Step 4: 把 onFieldRemove 传给 FieldItem**

替换现有 `@remove="form.fields.splice(i, 1)"` 为 `@remove="onFieldRemove"`。

- [ ] **Step 5: 验证 typecheck + lint**

```bash
cd packages/web && pnpm typecheck && pnpm lint
```

Expected：exit 0。

- [ ] **Step 6: 提交**

```bash
git add packages/web/src/views/admin/TemplateEditorView.vue
git commit -m "feat(REQ-002-1): undo toast + collapse-all + search (30+ threshold)"
```

---

## Task 4: 子树复制逻辑（深拷贝 + key 后缀）

**Files:**
- Modify: `packages/web/src/views/admin/FieldItem.vue`

- [ ] **Step 1: 添加 onCopySubtree 函数**

```typescript
function deepCopyField(f: Field): Field {
  const copy: Field = {
    key: f.key,
    label: f.label,
    type: f.type,
    description: f.description,
  }
  if (f.children) copy.children = f.children.map(deepCopyField)
  if (f.columns) copy.columns = f.columns.map(c => ({ ...c }))
  if (f.items) copy.items = f.items.map(deepCopyField)
  return copy
}

function nextCopySuffix(siblingKeys: string[], baseKey: string): string {
  let n = 1
  while (siblingKeys.includes(`${baseKey}_copy_${n}`)) n++
  return `${baseKey}_copy_${n}`
}

function onCopySubtree(index: number) {
  const original = modelValue.value[index]
  const copy = deepCopyField(original)
  const siblingKeys = modelValue.value.map(f => f.key ?? '')
  copy.key = nextCopySuffix(siblingKeys, original.key ?? 'field')
  copy.label = `${original.label} (副本)`
  modelValue.value.splice(index + 1, 0, copy)
  emit('update:modelValue', [...modelValue.value])
  emit('update')
}
```

注意：递归深拷贝时，子字段的 key 也需加后缀。改进 deepCopyField：

```typescript
function deepCopyFieldWithSuffix(f: Field, parentSuffix: string): Field {
  const suffixKey = `${f.key ?? 'field'}_${parentSuffix}`
  const copy: Field = {
    key: suffixKey,
    label: f.label,
    type: f.type,
    description: f.description,
  }
  if (f.children) copy.children = f.children.map(c => deepCopyFieldWithSuffix(c, parentSuffix))
  if (f.columns) copy.columns = f.columns.map(c => ({ ...c, key: `${c.key}_${parentSuffix}` }))
  if (f.items) copy.items = f.items.map(c => deepCopyFieldWithSuffix(c, parentSuffix))
  return copy
}

function onCopySubtree(index: number) {
  const original = modelValue.value[index]
  const suffix = `copy_${Date.now()}_${index}`  // 唯一后缀
  const copy = deepCopyFieldWithSuffix(original, suffix)
  copy.label = `${original.label} (副本)`
  modelValue.value.splice(index + 1, 0, copy)
  emit('update:modelValue', [...modelValue.value])
  emit('update')
}
```

- [ ] **Step 2: 把 onCopySubtree 接到 FieldCard 的 copySubtree emit**

```vue
<FieldCard
  ...
  @copy-subtree="onCopySubtree(i)"
/>
```

- [ ] **Step 3: 验证 typecheck + lint**

```bash
cd packages/web && pnpm typecheck && pnpm lint
```

Expected：exit 0。

- [ ] **Step 4: 提交**

```bash
git add packages/web/src/views/admin/FieldItem.vue
git commit -m "feat(REQ-002-1): subtree copy with deep clone + key suffix"
```

---

## Task 5: 搜索过滤实现（FieldItem 接收 searchQuery prop）

**Files:**
- Modify: `packages/web/src/views/admin/FieldItem.vue`

- [ ] **Step 1: 添加 searchQuery prop**

```typescript
const props = defineProps<{
  modelValue: Field[]
  searchQuery?: string
}>()
```

- [ ] **Step 2: 在 flatNodes computed 中应用过滤**

```typescript
const flatNodes = computed(() => {
  const result: (Field & { id: string; depth: number; matched: boolean })[] = []
  const q = (props.searchQuery ?? '').toLowerCase().trim()
  
  function walk(nodes: Field[], depth: number, parentMatched: boolean) {
    nodes.forEach(node => {
      const id = node.id ?? crypto.randomUUID()
      const matched = !q || parentMatched ||
        (node.key ?? '').toLowerCase().includes(q) ||
        (node.label ?? '').toLowerCase().includes(q)
      result.push({ ...node, id, depth, matched })
      if (node.children?.length) walk(node.children, depth + 1, matched)
      if (node.items?.length) walk(node.items, depth + 1, matched)
    })
  }
  walk(props.modelValue, 0, false)
  return result
})
```

- [ ] **Step 3: 在模板中应用 matched 属性（dim / 隐藏）**

```vue
<FieldCard
  v-for="node in flatNodes"
  v-show="node.matched"
  :class="{ 'dimmed': !node.matched }"
  :key="node.id"
  ...
/>
```

CSS：
```css
.dimmed { opacity: 0.3; }
```

- [ ] **Step 4: 验证 typecheck + lint**

```bash
cd packages/web && pnpm typecheck && pnpm lint
```

Expected：exit 0。

- [ ] **Step 5: 提交**

```bash
git add packages/web/src/views/admin/FieldItem.vue
git commit -m "feat(REQ-002-1): search filter in FieldItem (parent-matched propagation)"
```

---

## Task 6: 文档回填

**Files:**
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Modify: `docs/03-engineering-governance/current-work.md`

- [ ] **Step 1: Backlog REQ-002-1 状态推进**

把 REQ-002-1 行的 `下一步` 从"等 REQ-002-3合并后再开 spec" 改为本次 spec/plan 已建，状态 `🔵 Ready` → `🟡 Planned`，并加 spec/plan 链接。

- [ ] **Step 2: P2 里程碑 Open Items 加 REQ-002-1 行**

状态 `🔵 Ready`，引用本 spec。

- [ ] **Step 3: current-work.md 把 REQ-002-1 移入"当前进行中"**

由于 current-work 当前只有 REQ-002-3 在进行中（REQ-002-3 也在 backlog / milestone），按之前的去重策略，把 REQ-002-1 直接放入进行中，状态 `🟡 Planned`，记录分支名 + 当前进展。

- [ ] **Step 4: 跑工程门禁**

```bash
python3 scripts/check-engineering-docs
```

Expected：`engineering docs checks passed`。

- [ ] **Step 5: 提交**

```bash
git add docs/01-product-planning/04-backlog.md \
        docs/01-product-planning/02-milestones/02-growth-phase.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(REQ-002-1): register in backlog, milestone, current-work"
```

---

## Task 7: UI 回归（手测或 e2e）

- [ ] **Step 1: 启动前端 + 后端 dev server**

按 `docs/03-engineering-governance/01-rules/local-development.md` 启动 dev 环境。

- [ ] **Step 2: 手测脚本**

打开 TemplateEditorView，依次执行：
1. 添加 3 个 root 字段（text / object / array 各 1）
2. 拖拽排序：把 array 拖到第一位
3. 点击 array 卡片的"复制子树"按钮
4. 删除一个字段
5. 在 5 秒内点击 toast 的"撤销"按钮
6. 在 object 字段添加 2 个子字段，拖拽排序
7. 保存

验证：
- 拖拽后顺序与预期一致
- 复制后新字段的 key 含 `_copy_` 后缀
- 撤销后字段恢复到原 index
- 保存后 `template.fields` 数组顺序与拖拽后一致（reload 页面验证）

- [ ] **Step 3: 截图 / 录屏**

把截图附到 PR 描述。

- [ ] **Step 4:（可选）e2e**

若项目已用 playwright/puppeteer，写 1 条 e2e 覆盖上述流程；否则手测记录即可。

---

## Task 8: 完整回归

- [ ] **Step 1: 前端 typecheck + lint**

```bash
cd packages/web && pnpm typecheck
cd packages/web && pnpm lint
```

- [ ] **Step 2: 前端 build（可选）**

```bash
cd packages/web && pnpm build
```

- [ ] **Step 3: 后端回归（不改动，但确认没破坏）**

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document tests/contexts/template -q
cd packages/server-python && .venv/bin/python -m ruff check app/ tests/
```

- [ ] **Step 4: 工程门禁**

```bash
python3 scripts/check-engineering-docs
git diff --check main...HEAD
bash scripts/scan-source-sizes --diff
```

Expected：全部通过。

---

## 自检清单

1. **Spec coverage**：逐条检查 spec 17 个 AC，每个都有对应 task 实现。
2. **Placeholder scan**：无 TBD / TODO / 未实现步骤。
3. **Type consistency**：前端 `Field` / `FieldItem` / `FieldCard` / `TemplateEditorView` 之间的 prop / emit 名称一致。
4. **边界条件**：拖拽 handle 在 0 字段 / 1 字段时不应报错；撤销栈在 5 秒后清空；搜索框在 0 匹配时不影响 UI。
5. **行为不变**：API 契约、DB schema、后端代码全部不变。
6. **REQ-002-3 兼容**：不破坏既有溯源元信息卡 / 不改 `_merge_template_structured_data`。
7. **vuedraggable 依赖**：已在 package.json，无需新增。
