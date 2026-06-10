# TD-041: FieldCard 递归渲染嵌套字段 — Plan

> Plan 入口：TD-041 实施拆分。Spec 见 `docs/02-delivery-plans/01-specs/2026-06-10-td-041-field-card-recursive-rendering.md`。

## 架构

新建 `FieldList.vue` 递归组件，包裹 `<draggable>` + `<FieldCard>`：

```
TemplateEditorView / TemplateFormFields
  └── FieldItem (root 编排：搜索、expandedIds、copySubtree)
        └── FieldList (递归：draggable + FieldCard, depth=0)
              └── FieldCard (展示)
                    └── FieldList (children/items, depth+1)
                          └── FieldCard
                                └── ... (递归)
```

事件上浮：直接 emit chain（最多 3-4 层深度）。

## Task 拆分

### TASK-1: 新建 FieldList.vue

- Props: `fields: Field[]`, `depth: number`, `expandedIds: Set<string>`, `matchedIds: Set<string>`, `searchQuery?: string`
- Emits: `update`, `remove`, `updateField`, `changeType`, `addChild`, `addColumn`, `removeColumn`, `copySubtree`, `toggle`
- Template: `<draggable :list="fields" item-key="id" handle=".drag-handle" :animation="150" @end="onDragEnd">` + `<FieldCard>` per item
- `defineOptions({ name: 'FieldList' })` 让组件自引用
- MAX_DEPTH=5 守卫
- CSS: depth>0 时容器加 `margin-left: 20px; border-left: 2px solid var(--panel-border)`

### TASK-2: 修改 FieldCard.vue

- 新增 props: `expandedIds: Set<string>`, `matchedIds: Set<string>`, `searchQuery?: string`
- `expanded` 从 local ref 改为 `computed(() => props.expandedIds.has(props.node.id))`
- object 子字段区域：非空时渲染 `<FieldList :fields="node.children" :depth="depth + 1" ...>`
- array items 区域：非空时渲染 `<FieldList :fields="node.items" :depth="depth + 1" ...>`
- 移除 card-detail 和 sub-section 的 paddingLeft inline style
- 保留 card-header 的 paddingLeft inline style

### TASK-3: 修改 FieldItem.vue

- root 层 `<draggable>` + `<FieldCard>` 替换为 `<FieldList>`
- 新增 `matchedIds` computed
- 修 `onCopySubtree`：接收 `id: string`，新增 `findNodeAndParent` helper
- 修 removeColumn relay：`(parentId, ci) => emit('removeColumn', parentId, ci)`
- 新增 `collapseAll(collapsed: boolean)` 方法
- 移除 `genId`

### TASK-4: 修改 TemplateEditorView.vue

- toggleAllCollapse 改为通过 template ref 调用 FieldItem 的 `collapseAll`
- 移除 `window.dispatchEvent(CustomEvent)` 逻辑

### TASK-5: 文档更新 + 质量门禁

- 更新 `technical-debt.md` TD-041 状态
- 更新 `current-work.md` 任务进度
- 运行：`pnpm typecheck` + `pnpm lint` + `scripts/check-engineering-docs` + `git diff --check`
